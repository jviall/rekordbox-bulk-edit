# What Rekordbox Does When a Track Is Removed: Test Plan

## Question

Implementing the `remove` command requires knowing what rekordbox itself does
when a user removes a track from the collection. Removal is the first
irreversible operation this tool would offer, and three of its decisions have no
evidence behind them.

**Does the `DjmdContent` row disappear, or does it become a tombstone?** The row
carries `rb_local_deleted`, `rb_data_status`, `rb_local_data_status`, and
`rb_local_usn`, all of which exist to describe a row to a syncing peer. A peer
cannot learn that a row was deleted from a row that is simply absent, so cloud
sync is a reason to expect a tombstone. The one measurement this repository
holds points the other way: `edit-relational-fields` found that rekordbox
**hard-deletes** a `DjmdArtist` or `DjmdAlbum` row the moment nothing references
it, in the same save, neither soft-deleted nor deferred to a restart. Whether
that generalizes from a shared record to a content row is unknown.

**Which child rows go with it?** Thirteen tables carry a `ContentID`. A
hand-written list of the ones to clear is exactly the kind of thing that is
wrong in a way no test catches, so the census must be global.

**What happens to the analysis files and to the shared records the track
vacated?** The `AnalysisDataPath` names a per-track directory under the share
tree, and the track's artist, album, genre, label, and key may each be left with
no remaining reference.

## Hypothesis

Stated before the arms run, so the findings can contradict it:

1. The `DjmdContent` row is hard-deleted, by extension of the orphan behavior
   measured in `edit-relational-fields`.
2. Every child row keyed by `ContentID` is deleted with it.
3. The per-track analysis directory is removed along with its contents.
4. Orphaned artist and album records are hard-deleted, matching the inline-edit
   behavior; genre, label, and key are less certain, because those tables are
   small, enumerable, and behave more like vocabularies than like per-track
   records.
5. `localUpdateCount` advances.

## Subjects: Purpose-Built Fixtures in a Large Disposable Library

The library under study is at `/Volumes/GIG MUSIC/PIONEER/Master`, which
`pyrekordbox`'s `get_config("rekordbox7")` resolves to. It holds 924 tracks
pointing into a collection of roughly 2,600 artist directories. It is not a
production library and its contents are disposable, but it is large and was
built by rekordbox itself, so its schema, its cloud-sync bookkeeping, its
`agentRegistry` counter, and its relational tables are the ones the command will
actually meet. That is what a hand-built fixture database cannot be trusted to
reproduce.

Its emptiness in places is a property of its history rather than a finding: it
carries no `DjmdCue` rows and no MyTag assignments anywhere, because nobody ever
set any. That is why the arms cannot rely on existing tracks and why fixture
preparation below is a required step rather than a convenience.

Subjects are purpose-built rather than borrowed. `scripts/build_fixtures.py`
copies four files out of the collection into `/private/tmp/rbe-remove-fixtures`
and retags each copy with a name no other row uses, under the recognizable
`RBE Remove Fixture` prefix. The study imports the copies, so the shared artist,
album, and genre records the arms watch are reachable from nothing else in the
library. That isolation is what makes orphan collection observable in a single
trial: a borrowed track's artist is entangled with the rest of the collection,
and a reference count that moves for an unrelated reason would be
indistinguishable from the effect under test.

| Label | Title | Artist / album | Role |
| --- | --- | --- | --- |
| F1 | RBE Remove Fixture Alpha | Artist Alpha / Album Alpha | Sole reference to its artist, album, and genre. The orphan-collection arm, and the delete-the-file arm. FLAC, and it carries no artwork. |
| F2 | RBE Remove Fixture Beta | Artist Shared / Album Shared | Shares its artist and album with F3. The control: removing it must leave both records standing. |
| F3 | RBE Remove Fixture Gamma | Artist Shared / Album Shared | Exists to hold F2's artist and album referenced. Not itself removed. |
| F4 | RBE Remove Fixture Delta | Artist Delta / Album Delta | Imported but **not analyzed**, so `AnalysisDataPath` stays empty. |
| F5 | RBE Remove Fixture Epsilon | Artist Art / Album Art | Added for R6. Byte-identical cover art to F6, and the only fixture carrying a label. |
| F6 | RBE Remove Fixture Zeta | Artist Art / Album Art | Holds F5's artist, album, and genre referenced. Not itself removed. |
| F7 | RBE Remove Fixture Eta | Artist Folder / Album Folder | Added for R7. Sits beside a `cover.jpg` with its embedded art stripped. |
| F8 | RBE Remove Fixture Theta | Artist Folder / Album Folder | The same, so the pair also shows whether folder art is keyed per track or per album. |

The build script is idempotent and re-derives each copy from its source, so an
arm that deleted a fixture file gets a byte-identical replacement rather than a
restore from backup.

### A Note on `get_anlz_dir` and the Empty Path

F4 is in this study because of a hazard found while selecting subjects.
`pyrekordbox`'s `get_anlz_dir` strips the leading separator from
`AnalysisDataPath` and joins the remainder onto the share directory. For an
empty `AnalysisDataPath` that resolves to the **share root itself**, not to a
per-track directory. A `remove` implementation that resolved the analysis
directory and deleted it recursively would therefore destroy the entire share
tree for any unanalyzed track. `_update_anlz_paths` in
`rekordbox_edit/api/_utils.py` already guards this by returning early on a falsy
`AnalysisDataPath`, and `remove` must carry the same guard under a test that
fails loudly without it. This holds regardless of what the arms find, and
belongs in the decision record either way.

The analysis directories also hold AppleDouble siblings (`._ANLZ0000.DAT` and
its kin) beside the three real files, so removal targets the directory rather
than three known filenames.

### Artwork Is a Second Per-Track Artifact

Found while preparing the fixtures, and not part of the original plan. A track's
cover art is written to `share/PIONEER/Artwork/<xxx>/<uuid>/` as `artwork.jpg`
with `_s` and `_m` thumbnails, and `DjmdContent.ImagePath` points at it in the
same device-relative form `AnalysisDataPath` uses, keyed by the same content
UUID. Removal therefore has two on-disk artifacts to account for, not one, and
`ImagePath` needs the same empty-value guard as `AnalysisDataPath`.

Whether artwork is ever shared between rows is **unsettled and cannot be settled
here**: only two rows in this library carry an `ImagePath` at all, both of them
fixtures, and they do not share. F2 and F3 sit on the same album and still got
separate artwork directories, which suggests the key is the track rather than
the album, but two observations support no general claim. The snapshot records a
`shared_with` count for each subject so the arms report what they see, and the
implementation should check for other referents before deleting the files
regardless of what the arms show, because the check is cheap and being wrong is
not.

### Where the Vocals Analysis Lives

The library was analyzed with the "Vocals" target enabled, which raised the
question of whether it writes files this study does not know about. It does not.
A tag walk of a fixture's analysis files shows the classic three and nothing
else, with the vocal data carried as a `PVDI` tag inside `ANLZ0000.2EX`
alongside `PWV6`, `PWV7`, and `PWVC`. Phrase and structure data sits in the
`PSSI` tag in the `EXT`. Every extra analysis target this library exercises
therefore lands inside the same three files, so removing the per-track directory
still covers all of it.

## Scope and Goals

Five arms, each answering one question the apply logic must resolve. R4 exists
to draw a boundary rather than to implement one: removing a track from a
playlist is a different operation from deleting it from the library, and this
study confirms the two are distinguishable so that `remove` cannot be
implemented as the wrong one.

| Arm | Subject | Gesture | Answers |
| --- | --- | --- | --- |
| R1 | F1 | Remove from Collection, keep the file | Hard delete against tombstone; the `ContentID` sweep; the analysis directory; orphan collection |
| R2 | F1 | Remove from Collection, delete the file | **Cancelled, see below** |
| R3 | F2 | Remove from Collection, keep the file | Artist and album shared with F3: confirms nothing is collected when references remain |
| R4 | F2 | Remove from a playlist only | The boundary: this must touch `djmdSongPlaylist` alone |
| R5 | F4 | Remove from Collection, keep the file | An empty `AnalysisDataPath`: confirms no analysis directory is involved |
| R6 | F5 | Remove from Collection, keep the file | Whether an orphaned label is collected, and what happens to artwork two rows may share |
| R7 | F7, F8 | Import only, no removal | Whether rekordbox reads cover art sitting beside the audio, and where it points `ImagePath` |
| R8 | F9, F10 | Import both, analyze one | When rekordbox extracts embedded art into `share/PIONEER/Artwork` |

## Snapshot Tooling

Three scripts, built for this study, writing only to `evidence/` and to the
fixture staging directory.

`scripts/build_fixtures.py` stages and retags the four subject copies.

`scripts/removal_snapshot.py <content_id> <stage>` captures the subject
`DjmdContent` row in full, every child row in every table carrying a
`ContentID`, the shared records the subject points at with their library-wide
reference counts, the analysis directory with a SHA-1 per file, the audio file,
a global row census of every mapped table, and `localUpdateCount`. It writes
`evidence/rm-<id>-<stage>.json`.

`scripts/removal_diff.py <content_id> <stageA> <stageB>` prints the subject
row's fate, the columns that moved on it, child rows cleared per table, records
orphaned or collected, the files removed, every census table whose count moved,
and the `localUpdateCount` delta.

`scripts/restore.sh [backup-name]` returns the library to a captured backup and
rebuilds the fixture files.

The snapshot and diff scripts default to the library above and honor
`RBE_DATABASE_PATH`. Read the snapshot with rekordbox closed so it sees
committed state.

The child-table list is discovered by reflection over `pyrekordbox`'s mapped
tables rather than written out by hand, and the census spans every table rather
than the ones this plan expects to move. Both choices exist for the same reason:
the interesting result is a table nobody thought to watch. A probe run already
justified it by turning up three `contentFile` rows on a subject, a cloud-sync
table absent from the original list of children.

## Fixture Preparation

Cue rows are the child records a DJ would most regret losing silently, so the
arms have to be able to observe them being cleared. The library contains none,
and neither cues nor MyTag assignments can be created from outside rekordbox, so
they have to be set by hand before any arm runs.

With rekordbox open on the library:

1. Import all four files from `/private/tmp/rbe-remove-fixtures`.
2. Analyze **F1, F2, and F3** only. Leave **F4 unanalyzed**, which is the whole
   point of that subject.
3. On **F1**, set two hot cues and one memory cue, and assign any MyTag.
4. On **F2**, set one hot cue, assign a MyTag, and add it to any playlist. R4
   later removes it from that playlist, so note which one.
5. Quit rekordbox so the writes commit.

Then capture the prepared baselines and the backup they restore from. A baseline
whose `djmdCue` child count is zero means the preparation did not take, and the
arm that follows it cannot answer the cue question.

## Backup and Revert Protocol

Removal destroys on-disk state that a database restore does not bring back, so
the backup covers the database and the analysis directories. The fixture audio
needs no backup, because `build_fixtures.py` rebuilds it.

1. Quit rekordbox.
2. Copy `master.db`, and its `-wal` and `-shm` if present, from the library
   directory to `~/rb-remove-test-backup/<name>/master.db`.
3. Copy the four subjects' analysis directories from `share/PIONEER/USBANLZ/`
   into `~/rb-remove-test-backup/<name>/anlz/`, preserving the two-level
   `xxx/yyyy-...` layout `restore.sh` expects.

`~/rb-remove-test-backup/pre-prep/` holds the state before the fixtures were
imported, taken with rekordbox closed and no `-wal` or `-shm` present. The
`prepared` backup is captured after fixture preparation, and is what every arm
restores from. The backups exist for methodology rather than for safety: each
arm must start from an identical state for its diff to be attributable, and the
library itself is expendable.

Restore between arms with `scripts/restore.sh prepared`, so each arm starts from
the same state and its effects are attributable to that arm alone. The script
refuses to run while rekordbox is open.

## The Arms

Each arm is the same sequence: restore, confirm the baseline, perform the
gesture in rekordbox, quit rekordbox, snapshot, diff. Only the gesture and the
reading differ.

### R1: Remove From Collection, Keeping the File

Remove F1 from the Collection, declining any offer to delete the file. Quit.
Snapshot `r1-10-removed`. Diff `r1-00-baseline` against it.

What to read:

- **Hard delete against tombstone.** Is the `DjmdContent` row absent from the
  table, or present with `rb_local_deleted` flipped to 1? This is the single
  most load-bearing result in the study. A tombstone means `remove` must write
  one, and the whole apply design changes.
- **The child sweep.** Which of the thirteen `ContentID` tables lost the
  subject's rows, and did any keep them? A child row surviving its parent is a
  dangling reference, and `remove` would have to clear it whether rekordbox does
  or not.
- **The census.** Did any table move that this plan did not expect, including
  `contentFile` and the other cloud tables?
- **The analysis directory.** Removed, emptied, or left in place? If left, the
  share tree accumulates orphaned analysis, and `remove` removing it is a
  deliberate divergence rather than a mirror.
- **Orphan collection.** F1's artist, album, and genre each had one reference.
  Were they collected, as `edit-relational-fields` measured for the inline edit,
  or left behind? The genre answer is the genuinely open one.
- **The artwork directory.** F1 carries no artwork, so R1 cannot answer this;
  R3 is the arm that can, and R1's reading is only that the share tree's
  `Artwork` subtree is untouched.
- **`localUpdateCount`.** By how much did it advance, and did any surviving
  related row take a fresh `rb_local_usn`?

### R2: Remove From Collection, Deleting the File (Cancelled)

**This arm was never run, because the gesture it tests does not exist.**
Rekordbox offers no option to delete the audio file when removing a track from
the collection, confirmed by the maintainer and consistent with every other arm,
in each of which the source file survived untouched.

The finding stands in place of the measurement: there is no native behavior for
`--delete-source` to mirror, so what that flag should do is a design decision
rather than something this study can settle. It is recorded in
`decisions/remove-command-behavior.md`.

### R3: A Track Whose Artist and Album Are Shared

Restore. Remove F2 from the Collection, keeping the file. Quit. Snapshot
`r3-10-removed`. Diff against `r3-00-baseline`.

What to read: that the artist, album, and genre reference counts each fall by
one and all three records **survive**, held by F3. F2 also carries artwork, so
this is the arm that shows whether rekordbox removes the artwork directory along
with the track, and whether it does so while F3's separate artwork stands. R1 shows what happens when a
record is orphaned; R3 is the control showing that collection is driven by the
reference count and not by removal itself.

### R4: Removing From a Playlist Only

Restore. In the playlist F2 was added to, remove F2 from the playlist rather
than from the Collection. Quit. Snapshot `r4-10-playlist-only`. Diff against
`r3-00-baseline`.

What to read: that exactly one `djmdSongPlaylist` row disappeared, the
`DjmdContent` row is untouched, no other child table moved, and no file was
deleted. Any result broader than that means the two gestures are entangled and
the scope boundary this command draws has to be reconsidered.

### R5: A Track With No Analysis

Restore. Remove F4 from the Collection, keeping the file. Quit. Snapshot
`r5-10-removed`. Diff against `r5-00-baseline`.

What to read: that the share tree is intact and no analysis directory was
involved, and that the sole-reference artist and album were collected as in R1.
This arm is the fixture the `remove` implementation's own regression test should
imitate.

### R6: An Orphaned Label, and Artwork Two Rows May Share

Added after the first four arms, to close the two questions they left open.
Restore, import **F5** and **F6**, and analyze both. Before removing anything,
snapshot both: their `ImagePath` values answer the artwork question on their own.
Then remove **F5** from the Collection, keeping the file. Quit. Snapshot
`r6-10-removed` and `f6-10-control`, and diff each against its baseline.

F5 and F6 sit on one album with byte-identical cover art, and F5 alone carries a
label. Removing F5 therefore leaves the artist, album, and genre referenced by
F6, so the label and the artwork are the only things at stake.

What to read:

- **Artwork identity.** Do F5 and F6 share one `ImagePath`, or does each get its
  own artwork directory? An earlier pair sharing an album got separate
  directories, but they carried different source art, so identity was never
  tested against identical bytes.
- **Artwork deletion when shared.** If the two do share a path, does rekordbox
  delete the image files while F6 still points at them? This is the one case in
  the study where mirroring rekordbox could destroy data a surviving track
  depends on, and it decides whether the `ImagePath` referent check in the
  implementation is load-bearing or merely prudent.
- **Label collection.** Is the orphaned `DjmdLabel` hard-deleted, as artist,
  album, and genre were in R1? This is the only behavior the command would
  otherwise infer rather than measure.
- **The control.** F6 must be untouched, and the shared artist, album, and genre
  must survive with reference counts down by one.

### R7: Cover Art Beside the Audio Rather Than Inside It

Restore, import the `rbe-folder-art-album/` directory holding **F7** and **F8**
beside a `cover.jpg`, and analyze both. Quit. Read their `ImagePath` values. No
removal is needed; the import answers the question.

Both copies have their embedded art stripped, so folder art is the only art
available. Neither carries a label, so this pair cannot disturb the label census
R6 reads, and the two arms may share a rekordbox session.

What to read, and what each outcome means:

- **`ImagePath` under `/PIONEER/Artwork`.** Rekordbox copied the folder art into
  its managed tree, exactly as it does for embedded art. Nothing changes.
- **`ImagePath` pointing at the `cover.jpg` itself.** Rekordbox references the
  user's own file in place, and `remove` must never delete artwork outside the
  share directory. Neither the empty-path guard nor a reference count would
  catch this: one imported track from an album folder has exactly one referent,
  so the check would pass and a cover image the rest of the folder depends on
  would be destroyed.
- **`ImagePath` empty.** Rekordbox ignores folder art, and artwork originates
  only from embedded tags.

### R8: When Artwork Is Extracted

R5 already showed that importing is not enough: F4 carried a 690 KB embedded
image, was imported without being analyzed, and its `ImagePath` stayed empty.
What that leaves open is *which* later step does it. Every track that did get
artwork had been imported, analyzed, selected, and displayed in one session, so
analysis was never separated from merely being looked at, and a lazy extraction
on first display would produce identical evidence.

Two stages, with a snapshot between them.

1. Import **F9** and **F10** from `rbe-artwork-timing/`. **Analyze neither.**
   Quit. Snapshot both as `r8-00-imported`. Both `ImagePath` values are expected
   to be empty, which replicates the F4 result on purpose.
2. Analyze **F9 only**, leaving F10 untouched and preferably unselected. Quit.
   Snapshot both as `r8-10-analyzed`.

F10 is the control. It holds embedded art and sits in the library across the
same interval as F9, so it accounts for anything that follows from time passing
or from a background pass rather than from analysis.

What to read:

- **F9 gains artwork and F10 does not.** Analysis is the trigger.
- **Both gain artwork.** Something other than analysis extracts it, most likely
  a background pass over the library, and the trigger is still not isolated.
- **Neither gains artwork.** Analysis is not the trigger either, and the cause
  lies somewhere this plan has not considered.

Nothing here changes what `remove` does, since the command reads `ImagePath` and
acts on what it finds. The arm exists because the findings should not stay silent
on when an artifact the command deletes comes into being, and because a track
that can acquire artwork after import is worth knowing about.

## What Each Run Answers

| Question | Arm · stage diff | Measurement | Guides |
| --- | --- | --- | --- |
| Hard delete or tombstone | R1 · `r1-00`→`r1-10` | Row absent, against `rb_local_deleted == 1` | Whether `remove` deletes or flags the content row |
| Which children are cleared | R1 · `r1-00`→`r1-10` | Per-table child counts falling to zero | The delete sweep, and which tables it must cover |
| An unwatched table moved | R1 · census delta | Any count moving outside the expected set | Whether the sweep is complete |
| Analysis directory fate | R1 · on-disk diff | Directory removed against left in place | Whether `remove` deletes analysis, and whether that mirrors or diverges |
| Orphan collection on removal | R1, R5 · relations | `total_refs` reaching 0, record collected or not | Reuse of `_delete_if_orphaned`, and how wide to cast it |
| Genre, label, and key collection | R1 · relations | Whether a vocabulary table is collected like artist and album | How wide the orphan sweep goes |
| Collection is reference-driven | R3 · relations | Refs fall by one, records survive | That orphan cleanup is not unconditional |
| Whether rekordbox deletes source files at all | all arms · on-disk | The file survived every removal | `--delete-source` mirrors nothing; it is the tool's own affordance |
| Label collection | R6 · relations and census | Orphaned `DjmdLabel` collected or left | Whether the orphan sweep covers labels |
| Artwork identity | R6 · `ImagePath` on F5 and F6 | One shared path against two | Whether artwork is per-track or per-album |
| Artwork deletion when shared | R6 · on-disk | Image files removed while F6 still references them | Whether the `ImagePath` referent check is load-bearing |
| Folder art against embedded art | R7 · `ImagePath` on F7 and F8 | Copied, referenced in place, or ignored | Whether `remove` can reach a file outside the share tree |
| When artwork is extracted | R8 · `r8-00`→`r8-10` on F9 against F10 | Artwork appearing for the analyzed track alone | Whether a track can acquire artwork after import |
| Playlist removal is separable | R4 · `r3-00`→`r4-10` | One `djmdSongPlaylist` row and nothing else | The command's scope boundary |
| No analysis is safe | R5 · on-disk | Share tree intact | The empty-`AnalysisDataPath` guard |
| Artwork directory fate | R3 · on-disk diff | Directory removed against left in place | Whether `remove` deletes artwork, and the `ImagePath` guard |
| USN accounting | all · `localUpdateCount` | The delta, and `rb_local_usn` on survivors | How `stamp_usns` applies to a delete |
