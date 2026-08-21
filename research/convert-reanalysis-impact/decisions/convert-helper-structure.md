# Convert Helper Structure

Whether `convert`'s two ffmpeg helpers (`_convert_to_hi_res`,
`_convert_to_mp3`) should be merged, split, or left as they are.

## Context

The two helpers share nearly all their code. Identical between them:

- the `ffmpeg_in_path()` guard,
- the `ffmpeg.input(...).output(..., **kwargs).overwrite_output().run(...)` call,
- the `except FfmpegError` block (log, decode stderr, return `False`),
- the `except Exception` block (log, re-raise),
- the success debug log.

The only real difference is the ffmpeg output kwargs: hi-res selects a codec
from `_HI_RES_CODECS` by format and passes `ar=sample_rate` (plus
`sample_fmt="s16"` for FLAC); MP3 uses a fixed `libmp3lame / 320k / s16p` set.
The duplicated `try/except` scaffold is the kind of code that drifts — a fix to
one branch can miss the other.

## Decision

Merge them into one runner plus per-format kwargs builders:

```python
def _run_ffmpeg(input_path, output_path, output_kwargs, label) -> bool: ...
def _hi_res_output_kwargs(output_format, sample_rate) -> dict: ...
def _mp3_output_kwargs(sample_rate) -> dict: ...
```

The shared guard, run, and error handling live in `_run_ffmpeg` exactly once.
Each kwargs builder is a pure function, unit-testable without mocking ffmpeg.
The convert loop picks a builder and calls the runner.

## Alternatives rejected

- **Full merge** — a single `_build_output_kwargs` covering MP3 and hi-res. The
  MP3 kwargs differ enough from the PCM/FLAC set that folding them in adds a
  conditional that reads worse than two small builders.
- **Step-by-step granular helpers** (validate → build → run → handle, each its
  own function). Over-engineered at this size; the runner-plus-builders shape
  already provides the step-wise testability a split would chase.

## Implementation

A single behavior-preserving refactor commit. The existing `convert` tests are
the safety net; add focused unit tests for the two kwargs builders.
