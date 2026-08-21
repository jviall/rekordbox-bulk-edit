# File Types

## Question

How should `convert` and the display layer treat Rekordbox `FileType` codes the
tool does not map — AAC, ALAC, and the video formats Rekordbox supports but `rbe`
does not convert?

## Findings

`get_file_type_name` mapped six audio codes and raised on everything else, and
`_classify_convert` gated convertibility by enumerating exclusions, so unmapped
codes and video files fell through and were handed to ffmpeg as if they were
hi-res lossless sources. The fix is a total display map that returns `None` for
unmapped codes, and a classifier that gates on a positive input whitelist
(`FLAC`, `AIFF`, `WAV`) so every other code is skipped with a clear reason. The
full record is in `decisions/unknown-file-types.md`.

The media fixtures used to probe the format matrix, and the session notes for
this investigation, are kept in the ignored `ai-docs/` tree rather than committed
here.
