# How Rekordbox Handles Relational Metadata Edits: Test Plan

## Question

Implementing the `edit` command's `ArtistName` and `AlbumName` fields (issue #17)
requires knowing what rekordbox does to shared records. Unlike `Title`, `Comment`,
and `Rating`, which live on the `DjmdContent` row itself, artist and album names
live on shared `DjmdArtist` and `DjmdAlbum` records that many tracks reference
through a foreign key. Editing one track's artist therefore cannot be a plain
column write: it has to decide whether to reuse an existing record, create a new
one, or repoint the track's foreign key, and what to do with a record the edit
leaves behind. This plan establishes what rekordbox itself does for each choice,
so the `edit` command can mirror it.

The subject is the real local rekordbox 6 library; the experiments use existing
records rather than purpose-built fixtures, and a single `master.db` backup taken
before the first edit makes every step reversible. No experiment touches an audio
or ANLZ file, because artist, album, rating, and comment edits are database-only.

## Scope and Goals

Four experiments, each answering one question the apply logic must resolve, plus
a set of edge-case variants folded into the relevant experiment. The through
line is behavioral fidelity: whatever rekordbox does on an inline field edit is
what the tool should reproduce.

**E1, artist reassignment.** Change a track's artist to a name that already
belongs to another artist. Does rekordbox reuse the existing `DjmdArtist`, or
create a second row with the same name? A control assertion rides along: a
sibling track that shared the original artist must stay put, and the original
artist's `Name` must not change. That confirms the inline field edit reassigns
the single track rather than renaming the shared record for every track, which
is the assumption the whole design rests on.

**E2, album reuse with a matching album-artist.** Change a track's album to an
existing album whose album-artist matches the track's artist. Does rekordbox
reuse that `DjmdAlbum`, and does album identity key on name alone?

**E3, album identity against the album-artist.** Change a track's album to an
existing album name whose album-artist differs from the track's artist. Does
rekordbox create a new `DjmdAlbum` that shares the name but carries its own
album-artist, and does that new album-artist resolve to an existing `DjmdArtist`
by name or a freshly created one? This is what reveals whether album identity is
`(Name, AlbumArtist)` rather than `Name`.

**E4, orphan handling.** After an edit moves a track off a record that no track
now references, does rekordbox delete the orphan, soft-delete it
(`rb_local_deleted`), or leave it in place? The answer confirms or informs the
decision to defer orphan cleanup in the first implementation.

Across all four, every snapshot captures `SearchStr` and the sync bookkeeping
(`UUID`, `rb_local_deleted`, `usn`, `rb_local_usn`, timestamps) on the artist and
album rows. Those deltas show what value rekordbox writes into `SearchStr` on a
created row and how it moves the update-sequence numbers, both of which the
tool's own writes must imitate to keep the record sync-consistent.

## Snapshot Tooling

Two read-only scripts, built for this study and writing only to `evidence/`:

`scripts/relational_snapshot.py <content_id> <stage>` captures the
subject `DjmdContent` row's relational foreign keys and their proxy names, then
a full census of `DjmdArtist` and `DjmdAlbum`. Each census row records its name,
`SearchStr`, sync bookkeeping, and a reference count computed across the whole
library. The reference count spans every `DjmdContent` column that points at an
artist (`ArtistID`, `RemixerID`, `OrgArtistID`, `ComposerID`, `Lyricist`) plus
every album's `AlbumArtistID`, so a record that reads as orphaned by `ArtistID`
but is still someone's remixer is not miscounted. The census is global, so a
single subject's snapshot tracks every artist and album change regardless of
which track was edited. It writes `evidence/rel-<id>-<stage>.json`.

`scripts/relational_diff.py <content_id> <stageA> <stageB>` prints the
subject's foreign-key moves and then the artist and album rows created, removed,
renamed, relinked, soft-deleted, or orphaned in place, with the `usn` and
`rb_local_usn` moves called out.

Read the snapshot with rekordbox closed so it sees committed state. The `usn` and
`rb_local_deleted` fields are load-bearing: a created row carries a new `UUID`
and bumped update-sequence numbers, a reused row does not move, and a soft-delete
flips `rb_local_deleted` while leaving the row present.

## Subject Selection

The baseline census picks the subjects, so no track is chosen blind. Run
`relational_snapshot.py <any_content_id> e0-census` once, then read
`rel-<id>-e0-census.json` to choose:

- **E1 subject T1 and target A_exist.** A track T1 whose artist A_old is shared
  by at least one sibling track S1 (so the control has something to hold still),
  and a different existing artist A_exist to reassign T1 to. For the E4 orphan
  arm, prefer a T1 whose A_old has `total_refs == 1`, so reassigning T1 orphans
  A_old immediately.
- **E2 subject T2 and album Alb_match.** A track T2 and an existing album whose
  `AlbumArtistID` resolves to T2's artist.
- **E3 subject T3 and album Alb_diff.** A track T3 and an existing album whose
  `AlbumArtistID` resolves to an artist other than T3's. For the artist-less
  variant, also note a track T3b whose `ArtistID` is null.
- **Null or compilation album.** An existing album with a null `AlbumArtistID`
  or `Compilation == 1`, for the E2 variant.

The maintainer confirms or swaps any subject before running its experiment.

## Backup and Revert Protocol

Metadata edits are database-only, so the backup is `master.db` alone.

1. Quit rekordbox.
2. Copy `master.db` (and its `-wal` and `-shm` if present) to the existing
   backup root used by the convert studies, or any location off the library
   directory. Record the copy's path.

Restore by quitting rekordbox and copying the backup back over `master.db`. E4
runs contiguously after its E1 or E2 edit and before any restore, because it has
to observe the orphan surviving an application restart. Restore between the other
experiments so each starts from the pristine baseline and its effects are
attributable to that experiment alone.

## E1: Artist Reassignment

1. **`e1-00-baseline`.** Snapshot T1. Note A_old's `ID`, `total_refs`, and the
   sibling S1's `ArtistID`.
2. **`e1-10-reuse`.** In rekordbox, edit T1's Artist field to the exact name of
   A_exist. Quit rekordbox. Snapshot. Diff `e1-00` to `e1-10`.
3. **`e1-20-clear`.** Restore baseline. Edit T1's Artist field to empty. Quit.
   Snapshot. Diff against `e1-00`.
4. **`e1-30-casews`.** Restore baseline. Edit T1's Artist field to A_exist's name
   with a leading and trailing space and an altered case, for example
   ` alpha ` when the record is `Alpha`. Quit. Snapshot. Diff against `e1-00`.

What to read:

- **Reuse versus create.** In `e1-10`, does T1's `ArtistID` become A_exist's
  existing `ID` with no new artist row (reuse), or does a new `DjmdArtist` appear
  carrying the same name (create)?
- **Reassign versus rename (control).** S1's `ArtistID` and A_old's `Name` must
  be unchanged in `e1-10`. If A_old's `Name` changed instead, the inline edit
  renames the shared record and the whole apply design has to change.
- **Clearing.** In `e1-20`, does T1's `ArtistID` go null, or point at an
  empty-named artist row?
- **Normalization.** In `e1-30`, does rekordbox trim and case-fold before
  matching, reusing A_exist, or does it create a distinct row for ` alpha `?

## E2: Album Reuse With a Matching Album-Artist

1. **`e2-00-baseline`.** Snapshot T2.
2. **`e2-10-reuse`.** Edit T2's Album field to the exact name of Alb_match, whose
   album-artist matches T2's artist. Quit. Snapshot. Diff against `e2-00`.
3. **`e2-20-nullcomp`.** Restore baseline. Edit T2's Album to an existing album
   whose `AlbumArtistID` is null or which is flagged `Compilation`. Quit.
   Snapshot. Diff against `e2-00`.

What to read: whether T2's `AlbumID` becomes the existing album's `ID` (reuse) or
a new album row appears, and whether the null or compilation album-artist changes
that behavior.

## E3: Album Identity Against the Album-Artist

1. **`e3-00-baseline`.** Snapshot T3.
2. **`e3-10-diffartist`.** Edit T3's Album field to the exact name of Alb_diff,
   whose album-artist differs from T3's artist. Quit. Snapshot. Diff against
   `e3-00`.
3. **`e3-20-noartist`.** Restore baseline. On T3b, whose artist is null, set the
   Album field to a name that does not yet exist. Quit. Snapshot. Diff against
   `e3-00`.

What to read:

- **Album identity.** In `e3-10`, does a new `DjmdAlbum` appear that shares
  Alb_diff's name but carries a different `AlbumArtistID`, proving identity is
  `(Name, AlbumArtist)`, or does T3 reuse the existing album despite the
  album-artist mismatch?
- **Album-artist resolution.** If a new album is created, does its
  `AlbumArtistID` resolve to an existing `DjmdArtist` matching T3's artist name,
  or a newly created artist?
- **Artist-less creation.** In `e3-20`, what `AlbumArtistID` does the freshly
  created album carry when there is no track artist to derive it from?

## E4: Orphan Handling

Runs immediately after `e1-10` (or `e2-10`), before any restore, when the edit
has just moved T1 off A_old and A_old's `total_refs` is now zero.

1. **`e4-10-orphaned`.** This is the `e1-10` snapshot already taken. Confirm
   A_old still exists, its `total_refs` is zero, and whether `rb_local_deleted`
   flipped and `rb_local_usn` moved.
2. **`e4-20-restart`.** Relaunch rekordbox, let the library load fully, then quit.
   Snapshot. Diff `e4-10` to `e4-20`.

What to read: whether rekordbox removes the orphaned row, soft-deletes it, or
leaves it untouched on the next application load, and whether the orphaned artist
still appears in rekordbox's artist browser as a zero-track entry.

## What Each Run Answers

| Question | Experiment · stage diff | Measurement | Guides |
| --- | --- | --- | --- |
| Reuse an existing artist by name | E1 · `e1-00`→`e1-10` | T1 `ArtistID` equals A_exist's `ID`, no new artist row | Get-or-create by name for artist |
| Inline edit reassigns, not renames | E1 · `e1-00`→`e1-10` | S1 `ArtistID` and A_old `Name` unchanged | The core apply assumption |
| Clearing an artist | E1 · `e1-00`→`e1-20` | `ArtistID` null versus empty-named row | What `--replace ""` does |
| Trim and case matching | E1 · `e1-00`→`e1-30` | Reuse of A_exist versus a distinct new row | Name normalization before lookup |
| Reuse an existing album | E2 · `e2-00`→`e2-10` | T2 `AlbumID` equals the existing album's `ID` | Album lookup keying |
| Null or compilation album-artist | E2 · `e2-00`→`e2-20` | Reuse behavior when album-artist is absent | Album lookup edge |
| Album identity vs album-artist | E3 · `e3-00`→`e3-10` | New album sharing the name but a different `AlbumArtistID` | Whether lookup keys on `(Name, AlbumArtist)` |
| Album-artist resolution on create | E3 · `e3-00`→`e3-10` | New album's `AlbumArtistID` resolves to existing artist by name | How a created album's album-artist is set |
| Artist-less album creation | E3 · `e3-00`→`e3-20` | Created album's `AlbumArtistID` value | Album-artist when no track artist exists |
| Orphan handling | E4 · `e4-10`→`e4-20` | Orphan removed, soft-deleted, or left after restart | Confirms deferring orphan cleanup |
| SearchStr and USN on created rows | all · any create | `SearchStr` value and `usn` / `rb_local_usn` on new rows | What the tool's writes must imitate |

## Open Risks and Notes

- Single trials per experiment, as with the earlier in-app work. The goal is to
  characterize the behavior and its failure modes, not to establish a rate.
- Rekordbox must be fully quit before each snapshot; a snapshot taken while it
  runs reads uncommitted or locked state and is not trustworthy for evidence.
- `Rating` and `Comment` are database-only columns and need no rekordbox
  behavior study. Their edge cases (a zero or empty value, an out-of-range
  rating, unicode text) belong in the implementation's unit tests, not here.
- If E1 shows the inline edit renaming the shared record rather than reassigning
  the track, stop and redesign: the field-handler apply for artist and album
  would then be wrong in its core, and the reuse and orphan questions become moot.
