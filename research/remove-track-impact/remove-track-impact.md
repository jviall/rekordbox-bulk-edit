# What Rekordbox Does When a Track Is Removed: Findings

## Question

What does rekordbox do to the database and to the filesystem when a user removes
a track from the collection? The answer grounds the `remove` command: whether it
deletes a row or tombstones it, which of the thirteen tables carrying a
`ContentID` it must clear, what becomes of the analysis and artwork files, and
how far orphan cleanup of the shared relational records extends. The procedure,
subjects, and tooling are in `remove-track-impact-test-plan.md`.

Every result comes from a single trial against the library at
`/Volumes/GIG MUSIC/PIONEER/Master` under rekordbox 7, snapshotted with
rekordbox closed and restored from a `master.db` backup between arms. Subjects
are purpose-built copies imported for the study, so no arm removes a track the
library depended on. Evidence files are `evidence/rm-<id>-<stage>.json`.

## Summary

Removal is a hard delete with a wide but **incomplete** cleanup:

1. **The `DjmdContent` row is deleted, not tombstoned.** `rb_local_deleted` is
   never set.
2. **Every child row keyed by `ContentID` goes with it**, including the
   cloud-sync tables `contentCue` and `contentFile`.
3. **The analysis directory is removed**, along with the now-empty two-character
   prefix directory above it.
4. **Artwork is treated differently from analysis.** The image files are
   deleted, but the per-track directory is left behind, empty.
5. **Orphaned artist, album, genre, and label records are hard-deleted**,
   matching the inline-edit behavior measured in `../edit-relational-fields/`.
6. **Orphan collection is not transitive.** Collecting an orphaned album does
   not re-examine the artist that album's `AlbumArtistID` pointed at, so a
   removal can leave an artist at zero references still sitting in the table.
7. **The audio file is never deleted.** Rekordbox offers no gesture that would.
8. **Artwork comes only from embedded tags.** Rekordbox ignores a `cover.jpg`
   beside the audio, so every `ImagePath` resolves inside its own managed share
   tree and never into the user's music directory.
9. **Analysis, not import, produces both on-disk artifacts.** An unanalyzed
   track has no analysis directory and no artwork, however its tags are
   furnished.

## R1: Removal With Analysis, Cues, MyTags, and Sole-Reference Records

Subject `114745319` ("RBE Remove Fixture Alpha"), carrying three `djmdCue` rows,
three `djmdSongMyTag` rows, a `djmdMixerParam`, one `contentCue`, three
`contentFile`, an analysis directory, no artwork, and sole ownership of its
artist, album, and genre.

- The `DjmdContent` row was **absent** from the table afterward, and no row
  anywhere carried `rb_local_deleted == 1`. **Hard delete confirmed**; the
  tombstone hypothesis is rejected.
- All five occupied child tables fell to zero. The two that matter most are
  `contentCue` and `contentFile`, which are cloud-sync tables that a
  hand-enumerated list of children would plausibly omit.
- The analysis directory
  `share/PIONEER/USBANLZ/2ab/6b28b-bb71-4787-a33b-73e6eebc0dbb` was removed, and
  so was its parent `2ab/`, which the removal left empty.
- The artist, album, and **genre** were each hard-deleted at zero references.
  Genre was the open question in the hypothesis, and it resolves toward the
  wider sweep. The key `Dm`, held by 40 other tracks, was untouched.
- The audio file survived.
- The global census moved on exactly the nine tables the above accounts for and
  no others.

## R4: Removal From a Playlist Only

Subject `265892207` ("RBE Remove Fixture Beta"), removed from the `TestRemove`
playlist rather than from the collection.

- Exactly one `djmdSongPlaylist` row disappeared. The global census moved on
  that table alone.
- The `DjmdContent` row was untouched: not one column changed.
- The five other occupied child tables, the analysis directory, the artwork
  directory, and the audio file were all unchanged.
- The parent `DjmdPlaylist` row was **not** touched either. Its `rb_local_usn`
  held at 2901 and its `updated_at` still read the import timestamp. This is the
  same gap `../import-track-row-shape/decisions/commit-semantics-and-usn.md`
  recorded for `add_to_playlist`: rekordbox does not stamp a playlist whose
  membership changes.

Playlist removal and collection removal are therefore cleanly separable in the
database, which is what licenses scoping them as different commands.

## R3: Removal With Shared Records and Artwork

Subject `265892207` ("Beta"), whose artist, album, and genre are each shared with
`137975518` ("Gamma"), and which carries an artwork directory. Run in one
rekordbox session with R5, on a disjoint subject.

- Hard delete again, and all six occupied child tables cleared, this time
  including `djmdSongPlaylist`.
- The analysis directory and its `592/` prefix directory were removed.
- **The artwork files were deleted but the directory was not.**
  `share/PIONEER/Artwork/592/5bd94-8b47-4344-8424-cdf94d6a4283` still exists and
  is empty; `artwork.jpg`, `artwork_m.jpg`, and `artwork_s.jpg` are gone. The
  prefix directory `592/` also survives. Rekordbox therefore cleans up analysis
  directories and does not clean up artwork directories, and the asymmetry
  appears to be an oversight on rekordbox's part rather than a distinction with
  a purpose.
- The shared artist, album, and genre all **survived**, with reference counts
  falling from 3 to 2, 2 to 1, and 2 to 1 respectively, held by Gamma. Collection
  follows the reference count rather than the removal.
- The control subject Gamma was untouched: no column changed, its own child rows
  held, and its analysis and artwork directories were intact.

## R5: Removal Without Analysis, and the Non-Transitive Orphan Sweep

Subject `14241481` ("RBE Remove Fixture Delta"), imported but never analyzed, so
its `AnalysisDataPath` was empty and it held no child rows in any table. Its
album, genre, and artist were its own, and because rekordbox read `albumartist`
from the MP3 tags, the album's `AlbumArtistID` also pointed at that artist.

- Hard delete, with no child rows to clear and no analysis or artwork files
  involved. The share tree was untouched. The audio file survived.
- The album and genre were hard-deleted at zero references.
- **The artist was not.** `RBE Remove Fixture Artist Delta` remains in
  `DjmdArtist` with a reference count of zero.

The sequence explains it. The artist began with two references: the subject's
`ArtistID`, and the album's `AlbumArtistID`. Removing the subject dropped the
first, leaving one. Rekordbox then collected the album, which dropped the second
to zero. Nothing re-examined the artist afterward, so it survives as an orphan.

**Orphan collection is one pass, not a fixpoint.** A record that becomes
unreferenced as a consequence of another record being collected is not itself
collected. This is a genuine defect in rekordbox's cleanup, and any
implementation that mirrors rekordbox's single pass faithfully will reproduce
it.

## R6: An Orphaned Label, and Artwork Identity

Subjects `139425629` ("Epsilon") and `120331280` ("Zeta"), added after the first
four arms to close the two questions they left open. The pair sits on one album,
carries byte-identical embedded cover art, and only Epsilon carries a label.
Epsilon was removed from the collection; Zeta is the control.

**Artwork is per-track and is never shared.** The question was answered by the
import alone, before anything was removed. Despite sharing an album
(`AlbumID 792577934`) and carrying the same cover art bytes, the two rows
received **separate** artwork directories keyed by their own content UUIDs, and
the two `artwork.jpg` files are byte-identical (SHA-1 `6539ff9c…`, 39,269 bytes
each). Rekordbox duplicates artwork per track rather than deduplicating it.
Across the whole library, four rows carry an `ImagePath` and all four are
distinct.

Rekordbox also re-encodes: the 71,931-byte embedded image became a 39,269-byte
`artwork.jpg` plus `_m` and `_s` thumbnails.

**An orphaned label is collected.** `RBE Remove Fixture Label Epsilon` held
exactly one reference. Removing Epsilon dropped `djmdLabel` from 5 rows to 4 and
the label is gone from the table. Label collection therefore behaves as artist,
album, and genre do, which had previously been an inference rather than a
measurement.

The album, artist, and genre survived, held by Zeta, with reference counts
falling from 2 to 1, 3 to 2, and 2 to 1. Zeta itself was untouched, and its own
analysis and artwork directories were intact. Epsilon's artwork files were
deleted and its artwork directory left behind, the same asymmetry R3 found.

## R7: Cover Art Beside the Audio Rather Than Inside It

Subjects `36337051` ("Eta") and `143461275` ("Theta"), imported from a directory
holding a `cover.jpg` alongside them, with their embedded art stripped so folder
art was the only art available. Both were analyzed. Nothing was removed; the
import alone answers the question.

**Rekordbox does not read folder art.** Both rows carry an empty `ImagePath`, no
artwork directory was created for either, and the `cover.jpg` was left untouched.

The question mattered because of what the alternative would have meant. Had
rekordbox pointed `ImagePath` at the `cover.jpg` in place, then deleting "the
track's artwork" would have deleted a file inside the user's own music
directory, one that every other track in that album folder depends on and that
the user put there themselves. Neither the empty-path guard nor a reference
count would have prevented it: a single imported track from that album has a
reference count of one, so the check would pass and the file would go.

It does not arise. Artwork originates only from embedded tags, and every
`ImagePath` in the library resolves under `share/PIONEER/Artwork`. The
implication for the implementation is a containment check rather than a
divergence, recorded in `decisions/remove-command-behavior.md`.

## R8: Analysis, Not Import, Produces the Artwork

Subjects `74039842` ("Iota") and `109570093` ("Kappa"), imported together, each
carrying an embedded cover image, on separate albums. Neither was analyzed in
the first stage; only Iota was analyzed in the second. Kappa is the control,
holding embedded art and sitting in the library across the same interval, which
accounts for anything following from time passing or from a background pass
rather than from analysis.

- **After import, neither had artwork.** Both carried `Analysed = 0`, an empty
  `AnalysisDataPath`, and an empty `ImagePath`, and the `Artwork` tree held
  nothing at all. This replicates the R5 result, where F4's 690 KB embedded
  image survived an import without producing anything.
- **After analyzing Iota alone, Iota had artwork and Kappa did not.** Iota moved
  to `Analysed = 105` with an analysis directory and an `ImagePath` under
  `share/PIONEER/Artwork`; Kappa was unchanged in every respect.

- **Analyzing Kappa afterward gave it artwork too.** The control was analyzed
  once the arm had been read, and an artwork directory appeared for it at
  `share/PIONEER/Artwork/406/e4f73-d0d1-4503-8dc3-f43f45d867a3`, matching the
  `UUID` recorded for Kappa in `rm-109570093-r8-10-analyzed.json`. The database
  had been restored to its pre-study state by then, so no snapshot records the
  row, but the directory is keyed by Kappa's own UUID and is evidence in itself.

**Analysis is what extracts embedded art.** The control rules out a background
pass and rules out the passage of time, which the earlier arms could not: every
track that gained artwork before this one had been imported, analyzed, selected,
and displayed in a single session, so analysis was confounded with merely being
looked at. Analyzing the control afterward makes the result a within-subject
replication rather than a comparison between two tracks, which also rules out
an idiosyncrasy in the one that was analyzed first.

This unifies the two on-disk artifacts. Both the analysis directory and the
artwork directory are products of analysis, both are keyed by the track's
`UUID`, and both sit under `share/PIONEER/` in parallel trees. An unanalyzed
track has neither, which is why an empty `AnalysisDataPath` and an empty
`ImagePath` travel together.

Rekordbox re-encodes rather than copies, and the direction is not fixed: Iota's
42,248-byte source image became a 48,066-byte `artwork.jpg`, while F5's
71,931-byte image became 39,269 bytes. Each is written with `_m` and `_s`
thumbnails beside it.

## USN Accounting

The `localUpdateCount` counter advances on removal, but not by a figure this
study can predict:

| Arm | Rows deleted | `localUpdateCount` delta |
| --- | --- | --- |
| R1 | 15 | +15 |
| R4 | 1 | +2 |
| R3 and R5 combined | 13 | +14 |
| R6 | 8 | +13 |

No surviving row in any table carried either of the two values R4 consumed, so
the extra value was spent on something that leaves no trace in a row. R1's exact
match is therefore best read as coincidence rather than as a rule.

This matches the open question left in
`../import-track-row-shape/decisions/commit-semantics-and-usn.md`, where roughly
820 USN values in a sampled library went to something never established. What
the study does support is a lower bound: the counter advances by at least the
number of rows deleted.

## Source File Deletion

Rekordbox never offers to delete the audio file when removing a track from the
collection, and the file survived every arm. There is consequently **no native
behavior for `--delete-source` to mirror**. The flag is an affordance
rekordbox-edit adds rather than one it reproduces, and what it should promise,
an unlink against a move to the trash, is a design decision rather than a
finding.

## Conclusion

The `remove` command should hard-delete the `DjmdContent` row, clear every child
row keyed by `ContentID`, remove the analysis directory, and collect orphaned
artist, album, and genre records, because that is what rekordbox does.

It should diverge from rekordbox in two places, both of which are cleanup
rekordbox omits rather than behavior it intends:

1. **Repeat the orphan sweep until it reaches a fixpoint**, so that an artist
   left unreferenced by the collection of an album is itself collected.

Artwork sharing was settled by R6 and needs no divergence: rekordbox writes a
separate artwork directory per track even for two tracks on one album with
identical cover art, so removing a track's artwork can never strip a surviving
track of its own. An `ImagePath` referent check in the implementation is
therefore prudence rather than a load-bearing guard.

The decision record is `decisions/remove-command-behavior.md`.
