# What `remove` Does, and Where It Diverges From Rekordbox

**Status:** settled. Recorded while designing the `remove` command, from the
measurements in `../remove-track-impact.md`.

## Context

`remove` deletes a track from the library. It is the first irreversible
operation the tool offers, so each of its effects was measured against rekordbox
before being chosen rather than inferred. Six arms against eight purpose-built
subjects established what rekordbox does, and nothing in this record rests on
inference; this record states what `remove` does and why it differs where it
differs.

## Mirrored Without Change

Five behaviors are adopted as measured, because rekordbox's choice is the
correct one and diverging would surprise a user who knows the application.

**Hard-delete the `DjmdContent` row.** Rekordbox deletes rather than tombstones,
and never sets `rb_local_deleted`. The tombstone hypothesis was rejected on
evidence, so the sync-facing argument for writing one does not apply.

**Clear every child row keyed by `ContentID`.** Rekordbox clears all of them,
including the cloud-sync tables `contentCue` and `contentFile`. The
implementation discovers the child tables by reflection over the mapped
metadata rather than listing them, for the reason the study itself demonstrated:
a hand-written list omitted the two cloud tables, and the mistake is invisible
until a dangling row causes a problem elsewhere.

**Remove the analysis directory.** Rekordbox removes the per-track directory and
the two-character prefix directory above it once empty.

**Collect orphaned artist, album, genre, and label records.** Rekordbox
hard-deletes a shared record the moment nothing references it, which matches what
`../../edit-relational-fields/` measured for the inline edit. A record still
referenced survives, so collection follows the reference count and not the
removal. All four kinds were measured: artist, album, and genre in R1, and label
in R6.

**Key and color are never collected.** `DjmdKey` is a closed enumeration of
musical keys, 25 rows in the studied library, shared by hundreds of tracks, and
`ColorID` names a fixed palette. Collecting either would be wrong even at zero
references. R1 confirmed a key held by other tracks is untouched, and
`../../import-track-row-shape/import-track-row-shape.md` records `KeyID` as a
lookup against that fixed table rather than a per-track record.

## Divergence: The Orphan Sweep Runs to a Fixpoint

Rekordbox's orphan collection is a single pass. Measured in R5: removing a track
dropped one of its artist's two references, collecting the now-orphaned album
dropped the second to zero, and nothing re-examined the artist. It remains in
`DjmdArtist` unreferenced.

`remove` repeats the sweep until no record becomes newly unreferenced. The leak
is a defect rather than an intention, nothing depends on the orphan surviving,
and the alternative is a command that knowingly leaves the library dirtier than
it needs to be. This extends the shape already in
`RelationalField._delete_if_orphaned`, which likewise checks once; that handler
is not changed here, because an inline edit cannot cascade the way a removal
can.

## Divergence: The Artwork Directory Is Removed Too

Rekordbox deletes `artwork.jpg` and its `_s` and `_m` thumbnails but leaves the
per-track directory, and its prefix directory, in place and empty. This is
asymmetric with its own handling of analysis directories, where both are
removed.

`remove` removes them, on the same reasoning as the orphan sweep above: a leak
is a defect rather than an intention, and the two leaks are of one kind. The
directory is dead the moment its files are gone. Its name derives from
`DjmdContent.UUID`, which `add_content` mints as a fresh `uuid4` per inserted
row, so a re-import can never land back in a directory a removal left behind.
Nothing reaches it again, and one empty directory accumulates per removed track.

Removal is by `rmdir` rather than a recursive delete, first on the per-track
directory and then on the prefix directory. `rmdir` fails on a non-empty
directory, so anything unexpected inside stops the cleanup instead of being
swept away, and the artwork path ends up structurally identical to the analysis
path.

Two guards apply regardless:

- **`ImagePath` is checked for emptiness before resolving anything**, for the
  same reason `AnalysisDataPath` is. `get_anlz_dir` on an empty
  `AnalysisDataPath` resolves to the share root, so a naive recursive delete
  would destroy the entire share tree for an unanalyzed track. `ImagePath`
  resolves the same way and needs the same guard. Both guards get a test that
  fails loudly.
- **Deletion is confined to the share directory.** Every artwork path is
  resolved and checked to fall under `share/PIONEER/Artwork` before anything is
  deleted, and a path escaping it is logged and skipped rather than followed.

  R7 established that this cannot currently be violated: rekordbox ignores a
  `cover.jpg` sitting beside the audio and takes artwork only from embedded
  tags, so every `ImagePath` resolves inside its own managed storage. The check
  exists because that is a property of one rekordbox version measured once, and
  the failure it would prevent is deleting a cover image out of the user's own
  music directory, which no reference count would catch: a single imported track
  from an album folder has exactly one referent. The check costs one
  comparison and bounds the blast radius permanently.

- **Other referents are checked before deleting artwork files.** R6 settled that
  rekordbox writes a separate artwork directory per track, even for two tracks
  on one album carrying byte-identical cover art, so this cannot currently fire.
  It is retained as prudence rather than as a load-bearing guard, on the same
  reasoning as the containment check.

## `--delete-source` Unlinks, and Says So

Rekordbox offers no gesture that deletes the audio file, so there is no native
behavior to mirror and the choice is the tool's own.

`--delete-source` calls `os.remove`. Moving to the trash was considered and
rejected on portability grounds, established by measurement and by the
platforms' documented behavior:

- **macOS** trashes successfully even on an external exFAT volume, but the file
  lands in `<volume>/.Trashes/<uid>/` rather than `~/.Trash`, so it keeps
  consuming that volume's space. A user deleting tracks to free room on a full
  drive would free none.
- **Windows** has no Recycle Bin for removable or network drives, which is
  exactly where DJ libraries live. The Shell API deletes permanently there, and
  also for files above the bin's quota.
- **Linux** follows the XDG specification, needing a `.Trash-$uid` at the mount
  root for anything outside the home filesystem, which may not be creatable.

A flag that promises recoverability and silently fails to provide it on a
Windows USB drive is worse than one that never promised it. Unlinking behaves
identically everywhere, adds no dependency, and is honest. The safety burden
sits where it already sits for every other destructive path in this tool: the
confirmation prompt, `--dry-run`, and the fact that the flag is opt-in.

## Scope: Playlist Removal Is a Different Command

R4 established that removing a track from a playlist deletes exactly one
`djmdSongPlaylist` row, touches no other table, leaves the `DjmdContent` row
untouched, and does not even stamp the parent playlist. The two gestures are
cleanly separable in the database, so `remove` means removal from the library
and nothing else. Removing a track from a playlist, should it be wanted, is its
own command.

## USNs

`stamp_usns` reserves one USN per row and is used unchanged. Rekordbox's own
accounting could not be reproduced and is not worth reproducing: three arms
deleted 15, 1, and 13 rows and advanced `localUpdateCount` by 15, 2, and 14
respectively, and the values R4 consumed appear on no surviving row. Only a
lower bound is established, the counter advancing by at least the number of rows
deleted.

Over-reserving is harmless, because a syncing peer asks for rows *above* a
value, so extra values cost nothing while a reused stamp would hide a row.
Deleted rows need no stamp at all; what matters is that the counter moves past
them. This is the same reasoning recorded in
`../../import-track-row-shape/decisions/commit-semantics-and-usn.md`, and the
unexplained surplus there is the same phenomenon seen here.
