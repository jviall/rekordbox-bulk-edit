# The DjmdContent Row Rekordbox Writes for an Un-Analyzed Import: Findings

## Question

What does a `DjmdContent` row look like immediately after rekordbox imports a
track, before any analysis runs? The answer grounds the `import` command, which
creates rows for files rekordbox does not yet know about and cannot analyze.

Three sub-questions follow from it. Which columns does rekordbox fill from the
file and its tags, and which does it leave for analysis? Which columns does it
write as an empty value rather than NULL? And is `pyrekordbox.add_content` a
faithful enough row factory to build on?

## Method

Two libraries were sampled, both read-only from copies:

- **`gig`** — a device master database at
  `/Volumes/Gig Music/PIONEER/Master/master.db`, 924 tracks.
- **`local`** — the local library at `~/Library/Pioneer/rekordbox/master.db`,
  18 tracks.

The `gig` library is the load-bearing sample. It contains 906 tracks that
rekordbox imported by scanning a folder and never analyzed, identified by
`Analysed = 0` and an empty `AnalysisDataPath`. Their provenance is rekordbox
rather than a third-party tool: `rb_local_usn` runs sequentially from 969 to
2694, the top of that range equals the library's `localUpdateCount`, and
`DateCreated` preserves 2022 file dates against a 2026 `created_at`.

The `local` library contributed only the `SearchStr` and extension censuses; all
18 of its tracks are analyzed, so it holds no import-shaped rows.

Scripts are in `scripts/`, evidence in `evidence/`:

| Script                        | Evidence                              |
| ----------------------------- | ------------------------------------- |
| `import_row_shape.py`         | `import-row-shape-gig.json`           |
| `column_coverage.py`          | `column-coverage-gig.json`            |
| `tag_key_mapping.py`          | `tag-key-mapping-gig.json`            |
| `datecreated_source.py`       | `datecreated-source-gig.json`         |
| `filetype_and_searchstr.py`   | `filetype-searchstr-{gig,local}.json` |

A third source corroborates the census. The `convert-reanalysis-impact`
investigation captured a track at `Analysed = 0` and again after a Normal
analysis, which is a direct before-and-after observation of the same boundary:

```
research/convert-reanalysis-impact/evidence/subject-27790898-00-zero.json
research/convert-reanalysis-impact/evidence/subject-27790898-normal-01.json
```

That pair comes from a different machine, with a different `DeviceID`,
`MasterDBID`, and a Windows path, so it replicates the census independently
rather than restating it. It is cited below as the **zero-to-normal diff**.

## Findings

### Rekordbox Fills Tags and Duration, Not Audio Characteristics

Of the 906 un-analyzed rows, every one carries `FileType`, `FileSize`, and
`Length`, and their tag-derived columns vary across the sample:

| Column        | Populated  | Note                                   |
| ------------- | ---------- | -------------------------------------- |
| `Title`       | 906/906    | 881 distinct                           |
| `ArtistID`    | 906/906    | 259 distinct artists                   |
| `AlbumID`     | 906/906    | 303 distinct albums                    |
| `Length`      | 906/906    | seconds, 331 distinct                  |
| `KeyID`       | 861/906    | from the tag; `'0'` on the other 45    |
| `TrackNo`     | 905/906    | —                                      |
| `ReleaseYear` | 905/906    | —                                      |
| `ISRC`        | 623/906    | —                                      |
| `GenreID`     | 222/906    | tag-dependent                          |
| `ComposerID`  | 280/906    | tag-dependent                          |
| `Commnt`      | 92/906     | tag-dependent                          |
| `DiscNo`      | 37/906     | 0 on the rest                          |
| `LabelID`     | 4/906      | tag-dependent                          |

`SampleRate`, `BitRate`, `BitDepth`, and `BPM` are **0 on all 906 rows**.
Rekordbox reads a file's duration at import but not its audio characteristics;
those arrive with analysis. `Analysed` is 0, `AnalysisDataPath` is `''`, and
`AnalysisUpdated`, `TrackInfoUpdated`, and `CueUpdated` are NULL.

An `import` command therefore has no reason to probe audio. Tag and header reads
alone reproduce the import shape, which also keeps the command fast over large
directories.

### The Import and Analysis Boundary Is Exact

The zero-to-normal diff isolates which columns analysis owns. Eleven changed,
of which two are bookkeeping (`rb_local_usn`, `updated_at`):

| Column             | At import | After a Normal analysis          |
| ------------------ | --------- | -------------------------------- |
| `Analysed`         | `0`       | `105`                            |
| `AnalysisDataPath` | `''`      | the `ANLZ0000.DAT` path          |
| `AnalysisUpdated`  | NULL      | `'10'`                           |
| `TrackInfoUpdated` | NULL      | `'10'`                           |
| `BPM`              | `0`       | `13000`                          |
| `SampleRate`       | `0`       | `44100`                          |
| `BitDepth`         | `0`       | `16`                             |
| `KeyID`            | `'0'`     | a real `DjmdKey` ID              |
| `ContentLink`      | `14`      | `853518`                         |

Every other column held its import value, including `Title`, `ArtistID`,
`AlbumID`, `ComposerID`, `ISRC`, `ReleaseYear`, `TrackNo`, `Length`, `FileSize`,
`FileType`, `DateCreated`, `StockDate`, and the empty-value constants.

Three details follow that the census alone could not establish.

**`BitRate` is not analysis-filled.** It starts at 0 and stays 0 through
analysis on this FLAC track, consistent with rekordbox storing FLAC bitrate as 0
for variable-rate audio, which `_sync_audio_columns` already encodes.

**`ContentLink` is rewritten by analysis.** The `14` an import writes is the
TRACK menu item's `rb_local_usn`. Analysis replaces it with a large per-track
value. This explains the split in the `gig` library, where the 906 imported rows
hold 14 while the 18 analyzed rows hold 787982, 2950670, and 2885134. An `import`
command writes 14 and is correct to do so.

**Analysis does not run on its own.** The `convert-reanalysis-impact` findings
establish that rekordbox re-analyzes only when the user selects tracks for
analysis, never automatically because a file changed. A row an `import` command
creates therefore keeps `SampleRate`, `BitDepth`, and `BPM` at 0 until the user
analyzes it. That matches what rekordbox's own import leaves behind, and the 906
rows in this sample have sat that way since 2026-08-21.

### KeyID Comes From the Tag, and `'0'` Means No Key

`KeyID` is never NULL on an imported row. It is `'0'` when rekordbox found no
key, and a real `DjmdKey` foreign key when it did: 861 of 906 rows carry a key,
45 carry `'0'`.

Six files were checked directly against their tags:

| File's key tag                             | `KeyID` written |
| ------------------------------------------ | --------------- |
| `initialkey` = `G#m`, `Cm`, `Am`           | matching key, 3/3 |
| no key tag (2 files)                       | `'0'`           |
| `----:com.apple.iTunes:initialkey` = `Dm`  | `'0'`           |

Rekordbox reads the standard `initialkey` tag and ignores the iTunes freeform
MP4 atom, leaving a key that is present in the file unread.

Reproducing an import means reading the standard tag and falling back to `'0'`.
The freeform atom is the trap: a tag library's normalized key lookup surfaces
it, and honoring it would populate a key rekordbox deliberately leaves empty.
A faithful reader consults the standard `initialkey` tag only.

### Complete Column Coverage

`column_coverage.py` classifies all 78 `DjmdContent` columns by what fills them
at import, leaving none unclassified (`column-coverage-gig.json`):

| Kind                | Count | Columns                                                                                                          |
| ------------------- | ----- | ---------------------------------------------------------------------------------------------------------------- |
| `tag`               | 13    | `Title`, `ArtistID`, `AlbumID`, `GenreID`, `ComposerID`, `LabelID`, `TrackNo`, `DiscNo`, `ReleaseYear`, `Commnt`, `ISRC`, `Length`, `FileType` |
| `tag_then_analysis` | 1     | `KeyID`                                                                                                            |
| `file_stat`         | 1     | `DateCreated`                                                                                                      |
| `identity`          | 10    | `ID`, `UUID`, `rb_file_id`, `MasterSongID`, `DeviceID`, `MasterDBID`, `FolderPath`, `FileNameL`, `FileSize`, `StockDate` |
| `empty_constant`    | 26    | see the section below                                                                                              |
| `null_constant`     | 15    | see the section below                                                                                              |
| `analysis`          | 8     | `Analysed`, `AnalysisDataPath`, `AnalysisUpdated`, `TrackInfoUpdated`, `BPM`, `SampleRate`, `BitDepth`, `ContentLink` |
| `bookkeeping`       | 4     | `created_at`, `updated_at`, `rb_local_usn`, `usn`                                                                  |

Fourteen columns are therefore read from the file at import: the thirteen `tag`
columns plus `KeyID`. Reproducing an import means writing all fourteen.

**Relational targets.** Five of those columns are foreign keys needing a
get-or-create: `ArtistID` and `ComposerID` into `DjmdArtist`, `AlbumID` into
`DjmdAlbum`, `GenreID` into `DjmdGenre`, and `LabelID` into `DjmdLabel`.
`pyrekordbox` supplies `add_artist`, `add_album`, `add_genre`, and `add_label`
for these.

**`KeyID` is a lookup, never a create.** There is no `add_key` helper, and
`DjmdKey` holds a fixed set of 25 rows, every one of which this library uses:

```
A  Ab  Abm  Am  B  Bb  Bbm  Bm  C  C#m  Cm  D  Db
Dm  E  Eb  Ebm  Em  F  F#m  Fm  G  G#m  Gb  Gm
```

The set is enharmonically specific: it holds `C#m` but not `Dbm`, and `Gb` but
not `F#`. A tag naming the other spelling has no matching row. Matching an
existing `ScaleName` and falling back to `'0'` is the conservative reading;
whether rekordbox normalizes enharmonic spellings was not tested.

### Which Tag Key Rekordbox Reads, Per Format

A tag library's normalized interface cannot express this mapping. Mutagen's
`easy` mode supports `isrc` and `composer` for ID3 but not `comment`, and
supports `comment` for MP4 but neither `isrc` nor `composer`. No format exposes
`initialkey`. Reading tags through that interface would silently drop columns
rekordbox fills.

`tag_key_mapping.py` recovers the real mapping by comparing each stored column
against every raw tag in the file (`tag-key-mapping-gig.json`). Counts are the
number of files where the tag's value equals the stored value:

| Column       | Vorbis (FLAC)                   | ID3 (MP3)           | MP4 (m4a)              |
| ------------ | ------------------------------- | ------------------- | ---------------------- |
| `Title`      | `title` (794)                   | `TIT2` (91)         | `©nam` (21)            |
| `ArtistID`   | `artist` (794)                  | `TPE1` (91)         | `©ART` (21)            |
| `AlbumID`    | `album` (794)                   | `TALB` (91)         | `©alb` (21)            |
| `GenreID`    | `genre` (126)                   | `TCON` (75)         | `©gen` (21)            |
| `ComposerID` | `composer` (259)                | `TCOM` (2)          | `©wrt` (19)            |
| `LabelID`    | `label` (2), `organization` (1) | `TPUB` (1)          | not observed           |
| `ISRC`       | `isrc` (600)                    | `TSRC` (4)          | `xid ` (19), see below |
| `Commnt`     | `comment` (47), `description` (7) | `COMM` (43)       | `©cmt` (3)             |
| `KeyID`      | `initialkey` (770)              | `TKEY` (91)         | **ignored**            |

Two entries need explanation.

**MP4 ISRC is wrapped.** The `xid ` atom holds `<vendor>:isrc:<value>`, for
example `Universal:isrc:USQY51374467`. Rekordbox extracts the ISRC from it, so
a reader must parse the atom rather than take it whole.

**MP4 keys are ignored, conclusively.** All 21 `.m4a` files in the library carry
`----:com.apple.iTunes:initialkey` with a real key, and rekordbox left `KeyID`
at `'0'` for every one. A tag present while its column stays empty is proof of
an ignored tag, not an absent one.

The method produces coincidental matches alongside real ones: `AlbumID <- title`
appears 47 times because those tracks name the album and the title identically,
and binary tags such as `APIC` and `serato_overview` match short key strings by
substring. The primary source for each column is the semantically sensible key
with the highest count.

### Limits of the Constant Classification

A column constant across this sample is not proven to be one rekordbox always
writes empty. It may be a column rekordbox would fill from a tag that no sampled
file carries. All 906 files were scanned for the tags that would populate the
empty columns, and none carry `remixer`, `subtitle`, `lyricist`, `writer`, or
`originalartist` tags. `RemixerID`, `Subtitle`, `Lyricist`, and `OrgArtistID`
are therefore **untested**, not confirmed as ignored.

`ReleaseDate` is the exception, and it is confirmed. Twenty-five of the files
carry a full `YYYY-MM-DD` date tag, and rekordbox wrote `ReleaseDate = ''` for
every one while taking `ReleaseYear` from that same tag. Rekordbox discards the
month and day deliberately.

### Rekordbox Writes Empty Values, Not NULL

Forty-one columns hold the same literal on all 906 rows. These are rekordbox's
"no value" idiom, and a row that leaves them NULL is distinguishable from one
rekordbox wrote:

```
FileNameS=''         OrgFolderPath=''      ImagePath=''
Subtitle=''          ReleaseDate=''        ModifiedByRBM=''
DeliveryComment=''   Lyricist=''           Reserved1=''
ColorID='0'          VideoAssociate='0'    ExtInfo='null'
HotCueAutoLoad='on'  DeliveryControl='on'  AnalysisDataPath=''
Rating=0             DiscNo=0              DJPlayCount=0
BPM=0                SampleRate=0          BitRate=0
BitDepth=0           Analysed=0            LyricStatus=0
ServiceID=0          SamplerTrackInfo=0    SamplerPlayOffset=0
SamplerGain=0.0      rb_data_status=0      rb_local_data_status=0
rb_local_deleted=0   rb_local_synced=0
```

`KeyID='0'` belongs with these, per the section above.

The remaining constants are genuinely NULL: `SearchStr`, `Tag`, `CueUpdated`,
`AnalysisUpdated`, `TrackInfoUpdated`, `DisableQuantize`, `RemixerID`,
`OrgArtistID`, `rb_LocalFolderPath`, `usn`, `Reserved2` through `Reserved4`, and
the five `Src*` columns.

Three further constants are properties of the sampled environment rather than
literals to copy: `StockDate` (the import date), `MasterDBID`, and `DeviceID`.

### SearchStr Is Never Populated

`SearchStr` is NULL on every row of every table checked, across both libraries:

| Table         | `gig` rows | `local` rows | Populated |
| ------------- | ---------- | ------------ | --------- |
| `DjmdContent` | 924        | 18           | 0         |
| `DjmdArtist`  | 483        | 10           | 0         |
| `DjmdAlbum`   | 310        | 7            | 0         |

No observed value exists to imitate. A tool writing this column would be
inventing a format rather than matching rekordbox.

### File Extension Cannot Determine FileType

`.m4a` maps to two `FileType` codes in both libraries, splitting on the codec
inside the MP4 container:

| Extension | Codes observed        | `gig`        | `local`     |
| --------- | --------------------- | ------------ | ----------- |
| `.m4a`    | 4 (AAC), 6 (ALAC)     | 20 and 4     | 1 and 2     |
| `.flac`   | 5                     | 797          | 3           |
| `.mp3`    | 1                     | 93           | 2           |
| `.wav`    | 11                    | 9            | 9           |
| `.aiff`   | 12                    | 1            | 1           |

Typing a file by suffix mislabels ALAC as AAC. The codec must be read from the
file.

### DateCreated Comes From the File's Birth Time

All 906 rows were compared against their files on the mounted volume:

| Match                     | Count |
| ------------------------- | ----- |
| `st_birthtime` only       | 888   |
| both (birthtime == mtime) | 18    |
| `st_mtime` only           | 0     |
| neither                   | 0     |

`DateCreated` equals the file's birth time on 906 of 906 rows and never mtime
alone. Rekordbox copies the file's creation date; it does not stamp the import
date. `StockDate` carries the import date instead.

`st_birthtime` is available on macOS and BSD only, so a portable implementation
needs a fallback.

### pyrekordbox.add_content Is a Sound Row Factory With Two Wrong Values

What it gets right, confirmed against the sample: `ID` and `rb_file_id` through
`generate_unused_id`, `UUID`, `DeviceID` and `MasterDBID` from the device row,
`MasterSongID`, `FileNameL`, `FileSize`, `HotCueAutoLoad='on'`, `StockDate` as
today's date, and `ContentLink` from the TRACK menu item's `rb_local_usn`, which
is 14 in this library and matches all 906 rows.

What it gets wrong:

- **`FileType`** is derived from the file suffix, and its enum maps `M4A = 4`
  unconditionally, so it never produces ALAC's 6. An unmapped suffix such as
  `.aac` reaches `getattr`, which raises `AttributeError` while the surrounding
  handler catches only `ValueError`.
- **`DateCreated`** is set to today rather than the file's birth time.

It also leaves roughly twenty columns NULL that rekordbox writes as `''` or `0`,
and reads no tags at all.

Neither wrong value can be corrected through its `**kwargs`. `add_content`
passes `FileType`, `DateCreated`, and `FolderPath` positionally into
`DjmdContent.create()` ahead of `**kwargs`, so supplying them as keyword
arguments raises `TypeError: got multiple values for keyword argument`.
Corrections must be applied to the returned object before the commit.

### Stored Paths Do Not Match the Filesystem's Case

The 906 rows record paths under `/Volumes/GIG MUSIC/Contents/`, while the volume
mounts at `/Volumes/Gig Music`. `Path.resolve()` does not correct case on macOS,
so an exact string comparison against `FolderPath` would fail to recognize a
track already in the library and would insert a duplicate row.

This compounds a known separate discrepancy already documented in the e2e
fixtures: rekordbox stores the symlink-resolved form of a path, recording
`/private/tmp` where the user typed `/tmp`.

## Conclusion

An `import` command reproduces the import shape by reading tags and the stream
header, never by probing or analyzing audio. It writes `Title`, artist, album,
genre, composer, `TrackNo`, `DiscNo`, `ReleaseYear`, `Commnt`, `ISRC`, and
`Length` from the file; leaves `SampleRate`, `BitRate`, `BitDepth`, `BPM`, and
`Analysed` at 0 for analysis to fill; and writes rekordbox's empty-value literals
across the forty-one constant columns rather than leaving them NULL. `SearchStr`
stays NULL.

`add_content` is worth building on for identity and device linkage, with
`FileType` and `DateCreated` corrected on the returned object and file
extensions validated before the call.

Deduplication compares symlink-resolved, case-folded paths against `FolderPath`.
Both normalizations are required, and each is justified by a discrepancy
observed in a real library.

Reproducing an import means writing all fourteen file-derived columns, not a
subset: the thirteen `tag` columns plus `KeyID`. Five are foreign keys needing a
get-or-create into `DjmdArtist` (twice, for artist and composer), `DjmdAlbum`,
`DjmdGenre`, and `DjmdLabel`. `KeyID` is a lookup against the fixed 25-row
`DjmdKey` table, falling back to `'0'`.

Reading those tags requires the per-format key mapping above, not a tag
library's normalized interface, which does not cover `initialkey` at all and
covers `isrc` and `comment` inconsistently across formats. Three specific
cautions: rekordbox ignores the MP4 freeform key atom, extracts MP4 ISRC from
inside the `xid ` atom's `<vendor>:isrc:<value>` form, and takes only the year
from a date tag, leaving `ReleaseDate` empty even when the tag carries a full
date.

Related decision record: `decisions/commit-semantics-and-usn.md`.
