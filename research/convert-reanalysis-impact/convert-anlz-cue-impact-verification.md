# Convert Impact: In-App Verification Findings

## Question

The read-only study in `convert-anlz-cue-impact.md` reasoned from the binary
formats that convert rewrites only the `DjmdContent` row and that the beat grid and
cues are time-based, and left open questions it could not answer without running
rekordbox. This document records what real conversions did when driven through the
`rbe convert` CLI against purpose-built fixtures and inspected at every step.

Every claim cites a snapshot in `evidence/` produced by
`../shared/scripts/subject_snapshot.py`; compare any two with
`../shared/scripts/subject_diff.py <id> <stageA> <stageB>`. Results are a small
number of single trials, so "Caveats and Gaps" is part of the finding. The full
procedure and revert protocol are in `convert-anlz-cue-impact-test-plan.md`. The
remaining gaps are closed by `convert-anlz-cue-impact-experiment2.md` (results)
and `convert-anlz-cue-impact-experiment2-plan.md` (procedure): analysis
determinism, the zero-to-analyzed transition, the analysis modes, `PVB2` origin,
and drift magnitude.

## Summary

Convert is safe in isolation and the MP3 path has no gap. Across all five
conversions, convert changed only the `DjmdContent` row; cues and every ANLZ tag
held byte-for-byte. The MP3 output is sample-accurate against its source, so
there is no encoder-delay shift for a compliant decoder. Analysis Lock turned out
to live in bit `0x80` of the `Analysed` column, so convert can detect a locked
track and already preserves the lock.

The real risk is re-analysis, not conversion. Re-analysis is the only step that
moves a grid, changes detected BPM or key, or overwrites a hand-tuned grid. On a
lossy or resampled file it produces a measurably different grid, while on a
bit-identical file it reproduced the grid exactly. Two database bugs surfaced
along the way: `FileSize` stays stale after every conversion, and convert writes
mixed path separators into `FolderPath`.

## Method

Three real tracks from the `ConvertTest` playlist, each decoded from its 24-bit
FLAC to a non-compressed WAV so it could serve as a convert source (FLAC cannot be
a source for the "to FLAC" case, and the cases all start non-compressed). All
three were analyzed in rekordbox in High Precision mode, reaching `Analysed=105`.

| Fixture | ContentID | Source | Baseline grid | Cues | Baseline snapshot |
| --- | --- | --- | --- | --- | --- |
| A VUGUVUGUU | 205795680 | WAV 16/44.1 | first 0.422 s, 465 beats, 127.0 BPM | 6 | `subject-205795680-00-baseline.json` |
| B Vuelve | 205157376 | WAV 24/48 | first 0.055 s, 384 beats, 110.41 BPM | 4 | `subject-205157376-00-baseline.json` |
| C/D FodanCia | 230928195 | WAV 24/44.1 | first 0.008 s, 295 beats, 94.95 BPM (manual) | 5 | `subject-230928195-00-baseline.json` |

Each run snapshots the `DjmdContent` row, every `DjmdCue` row, and per ANLZ file a
raw tag walk with a SHA-1 of each tag's bytes plus a parsed grid and cue summary.
The per-tag hash is what makes "convert did not touch the ANLZ" and "re-analysis
rewrote it" provable without reading binary. Between runs the fixtures were
restored to baseline from `A:/rb-convert-test-backup/` via `restore_fixtures.sh`.

## Finding 1: Convert Touches Only the Content Row

All five conversions were run from the clean baseline, snapshotted, and diffed.
The result is uniform: the `DjmdContent` row changes, `updated_at` bumps, and
nothing else moves. Cue rows are byte-identical and every ANLZ tag SHA-1 holds
across `.DAT`, `.EXT`, and `.2EX`.

| Conversion | Row columns changed | Evidence (post-convert) |
| --- | --- | --- |
| A → AIFF (same 16/44.1) | FolderPath, FileNameL, FileType 11→12 | `subject-205795680-aiff-postconv.json` |
| A → FLAC | + BitRate 1411→0 | `subject-205795680-flac-postconv.json` |
| A → MP3 320 | + BitRate→320, FileType→1 (BitDepth stays 16) | `subject-205795680-mp3-postconv.json` |
| B → AIFF (downsample) | + SampleRate 48000→44100, BitDepth 24→16, BitRate | `subject-205157376-aiff-postconv.json` |
| C/D → MP3 320 | FileType→1, BitRate→320, BitDepth 24→16 | `subject-230928195-mp3-postconv.json` |

Reproduce, for example: `subject_diff.py 205795680 00-baseline aiff-postconv`. The
ANLZ section reads "no change in any ANLZ file" and the cue section "no change" for
every one of these.

## Finding 2: FileSize Stays Stale After Every Conversion

The `DjmdContent.FileSize` column keeps the source WAV's size after conversion,
even for MP3 where the real file is a fraction of it. Fixture A's row reports
`38758630` (the WAV) across the AIFF, FLAC, and MP3 post-convert snapshots, while
the actual files differ. This reproduces the research's row-level bug on every
path and is independent of the ANLZ question.

## Finding 3: Convert Writes Mixed Path Separators (New Bug)

Baseline `FolderPath` is rekordbox-native all-forward-slash, for example
`A:/Music/_ConvertTest/VUGUVUGUU.wav`. After conversion the same column reads
`A:\Music\_ConvertTest/VUGUVUGUU.aiff`: backslashes for the directory and a
forward slash before the filename (`subject-205795680-aiff-postconv.json`).
`_update_database_record` joins an `os.path.dirname` result, which carries
Windows backslashes, with `posixpath.join`. The in-app tolerance of this form was
not tested, but it deviates from how rekordbox stores paths.

## Finding 4: The MP3 Has No Encoder-Delay Gap

Decoding the converted MP3 and the original WAV to PCM and cross-correlating them
gives identical sample counts (9,689,606 each) and a best lag of 0 samples. The
MP3 is sample-accurate against its source, so a compliant decoder recovers the
exact timeline with no leading offset. The convert tool's MP3 needs no
LAME-specific gapless change for such decoders.

The Xing/Info header carries the gapless metadata correctly: encoder delay 576
samples (13.1 ms) and padding 1594 samples (36.1 ms), at the LAME-extension
offset. The catch is the 9-byte encoder signature, which reads `Lavc62.28` rather
than `LAME`, with no `iTunSMPB` present. A decoder that reads the extension by
offset compensates; one that requires the literal `LAME` signature would ignore
the fields. rekordbox's behavior is addressed in Finding 7: its MP3 re-analysis
anchored the grid earlier, not later, which is the opposite of an uncompensated
delay, so it does not appear to play the delay as leading silence.

## Finding 5: Stale PPTH Is Harmless, and Rekordbox Does Not Self-Re-Analyze

Opening the converted AIFF without analyzing it (`subject-205795680-aiff-postopen.json`):
the track played with no error, all 6 cues in place, the waveform normal, and no
re-analyze prompt. The snapshot shows the ANLZ byte-identical to baseline and
`PPTH` still naming the old `.wav`.

- **Q3 (stale `PPTH`)**: harmless on desktop. Playback, cues, and the waveform all
  work while `PPTH` names the wrong extension. rekordbox reaches the audio through
  `FolderPath` and the ANLZ through `AnalysisDataPath`.
- **Q4 (self-re-analysis)**: it does not happen. A changed file with `Analysed=105`
  is left untouched until the user asks. `subject_diff.py 205795680 00-baseline
  aiff-postopen` reports no ANLZ change.

## Finding 6: PVB2 Is Absent, So the Seek-Index Concern Is Moot Here

None of the three fixtures carry a `PVB2` tag in any ANLZ file, in baseline or
after conversion. This rekordbox version does not write the byte-coupled seek
index on normal analysis; the research found it only in older library files,
likely from USB export. The research's `PVB2` staleness worry therefore does not
apply to tracks analyzed by this version. Confirmed by scanning the tag lists in
the baseline snapshots for all three IDs.

## Finding 7: Re-Analysis Is the Only Step That Drifts, and It Tracks Sample Change

Re-analysis writes a new ANLZ generation (`ANLZ0000 → ANLZ0001` in the same UUID
folder, old set orphaned), repoints `AnalysisDataPath`, rewrites the grid
(`PQTZ`/`PQT2`), phrases (`PSSI`), every waveform (`PWAV`/`PWV*`/`PWVC`), and
`PVBR`, and corrects `PPTH`. It bumps `CueUpdated`, `AnalysisUpdated`,
`TrackInfoUpdated`, and `rb_local_usn`.

How far the new grid moves from the original tracks how much the conversion changed
the audio samples:

| Change type | Case | Samples | Re-analysis grid (1 trial) | Evidence |
| --- | --- | --- | --- | --- |
| Uncompressed → uncompressed, same depth/rate | A → AIFF 16/44.1 | bit-identical | reproduced byte-identical (first 0.422 s, 465 beats, same times hash) | `subject-205795680-aiff-postanalyze.json` |
| Bit-depth + sample-rate together | B → AIFF 16/44.1 from 24/48 | resampled | first 0.055→0.050 s, 384→385 beats, BPM 110.41→109.09, new key | `subject-205157376-aiff-postanalyze.json` |
| Lossy | A → MP3 320 | lossy | first 0.422→0.043 s, 465→466 beats, ~0.8-beat re-anchor, KeyID changed | `subject-205795680-mp3-postanalyze.json` |

The bit-identical conversion reproduced the grid exactly, which is consistent with
deterministic analysis but does not prove it from one trial. The downsample and
the MP3 produced different grids, BPM, and key. Because the MP3 is sample-accurate
in time (Finding 4) and the downsample preserves duration, these are
beat-detection differences on changed samples, not timeline slips. The kept
(pre-conversion) analysis stays time-valid against the converted audio; the
difference is latent and appears only if the user re-analyzes.

## Finding 8: Analysis Lock Is Bit 0x80 of the Analysed Column

Toggling Analysis Lock on, with no convert and no re-analysis, changed exactly one
`DjmdContent` field: `Analysed 105 → 233`. The lock is bit `0x80` (128) of
`Analysed`, not a separate column (`233 = 105 + 128`). Cues and ANLZ were
untouched. Compare `subject-230928195-prelock.json` to `subject-230928195-postlock.json`.

- Convert can detect a locked track with `content.Analysed & 0x80`, and since
  convert never writes `Analysed`, it already preserves the lock.
- This corrects the research's Finding 7, which searched for a dedicated lock
  column and `DisableQuantize` and found none.
- Observed under High Precision only (base `105`); Normal mode uses a different
  base, so re-confirm the bit there.

## Finding 9: The Lock Blocks Re-Analysis; Unlocked Re-Analysis Overwrites Manual Grids

With the lock on, convert preserved the lock bit (`Analysed` stayed `233`) and the
Analyze action is disabled in the rekordbox UI, so re-analysis cannot be
triggered. The manual grid stayed byte-identical to baseline
(`subject-230928195-mp3-locked.json`).

With the lock off, re-analysis of the converted MP3 overwrote the hand-tuned grid:
first beat `0.008 → 0.071 s`, BPM `94.95 → 95.01`, same 295 beats
(`subject-230928195-mp3-unlocked-reanalyze.json`). The manual downbeat was
replaced by auto-detection.

Re-analysis is the only step that refreshes
a stale analysis against the converted audio, and the only step that overwrites a
manual grid. Users trade one against the other. Because not everyone uses Analysis
Lock, a bulk re-analysis after a bulk conversion can silently overwrite hand-tuned
grids. Whether that is worth doing depends on the drift magnitude, which this set
of single trials does not size.

## Open Thread: Re-Analysis Zeroes a Cue's BeatLoopSize

On fixtures A and B, re-analysis reset a cue's `BeatLoopSize` from `65537`
(`0x00010001`, a packed value, not a literal beat count) to `0`, with the cue
position unchanged (A: Kind=5 at 122780 ms, `subject-205795680-mp3-postanalyze.json`;
B: Kind=0 at 112433 ms, `subject-205157376-aiff-postanalyze.json`). Convert never
touches it. FodanCia's cues had no beat loop, so nothing reset there. This may
mean re-analysis strips beat-loop sizing from cues and wants a focused drill-down;
`subject_diff` reports `BeatLoopSize` changes, so recurrences are captured.

## Caveats and Gaps

These results are a few single trials and leave concrete gaps for a follow-up:

- **Determinism is unproven.** One bit-identical reproduction (Finding 7) is
  consistent with deterministic analysis but does not establish it. The MP3 and
  downsample drift cannot yet be split into a faithful re-read of the converted
  audio versus run-to-run non-determinism. Re-analyze the same unchanged file
  several times per format to measure variance.
- **No unanalyzed baseline.** Every fixture started at `Analysed=105`. The
  `0 → analyzed` transition was never observed, so what an analysis creates from
  scratch, and which columns and files first appear, is untested.
- **Change types not isolated.** The downsample changed bit-depth and sample-rate
  together. Bit-depth-only (24/44.1 → 16/44.1) and sample-rate-only
  (16/48 → 16/44.1) were never separated, so which contributes more is unknown.
- **FLAC was never re-analyzed.** The "uncompressed → compressed, same depth/rate"
  case was only converted. It should reproduce the grid like the AIFF same-rate
  case, since the samples are bit-identical, but this was not confirmed.
- **Normal analysis mode untested.** All runs used High Precision. Re-run key
  cases under Normal mode and re-confirm the `Analysed & 0x80` lock test against
  its base value.
- **Drift magnitude unquantified.** Across a varied fixture set, the stale-versus-
  re-analyzed delta should be measured in DJ-relevant terms: BPM error, beat phase
  error in ms, key change rate, and cue drift relative to the re-analyzed grid.

## Reproduction

The scripts run against the local rekordbox library. Close rekordbox first so reads
see committed state. `subject_snapshot.py` and `subject_diff.py` live in
`../shared/scripts/`; `restore_fixtures.sh` in `scripts/`.

| Script | Purpose |
| --- | --- |
| `subject_snapshot.py <id> <stage>` | Write a three-layer snapshot to `evidence/subject-<id>-<stage>.json` |
| `subject_diff.py <id> <stageA> <stageB>` | Diff two snapshots across row, cues, and ANLZ tag hashes |
| `restore_fixtures.sh` | Restore `master.db` and the fixtures' ANLZ folders from the backup, drop converted outputs |

Conversions were run as `uv run rbe convert <id> --format-out <fmt>
--delete-originals none --yes`. The `none` is required so the source WAV survives
for the next run.
