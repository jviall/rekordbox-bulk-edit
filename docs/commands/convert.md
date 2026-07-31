# convert

Convert audio files between formats and update the Rekordbox database to point at the new files. Cues, analysis, beatgrids, and all other metadata are preserved — see [Frequently Asked Questions](../faqs.md) for more info.

## Supported Formats

- **Input:** FLAC, AIFF, WAV (hi-res formats only — lossy-compressed sources are skipped)
- **Output:** AIFF (default), FLAC, WAV, or MP3 (320kbps CBR)

Tracks already in the target format are skipped, as are tracks whose output file already exists (override with `--overwrite`).

## Bit Depth and Sample Rate

All conversions target **16-bit / 44.1 kHz**, with a few nuances:

- A source already at the target bit depth and sample rate converts losslessly.
- A higher-resolution source (say 24-bit or 96 kHz) is down-sampled to the target, and is considered **lossy** even between lossless formats.
- Other than conversion to MP3, which always encode to 44.1 kHz, a source with a lower sample rate than the target fidelity keeps its original sample rate.

## Originals: Delete or Keep

`--delete-originals` controls what happens to the source file after a successful conversion:

- `lossless` (default) — delete the original only when the conversion lost no audio information; keep it when the conversion was lossy (MP3 output or down-sampled hi-res output)
- `all` — always delete the original
- `none` — never delete the original

## Examples

```bash
# Preview conversion
rbe convert --format-out aiff --format flac --dry-run

# Convert and skip confirmation
rbe convert --format-out wav --artist "Burial" --yes

# Convert to MP3 but delete originals
rbe convert --format-out mp3 --playlist "Export" --yes --delete-originals all

# Keep originals when converting to AIFF
rbe convert --format-out aiff --format flac --yes --delete-originals none

# Get just the IDs of files that would be converted
rbe convert --format-out aiff --format flac --print ids --dry-run

# Convert everything a search finds
rbe search --artist "Lauryn Hill" --print ids | rbe convert --yes
```

### Guardrails
- Without flags, `convert` shows every planned change and asks once before applying. `--interactive` confirms each track individually; `--dry-run` previews without writing; `--yes` confirms the default choice for all prompts without asking.
- Editing while Rekordbox is open risks corrupting your database. By default `convert` warns and asks for confirmation (defaulting to no, so a `--yes` would exit); in a non-interactive mode (e.g. `--print ids`) it throws an error.
- Before a large run, walk through the checklist in [What Should I Do Before Converting?](../faqs.md#what-should-i-do-before-converting)

## Reference

::: mkdocs-click
    :module: rekordbox_edit.cli.convert
    :command: convert_command
    :prog_name: rbe convert
    :depth: 1
