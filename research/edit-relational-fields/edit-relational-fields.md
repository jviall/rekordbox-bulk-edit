# How Rekordbox Handles Relational Metadata Edits: Findings

## Question

What does rekordbox do to the shared `DjmdArtist` and `DjmdAlbum` tables when a
user edits a track's Artist or Album inline? The answer grounds the `edit`
command's relational field handlers (issue #17). The procedure, subjects, and
tooling are in `edit-relational-fields-test-plan.md`.

Every result comes from a single trial against the real local library,
snapshotted with rekordbox closed, and reverted from a `master.db` backup between
experiments. The evidence files are `evidence/rel-<id>-<stage>.json`.

## Summary

Rekordbox's inline artist and album edit is a match-by-name reassignment with
aggressive cleanup, not a rename and not a relational merge:

1. **It reuses an existing shared record by exact name.** Retyping a track's
   Artist or Album to a name already in the table repoints the track's foreign
   key to that existing row; it never creates a duplicate row for the same name.
2. **It keys identity on name alone, ignoring album-artist.** An album match
   succeeds on name even when the existing album's album-artist differs from the
   edited track's artist. Same-name albums that differ only by album-artist do
   exist in the library, but they come from the import path, not inline editing.
3. **It reassigns the single track; it does not rename the shared record.** Other
   tracks referencing the old record keep their reference and the record keeps
   its name.
4. **It hard-deletes a record left with no references.** When the edit moves the
   only track off an artist or album, that row is removed from the table
   immediately, in the same save, not soft-deleted and not deferred to a restart.
5. **It blanks the reused record's album-artist.** This is the one destructive
   surprise, detailed below, and the main reason to diverge from faithful mirror.
6. **It writes empty strings, not NULL, for cleared foreign keys**, and leaves
   `SearchStr` NULL on records it creates.

## E1: Artist Reassignment

Editing track `176388182` (Daft Punk, 21 tracks) to artist `Stromae`, an existing
artist.

- The track's `ArtistID` moved from Daft Punk to the **existing** Stromae row
  (`240003483`); Stromae's reference count rose 25 to 26. The artist total held at
  1523, so no duplicate `Stromae` was created. **Reuse by name confirmed.**
- Daft Punk survived with its name intact, dropping one reference (21 to 20).
  **The edit reassigns the track, it does not rename the shared record** — the
  assumption the whole apply design rests on.
- Side effect: the track's album row had its `AlbumArtistID` coerced from NULL to
  `''` and its `rb_local_usn` bumped. Editing a track touches that track's album
  row even when only the artist changed.

## E2: Album Reuse With a Matching Album-Artist

Editing track `112264610` (Kelly Lee Owens, on the sole-reference album "More Than
A Woman") to album `Melt!`, an existing album whose album-artist is Kelly Lee
Owens.

- The track's `AlbumID` moved to the **existing** "Melt!" (`983114985`); no album
  was created. **Album reuse by name confirmed.**
- The vacated album "More Than A Woman" (`3807067907`), now referenced by nothing,
  was **removed from the table** (album total 1021 to 1020). **Orphan hard-delete
  confirmed for albums**, immediately, within the edit.
- **Destructive surprise:** "Melt!" had its `AlbumArtistID` wiped from Kelly Lee
  Owens (`1693627479`) to `''`, and Kelly Lee Owens' album-artist reference fell 1
  to 0. Reusing an album via an inline track edit **strips that album's
  album-artist**, affecting every other track on the album.

## E3: Album Identity Against the Album-Artist

Editing track `57701453` (Gamma) to album `Arian`, an existing album whose
album-artist is "Arian", deliberately not Gamma.

- The track reused the **existing** "Arian" album (`1091646474`) despite the
  album-artist mismatch; no new album appeared. **Album identity keys on name
  alone**, not on `(Name, AlbumArtist)`.
- The "Arian" album's album-artist was blanked to `''` (same as E2), and the
  vacated "AIFF Sampler" orphan was hard-deleted (same as E2).

The library does contain same-name albums that differ only by album-artist (two
"Movimiento Para Cambio" rows, one with an album-artist and one without). Because
inline editing reuses by name, those duplicates cannot have come from inline
edits; they originate in rekordbox's import and tag-reading path, which can key
album identity on the album-artist. The two code paths behave differently, so
"mirror rekordbox" is ambiguous for album identity, and the inline behavior is
the one this command emulates.

## V1–V3: Album-Artist Blanking, Re-Confirmed on Three More Fixtures

The album-artist blanking is destructive enough to justify diverging from
rekordbox, so it was re-tested on three additional albums chosen to vary the
condition. Each subject sat on a multi-track source album and moved onto a
multi-track destination, so nothing orphaned and each trial isolates the
destination blank. All three edits ran in one rekordbox session; the diffs share
a census, so every destination shows in each.

- **V1 — populated, non-matching album-artist.** Track `71974950` ("House 1",
  artist rekordbox) moved onto "High Life" (`4213612001`, album-artist Detroit
  Swindle). "High Life" `AlbumArtistID` went `2969573714` to `''`; Detroit
  Swindle's album-artist reference fell 1 to 0.
- **V2 — compilation / Various Artists destination.** Track `50395296` ("House
  2") moved onto "Ivory Music Classics, Vol. 2" (`6561467`, album-artist Various
  Artists). Its `AlbumArtistID` went `2999571375` to `''`; a compilation album is
  not exempt.
- **V3 — destination album-artist equals the moving track's own artist.** Track
  `47413782` ("Drive Through", artist DJ Black Low) moved onto "Uwami"
  (`1647593099`, album-artist DJ Black Low). The album-artist was **still** wiped
  to `''` even though every track on the album, including the one just added, is
  by DJ Black Low. The blank is unconditional, not a "the album-artist no longer
  applies" cleanup.

In all three, `rb_local_usn` bumped on the destination album (rekordbox wrote the
row), the destination gained the subject and each source lost it, and the census
held at 1523/1021 with no orphan. Across E2, E3, and V1–V3 the blanking is
confirmed on five fixtures spanning matching, non-matching, and compilation
album-artists. The decision not to mirror it stands.

## E3b: Album Creation From an Artist-Less Track

Editing track `141833798` (no artist) to a brand-new album name `RBE Test Album
ZZZ`.

- A new album row was created (`3219926450`; album total 1021 to 1022).
- Its `AlbumArtistID` is `''`, because the track has no artist to derive one from.
- Its `SearchStr` is **NULL**: the inline path does not populate the album search
  string on creation. `rb_local_usn` was set to the current global counter and
  `usn` left NULL.
- The track's own NULL `ArtistID` was coerced to `''`.

## E4: Orphan Handling for Artists

Editing sole-reference artist `Delta` (`1442926686`, one track, `183309432`) off
its only track. (The track ended artist-less rather than reassigned, which does
not affect the orphan result and additionally records the clear-artist case.)

- **Delta was removed from the table** immediately (artist total 1523 to 1522).
  **Artists are hard-deleted when orphaned, exactly like albums**, in the same
  save, so the planned restart arm was unnecessary.
- Clearing an artist sets the track's `ArtistID` to `''` (empty string, not NULL)
  and deletes the now-orphaned artist.

## Design Conclusions

These findings settle the provisional relational decisions in
`decisions/edit-field-handlers.md`.

- **Get-or-create by exact name, then relink** is correct and matches rekordbox.
  The artist handler looks up `DjmdArtist` by name, creates it if absent, and sets
  the track's `ArtistID`. The album handler does the same on `DjmdAlbum` keyed on
  name alone.
- **Do not mirror the album-artist blanking.** Rekordbox strips a reused album's
  album-artist, which corrupts shared data for every other track on that album.
  The command should reuse the album by name and **leave its `AlbumArtistID`
  untouched**. This is a deliberate, documented divergence from rekordbox for the
  sake of not damaging unrelated tracks.
- **Orphan cleanup is now in scope, not deferred.** Because rekordbox itself
  hard-deletes an artist or album the moment its last reference leaves, matching
  that behavior keeps the library consistent with what the desktop app would do.
  After relinking a track, the handler checks whether the vacated record has any
  remaining reference across all six artist foreign keys (`ArtistID`,
  `RemixerID`, `OrgArtistID`, `ComposerID`, `Lyricist`, and `DjmdAlbum`.
  `AlbumArtistID`) or, for an album, any remaining `AlbumID` reference, and deletes
  it when the count reaches zero. Leaving orphans, the earlier provisional choice,
  would diverge from rekordbox in the opposite direction and slowly litter the
  library.
- **Empty string, not NULL, for a cleared foreign key.** `--replace ""` on artist
  or album sets the foreign key to `''` and triggers the same orphan check.
- **Do not populate `SearchStr` on created records.** Rekordbox leaves it NULL on
  the inline path, so `add_artist` / `add_album` should not fabricate one.

## Open Items and Caveats

- Single trials per experiment; the goal was to characterize behavior, not rate.
- The album-artist blanking was observed on the inline album edit; whether the
  same blanking occurs on an artist-only edit was not the target, though E1 showed
  an artist edit still coerces the album's `AlbumArtistID` NULL to `''`.
- Orphan deletion here is a hard row delete. Whether rekordbox's cloud sync later
  reconciles that deletion through the `usn` and `rb_local_deleted` bookkeeping is
  out of scope; the command deletes the row as rekordbox's own desktop edit does.
- `SearchStr` behavior is recorded only for the inline-created album; artist
  creation via inline edit was not exercised for its `SearchStr`, but the album
  result and the general NULL-leaving pattern make a populated string unlikely.
