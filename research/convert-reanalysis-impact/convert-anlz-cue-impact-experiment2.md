# Analysis Behavior and Conversion Drift: Experiment 2 Findings

## Question

`convert-anlz-cue-impact-verification.md` proved that convert rewrites only the
`DjmdContent` row and that re-analysis, not conversion, moves a grid. It left its
strongest claims as single trials and could not say how repeatable an analysis is,
what an analysis creates from nothing, how the analysis modes differ, what authors
the `PVB2` seek index, or how large the latent drift is when a user re-analyzes a
converted file. This experiment answers those.

Every claim cites a snapshot in `evidence/` produced by
`../shared/scripts/subject_snapshot.py`; grids are compared with
`../shared/scripts/subject_diff.py` and `grid_drift.py`, the library-wide `PVB2`
census with `pvb2_origin.py`. The framing throughout is variance, not accuracy:
rekordbox analysis is an estimate, and the question is how much that estimate moves
across codecs, resolutions, and repeated runs, not whether it is correct. The
read-only study is `convert-anlz-cue-impact.md`; the full procedure and inline
results are in `convert-anlz-cue-impact-experiment2-plan.md`.

## Summary

rekordbox analysis is deterministic. Across 34 analyses in five mode combinations,
every within-mode run was byte-identical, for both a steady-tempo house track and a
variable-tempo live cumbia. What moves a grid is the setting, not chance.

Conversion drift follows one rule: the samples, not the container. A container-only
change that preserves the audio samples (WAV to FLAC at the same depth and rate)
reproduces the grid exactly. Any change that alters the samples (a resample or a
requantize) shifts the grid a small, bounded amount, and that shift is a threshold,
not a per-axis quantity: dropping bit depth alone, sample rate alone, or both from a
pristine hi-res source produces the same drift.

The `PVB2` seek index is authored by analysis for FLAC files only, which corrects the
first experiment's guess that it came from USB export. High Precision differs from
Normal only in the grid, Auto is a safe per-track chooser, and the Dynamic mode can
overfit a steady track. Analysis Lock is bit `0x80` of `Analysed` in every mode.

## Method

Two fresh FLAC tracks were imported with auto-analyze off so they began at
`Analysed=0`: F1 Immigrant by Moktar (steady house, `27790898`) and F2 Pregonando by
Conjunto Miramar (variable-tempo live cumbia, `174954387`). One existing FLAC library
track carried a populated `PVB2`, P1 Do My Thing by Erika de Casier (`7691309`). The
three restorable Experiment 1 fixtures supplied the drift cases, with two single-axis
intermediates derived from fixture B by ffmpeg.

Each snapshot captures the `DjmdContent` row, every `DjmdCue` row, and per ANLZ file a
raw tag walk with a SHA-1 of each tag plus the parsed beat grid, now including the full
per-beat times. Determinism was tested by restoring a fixture to `Analysed=0` before
each run (`reset_fresh_to_zero.py`) so every run began from an identical input. A load-
bearing lesson emerged: rekordbox silently skips re-analyzing an already-`105` track in
some selection paths, which reads as false zero drift, so every re-analysis result is
gated on the snapshot showing a new ANLZ generation and a `PPTH` updated to the new
extension.

## Finding 1: PVB2 Is a FLAC-Only Analysis Artifact

A read-only census of the whole library (`pvb2_origin.py`,
`evidence/exp2-00-pvb2-origin.txt`) settles the origin the first experiment could not.
Of 1,241 fully-analyzed tracks, `FileType=5` (FLAC) carries `PVB2` in 1,187 of 1,188
cases (100%); MP3, M4A, WAV, and AIFF carry it in zero cases. Release years span 1961
to 2025 and `DateCreated` 2020 to 2026 with no cutoff, which rules out an older-version
or USB-export origin. Verification Finding 6 saw no `PVB2` on its fixtures only because
they were analyzed as WAV. The mechanism fits a seek index: constant-rate PCM needs
none, MP3 and M4A carry their own frame or container index, and FLAC's variable
compressed blocks are what rekordbox indexes with `PVB2`, its length scaling with
duration from 432 bytes for a clip to 8032 for a full track.

The experiment confirms both directions. A fresh FLAC analyzed from zero authors an
8032-byte `PVB2` (`subject-27790898-normal-01.json`), in every mode. Converting P1 from
FLAC to AIFF leaves the tag byte-stale, and re-analyzing the now-AIFF file drops it
(Finding 7).

## Finding 2: Analysis Is Deterministic in Every Mode

From an identical FLAC input, rekordbox analysis is byte-identical run to run. Six
Normal runs, five High Precision runs, three Dynamic-Normal runs, three Dynamic-High
runs, and three High-Auto runs of each fixture all reproduced every ANLZ tag SHA-1,
BPM, grid time, beat count, and key within their mode (`subject-{27790898,174954387}-
{normal,high,dyn-normal,dyn-high,high-auto}-0*.json`). The variable-tempo cumbia
reproduced exactly alongside the steady track. Analysis is a deterministic function of
the audio and the settings.

One qualification: two `DjmdContent` bookkeeping columns are not deterministic.
`AnalysisUpdated` and `TrackInfoUpdated` take a small even value that changes each
session (Normal runs: 10, 6, 2, 4, 2, 2) and is identical for both tracks analyzed in
the same session, so it is a session-scoped marker, not a per-mode or per-track
fingerprint. It does not touch grid, cue, or waveform data.

## Finding 3: The Modes Differ Only in the Grid

High Precision differs from Normal only in `PQTZ`/`PQT2`, and in the `PSSI` phrases that
ride the grid when it moves enough. Every other tag, including all waveforms and `PVB2`,
is byte-identical between the two modes, so High Precision does not deepen the waveform
or add files. On the steady track it refined the grid slightly (551 to 552 beats, anchor
0.150 to 0.145 s, BPM unchanged); on the variable track it landed a different grid
(342 to 343 beats, anchor 0.179 to 0.097 s, BPM 114.62 to 115.02), which dragged the
phrases with it (`subject-*-normal-01.json` versus `subject-*-high-01.json`).

The beat-grid modes rank by aggressiveness: Normal (single tempo) < static High <
Dynamic-Normal < Dynamic-High. Dynamic fits a per-beat variable tempo, which the cumbia
warrants (Dynamic-Normal gave it 12 tempi over 113.2 to 115.6 BPM). The caution is
Dynamic-High on steady material: it gave the rock-steady 130 BPM house track a 125.0 to
176.5 BPM, 15-tempo grid (`subject-27790898-dyn-high-01.json`), an overfit that Normal
and static High both avoided.

Auto, available only under High Precision, is a per-track chooser. Its output is byte-
identical to static High for the steady track and to Dynamic-High for the variable one
(`subject-*-high-auto-01.json`), taking the variable grid where warranted and the clean
grid where not, so it sidesteps the Dynamic-High overfit. The "Embedding" pass named in
one rekordbox tooltip never recurred under any beat-grid mode and left no ANLZ or row
trace; it is a separate RB7 cloud-analytics feature for compatibility recommendations,
out of scope here.

## Finding 4: What an Analysis Creates From Zero

The `00-zero` to `normal-01` diff is the first direct observation of an analysis from
nothing (`subject-27790898-00-zero.json` to `-normal-01.json`). From `Analysed=0` with
`SampleRate`, `BitDepth`, and `BitRate` all zero, a Normal analysis writes the full
`DAT+EXT+2EX` tag set, populates `BPM`, `KeyID`, `SampleRate` (to 44100), and `BitDepth`
(to 16), sets `AnalysisDataPath`, sets `Analysed` to 105, and for FLAC authors the
`PVB2`. Normal reaches the same depth and the same `Analysed=105` that High Precision
does; the earlier worry that Normal used a different base was wrong.

## Finding 5: The In-Place Upgrade Is Path-Independent

Analyzing a fixture in Normal, then re-analyzing it in High Precision in place without a
reset, produced an ANLZ byte-identical to a clean zero-to-High analysis
(`subject-*-normal-then-high.json` versus `-high-01.json`). Analysis output depends only
on the audio and the mode, not on any prior analysis state. The upgrade a real user
performs by bumping the setting and re-analyzing lands exactly where a from-scratch High
analysis would.

## Finding 6: Analysis Lock Is Bit 0x80 in Every Mode

Locking a Normal-analyzed F1 read `Analysed=233`, while the unlocked F2 reference stayed
`105`, a clean 128 delta (`subject-27790898-normal-locked.json`,
`subject-174954387-normal-unlocked-ref.json`). The Normal base is 105, identical to High
Precision, so the lock bit `0x80` is mode-independent. This closes the gap that
Experiment 1 saw the bit only against the High Precision base.

## Finding 7: Convert Leaves PVB2 Stale, Re-Analysis Drops It

P1, a real FLAC library track, carried an 8032-byte `PVB2` at baseline
(`subject-7691309-pvb2-baseline.json`). Converting it to AIFF changed `FileType` 5 to 12
and left every ANLZ tag byte-identical, so `PVB2` went stale in place, and both known
convert bugs reproduced: `FileSize` kept the FLAC size and `FolderPath` got mixed
separators (`-pvb2-postconv.json`). Re-analysis wrote a new generation (`ANLZ0000` to
`ANLZ0001`, old orphaned, `AnalysisDataPath` repointed) whose `.EXT` has no `PVB2`
(`-pvb2-postanalyze.json`), because the track is now AIFF. P1's original `.EXT` also
predated the current format (it had `PVB2` but no `PQT2`), so the generation changed too,
but only `PVB2` dropped, which isolates the cause to the codec.

## Finding 8: Drift Tracks the Samples, Not the Container

The load-bearing drift result. Convert never moves a grid; re-analysis of the converted
audio can. How much depends only on whether the conversion changed the audio samples.

A container-only change preserves the samples and the grid. Converting fixture A from
16/44.1 WAV to FLAC, then re-analyzing, reproduced the grid byte-identical: 0 BPM, beat,
and phase drift, and all six cues dead on-grid (`grid_drift.py 205795680
flac-ctrl-baseline flac-ctrl-postanalyze2`). The only change was that the FLAC re-analysis
authored an 8032-byte `PVB2` the WAV analysis lacked, a second confirmation of Finding 1.

A sample-changing conversion shifts the grid a small, bounded amount, and the shift is a
threshold, not a per-axis quantity. Analyzed in the controlled High Precision plus Normal
mode, the pristine 24/48 source reads 109.421 BPM, 384 beats, first beat 55 ms, while
every reduced variant reads the same 109.99 BPM, 386 beats, 83 ms: the 24/44.1 (rate
reduced), the 16/48 (depth reduced), and the 16/44.1 (both). Changing either axis alone
moves the grid the full amount (+0.57 BPM, +2 beats, +28 ms first beat, cues up to 22 ms
off the new grid, up to a half-beat phase drift by track end), and changing both adds
nothing (`grid_drift.py 205157376 combined-ctrl-baseline combined-ctrl-postanalyze2`, and
the variant BPM table in the plan). Bit depth versus sample rate cannot be ranked; each
independently triggers the same drift. This reconciles Experiment 1, whose Vuelve drift
was real and format-induced, not the mode artifact an early mis-run here suggested.

## Caveats and Gaps

- **Two tracks, one library, one rekordbox version.** The mode and drift findings rest on
  a steady and a variable FLAC plus the Experiment 1 fixtures, on one machine. The
  determinism result is strong within that scope but does not speak to other rekordbox
  builds or exotic material.
- **Re-analysis can be silently skipped.** rekordbox skipped re-analyzing already-`105`
  tracks in some selection paths, producing a false zero drift until forced. Any future
  automated re-analysis must verify a new ANLZ generation, not assume the request took.
- **`BeatLoopSize` was not revisited.** The Experiment 1 open thread (re-analysis zeroing a
  cue's `BeatLoopSize`) did not recur on these fixtures and was not drilled into.
- **Drift measured on one hi-res source.** The threshold-effect result comes from Vuelve;
  the magnitude on other hi-res tracks is unmeasured, though the sample-versus-container
  principle should generalize.

## Reproduction

The scripts run against the local library with rekordbox closed. `subject_snapshot.py`
and `subject_diff.py` live in `../shared/scripts/`; the rest in `scripts/`.

| Script | Purpose |
| --- | --- |
| `pvb2_origin.py` | Library-wide `PVB2`-presence correlation by track attribute |
| `subject_snapshot.py <id> <stage>` | Three-layer snapshot to `evidence/subject-<id>-<stage>.json` |
| `subject_diff.py <id> <A> <B>` | Diff row, cues, and ANLZ tag hashes |
| `grid_drift.py <id> <A> <B>` | BPM, phase, key, and cue drift between two snapshots |
| `reset_fresh_to_zero.py` | Restore F1 and F2 to `Analysed=0` for a determinism run |

Analyses were driven in the rekordbox UI with the mode set as each finding names, then
rekordbox was quit so snapshots read committed state.
