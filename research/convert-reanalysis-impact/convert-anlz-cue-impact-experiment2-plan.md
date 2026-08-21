# Experiment 2: Analysis Variance and Drift Magnitude

## Question

`convert-anlz-cue-impact-verification.md` proved that convert is safe in isolation
and that re-analysis is the only step that moves a grid, but left its strongest
claims as single trials. This experiment characterizes the analysis step itself:
what it creates from nothing, how Normal and High Precision modes differ, how
repeatable each mode is, what happens to a populated `PVB2` seek index, and how
large the latent drift becomes when a user re-analyzes a converted file.

Every claim cites a snapshot in `evidence/` produced by
`../shared/scripts/subject_snapshot.py`. The read-only study is
`convert-anlz-cue-impact.md`; the first in-app experiment is
`convert-anlz-cue-impact-verification.md` (results) and
`convert-anlz-cue-impact-test-plan.md` (procedure); this experiment's standalone
results write-up is `convert-anlz-cue-impact-experiment2.md`.

## Framing: Variance, Not Accuracy

rekordbox analysis is an estimate, not ground truth. On steady electronic material
it tends to lock a stable grid; on live, tempo-variant material it often places the
grid where a DJ would not. This experiment does not judge whether a grid is
correct. The question is narrower and answerable: given one musical source, how
much does the estimate **move** when the same audio is presented at a different bit
depth, sample rate, or codec, and how much does it move run to run with the input
held fixed. A wandering grid on a live cumbia track is expected; what matters is
whether converting that track and re-analyzing it produces a *different* wandering
grid than the original would have.

## What This Adds to Experiment 1

| Question or gap | Phase | Method |
| --- | --- | --- |
| Zero to analyzed: what an analysis creates from scratch (gap 2) | 1 | Snapshot `Analysed=0`, analyze, diff |
| What Normal vs High Precision each create from zero (new) | 1 | Zero to Normal and zero to High on the same track, via restore |
| What changes upgrading Normal to High in place (new) | 1 | Analyze Normal, re-analyze High, diff |
| Determinism within each mode (gap 1, new) | 1 | Five repeats per (fixture, mode), restore to zero each |
| Determinism: Normal vs High (new) | 1 | Compare the variance of the five Normal runs against the five High runs |
| Normal-mode `Analysed` base and lock bit (gap 5) | 1 | Read `Analysed` after a Normal analysis; re-confirm `& 0x80` |
| What authors a `PVB2` tag (new) | 0 | Read-only library correlation, plus the zero-to-analyzed signal from F1/F2 |
| Behavior of a populated `PVB2` (new) | 1 | Convert and re-analyze a `PVB2`-bearing track; watch the tag |
| Bit-depth-only vs sample-rate-only drift (gap 3) | 2 | Two isolating conversions, then re-analyze |
| FLAC re-analyzed (gap 4) | 2 | Re-analyze the FLAC convert output |
| Drift magnitude in DJ terms (gap 6) | 2 | A metrics pass over stale-vs-re-analyzed grids |
| `BeatLoopSize` reset (open thread) | both | `subject_diff` already reports it; record any recurrence |

## Fixtures

| Fixture | ContentID | Origin | Character | Role |
| --- | --- | --- | --- | --- |
| F1 Immigrant (Moktar) | assigned at import | Fresh import, held at `Analysed=0` | Constant-tempo house | Zero-to-analyzed, Normal-vs-High, determinism |
| F2 Pregonando (Conjunto Miramar) | assigned at import | Fresh import, held at `Analysed=0` | Live cumbia, variable tempo | Same, plus the high-variance case |
| P1 Do My Thing (Erika de Casier) | 7691309 | Existing library track, USB-origin | `.EXT` carries an 8032-byte `PVB2` | `PVB2` convert and re-analysis behavior |
| A VUGUVUGUU | 205795680 | Experiment 1 fixture, restorable | WAV 16/44.1 | Phase 2 FLAC re-analysis |
| B Vuelve | 205157376 | Experiment 1 fixture, restorable | WAV 24/48 | Phase 2 isolation conversions |
| C FodanCia | 230928195 | Experiment 1 fixture, restorable | WAV 24/44.1, manual grid | Spare, `BeatLoopSize` watch |

F1 and F2 are imported with auto-analyze off, so they arrive at `Analysed=0` and
give the never-before-observed zero origin. F2 carries a grid that rekordbox tends
to misplace; per the framing above, that is the point, not a defect. P1 is a real
track, so the protocol backs up its row and ANLZ folder before anything touches it.

## Tooling

The raw tag walk in `subject_snapshot.py` already hashes every tag including
`PVB2`, and `subject_diff.py` already reports per-tag SHA-1 changes and
`BeatLoopSize`, so the diff and the `PVB2` work need no tooling change. The drift
metrics do need one small change: the snapshot currently stores a beat-times hash
plus first, last, and count, but not the per-beat times themselves, so a phase
metric cannot be computed offline. `subject_snapshot.py` gains a `times` array in
its `pqtz` block (the hash stays for compatibility with existing snapshots).

| Script | Status | Use |
| --- | --- | --- |
| `pvb2_origin.py` | **new** | Read-only: correlate `PVB2` presence against per-track attributes |
| `subject_snapshot.py <id> <stage>` | **extend** | Three-layer snapshot; add full per-beat `times` to the `pqtz` block |
| `subject_diff.py <id> <A> <B>` | reuse | Diff row, cues, and ANLZ tag hashes |
| `grid_drift.py <id> <A> <B>` | **new** | DJ-relevant metrics between two snapshots' grids and cue sets |
| `restore_fixtures.sh` | extend | Add P1 and the F1/F2 zero states |

`grid_drift.py` is the substantive new code. From the `pqtz.times` arrays and the
`DjmdCue` rows in two snapshots it reports: BPM delta, first-beat phase delta in
ms, the maximum beat-phase error across the track in ms (after best-fit alignment),
whether the detected key changed, and each cue's drift in ms against the grid of
stage B. It reads the snapshots, so it needs no live database and runs any time.
The `times` extension must land before any snapshot the drift pass will consume.

## Revert and Backup Protocol

Every snapshot is read with rekordbox closed so reads see committed state. Between
analyses a fixture is restored to a fixed pre-analysis state, which is what isolates
analysis-process variance from "re-analyze on top of an existing grid."

Step 0, once, before touching anything:

1. Back up `master.db` to the existing backup root `A:/rb-convert-test-backup/`.
2. Back up P1's ANLZ folder to the same root, recording its UUID path.
3. Import F1 and F2 with auto-analyze off, snapshot each at `00-zero`, then back up
   `master.db` again (now carrying the two zero rows) and confirm neither fixture
   has an ANLZ folder yet.

`restore_fixtures.sh` gains: restore P1's ANLZ folder, and a "restore to zero"
path for F1/F2 that copies back the zero-state `master.db` row and deletes any
ANLZ folder rekordbox created for them. The Experiment 1 fixtures restore exactly
as before.

## Phase 0: PVB2 Origin Discovery

We do not yet know what authors a `PVB2` tag. Finding 6 observed that desktop High
Precision analysis did not create one and guessed at USB export, but the origin was
never identified. Phase 0 turns the guess into evidence and needs no fixtures, so
it runs first.

`pvb2_origin.py` walks every `.EXT` in the library read-only, records `PVB2`
presence and length per track, then joins that against the `DjmdContent` row and
reports how cleanly each attribute separates the tracks that carry `PVB2` from the
analyzed tracks that do not.

**Result (`evidence/exp2-00-pvb2-origin.txt`): the codec authors `PVB2`, and the
codec is FLAC.** Of 1,241 fully-analyzed tracks, `FileType=5` (FLAC) carries `PVB2`
in 1,187 of 1,188 cases (100%); every other format (MP3, M4A, WAV, AIFF) carries it
in zero cases. The `BitRate=0` correlation is a proxy for FLAC. Release years span
1961 to 2025 and `DateCreated` 2020 to 2026 with no cutoff, which rules out the
older-version and USB-export hypotheses. This corrects Verification Finding 6: the
Experiment 1 fixtures lacked `PVB2` because they were analyzed as WAV, not because
desktop analysis never writes it. The mechanism fits a seek index: constant-rate
PCM (WAV/AIFF) needs none, MP3 and M4A carry their own frame or container index, and
FLAC's variable compressed blocks are what rekordbox indexes with `PVB2` (its length
scales with duration, 432 bytes for clips up to 8032 for full tracks).

The experimental confirmation still runs in Phase 1: a fresh FLAC analyzed from
`Analysed=0` should author `PVB2` (direct proof of "FLAC gets it"), and the P1
re-analysis (below) should **drop** `PVB2` after converting the FLAC to AIFF
(proof of "non-FLAC does not"). This makes at least one FLAC fresh fixture valuable;
if neither F1 nor F2 is FLAC, P1 still covers the drop half.

## Phase 1: Analysis Characterization

All Phase 1 work runs on F1 and F2; P1 has its own short sequence at the end.

### Snapshot Stages

1. `00-zero`: imported, `Analysed=0`, no ANLZ folder.
2. `normal-01` through `normal-05`: restore to zero, analyze in **Normal** mode,
   snapshot. Five independent runs from the identical zero input.
3. `high-01` through `high-05`: restore to zero, analyze in **High Precision**,
   snapshot. Five independent runs.
4. `normal-then-high`: from a Normal analysis (reuse `normal-05`'s end state),
   re-analyze in High Precision in place, snapshot. This is the in-place upgrade
   path a user actually takes, kept as a single observation alongside the
   restore-to-zero runs.
5. Dynamic-mode determinism, **F2 Pregonando only**, three runs each: `dyn-normal-01`
   through `dyn-normal-03` (Normal quality, Dynamic tempo analysis on) and
   `dyn-high-01` through `dyn-high-03` (High Precision, Dynamic on). Dynamic analysis
   is tempo-change aware, so the variable-tempo cumbia is where non-determinism, if
   it exists anywhere, is most likely to appear.

The user performs each import, mode switch, and analyze in the rekordbox UI, then
quits rekordbox so the snapshot reads committed state.

### Determinism Within and Across Modes

Determinism within a mode: diff the five same-mode snapshots against the first by
ANLZ tag SHA-1, and compare parsed BPM, first-beat time, beat count, and detected
key. Byte-identical across all five is strong evidence of a deterministic pipeline
for that input; any divergence is quantified with `grid_drift.py`.

Determinism across modes: compare the spread of the five Normal runs against the
spread of the five High runs. The deliverable states, per fixture, whether either
mode varied at all and which varied more. F1 (steady) and F2 (variable) are
expected to differ here; the experiment records the contrast rather than assuming
it.

**Result (Normal and High Precision, 5 runs each): zero variance in both modes.**
All five Normal runs and all five High runs of both F1 (steady house) and F2
(variable cumbia) are byte-identical across every ANLZ tag SHA-1, with identical
BPM, grid times, beat count, and key within each mode. Even the variable-tempo
track reproduced exactly. Both modes are deterministic from identical FLAC input.

The two modes differ only from **each other**, and only in the grid: High Precision
refines `PQTZ`/`PQT2` (Immigrant 551→552 beats, anchor 0.150→0.145 s, BPM unchanged;
Pregonando 342→343 beats, anchor 0.179→0.097 s, BPM 114.62→115.02), which drags
`PSSI` phrases with it when the grid moves enough (Pregonando). Every other tag,
including all waveforms and `PVB2`, is byte-identical between modes, so High
Precision does not deepen the waveform or add files. Dynamic mode is the remaining
place variance could surface.

Determinism has one qualification: the analytically meaningful output (every ANLZ
tag, grid, BPM, key) is byte-identical across runs, but two `DjmdContent` bookkeeping
columns are not. `AnalysisUpdated` and `TrackInfoUpdated` take a small even value
that changes each session (Normal runs: 10, 6, 2, 4, 2; High runs: 6, 2, 2, 2, 4)
and is **identical for both tracks analyzed in the same session**, so it is a
session-scoped marker, not a per-mode or per-track fingerprint. Its exact meaning is
unresolved and left as a note; it does not affect grid, cue, or waveform data.

**All four modes are deterministic (final).** Across 34 analyses (Immigrant and
Pregonando each: 6 Normal, 5 High, 3 Dynamic-Normal, 3 Dynamic-High), every within-
mode run is byte-identical. Analysis output is a deterministic function of the audio
and the settings; the setting, not chance, is what moves a grid.

**Dynamic mode, and a caution.** Dynamic analysis fits a per-beat variable tempo.
On Pregonando it produced a genuinely variable grid (Dynamic-Normal: 12 tempi,
113.2–115.6 BPM; Dynamic-High: 24 tempi, 77.9–127.7 BPM) where static Normal forced
a single ~114.6. The caution is Dynamic-High on **steady** material: it gave Immigrant
a 125.0–176.5 BPM, 15-tempo grid despite the track being a rock-steady 130, which
Normal and static High both read cleanly. Grid aggressiveness ranks Normal < static
High < Dynamic-Normal < Dynamic-High, and the most aggressive setting can overfit a
constant-tempo track. Every mode difference is grid-only (`PQTZ`/`PQT2` plus the
`PSSI` phrases that ride the grid); waveforms and `PVB2` never differ across modes.

**Auto mode (High Precision only) is a per-track chooser.** With the beat-grid mode
set to Auto, the output is byte-identical to whichever fixed grid fits the track:
static High for steady Immigrant (chose the clean 130.0 grid, not the Dynamic-High
overfit) and Dynamic-High for variable Pregonando (the 24-tempo grid). It is
deterministic across 3 runs each. Auto is the safe default: it takes the variable
grid where warranted and the constant grid where not, dodging the Dynamic-High
overfit on steady material.

The "Embedding" pass shown in the very first High Precision screenshot never
reappeared under any beat-grid mode and left no ANLZ or row trace. It is a separate
RB7 cloud-analytics feature that derives compatibility-recommendation metadata, not
part of local grid/waveform analysis, so it is out of scope here.

### Zero to Analyzed, and Normal vs High Precision

The `00-zero` to `normal-01` diff is the first direct observation of what an
analysis creates from nothing: which ANLZ files first appear, which `DjmdContent`
columns change, and the value `Analysed` takes for a Normal analysis. The
`00-zero` to `high-01` diff is the same for High Precision. Comparing the two
end states answers what High Precision adds over Normal (result above: only the
grid, not extra files or richer waveforms), and `normal-then-high` shows whether the
in-place upgrade reaches the same state as a clean zero-to-High analysis.

**In-place upgrade result: byte-identical to clean zero-to-High, both fixtures.**
Analyzing Normal then re-analyzing High in place produced exactly the same ANLZ as
analyzing High from zero. Analysis output depends only on the audio and the mode,
not on any prior analysis state, so the upgrade path is path-independent.

The Normal-mode `Analysed` base value is recorded and the lock bit re-tested: lock
F1 after a Normal analysis, confirm `Analysed` gains `0x80` over the Normal base.
This closes the gap that Experiment 1 saw `0x80` only against the High Precision base
of 105.

**Result (gap 5 closed):** the Normal base is `105`, identical to High Precision. A
Normal-analyzed F1 locked reads `233 = 105 + 0x80`, while the unlocked F2 reference
stays `105`, a clean 128 delta. The lock bit is mode-independent; there is no
separate Normal base to worry about.

### PVB2-Present Behavior (P1)

A short sequence answers what convert and re-analysis do to a populated, byte-coupled
seek index:

1. `pvb2-baseline`: snapshot P1 as-is, confirming the 8032-byte `PVB2` in the `.EXT`.
2. `pvb2-postconv`: convert P1 to AIFF, snapshot. Expectation from Experiment 1:
   convert leaves every ANLZ tag, including `PVB2`, byte-identical, so the index
   goes stale against the new file.
3. `pvb2-postanalyze`: re-analyze P1 in High Precision, snapshot. Phase 0 predicts
   the re-analysis drops `PVB2`, because the track is now AIFF and `PVB2` is authored
   only for FLAC. Confirming the drop closes the loop with the fresh-FLAC authoring
   check.

**Results:** all three confirmed. Baseline P1 carried an 8032-byte `PVB2`. Convert to
AIFF (`FileType 5→12`) left every ANLZ tag byte-identical, so `PVB2` went stale
in place, and both convert bugs reproduced (`FileSize` kept the FLAC size, `FolderPath`
got mixed separators). Re-analysis wrote a new generation (`ANLZ0000→ANLZ0001`, old
orphaned, `AnalysisDataPath` repointed) whose `.EXT` has **no `PVB2`** — the codec, now
AIFF, no longer earns the seek index. P1's original `.EXT` also predated the current
format (it had `PVB2` but no `PQT2`, while fresh analyses write both for FLAC), so the
generation changed too, but only `PVB2` dropped, isolating the cause to the codec.
P1 is now in a converted, re-analyzed state and must be restored from its `exp2`
backup at cleanup.

## Phase 2: Drift Magnitude

Phase 2 reuses the restorable Experiment 1 fixtures and quantifies, in DJ-relevant
terms, how far a re-analyzed grid sits from the grid the user kept after a
conversion.

### Isolation Conversions

Experiment 1 changed bit depth and sample rate together (24/48 to 16/44.1) and
could not attribute the drift. Two intermediates from B's 24/48 source (a 24/44.1
and a 16/48, one ffmpeg step each) plus the pristine 24/48 let us analyze every
resolution variant and compare.

**Result: the drift is a threshold effect, not a per-axis quantity.** Analyzed in
the controlled High Precision + Normal mode, the pristine 24/48 reads 109.421 BPM,
384 beats, first beat 55 ms. Every reduced variant reads the same 109.99 BPM, 386
beats, 83 ms: 24/44.1 (rate reduced), 16/48 (depth reduced), and 16/44.1 (both).
So changing **either** axis alone moves the grid the full amount (+0.57 BPM, +2
beats, +28 ms first beat, cues up to 22 ms off the new grid, up to a half-beat
phase drift by track end), and changing both adds nothing. Bit-depth versus
sample-rate cannot be ranked; each independently triggers the same drift.

The deeper principle: **drift tracks whether the audio samples change, not the
container.** Any resample or requantize shifts the grid slightly; a container-only
change that preserves the samples does not (see FLAC below). This is a
methodological caution too: comparing two already-converted intermediates against
each other reads ~0 drift and hides the real shift, which happens on the first
departure from the pristine source.

This reconciles Experiment 1: its Vuelve drift was real and format-induced, not a
mode artifact. (An early run here misread it as zero drift because rekordbox
skipped the re-analysis of an already-`105` track; the snapshot must show a new
ANLZ generation and an updated `PPTH` to confirm the re-analysis actually ran.)

### FLAC Re-Analysis

Convert fixture A (16/44.1 WAV) to FLAC, re-analyze, snapshot. **Result: the grid
reproduced byte-identical** (0 BPM/beat/phase drift, all six cues dead on-grid),
because WAV to FLAC at the same depth and rate is bit-identical in the sample
domain. The only change is that the FLAC re-analysis **authored an 8032-byte
`PVB2`**, which the WAV analysis did not have, a second confirmation of the
codec-driven `PVB2` finding. This closes gap 4 and anchors the "samples, not
container" principle at the zero-drift pole.

### Drift Metrics

For every Phase 2 re-analysis, `grid_drift.py` reports BPM delta, first-beat phase
delta in ms, maximum beat-phase error across the track in ms, key-change yes or no,
and per-cue drift in ms against the re-analyzed grid. The Phase 1 determinism result
sets the noise floor at exactly zero: every mode reproduces byte-identically, so any
non-zero Phase 2 delta is real codec-induced drift, not analysis noise.

Because the noise floor is zero, the load-bearing check is that the re-analysis
actually ran. rekordbox silently skips re-analyzing an already-`105` track in some
selection paths, which reads as a false zero-drift. Every drift result must be
gated on the post snapshot showing a new ANLZ generation (`ANLZ0001`) and a `PPTH`
updated to the new extension; otherwise the comparison is a snapshot against itself.

## Open Risks and Notes

- The restore-to-zero determinism design measures variance of the analysis process
  from a fixed input. It does not measure variance of repeated *in-place*
  re-analysis, which stage 4 samples once but does not repeat.
- `grid_drift.py`'s "maximum beat-phase error" needs a defined alignment. The plan
  is a best-fit constant offset between the two grids, so the metric reports tempo
  and phase drift rather than a fixed-anchor offset; the script documents this.
- P1 is the only fixture whose true clean state cannot be regenerated by
  re-analysis (this version may not re-author `PVB2`), so its backup is the only
  way back. The protocol backs it up first for that reason.
