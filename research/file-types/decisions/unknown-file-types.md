# Unknown File Types

How `convert` and the display layer treat Rekordbox `FileType` codes that
RBE does not map, including video and other formats Rekordbox supports but
RBE does not convert.

## Context

`get_file_type_name` maps the Rekordbox `FileType` integer to a name and has
six entries: MP3 (`0`, `1`), M4A (`4`), FLAC (`5`), WAV (`11`), AIFF (`12`).
Rekordbox stores many more codes than these — AAC, ALAC, and video files all
have codes RBE does not map.

Two problems followed from the previous design:

1. **`get_file_type_name` raised on unmapped codes.** Both call sites
   (`display._cell_value` and `convert._classify_convert`) are
   display/informational, and neither uses the exception as a gate. The raise
   only forced each caller to wrap the call in `try/except`, so a function that
   produces a display value was harder to use correctly than incorrectly.

2. **`_classify_convert` gated convertibility by enumerating exclusions.** It
   skipped a track only when its `FileType` was the target, MP3, or M4A.
   Everything else — including video files and unmapped audio codes — fell
   through to `_convert_to_hi_res` and was handed to ffmpeg as if it were a
   hi-res lossless source. A video file would be silently stripped to an
   audio-only output with its database record rewritten to point at it, or the
   whole batch would abort.

## Decisions

### A. `get_file_type_name` is a total display map, not a guard

It returns `None` for unmapped codes instead of raising. Each caller chooses
its own fallback: `display` renders `"UNKNOWN"`, `convert` leaves
`source_file_type` as `None`. Both `try/except` blocks are removed.

### B. `_classify_convert` gates on a positive input whitelist

RBE converts only hi-res lossless sources, and that whitelist already exists as
`InputFormats = {FLAC, AIFF, WAV}`. The classifier now decides in this order:

1. `source == target` → skip `already_target_format` (unchanged).
2. `source not in InputFormats` → skip `unsupported_source_format`.
3. otherwise → convert.

MP3, M4A, video, and unmapped codes all land on the `unsupported_source_format`
branch, so the explicit MP3/M4A enumeration is gone and video files are skipped
with a clear reason instead of being fed to ffmpeg.

## Implementation

- One commit for decision A.
- One commit for decision B, built test-first (TDD). B adds the
  `unsupported_source_format` `SkipReason`, its CLI skip reporting, and tests.
- Both on the current branch.
