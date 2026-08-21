# Convert Impact: In-App Verification Test Plan

## Question

The read-only study in `convert-anlz-cue-impact.md` settled the theory: the beat
grid, phrases, and all cues are time-based, convert rewrites only the
`DjmdContent` row, and the ANLZ files go stale in three bounded ways (`PPTH`,
`PVB2`, the waveforms) while `FileSize` stays wrong. This plan drives real
conversions through the CLI against purpose-built fixtures in the local rekordbox
6 library and watches what changes at each step, so the open questions the study
deferred are answered in the app rather than inferred from binary. The standalone
results write-up is `convert-anlz-cue-impact-verification.md`.

The local library is a safe test subject: convert keeps every fixture's audio
original, and a backup taken after fixture setup makes every run reversible.

## Scope and Goals

Six questions, each tied to a fixture and a measurement (see "What Each Run
Answers"):

1. Does a lossless-to-MP3 convert shift the beat grid and cues, and does
   producing a LAME gapless header prevent it?
2. Does rekordbox reuse the stored `PVB2` seek index after a re-encode, or
   rebuild it?
3. Does a stale `PPTH` path tag cause any user-visible problem?
4. Does rekordbox ever re-analyze a track on its own when the file changes but
   `Analysed` stays 105?
5. Which `DjmdContent` column records Analysis Lock, and does the lock block a
   re-analysis?
6. How far does a waveform diverge from the new audio after each conversion
   type?

A through-line runs under questions 1 and 5: both the LAME gapless header and the
lock column are readable at convert time. They are the two facts convert could
surface as a warning without any re-analysis, so the plan tests whether that
detection is reliable.

## Summary: Answers and Gaps

The headline results, framed against the four questions that matter for a convert
feature. Detail and evidence are under "Findings"; each result here is a small
number of single trials, so the gaps are load-bearing, not footnotes.

**How to tell if Analysis Lock is on.** The lock is bit `0x80` (128) of the
`Analysed` column, not a separate field: an unlocked, fully analyzed track reads
`Analysed=105`, a locked one `233` (`105 + 128`). Convert can detect it with
`content.Analysed & 0x80`, and since convert never writes `Analysed`, it already
preserves the lock. _Gap:_ confirmed only under High Precision analysis (base
`105`); Normal mode uses a different base, so re-confirm the bit there.

**What an analysis creates or changes.** A re-analysis writes a new ANLZ
generation (`ANLZ0000 → ANLZ0001` in the same UUID folder, old set orphaned),
repoints `AnalysisDataPath`, and rewrites the grid (`PQTZ`/`PQT2`), phrases
(`PSSI`), every waveform (`PWAV`/`PWV*`/`PWVC`), and `PVBR`, while correcting
`PPTH` to the new name. It bumps `CueUpdated`, `AnalysisUpdated`,
`TrackInfoUpdated`, and `rb_local_usn`, can change `BPM` and `KeyID`, and zeroes a
cue's `BeatLoopSize`. _Gap (significant):_ every fixture started already analyzed
(`Analysed=105`). We never observed the `0 → analyzed` transition, so what an
analysis creates from scratch, and which columns and files first appear, is
untested.

**How lossy conversion creates drift.** The conversions preserve the timeline:
the MP3 round-trip is sample-accurate (zero offset), and the downsample preserves
duration. So the kept cues and grid stay time-valid against the converted audio
with no re-analysis, and cue positions never drift from conversion alone (they
are time-anchored rows convert does not touch). The drift is latent: the kept
analysis was computed on the original samples, the converted file's samples
differ (lossy or resampled), and a re-analysis therefore yields a different grid
phase, BPM, and key. The drift is realized only if the user re-analyzes. _Gap:_
we cannot yet separate real conversion drift from re-analysis non-determinism,
and the magnitude is uncharacterized.

**Does the drift differ by change type?** It tracks how much the conversion moves
the audio samples:

| Change type | Tested case | Samples | Re-analysis drift (1 trial) |
| --- | --- | --- | --- |
| Uncompressed → uncompressed, same depth/rate | WAV→AIFF 16/44.1 | bit-identical | none (grid reproduced) |
| Uncompressed → compressed, same depth/rate | WAV→FLAC 16/44.1 | bit-identical | _not re-analyzed (gap)_ |
| Bit-depth + sample-rate together | 24/48→16/44.1 | resampled | +1 beat, BPM `110.41→109.09`, key |
| Lossy | →MP3 320 | lossy | ~0.8-beat re-anchor, key |

Bit-identical conversions (same depth/rate, whether the container compresses or
not) carry no drift; sample-changing conversions do. _Gaps:_ the FLAC case was
only converted, never re-analyzed; bit-depth-only (e.g. 24/44.1→16/44.1) and
sample-rate-only (e.g. 16/48→16/44.1) were never isolated, so we cannot yet say
which of depth or rate contributes more.

**The decision this informs.** Re-analysis is the only step that overwrites a
manual grid and the only step that refreshes a stale analysis, so users trade one
against the other. A bulk re-analysis after a bulk conversion can silently
overwrite hand-tuned grids on tracks that are not lock-protected. Whether that is
worth doing depends on the drift magnitude, which the follow-up experiment must
size. See "Follow-Up."

## The Convert Tool, As Built

Confirmed by reading `rekordbox_edit/api/convert.py`:

- Output is hardcoded to 16-bit / 44.1 kHz (`TARGET_BIT_DEPTH = 16`,
  `TARGET_SAMPLE_RATE = 44100`). The sample rate only ever clamps down, never up.
  A true hi-res-to-same-hi-res conversion (24/96 to 24/96) is therefore not
  producible today; that case is the work the planned `--bit-depth-out` /
  `--sample-rate-out` args would unlock.
- Convert writes a new file alongside the source and keeps the original unless
  `--delete-originals` is set. Originals stay put for this plan.
- The row columns it writes are `FolderPath`, `FileNameL`, `FileType`,
  `SampleRate`, `BitDepth`, and `BitRate`. It never opens an ANLZ file and never
  touches `DjmdCue`, `FileSize`, `Analysed`, or `AnalysisUpdated`.
- Convert skips a track whose `FileType` already equals the target
  (`already_target_format`) and one whose source type is outside the hi-res
  lossless input whitelist (`unsupported_source_format`).

Because of the 16/44.1 hardcode, the "same bit depth/sample rate" case is run as
16/44.1 to 16/44.1, which the tool produces sample-accurately.

## Fixtures

Three files, from three real tracks staged in the `ConvertTest` playlist. The
format matrix splits the cue-rich subject in two: the "same" case needs a
16/44.1 source while the "lower" case needs a 24/48 source. The grid and lock
tests share one hand-gridded track across two phases, since the revert protocol
restores between runs. Waveform impact needs no dedicated fixture; it rides along
on the MP3 and downsample runs, where the audio amplitude actually diverges.

All three sources were 24-bit FLAC. Each was decoded to WAV (FLAC cannot be a
source for the "→ compressed (FLAC)" case, and the cases all start non-compressed):

| Fixture | Song | Decoded source | rekordbox state | Conversions it drives |
| --- | --- | --- | --- | --- |
| A — Cues (CD) | VUGUVUGUU | `_ConvertTest/VUGUVUGUU.wav` 16/44.1 | hot + memory cues | same-rate lossless (WAV to AIFF), compressed (to FLAC), MP3 320 |
| B — Cues (hi-res) | Vuelve | `_ConvertTest/Vuelve.wav` 24/48 | hot + memory cues | the "lower" case: downsample to 16/44.1 lossless |
| C/D — Grid + lock | FodanCia | `_ConvertTest/FodanCia.wav` 24/44.1 | hand-edited beat grid | MP3 320, run twice: phase D lock on, phase C lock off |

A and B carry cues so cue survival and waveform divergence are measured on every
format transition. FodanCia carries the hand grid for both lock phases: phase D
(lock on) confirms the grid survives a re-analyze attempt; phase C (lock off)
confirms an unlocked hand grid gets overwritten. Lock-column discovery runs at
the start of phase D.

## Building the Fixtures

Beat grids and waveforms only mean something on real music, so synthetic tones
are out.

**Audio preparation.** The three FLAC sources were decoded with
ffmpeg to `A:/Music/_ConvertTest/`: VUGUVUGUU to 16/44.1 WAV (the "same" case
needs a true 16/44.1 source), Vuelve to 24/48 WAV (keeps hi-res for the
downsample), FodanCia to 24/44.1 WAV (it only drives MP3, so depth is
incidental). All three verified with ffprobe as stereo PCM at the stated depth
and rate.

**rekordbox setup.** Import the three WAVs, run full analysis, then
set state: A and B get two hot cues plus two memory cues; FodanCia gets a
hand-edited beat grid with lock confirmed off. Quit rekordbox so the database
commits.

**Backup.** Take the backup described under "Revert Protocol" before any
conversion.

**Record IDs.** Query each fixture by filename to capture its
`ContentID` and ANLZ folder, and pin them here once known:

| Fixture | Song | ContentID | Format | ANLZ folder (under USBANLZ) |
| --- | --- | --- | --- | --- |
| A | VUGUVUGUU | 205795680 | WAV 16/44.1 | `967\6fc9e-2691-42ea-b006-124fe44c354f` |
| B | Vuelve | 205157376 | WAV 24/48 | `bf7\1f0c1-704d-46fb-b47d-cefb16a5e3aa` |
| C/D | FodanCia | 230928195 | WAV 24/44.1 | `47a\337b6-897a-45a2-a086-f8b88e2f5c40` |

Baseline grids: A 465 beats / first 0.422 s, B 384 beats / first 0.055 s,
C/D 295 beats / first 0.008 s (manually edited). All three at `Analysed=105`.

## Snapshot Tooling

One parameterized script, `../shared/scripts/subject_snapshot.py <content_id>
<stage>`, writes `evidence/subject-<id>-<stage>.json` and captures all three
layers in one pass:

- `DjmdContent` columns (reusing `row_snapshot.py`'s approach), including the
  lock column once it is known.
- The full `DjmdCue` rows: `Kind`, `InMsec`, `InFrame`, `OutMsec`,
  `CueMicrosec`, and the MPEG/seek fields.
- Per ANLZ file: the raw tag walk, the parsed `PQTZ` grid (count, BPM, first and
  last beat time, and a hash of every beat time), the `PCO2`/`PCOB` counts, the
  `PPTH` string, and the byte length plus SHA-1 of `PVB2` and of each `PWV*`
  waveform array.

The hashes are the load-bearing addition. They prove convert never touched the
ANLZ (hashes identical from baseline to post-convert) and that re-analysis
rewrote the waveform and seek index (hashes differ), with no binary eyeballing.
A companion `subject_diff.py <id> <stageA> <stageB>` prints the deltas between
any two stages.

## Per-Run Procedure

Each run follows the three-step pattern, with a snapshot at each stage:

1. **Baseline** (`00-baseline`), right after fixture setup. This is the "inspect
   and record" step.
2. **Convert** via the CLI, dry-run first, then real, then snapshot
   `10-postconvert` and diff against baseline. Confirm that only the six
   `DjmdContent` columns move, cue rows and every ANLZ hash stay identical, and
   `PPTH` and `FileSize` are now stale.
3. **Re-analyze** by hand in rekordbox, quit, snapshot `20-postanalyze`, and diff
   against both prior stages.

## Revert Protocol

Step 3 rewrites ANLZ files on disk, which a row-level undo cannot reverse, so the
backup must cover both stores. The post-fixture backup must include `master.db`
and the four fixtures' ANLZ UUID folders under `share/PIONEER/USBANLZ` (backing
up the whole `USBANLZ` directory is the safe move). Convert keeps the original
audio, so the source files need no special handling. Complete all of a fixture's
runs, then restore `master.db` and its ANLZ folders from the backup and delete
any converted output files before moving to the next fixture.

## What Each Run Answers

| Question | Fixture · conversion | Measurement | Hypothesis |
| --- | --- | --- | --- |
| MP3 timeline shift (Q1) | A and C · to MP3 320 | At convert time, parse the MP3's Xing/Info + LAME header for encoder delay and padding. After convert + re-analyze, compare new `PQTZ` first-beat time and first-cue-to-grid offset against baseline; a ~13 or ~26 ms shift means the delay leaked, near-zero means it was honored. | LAME gapless header is present, so the shift is recoverable; verify rekordbox uses it. |
| `PVB2` reuse or rebuild (Q2) | A · to MP3, B · downsample | `PVB2` SHA-1: identical baseline to post-convert, changed after re-analyze; in-app needle-drop is the manual check before re-analyze. | Convert leaves it stale; re-analyze rebuilds it. |
| Stale `PPTH` impact (Q3) | every run | `PPTH` still names the old extension post-convert; observe whether the track loads and plays in-app. | Harmless on desktop, matters only on export. |
| Self-triggered re-analyze (Q4) | any · post-convert | Reopen rekordbox without asking to analyze, quit, snapshot. | Nothing changes; `Analysed` stays 105. |
| Lock column and behavior (Q5) | D | `row_snapshot.py` before and after toggling lock finds the column; then D to MP3 to re-analyze attempt leaves the grid intact, versus C to MP3 to re-analyze where an unlocked hand grid can be overwritten. | Lock lives in one column convert can read; it blocks re-analysis. |
| Waveform divergence (Q6) | A (to FLAC, to MP3, to same), B (downsample) | `PWV*` SHA-1 baseline vs post-convert (identical) vs post-analyze (changed); divergence largest for MP3 and for 24 to 16. | Convert never redraws; re-analyze redraws, visibly off only for lossy or depth-reduced targets. |

## Findings

### Phase 1: Convert-Only (no re-analysis), all five conversions

Every conversion was run from the clean baseline (restore between each),
snapshotted, and diffed. The result is uniform across all formats:

| Conversion | Row columns changed | FileSize | Cues | ANLZ bytes |
| --- | --- | --- | --- | --- |
| A WAV 16/44.1 → AIFF | FolderPath, FileNameL, FileType (11→12) | stale | unchanged | identical |
| A WAV → FLAC | + BitRate (1411→0) | stale | unchanged | identical |
| A WAV → MP3 320 | + BitRate (→320), FileType (→1) | stale | unchanged | identical |
| B Vuelve 24/48 → AIFF 16/44.1 | + SampleRate (48000→44100), BitDepth (24→16), BitRate | stale | unchanged | identical |
| C/D FodanCia → MP3 320 | FileType, BitRate, BitDepth (24→16) | stale | unchanged | identical |

Confirmed empirically, matching the research:

- **Convert touches only the `DjmdContent` row**, plus `updated_at`. Cue rows are
  byte-for-byte unchanged and every ANLZ tag SHA-1 holds across all three files
  (`.DAT`, `.EXT`, `.2EX`). `PPTH` still names `.wav` in every case.
- **`FileSize` is stale after every conversion.** The row keeps the source WAV's
  size even for the MP3 target, where the real file is a fraction of it. This is
  the row-level bug from the research, reproduced on every path.
- The downsample correctly updates `SampleRate` and `BitDepth`; MP3 holds
  `BitDepth=16` and sets `BitRate=320`; FLAC sets `BitRate=0`.

Two findings beyond the research:

- **Mixed path separators (new, likely a bug).** Baseline `FolderPath` is
  rekordbox-native all-forward-slash. Convert writes
  `A:\Music\_ConvertTest/VUGUVUGUU.aiff`: backslashes for the directory, a
  forward slash before the filename. `_update_database_record` joins an
  `os.path.dirname` result (backslashes on Windows) with `posixpath.join`. This
  deviates from how rekordbox stores paths; in-app tolerance is untested.
- **MP3 gapless header is present but `Lavc`-tagged.** The MP3 carries a Xing/Info
  CBR header with encoder delay `576` samples (13.1 ms) and padding `1594`
  samples (36.1 ms) at the LAME-extension offset, which is exactly the gapless
  metadata a player needs. The 9-byte encoder signature reads `Lavc62.28`, not
  `LAME`, and there is no `iTunSMPB`. A decoder reading the extension by offset
  compensates; one requiring the literal `LAME` signature ignores the fields and
  plays ~13 ms of encoder delay as leading silence. Whether rekordbox honors it
  is the Phase 2 question.

### Phase 2: Re-Analysis (in-app)

**Run 1 — Fixture A, WAV → AIFF (lossless control), Q3/Q4 + control.**

Opening the converted track without analyzing (Run 1a): it played with no error,
all 6 cues in place, waveform normal, no re-analyze prompt. The snapshot showed
the ANLZ byte-identical to baseline and `PPTH` still `.wav`.

- **Q4 answered: rekordbox does not self-re-analyze.** A changed file with
  `Analysed=105` is left alone until the user asks. Nothing changed from merely
  opening and playing.
- **Q3 answered: stale `PPTH` is harmless on desktop.** Playback, cues, and
  waveform all worked while `PPTH` still named the old `.wav`.

Re-analyzing the AIFF (Run 1b):

- **Grid reproduced exactly**: first beat `0.422 s`, 465 beats, byte-identical
  grid to baseline. This single trial is consistent with re-analysis being
  deterministic for bit-identical input, but one observation does not establish
  it; run-to-run non-determinism is not ruled out (see "Follow-Up").
  Treated here as a working control, not proof.
- **Re-analysis writes a new ANLZ generation.** `AnalysisDataPath` moved
  `ANLZ0000.DAT → ANLZ0001.DAT` in the same UUID folder; the old set is orphaned,
  not overwritten.
- **The new ANLZ is byte-identical to the original except `PPTH`.** Every
  waveform, grid, and `PVB2` tag hash matched; only the path tag changed, now
  correctly `.aiff`. Re-analysis both confirms determinism and repairs the stale
  `PPTH`.
- **It normalized one cue's metadata**: a Kind=5 cue's `BeatLoopSize` went
  `65537 → 0` with position unchanged. Re-analysis can touch `DjmdCue`, but it did
  not move the cue.

The folder-level restore (delete the UUID folder, copy the backup back, restore
`master.db`) correctly removes the orphaned `ANLZ0001` generation and repoints
the row at `ANLZ0000`. Verified before continuing.

**Run 2 — Fixture A, WAV → MP3 320, re-analyzed (the gapless test, Q1).**

The decisive evidence is an offline cross-correlation, not the grid alone.
Decoding the converted MP3 and the original WAV to PCM and aligning them:

```
WAV samples: 9689606   MP3 samples: 9689606   diff: 0 (0.0 ms)
best lag (MP3 vs WAV): 0 samples = 0.00 ms
```

- **No encoder-delay gap.** The decoded MP3 is sample-accurate with the WAV:
  identical length, zero lag. ffmpeg's libmp3lame output is effectively gapless;
  the `Lavc`-tagged Xing delay/padding is correct and a compliant decoder strips
  it to recover the exact timeline. The convert tool's MP3 needs no LAME-specific
  gapless change for compliant decoders.
- **Re-analysis still produced a different grid**: first beat `0.422 → 0.043 s`,
  465 → 466 beats, a ~0.8-beat downbeat re-anchor, BPM unchanged at 127.0. With
  zero audio offset, this is consistent with **beat-detection difference on lossy
  samples** rather than a timeline slip. Whether the difference is a faithful
  re-read of the converted audio or partly re-analysis non-determinism is not
  separated here (see "Follow-Up"). The grid anchored earlier, the
  opposite of what un-stripped encoder delay would cause, which argues against a
  gap in rekordbox's own decode.
- **`KeyID` changed** (`1186508287 → 3995792994`): the same lossy-detection
  variance reached key detection.
- **Full ANLZ rewrite** on re-analysis: `PQTZ`/`PQT2` grid, `PSSI` phrases, every
  `PWAV`/`PWV*`/`PWVC` waveform, `PVBR`, and `PPTH` (now `.mp3`).
- **`BeatLoopSize 65537 → 0` recurred**, confirming re-analysis zeroes it
  regardless of target format (see Open Threads).
- **Q2 not testable here**: this track carries no `PVB2` tag in either the
  baseline or MP3 EXT, so the seek-index reuse question needs a fixture that has
  one. To check on B and FodanCia.
- Cues did not move (rows untouched) and landed correctly in-app per visual check.

**Run 3 — Fixture B, WAV 24/48 → AIFF 16/44.1 (downsample), re-analyzed.**

- **Timeline preserved**: first beat `0.055 → 0.050 s`, duration intact (last beat
  `210.13 → 210.28 s`).
- **Re-analysis drifted**: `+1` beat (384→385) and detected BPM changed
  `110.41 → 109.09` (≈1.3 BPM), plus a new key. Resampling preserves true tempo,
  so the BPM move is a re-analysis difference, not a real tempo change. As with
  the MP3, this cannot yet be split into "faithful re-read of resampled audio"
  versus re-analysis non-determinism.
- **`BeatLoopSize 65537 → 0` recurred** (Kind=0 cue), confirming it as a general
  re-analysis behavior, format-independent.

The three re-analysis runs, ordered by how far the conversion moves the samples:

| Conversion | Samples vs original | Re-analysis grid (single trial) |
| --- | --- | --- |
| Same-rate lossless (WAV↔AIFF 16/44.1) | bit-identical | reproduced byte-identical |
| Downsample (48k→44.1k) | resampled | +1 beat, BPM `110.41→109.09`, key change |
| MP3 320 | lossy | ~0.8-beat re-anchor, key change |

Each conversion preserves the timeline, so the kept analysis stays time-valid.
The drift only appears on re-analysis, and its magnitude tracks how much the
samples changed. Quantifying that drift, and confirming it is real rather than
noise, is the follow-up below.

**Run 4a — Fixture C/D (FodanCia), lock-column discovery (Q5).**

Toggling Analysis Lock on (no convert, no re-analyze) changed exactly one
`DjmdContent` field: `Analysed 105 → 233`. The lock is **bit `0x80` (128) of
`Analysed`**, not a separate column: `233 = 105 + 128`. Cues and ANLZ unchanged.

- **Detecting lock at convert time is `content.Analysed & 0x80`.** Convert never
  writes `Analysed`, so it already preserves the lock bit.
- This corrects the research's Finding 7, which searched for a dedicated lock
  column and `DisableQuantize` and found none. The lock rides in `Analysed`.
- **Caveat: observed under High Precision analysis mode.** All fixtures were
  analyzed in High Precision, where the base is `Analysed=105`. Normal mode likely
  uses a different base value (the research saw `16` and `88`), so the `& 0x80`
  lock test should be re-confirmed under Normal mode; the bit should still encode
  the lock, but the base it is added to differs.

**Run 4b — lock ON, convert to MP3, re-analyze attempt.** Convert preserved the
lock bit (`Analysed` stayed `233`). In the app, **the Analyze action is disabled
while the lock is on**, so re-analysis cannot even be triggered. The manual grid
stayed byte-identical to baseline; only the row's format columns and the lock bit
differ. The lock fully protects the hand grid.

**Run 4c — lock OFF, convert to MP3, re-analyze.** With the lock off the Analyze
action is enabled, and re-analysis overwrote the manual grid: first beat
`0.008 → 0.071 s` (63 ms), BPM `94.95 → 95.01`, same 295 beats. The hand-tuned
downbeat was replaced by auto-detection. This is the loss Analysis Lock prevents.

**The risk this exposes.** Re-analysis is the only step that overwrites a manual
grid, and it is also the only way to refresh a stale analysis against the
converted audio. So a user faces a tradeoff: re-analyze after converting to make
the analysis match the new file, or keep hand-tuned grids. Not everyone uses
Analysis Lock, so a bulk re-analysis run after a bulk conversion can silently
overwrite manual grid work across a library. Whether that tradeoff is worth
making depends on how large the conversion-induced analysis drift actually is,
which is the open question the follow-up must size.

## Follow-Up

The decision-relevant question is the inverse of "what convert leaves
unchanged": **if a user re-analyzes after converting, how far does the analysis
move, and therefore by how much does the kept (stale) analysis misrepresent the
actual converted audio?** The kept analysis describes the original file; the
converted file is a lossy or resampled approximation, so a re-analysis delta
measures the conversion's analytical footprint.

Two limits of the current data:

- **Determinism is unproven.** A single bit-identical reproduction (Run 1b) is
  consistent with deterministic analysis but does not establish it. The drift
  seen on MP3 and downsample re-analysis cannot yet be split into a faithful
  re-read of the converted audio versus run-to-run non-determinism.
- **One fixture per format.** Beat-detection downbeat phase, BPM, and key
  behavior vary by track. Three tracks cannot characterize the scope.

A follow-up experiment should:

1. **Test determinism directly** by re-analyzing the same unchanged file several
   times and diffing, per format, to measure run-to-run variance.
2. **Widen the fixture set** across genres, tempos, keys, and source rates/depths.
3. **Quantify the stale-versus-true delta** in DJ-relevant terms: BPM error, beat
   phase error in ms, key change rate, and whether cues drift relative to the
   re-analyzed grid. This tells us to what degree a kept analysis "lies" about
   the converted file, which is the decision-relevant number.
4. **Cover both analysis modes.** All runs here used High Precision
   (`Analysed=105` base). Normal mode uses a different base value and may analyze
   differently; re-run key cases under it, and re-confirm the `Analysed & 0x80`
   lock test against the Normal-mode base.

## Open Threads

- **Re-analysis zeroes a hot cue's `BeatLoopSize`.** Fixture A had a 1-beat hot
  cue loop (Kind=5 at 122780 ms). Re-analysis (Run 1b) reset its `BeatLoopSize`
  from `65537` (`0x00010001`, a packed value, not a literal beat count) to `0`,
  leaving the cue position intact. Convert never touches it; only re-analysis
  does. This may mean re-analysis strips beat-loop sizing from cues, a possible
  data-loss concern. Deferred for a focused drill-down; the `subject_diff`
  tooling reports `BeatLoopSize` changes, so every recurrence is captured
  automatically.
