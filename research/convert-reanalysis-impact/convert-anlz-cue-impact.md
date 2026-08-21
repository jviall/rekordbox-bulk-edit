# Convert Impact on Analysis Files, Cues, and the Content Row

## Question

What does a `convert` run invalidate across the three places rekordbox keeps a
track's analysis: the `DjmdContent` row, the `DjmdCue` rows, and the on-disk ANLZ
files (`.DAT` / `.EXT` / `.2EX`)? Convert rewrites the database row but never
updates the path inside the ANLZ files; this document scopes the real impact of
that gap.

Every claim is backed by a dump in `evidence/`, produced by the scripts in
`scripts/`, run read-only against the local rekordbox 6 library (pyrekordbox
0.4.4, 1230 tracks, 2676 ANLZ files). The in-app follow-up is
`convert-anlz-cue-impact-verification.md` (results, with evidence) and
`convert-anlz-cue-impact-test-plan.md` (procedure).

## Summary

Converting a file does not make its analysis inherently corrupt. The
load-bearing analysis (beat grid, phrases) and **all** cues are indexed by
**time**, not by sample position or byte offset, so they stay correct as long as
the conversion preserves the audio timeline. A manual test in which cues and the
beat grid survived a convert plus a database path edit is the expected result.

Four things do go stale after a convert, in descending order of how much they
matter:

1. The MP3-to-timeline question. A lossless to MP3 convert can shift the whole
   timeline by tens of milliseconds because of encoder delay, which is the one
   way to actually misalign the beat grid and cues. This needs in-app
   verification.
2. `PVB2`, a populated seek index in the `.EXT` file whose byte offsets point
   into the old file.
3. The `PPTH` path tag, which still names the old file extension.
4. `DjmdContent.FileSize`, which convert never updates (a real row-level bug).
   Convert also leaves the `Analysed` flags alone, which is most likely correct:
   it keeps rekordbox from regenerating, and possibly discarding, a hand-edited
   beat grid. See "Finding 7."

Cues are the safest part of the whole system, because on the desktop they are
database rows keyed by `ContentID` and convert does not touch them.

## Method

The `convert` code under review is `rekordbox_edit/api/convert.py`. The relevant
function is `_update_database_record`, which sets six columns on the
`DjmdContent` row and commits. It never opens an ANLZ file and never calls
pyrekordbox's `update_content_path`.

The e2e fixtures in the `Compressed` and `Lossless Only` playlists turned out to
carry **no** beat grid, cue, or waveform analysis: they are 1 to 2 second clips
and their `PQTZ` beat grids are empty (`evidence/01-inventory.txt`,
`evidence/04-anlz-deep.txt`). A write experiment on them would prove nothing
about cue or beat-grid survival, so the subjects here are real full-length
tracks, read without modification:

| Role | ID | Type | Name | Length |
| --- | --- | --- | --- | --- |
| MP3 with cues | 131718786 | 1 (MP3) | `01. Melt!.mp3` | 214 s |
| FLAC with cues | 80401918 | 5 (FLAC) | `01. NUEVAYoL - Bad Bunny.flac` | 183 s |
| AAC with cues | 211711899 | 4 (M4A) | `05 - Nigeria What-.m4a` | 233 s |

## The Three Layers and How Convert Touches Them

A rekordbox track's analysis is spread across three stores. Convert writes to
exactly one of them.

**`DjmdContent` row (master.db).** One row per track. Convert updates
`FolderPath`, `FileNameL`, `FileType`, `SampleRate`, `BitDepth`, and `BitRate`
(see `_update_database_record`). It leaves `FileSize`, `Length`, `OrgFolderPath`,
`Analysed`, and `AnalysisUpdated` untouched. `AnalysisDataPath` correctly stays
the same because the ANLZ files do not move.

**`DjmdCue` rows (master.db).** Zero or more rows per track, one per hot cue,
memory cue, or loop. Convert does not touch this table at all.

**ANLZ files (on disk).** One `.DAT`, optionally an `.EXT` and a `.2EX`, in a
per-track UUID directory under `share/PIONEER/USBANLZ`. Convert never opens
these.

So the question "what does convert break" reduces to: which facts in these three
stores depend on the audio file's encoding, name, or byte layout, and which
depend only on musical time.

## Finding 1: Cues Live in the Database, Not in the ANLZ Files

This is the single most important structural fact, and it is the reason cues
survive a convert.

The census walked every ANLZ file in the library and checked the count field of
every `PCOB` and `PCO2` cue list (`evidence/05-census.txt`):

```
contents scanned: 1230
ANLZ files scanned: 2676
contents that have DjmdCue rows: 366

ANLZ files with a NON-EMPTY PCOB/PCO2 cue list: 0
```

366 tracks have cues in the database, and **not one** ANLZ file holds a
non-empty cue list. The cue tags exist in the files, but as empty placeholders.
You can see this directly in `evidence/04-anlz-deep.txt`: the FLAC track has nine
`DjmdCue` rows yet its `.DAT` carries two `PCOB` tags of length 24, which is
header-only, and it has no `.EXT` at all:

```
=== DAT : ...\4ab\e364c-...\ANLZ0000.DAT
    PCOB  lh=24 lt=24
    PCOB  lh=24 lt=24
```

The MP3 and AAC tracks do have `.EXT` files, and there too the cue lists report
`count=0`:

```
PCO2 obj_type=hotcue count=0
PCO2 obj_type=memory count=0
```

On the desktop, hot cues, memory cues, and loops are database state. The ANLZ
cue lists only get populated when you export a track to a USB drive for a CDJ.
Because convert does not modify `DjmdCue` and does not break the `ContentID`
linkage, **cues are preserved by construction.**

The raw cue rows for the FLAC track (`evidence/02-cue-schema.txt`):

```
Kind=1 InMsec=55    InFrame=8    OutMsec=-1 ...   (hot cue A)
Kind=2 InMsec=2061  InFrame=309  OutMsec=-1 ...   (hot cue B)
Kind=3 InMsec=20837 InFrame=3125 OutMsec=-1 ...
Kind=6 InMsec=124289 InFrame=18643 OutMsec=124799 OutFrame=18719  (a loop)
```

## Finding 2: Everything Is Indexed by Time, Not by Samples or Bytes

If cue and beat positions were stored as sample indices or byte offsets, then
changing the sample rate or re-encoding would corrupt them. They are not. The
analysis uses a time base throughout, and two independent encodings agree on it.

**Cues carry the same position three times, all in time units.** `DjmdCue` has
`InMsec` (milliseconds), `InFrame` (a frame counter), and `CueMicrosec`
(microseconds). The frame counter is just milliseconds on a 150-frames-per-second
grid. Taking the FLAC track's cues and computing `floor(InMsec * 150 / 1000)`:

| `InMsec` | `floor(InMsec * 0.15)` | actual `InFrame` |
| --- | --- | --- |
| 55 | 8 | 8 |
| 2061 | 309 | 309 |
| 20837 | 3125 | 3125 |
| 22725 | 3408 | 3408 |
| 124289 | 18643 | 18643 |

The frame column is a pure function of the millisecond column. There is no
sample-rate term anywhere in it. (One frame is `1000 / 150 = 6.667` ms.)

**The MP3 byte-seek columns are dead.** `DjmdCue` also has `InMpegFrame`,
`InMpegAbs`, `InPointSeekInfo`, and `OutPointSeekInfo`, which would tie a cue to
a byte position inside an MP3. Across the whole library these are zero or null on
every row, including for MP3 and AAC sources
(`evidence/03-cue-fields-by-format.txt`):

```
===== FileType 1 (MP3) ID=131718786 name='01. Melt!.mp3' =====
  Kind=1 InMsec=187 InFrame=28 InMpegFrame=0 InMpegAbs=0 CueMicrosec=0
      InPointSeekInfo=None OutPointSeekInfo=None
```

So even for an MP3 the cue is positioned purely by time. rekordbox 6 desktop does
not depend on the byte-seek columns.

**The beat grid is stored in milliseconds.** The `PQTZ` tag's entries are
`(beat, tempo*100, time_in_ms)` (see `pyrekordbox/anlz/structs.py`,
`AnlzQuantizeTick`). The dump reports the first and last beat as absolute times,
for example the MP3's grid runs `first=0.187s last=213.623s`
(`evidence/04-anlz-deep.txt`).

**Beat grid and cues agree.** For the MP3, the first hot cue sits at
`InMsec=187` and the first beat sits at `0.187 s`. Both encodings point at the
same millisecond, which is what lets a converted file keep its grid and cues in
register as long as that millisecond still marks the same musical moment.

**Even the waveform is on the same 150 fps time grid.** The `PWV3` detail
waveform stores one byte per `1/150` second. Its entry count tracks duration, not
sample count:

```
PWV3 len_entries=32155  dur*150=32100  ratio=1.002   (MP3, 214 s)
PWV3 len_entries=34987  dur*150=34950  ratio=1.001   (AAC, 233 s)
```

`32155 / 150 = 214.4 s`, which is the true duration; the stored `Length` of 214
is just the floor. The waveform is sampled in time, so a sample-rate change does
not change how many entries it has or where they fall.

**Phrases ride on the beat grid.** The `PSSI` song-structure tag indexes phrases
by beat number, for example the MP3's `end_beat=463` against a grid of 467 beats.
Beat numbers resolve to time through `PQTZ`, so phrases inherit the beat grid's
behavior.

The consequence: a conversion that preserves the audio timeline (every musical
moment stays at the same number of seconds from the start) leaves the beat grid,
the cues, the phrases, and the time axis of the waveform all valid.

## Finding 3: What Actually Couples to the File, Name, or Bytes

Three structures are not time-based. These are the genuine staleness after a
convert.

**`PPTH`, the path tag, names the file.** It appears in every ANLZ file (`.DAT`,
`.EXT`, `.2EX`). The census shows it stores a device-relative form, `?/<name>`,
in 2676 of 2676 files, never a full OS path:

```
PPTH path forms: {'?/...': 2676}
```

For the MP3 the tag reads `?/01. Melt!.mp3` even though the database `FolderPath`
is `A:/Music/Kelly Lee Owens .../01. Melt!.mp3`. The `?` stands in for the
volume root, so the only file-specific content in `PPTH` is the name and
extension. After a convert from FLAC to AIFF, `PPTH` still says `.flac`. Its tag
length also encodes the name length (the FLAC's `PPTH` is `lt=80`, the MP3's is
`lt=48`), so a rename shifts it.

**`PVBR` is allocated but empty.** The `.DAT` carries a fixed 1620-byte `PVBR`
tag whose 400-entry index is a byte-offset seek table in principle. In this
library it is zero-filled in every file:

```
PVBR nonzero=0/400 max=0
```

So the classic VBR seek table is not a live structure in rekordbox 6 desktop.

**`PVB2` is the live seek index, and it is byte-coupled.** The `.EXT` file
carries a `PVB2` tag that pyrekordbox does not model. The census found it in 681
`.EXT` files, and its length scales with track duration, which is the signature
of a per-time byte-offset table:

```
PVB2 occurrences (first few):
 ('158539556', 5, '10-...-flac-44_1k-16b.flac', 'EXT', 432)
 ('247810405', 5, '02-flac-96k-24b.flac',       'EXT', 512)
 ('7691309',   5, '02. Do My Thing - ...flac',  'EXT', 8032)
```

The 1 to 2 second fixtures get a 432 to 512 byte `PVB2`; full tracks get about
8032 bytes. This is the one populated ANLZ structure whose contents address the
old file's bytes. After a re-encode those offsets are wrong for the new file.
Whether that produces a visible fault depends on whether rekordbox trusts the
stored index or rebuilds one on load, which this read-only study cannot settle.

**Waveforms become stale visuals.** The `PWAV`, `PWV2`, `PWV3`, `PWV4`, `PWV5`,
`PWV6`, `PWV7`, and `PWVC` tags are derived from the audio amplitude. Convert
does not regenerate them, so they keep showing the original audio. For lossless
to lossless the shape is effectively identical; for lossless to MP3 the
amplitudes differ slightly. This is cosmetic and time-aligned, not a corruption,
and rekordbox will not redraw it on its own because convert leaves the `Analysed`
flags alone (Finding 5).

## Finding 4: The Full Tag Inventory

From `evidence/05-census.txt`, tag presence by file extension across the library:

```
.DAT: PPTH, PQTZ, PVBR, PWAV, PWV2, PCOB            (1228 files)
.EXT: PPTH, PWV3, PWV4, PWV5, PCOB, PCO2, PSSI, PVB2 (725 files)
.2EX: PPTH, PWV6, PWV7, PWVC                         (723 files)
```

Classifying every tag by what it is indexed against:

| Tag / column | Store | Indexed by | Status after a timeline-preserving convert |
| --- | --- | --- | --- |
| `PQTZ` / `PQT2` beat grid | ANLZ DAT/EXT | milliseconds | Valid |
| `DjmdCue` cues and loops | master.db | ms, 1/150 s, µs | Valid (untouched, `ContentID` intact) |
| `PCOB` / `PCO2` ANLZ cue lists | ANLZ | n/a | Empty on desktop, irrelevant |
| `PSSI` phrases | ANLZ EXT | beat number | Valid through the beat grid |
| `PWAV` ... `PWVC` waveforms | ANLZ DAT/EXT/2EX | 1/150 s | Stale visual, time axis intact |
| `PPTH` path tag | ANLZ (all) | file name | Stale: still names the old extension |
| `PVBR` seek index | ANLZ DAT | byte offset | Zero-filled, so moot |
| `PVB2` seek index | ANLZ EXT | byte offset | Stale: addresses the old file |
| `FileSize` | DjmdContent | bytes | Stale: convert does not write it |
| `Analysed`, `AnalysisUpdated` | DjmdContent | flag | Unchanged: no regeneration requested |

## Finding 5: Stale Columns on the Content Row

Beyond the ANLZ files, convert leaves two database facts inconsistent
(`evidence/06-content-columns.txt`, real MP3 row):

```
FileSize        = 8596920
Analysed        = 105
AnalysisUpdated = '3'
AnalysisDataPath = '/PIONEER/USBANLZ/a90/af2bc-.../ANLZ0000.DAT'
```

`FileSize` is the byte size of the audio file. A FLAC to MP3 convert shrinks the
file by roughly an order of magnitude, but the row keeps the old size. This is a
database inconsistency independent of the ANLZ question.

`Analysed` and `AnalysisUpdated` are the flags rekordbox uses to decide whether a
track needs (re)analysis. Convert does not reset them, so rekordbox keeps the
existing waveforms and seek index rather than regenerating them against the new
file. That is the lever a future fix could pull if regeneration is the chosen
strategy.

`AnalysisDataPath` is correct as-is: the ANLZ directory does not move, so the row
should keep pointing at it. This is the one path-like column convert is right to
leave alone.

## Finding 6: What the Canonical Helper Actually Does

The issue suggests pyrekordbox's `update_content_path` as the helper convert
should use. Reading its source (`pyrekordbox/db6/database.py`) shows two things
worth knowing before adopting it.

It updates **only** the `PPTH` tag in the ANLZ files, then saves them:

```python
anlz_files = self.read_anlz_files(cid)
for anlz_path, anlz in anlz_files.items():
    anlz.set_path(path)          # PPTH only
...
cont.FolderPath = path
if cont.OrgFolderPath == old_path:
    cont.OrgFolderPath = path
cont.FileNameL = path.split("/")[-1]
```

So even the canonical helper does nothing for `PVB2`, the waveforms, or the beat
grid. It solves path staleness and nothing deeper. It does, helpfully, also fix
`OrgFolderPath` and `FileNameL`, which convert does not currently touch beyond
`FileNameL`.

Second, `set_path` writes the literal string it is given, which is the full OS
path, not rekordbox's native `?/<name>` form:

```python
def set(self, path):
    pathstr = str(path).replace("\\", "/")
    self.content.path = pathstr           # e.g. "A:/Music/.../x.aiff"
```

Calling the helper as-is would therefore put a `PPTH` value into the file that
does not match the `?/<name>` shape rekordbox writes in all 2676 files here.
Matching the native form is the safer move than adopting the helper verbatim.

## Finding 7: The Re-Analysis Flags and the Lock

A follow-up question: does convert need to touch `Analysed` and
`AnalysisUpdated` at all, and what does skipping that cost? The data says it
should not touch them, and for anyone who hand-edits beat grids it should
specifically leave them alone.

`Analysed` is not a boolean. Its value tracks how deep the analysis went, and it
lines up exactly with which ANLZ files exist (`evidence/07-analysis-flags.txt`):

```
Analysed=0   ->   2 tracks, no ANLZ           (never analyzed)
Analysed=16  -> 502 tracks, DAT only          (beat grid + preview waveform)
Analysed=105 -> 723 tracks, DAT + EXT + 2EX   (full nxs2 analysis)
Analysed=88  ->   3 tracks (rare intermediate state)
```

The values are state codes, not a clean additive bitfield (16 sets a bit that
105 does not), so the depth mapping is the reliable reading, not the arithmetic.
`AnalysisUpdated` is a separate small marker, distributed `'3': 706, '1': 511,
'2': 11, None: 2`, that does not track depth and reads as an analysis version or
mode tag. It is secondary here.

Convert leaves both alone, so a converted track keeps `Analysed=105`. To
rekordbox that means "fully analyzed," and it will not regenerate anything on its
own.

**Why skipping is correct.** The rekordbox 6.0.0 manual (page 76) describes
Analysis Lock as the feature that protects a hand-tuned grid:

> You can set a track to ignore re-analysis and editing of the beat grid. It
> prevents grid-adjusted tracks from being mistakenly overwritten. In the
> Analysis Lock mode, the following operations are not active: Track Analysis
> (BPM/Grid, key, and phrase) [and] Grid editing operations. When tracks ... are
> selected to be analyzed in a track list, analysis is skipped on tracks with
> the Analysis Lock mode.

Two things follow. Rekordbox re-analyzes only when the user asks it to (by
selecting tracks to analyze), not automatically because a file's bytes changed.
And the beat grid lives in the `.DAT` (`PQTZ`, milliseconds), which convert does
not rewrite, so a manual grid already survives a convert. The one action that
would put it at risk is convert resetting `Analysed` to invite a re-analysis. So
leaving the flags alone is the grid-preserving choice.

**What skipping costs.** Bounded, and mostly cosmetic:

- The waveform keeps showing the old audio. Indistinguishable for lossless to
  lossless, slightly off for an MP3 target. Never auto-redrawn.
- `PVB2` stays byte-stale, with the unverified seek caveat from Finding 3.
- `FileSize` stays wrong, which is a row-level fix, not a flag.

**What flipping would cost.** On any track that is not locked, a forced
re-analysis can recompute and overwrite the beat grid and BPM, the exact loss
Analysis Lock exists to prevent. That is a worse outcome than a stale waveform.

**Where the lock is stored.** No populated lock column appears in this library,
which fits a test library where nothing was locked: `DisableQuantize` is `None`
on all 1230 rows (it is the per-track quantize toggle, not the lock), and
pyrekordbox models no track-lock column. To pin it down, `scripts/row_snapshot.py`
dumps a track's full row and diffs it against the previous dump. Snapshot a
fixture, toggle its Analysis Lock in rekordbox, quit rekordbox, and snapshot
again; the changed column is the lock. Any future re-analysis policy must read
that column and skip locked tracks, exactly as rekordbox's own analyze action
does.

## Conclusions

**Does converting a file mean the ANLZ is inherently incorrect or corrupt?**
No. Nothing about a format change invalidates the beat grid, the phrases, or the
cues, because those are time-based and the ANLZ files are not even rewritten.
The earlier hands-on test confirms it.

**Are there scenarios where the analysis is effectively wrong?** Yes, three,
none of which is "the whole analysis is corrupt":

- The `PPTH` path tag is wrong after any convert, because the extension changes.
  Low functional impact (rekordbox finds the audio through `FolderPath` and the
  ANLZ through `AnalysisDataPath`), but it is a real inconsistency and could
  matter on export or to a stricter rekordbox version.
- The `PVB2` seek index is wrong after any convert, because it addresses the old
  file's bytes. This is the one populated, byte-coupled structure at risk. Its
  visible effect is unverified.
- The waveforms no longer match the new audio exactly, most visibly for a lossy
  target. Cosmetic.

**Which source and target combinations carry real risk?** The deciding factor is
whether the conversion preserves the start of audio and the time axis.

- Lossless to lossless at the same rate and depth (FLAC 44.1/16 to AIFF or WAV)
  is sample-accurate. The timeline is identical and the beat grid and cues stay
  perfectly aligned. Only `PPTH`, `PVB2`, and `FileSize` go stale. This is the
  case the manual test exercised.
- Hi-res lossless down to 16/44.1 (FLAC or WAV 96/24 to 44.1/16) preserves the
  time axis in seconds, because resampling changes sample count, not duration.
  The beat grid and cues stay aligned. Same staleness as above.
- Lossless to MP3 (320 CBR) is the higher-risk case. LAME encoding prepends
  encoder delay and padding. If rekordbox honors the LAME gapless header the
  timeline is preserved; if it does not, the entire track shifts by roughly 20 to
  50 ms (about 1100 to 2250 samples at 44.1 kHz) and every beat and cue lands
  early by that amount. This is the only path that can misalign cues and the beat
  grid, and it needs verifying in the app. CBR output keeps byte seeking linearly
  computable, which softens the `PVB2` concern for this target.

**How do conversions impact cues?** Less than any other part of the system. Cues
are database rows keyed by `ContentID`, positioned in time, and convert neither
moves nor rewrites them. The only way to disturb them is to shift the audio
timeline itself, which only the MP3 path threatens.

## Remediation (Deferred)

Scope of a future fix:

- Rewrite `PPTH` in all three ANLZ files to the new name, in rekordbox's native
  `?/<name>` form rather than the full-path form `set_path` produces. The
  canonical helper updates only `PPTH`, so the rest of this list stands
  regardless of whether the helper is used.
- Default to leaving `Analysed` and `AnalysisUpdated` untouched, which preserves
  manual beat grids (Finding 7). The stale waveform and `PVB2` are the price, and
  it is a cheap one. If refreshing them is ever offered, make it opt-in and have
  it skip any track whose Analysis Lock column is set, mirroring rekordbox.
- Update `DjmdContent.FileSize`, and `OrgFolderPath` when it matched the old
  path, alongside the columns convert already writes.

## Open Questions (In-App Verification)

These cannot be answered read-only and require a controlled test in rekordbox
itself, ideally on copies in the `Compressed` and `Lossless Only` playlists:

1. Does a lossless to MP3 convert shift the beat grid and cues? This is the
   gapless-delay question and the highest-value test.
2. Does rekordbox use the stored `PVB2` index, or rebuild a seek table, when it
   reopens a re-encoded file?
3. Does a stale `PPTH` cause any user-visible problem, or only an export-time
   inconsistency?
4. Does rekordbox ever re-analyze a track on its own when the on-disk file
   changes but `Analysed` stays 105, or only when the user requests it? The
   manual implies only on request.
5. Which `DjmdContent` column records Analysis Lock? Find it with
   `row_snapshot.py` (Finding 7), so a future re-analysis policy can respect it.

## Sources and Cross-Check

The binary layouts come from reading pyrekordbox's implementation directly
(`anlz/structs.py`, `anlz/tags.py`, `anlz/file.py`) and its `update_content_path`
source, then validating against live files. The pyrekordbox ANLZ format
reference (`pyrekordbox.readthedocs.io/en/latest/formats/anlz.html`), which builds
on Deep Symmetry's export analysis, agrees with the empirical findings on every
modeled tag:

- `PVBR`: "an index allowing rapid seeking to particular times within
  variable-bit-rate tracks," 400 unsigned 32-bit frame indices, and entries
  "often all zeros." This matches the all-zero `PVBR` found in every file here.
- `PQTZ`: beat number, BPM times 100, and "time ... in milliseconds." Time-based.
- `PCOB` / `PCO2`: each cue "records the position of the cue within the track, as
  a number of milliseconds." Time-based.
- `PWV3` / `PWV5`: "75 frames per second, so ... 150 waveform detail entries" per
  second. This is the `0x96` constant and the `len ~= dur x 150` ratios above.
- `PSSI`: phrases at beat-based positions.

Two claims go beyond that reference. `PVB2` is not modeled by pyrekordbox and is
not in the format docs; its role as a byte-coupled seek index is inferred here
from its presence only in `.EXT` files and its length scaling with duration, not
from documentation. The `?/<name>` shape of `PPTH` is an empirical observation
from this library; the docs describe the tag generically as the audio file path.
The Analysis Lock behavior is quoted from the rekordbox 6.0.0 manual, page 76.

## Reproduction

The scripts in `scripts/` are read-only against the local library. Each writes
its dump to the matching file in `evidence/`:

| Script | Evidence | What it shows |
| --- | --- | --- |
| `inventory.py` | `01-inventory.txt` | The fixture playlists and their columns |
| `cue_schema.py` | `02-cue-schema.txt` | `DjmdCue` columns and the richest cue tracks |
| `cue_fields_by_format.py` | `03-cue-fields-by-format.txt` | Cue seek fields per source format |
| `anlz_deep.py` | `04-anlz-deep.txt` | Raw tag walk plus parsed beat grid, cues, waveforms |
| `anlz_census.py` | `05-census.txt` | Library-wide tag census and the cue-emptiness proof |
| `content_columns.py` | `06-content-columns.txt` | Which `DjmdContent` columns convert leaves stale |
| `analysis_flags.py` | `07-analysis-flags.txt` | `Analysed` / `AnalysisUpdated` meaning and the lock search |
| `row_snapshot.py` | (interactive) | Diff a content row before/after a rekordbox change to locate the lock column |

Run, for example, `uv run python research/convert-reanalysis-impact/scripts/anlz_census.py`.
