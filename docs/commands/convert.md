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

## Converting Several Files at Once

`convert` operates on four files at a time by default so long as your CPU has the cores to do so. You can customize this by passing `--threads N` (or `-t N`), with your CPU's number of cores as an upper limit.

Depending on your environment and target format, your mileage with more or less threads will vary. MP3 output speeds up close to linearly with more threads due to `libmp3lame` being a single-threaded process, whereas FLAC gains about a 50% with. WAV and AIFF outputs only see minor benefits, as `ffmpeg` already multithreads their decoding, and they don't require any encoding step. As such, you'll likely be limited by I/O speed rather than CPU when converting to WAV/AIFF.

If you're converting across a network (like a mapped drive), more threads will likely only slow you down as each thread competes for network capacity, but if you're converting on a local drive it is likely to improve performance at least somewhat.

## Interrupted Runs

If a run stops partway, whether from a conversion failure, a full disk, or a Ctrl-C, everything it finished is kept and nothing is left half-converted. `convert` tells you which file it stopped on, how many converted, and how many it never got to. Rerun the same command to pick up where it left off.

A track whose file has moved or been deleted since the preview is skipped, and the rest of the batch continues.

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

# Max out your CPU to handle a batch of MP3s
rbe convert --format-out mp3 --playlist "NeedsConverting" --threads 8 --yes
```

### Checks

- Without flags, `convert` shows every planned change and asks once before applying. `--interactive` confirms each track individually; `--dry-run` previews without writing; `--yes` confirms the default choice for all prompts without asking. `--interactive` cannot be combined with `--yes` or `--dry-run`.
- `convert` will encode exactly the tracks the preview showed. If in between the time you're prompted and later confirm a new track that matches your filters lands in your library, it won't be included.
- **Rekordbox running:** Writing while Rekordbox is open risks losing your changes, so `convert` will refuse to perform any writes. `--dry-run` is unaffected.
- Before a large run, walk through the checklist in [What Should I Do Before Converting?](../faqs.md#what-should-i-do-before-converting)

## Reference

<!-- prettier-ignore -->
::: mkdocs-click
    :module: rekordbox_edit.cli.convert
    :command: convert_command
    :prog_name: rbe convert
    :depth: 1
