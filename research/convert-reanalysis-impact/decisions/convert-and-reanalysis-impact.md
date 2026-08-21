# Convert and Re-Analysis: Behavior, Decisions, and Guidance

What a `convert` run does to a track's analysis, what rekordbox-edit's modifying
commands should do about it, and what users should expect. This synthesizes two
in-app experiments into decisions. The evidence lives one level up: the read-only
study `../convert-anlz-cue-impact.md`, the first experiment
`../convert-anlz-cue-impact-verification.md`, and the second
`../convert-anlz-cue-impact-experiment2.md`.

## What We Know

A track's analysis is spread across three stores: the `DjmdContent` row, the
`DjmdCue` rows, and the on-disk ANLZ files (`.DAT`/`.EXT`/`.2EX`). Convert writes to
exactly one of them, the `DjmdContent` row, setting the path, name, file type,
sample rate, bit depth, and bit rate. It never opens an ANLZ file and never touches
a cue.

The load-bearing structures are indexed by musical time, not by sample position or
byte offset. The beat grid (`PQTZ`/`PQT2`) is stored in milliseconds, cues carry
their position in milliseconds and microseconds, phrases ride the beat grid, and the
waveform is sampled on a fixed 150-per-second time base. So any conversion that
preserves the audio timeline leaves the grid, the cues, the phrases, and the
waveform's time axis valid, regardless of a change in codec, sample rate, or bit
depth.

Re-analysis is the only step that moves a grid, changes detected BPM or key, or
overwrites a hand-tuned grid. Convert never triggers it, and rekordbox does not
re-analyze a track on its own when the file changes; it waits for the user to ask.
A converted track therefore keeps its existing, still-time-valid analysis until the
user chooses to re-analyze.

Analysis is deterministic. Across 34 analyses in five mode combinations, every
within-mode run reproduced the ANLZ byte-for-byte, for both a steady-tempo track and
a variable-tempo one. What moves a grid is the setting, not chance. The modes differ
only in the grid: High Precision refines the beat grid over Normal but adds no files
and no richer waveform, Auto chooses the fitting grid per track, and the Dynamic mode
can overfit a steady track with spurious tempo swings.

When a user does re-analyze a converted file, the drift follows one rule: the
samples, not the container. A container-only change that preserves the audio samples,
such as WAV to FLAC at the same depth and rate, reproduces the grid exactly. Any
change that alters the samples, meaning a resample or a requantize, shifts the grid a
small, bounded amount (on the order of half a BPM, tens of milliseconds of first-beat
offset, cues landing up to about 20 ms off the new grid). That shift is a threshold,
not a per-axis quantity: dropping bit depth alone, sample rate alone, or both from a
pristine hi-res source produces the same drift, so the two axes cannot be ranked.

Two format-specific facts round this out. The MP3 output is sample-accurate against
its source, with a zero-sample offset, so there is no encoder-delay gap for a
compliant decoder. And `PVB2`, a seek index in the `.EXT` file, is authored by
analysis for FLAC files only; converting a FLAC away from FLAC leaves the index
byte-stale, and a later re-analysis of the now non-FLAC file drops it.

Analysis Lock is bit `0x80` of the `Analysed` column (105 unlocked becomes 233
locked), in every analysis mode, not a separate column. Convert never writes
`Analysed`, so it already preserves the lock, and rekordbox disables the Analyze
action in the UI while the lock is on.

## What rekordbox-edit Should Do

Convert's current row write is correct in what it changes and correct in leaving
`Analysed` alone, which is the grid-preserving choice. It has three row-level gaps,
all verified against the current `_update_database_record` and `_get_output_path`.

`FileSize` is never updated, so the row keeps the source file's byte size after a
conversion, wrong by an order of magnitude for an MP3 target. Convert should write
the converted file's actual size alongside the columns it already sets.

`FolderPath` is written with mixed path separators. `_get_output_path` builds the
directory with `os.path.normpath` and `os.path.dirname`, which yield backslashes on
Windows, and `_update_database_record` then joins that with `posixpath.join`,
producing `A:\Music\dir/file.aiff`. rekordbox stores all-forward-slash paths, so the
directory portion should be normalized to forward slashes before the write.

`OrgFolderPath` is left unchanged. When it matches the old path it should follow the
new one, as rekordbox's own `update_content_path` helper does when it moves a file.

The `PPTH` path tag inside the ANLZ files stays stale, still naming the old
extension. This is harmless on the desktop, since rekordbox reaches the audio through
`FolderPath` and the ANLZ through `AnalysisDataPath`, so a fix is optional. If
correctness on export is wanted later, rewrite `PPTH` in rekordbox's native
`?/<name>` form rather than the full-path form the canonical helper writes. `PVB2`
needs no action: it goes stale only while the source stays FLAC and is dropped by any
re-analysis.

Convert should keep leaving `Analysed` untouched, and should not offer an automatic
re-analysis. Re-analysis is the one operation that can overwrite a manual grid, and
not every user runs Analysis Lock. Should a re-analysis feature ever be offered, it
must read the lock with `content.Analysed & 0x80` and skip locked tracks, warn that
an unlocked track's manual grid will be replaced, and verify that a new ANLZ
generation was written, because rekordbox silently skips re-analyzing an already
fully-analyzed track in some selection paths.

## What Users Should Expect

A lossless container swap at the same depth and rate, such as WAV to FLAC or WAV to
AIFF, changes nothing that matters. The beat grid and every cue stay exactly in
place, and they stay correct even if the user re-analyzes afterward, because the
samples are identical. The only stale artifacts are cosmetic: the waveform still
matches (identical audio), while `PPTH`, `PVB2` on a former FLAC, and the `FileSize`
row value are internally out of date without user-visible effect on the desktop.

A resample or a requantize, such as a hi-res track down to 16-bit/44.1 kHz, also
keeps the analysis time-valid and correct as it stands. The grid and cues remain
aligned to the audio. The difference is latent: if the user re-analyzes the converted
file, they get a slightly different grid (about half a BPM, tens of milliseconds), a
possible key change, and cues sitting a few to about twenty milliseconds off the new
grid. Until they re-analyze, the kept analysis stays usable.

An MP3 320 conversion has no gap. The output is sample-accurate, so cues and the grid
stay in register, and the waveform, now derived from lossy audio, differs only
cosmetically until a re-analysis redraws it.

## What Users Can Do

Turn on Analysis Lock before a bulk re-analysis to protect hand-tuned grids. A bulk
re-analysis after a bulk conversion will otherwise overwrite manual grids on every
unlocked track, silently, since re-analysis is the only step that does so.

Treat re-analysis as a deliberate choice, not a reflex after converting. Skipping it
keeps existing grids and cues, which stay time-valid; running it refreshes the
waveform and grid against the new audio at the cost of any manual grid work. For a
lossless container swap the choice is moot, since a re-analysis reproduces the same
grid. For a resample or requantize the drift is small but real, so re-analyze only
when a fresh grid is worth more than the current one.

Prefer the Auto beat-grid mode over Dynamic for general use. Auto takes a variable
grid on tracks that need one and a clean single-tempo grid on steady tracks, avoiding
the Dynamic mode's tendency to overfit a steady track with tempo swings that are not
there.
