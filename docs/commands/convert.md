# convert

Convert audio files between formats and update the Rekordbox database to point at the new files. Your cues, analysis, beatgrids, and all metadata are preserved.

## Supported Formats

- **Input:** FLAC, AIFF, WAV (lossless only — lossy sources are skipped)
- **Output:** AIFF (default), FLAC, WAV, ALAC, or MP3 (320kbps CBR)

Tracks already in the target format are skipped, as are tracks whose output file already exists (override with `--overwrite`).

## Originals: Delete or Keep

After a successful conversion the original file is **deleted** for lossless output (you can always convert back) and **kept** for MP3 output (the quality loss is one-way). Override either default with `--delete` or `--keep`.

## Examples

```bash
# Preview conversion
rbe convert --format-out aiff --format flac --dry-run

# Convert and skip confirmation
rbe convert --format-out wav --artist "Burial" --yes

# Convert to MP3 but delete originals
rbe convert --format-out mp3 --playlist "Export" --yes --delete

# Keep originals when converting to AIFF
rbe convert --format-out aiff --format flac --yes --keep

# Get just the IDs of files that would be converted
rbe convert --format-out aiff --format flac --print ids --dry-run

# Convert everything a search finds
rbe search --artist "Lauryn Hill" --print ids | rbe convert --yes
```

`--interactive` confirms each file individually; like `edit`, converting while Rekordbox is open triggers a warning (or a refusal in scripting modes). See [Filtering](../filtering.md) for the full filter language.

## Reference

::: mkdocs-click
    :module: rekordbox_edit.cli.convert
    :command: convert_command
    :prog_name: rbe convert
    :depth: 1
