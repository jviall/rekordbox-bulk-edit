# convert

Convert audio files between formats and update the Rekordbox database to point at the new files. Your cues, analysis, beatgrids, and all metadata are preserved.

## Supported Formats

- **Input:** FLAC, AIFF, WAV (hi-res only — lossy-compressed sources are skipped)
- **Output:** AIFF (default), FLAC, WAV, or MP3 (320kbps CBR)

Tracks already in the target format are skipped, as are tracks whose output file already exists (override with `--overwrite`).

## Originals: Delete or Keep

`--delete-originals` controls what happens to the source file after a successful conversion:

- `lossless` (default) — delete the original when converting to a hi-res format (you can always convert back); keep it when converting to MP3 (the quality loss is one-way)
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
- Editing while Rekordbox is open risks corrupting your database. By default `convert` warns; in a non-interactive mode (e.g. `--print ids`) it throws an error.

## Reference

::: mkdocs-click
    :module: rekordbox_edit.cli.convert
    :command: convert_command
    :prog_name: rbe convert
    :depth: 1
