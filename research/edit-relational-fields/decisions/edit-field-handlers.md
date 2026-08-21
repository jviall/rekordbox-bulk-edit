# Edit Field Handlers

How the `edit` command should support fields beyond `Title` (issue #17), starting
with `ArtistName`, `AlbumName`, `Comment`, and `Rating`.

Status: settled. The relational behavior was confirmed empirically in
`../edit-relational-fields.md` (experiments E1–E4). Two provisional
choices changed as a result: orphan cleanup moved from deferred to in scope, and
the album-artist blanking rekordbox performs is a deliberate non-mirror.

## Context

The initial `edit` implementation carries a flat `FIELD_COLUMNS = {name: column}`
map and applies every edit with a generic `getattr`/`setattr` against a
`DjmdContent` column. That holds for `Title`, but the four new fields span three
distinct behaviors that a single column write cannot cover:

- **Plain string column.** `Comment` maps to the misspelled `Commnt` column;
  otherwise it behaves exactly like `Title`, including `--match` find/replace.
- **Encoded integer column.** `Rating` is an `Integer` column, but rekordbox
  stores it as `0/51/102/153/204/255` (0–5 stars times 51, per pyrekordbox's
  `RATING_MAPPING`). It needs range validation and star-to-internal conversion,
  and `--match` substring replace is meaningless for it.
- **Relational name.** `ArtistName` and `AlbumName` are not columns. They are
  SQLAlchemy `association_proxy` fields reading through `ArtistID`/`AlbumID` into
  the shared `DjmdArtist`/`DjmdAlbum` tables. A plain `setattr` would rename the
  shared record for every referencing track, or fail on a null relation.

A `DjmdArtist` row is referenced from six foreign keys (`DjmdContent.ArtistID`,
`RemixerID`, `OrgArtistID`, `ComposerID`, `Lyricist`, and `DjmdAlbum`.
`AlbumArtistID`), so "the last track stopped referencing this artist" does not by
itself prove the record is unreferenced.

## Decision

**Field-handler registry (Approach A).** Replace the flat `FIELD_COLUMNS` map with
a registry of per-field handlers. Each handler declares the column it reads for
comparison, whether it supports `--match`, how it parses and validates an input
value into a stored value, and how it applies the write. `_classify_edit` and
`edit` dispatch through the handler instead of a generic `getattr`/`setattr`.

This isolates each field's quirks into its own testable unit and scales to the
fields issue #17 will keep adding (Genre, Label, Composer are relational; Year and
BPM are encoded ints). It matches the repo's "small testable units" and
"consistency of patterns" conventions.

Settled behaviors:

- **Comment.** String handler over the `Commnt` column. Supports `--match`.
- **Rating.** Accepts `--replace 0..5`, validates the range, converts to the
  internal 51x value. If `--match` is passed, ignore it and warn (do not error).
- **Artist / Album.** Get-or-create the shared record by exact name, then repoint
  the track's `ArtistID`/`AlbumID`. Other tracks referencing the old record are
  left untouched, and the record keeps its name (rekordbox reassigns the track, it
  does not rename the shared record: E1). Album identity keys on name alone, not
  `(Name, AlbumArtist)` (E3). A cleared value (`--replace ""`) sets the foreign key
  to `''`, the empty string rekordbox writes, not NULL (E4/E3b).
- **Orphan cleanup is in scope.** Rekordbox hard-deletes an artist or album the
  moment its last reference leaves (E2, E4), so the handler mirrors that: after
  relinking, if the vacated record has no remaining reference, delete it. An artist
  is unreferenced only when no row points at it across all six artist foreign keys
  (`DjmdContent.ArtistID`, `RemixerID`, `OrgArtistID`, `ComposerID`, `Lyricist`,
  and `DjmdAlbum.AlbumArtistID`); an album, when no `DjmdContent.AlbumID` points at
  it.
- **Do not populate `SearchStr` on created records.** Rekordbox leaves it NULL on
  the inline path (E3b), so `add_artist`/`add_album` should not fabricate one.

## Deliberate divergence from rekordbox

Rekordbox's inline album edit **blanks the reused album's `AlbumArtistID`** to `''`
(E2, E3), which strips the album-artist from every other track on that album. That
is destructive to shared data, so the command does **not** mirror it: it reuses the
album by name and leaves the existing `AlbumArtistID` untouched. This is the one
intentional behavioral difference from the desktop app, made to avoid damaging
tracks the user did not edit.

## Alternatives rejected

- **Special-case branches.** Keep `FIELD_COLUMNS`, add `if field == "Rating"` /
  `if field in (Artist, Album)` branches inside `_classify_edit` and `edit`. Least
  code now, but fragments each field's logic across two functions and worsens with
  every field added. Conflicts with the repo's factoring conventions.
- **Middle ground.** Simple `getattr`/`setattr` for string fields, with a writer
  and input-transform hook bolted on only for Rating and the relational fields.
  Leaves two parallel models of "how an edit works," the inconsistency the
  registry is meant to avoid.
- **Rename the shared record** for artist/album edits. Simpler, but a bulk side
  effect that changes every track sharing the artist/album, easy to trigger by
  accident. Rejected in favor of reassignment.
