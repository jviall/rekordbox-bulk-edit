# rekordbox-bulk-edit

[![Tests](https://img.shields.io/github/actions/workflow/status/jviall/rekordbox-bulk-edit/ci.yml?branch=main&logo=github&style=flat)](https://github.com/jviall/rekordbox-bulk-edit/blob/main/.github/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/jviall/rekordbox-bulk-edit/graph/badge.svg?token=ILZ1XHE61V)](https://codecov.io/gh/jviall/rekordbox-bulk-edit)
[![Version](https://img.shields.io/pypi/v/rekordbox-bulk-edit?style=flat)](https://pypi.org/project/rekordbox-bulk-edit/)
[![Platforms](https://img.shields.io/badge/platform-win%20%7C%20osx-blue?style=flat)](https://pypi.org/project/rekordbox-bulk-edit/)
[![License](https://img.shields.io/pypi/l/rekordbox-bulk-edit?color=lightgrey)](https://github.com/jviall/rekordbox-bulk-edit/blob/main/LICENSE)

A command-line tool for bulk operations on your Rekordbox library. Convert audio formats, search tracks, and update your database while preserving all your cues, analysis, and metadata.

## Installation

```bash
pip install rekordbox-bulk-edit
```

**Requirements:**

- Python 3.11+
- FFmpeg (for audio conversion)

### Installing FFmpeg

**macOS (Homebrew):**

```bash
brew install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**

```bash
winget install --id=Gyan.FFmpeg -e
```

Or download from [ffmpeg.org](https://ffmpeg.org/download.html).

## Quick Start

Search your library:

```bash
rekordbox-bulk-edit search --artist "Daft Punk" --format flac
rbe search --playlist "House Favorites"
```

Convert audio files:

```bash
# Preview what would be converted
rbe convert --artist "Daft Punk" --dry-run

# Convert all FLAC or WAV files to AIFF (default output format)
rbe convert --format flac --format wav --yes

# Convert all AIFF files in the playlist named 'ConvertMe' to MP3 without asking for confirmation
rbe convert --format AIFF --exact-playlist "ConvertMe" --match-all --out-format mp3 --yes
```

## Commands

### search

Find and display information on tracks in your Rekordbox database.

```bash
rbe search [OPTIONS]
```

**Examples:**

```bash
# Show all FLAC tracks by artist
rbe search --artist "Aphex Twin" --format flac

# Get track IDs for scripting
rbe search --playlist "Techno" --print ids

# Find tracks matching ALL filters (AND logic)
rbe search --artist "Burial" --album "Untrue" --match-all
```

### convert

Convert audio files between formats and update the Rekordbox database. Your cues, analysis, beatgrids, and all metadata are preserved.

```bash
rbe convert [OPTIONS]
```

**Supported formats:**

- Input: FLAC, AIFF, WAV (lossless only)
- Output: AIFF, FLAC, WAV, ALAC (lossless) or MP3 (320kbps CBR)

**Key options:**

- `--format-out [aiff|flac|wav|alac|mp3]`: Output format (default: aiff)
- `--dry-run`: Preview changes without converting.
- `--yes, -y`: Skip confirmation prompt
- `--interactive, -i`: Confirm each file individually
- `--delete`: Delete original files after conversion (default for lossless output)
- `--keep`: Keep original files after conversion (default for MP3 output)
- `--overwrite`: Replace existing output files instead of skipping

By default the original files will be kept when performing a lossy conversion to mp3, and deleted when performing a lossless conversion (since you can always convert back).
You can override this behavior with `--delete` or `--keep`.

**Examples:**

```bash
# Preview conversion
rbe convert --format-out aiff --format flac --dry-run

# Convert and skip confirmation
rbe convert --format-out wav --artist "Burial" --yes

# Convert to MP3 but delete originals
rbe convert --format-out mp3 --playlist "Export" --yes --delete

# Keep originals when converting to AIFF
rbe convert --format-out aiff --format flac --yes --keep

# Scripting: get IDs of files that would be converted
rbe convert --format-out aiff --format flac --print ids --dry-run

# Scripting: convert and get IDs of converted files
rbe convert --format-out aiff --format flac --print ids --yes
```

## Filters & Options

Both commands support all filters. Multiple values create an OR filter unless `--match-all` is used.

**Track filters:**

- `--track-id ID`: Filter by database track ID
- `--title TEXT`: Track title contains TEXT
- `--exact-title TEXT`: Track title exactly matches TEXT
- `--artist TEXT`: Artist name contains TEXT
- `--exact-artist TEXT`: Artist name exactly matches TEXT
- `--album TEXT`: Album name contains TEXT
- `--exact-album TEXT`: Album name exactly matches TEXT
- `--playlist TEXT`: Playlist name contains TEXT
- `--exact-playlist TEXT`: Playlist name exactly matches TEXT
- `--format [mp3|flac|aiff|wav|m4a]`: File format matches
- `--match-all`: Use AND logic (all filters must match)
- `ids` args: Specifying any other input to a command that is not a defined option is interpreted as one or more Track IDs. This is useful for scripting.

**Examples:**

```bash
# Get tracks by multiple artists
rbe search --artist "Daft Punk" --artist "Justice"

# Get tracks matching artist AND format
rbe search --artist "Aphex Twin" --format flac --match-all

# Get all the songs in this playlist
rbe search --exact-playlist "Main Room 2024"

# Get all the songs in all my "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# Find all the songs in all my "house" or "disco" playlists
rbe search --playlist "house" --playlist "disco"

# Find all the songs in my library that aren't in any playlist
rbe search --playlist ""
```

## Output

All commands support all levels of output. These generally control how much information is printed out to the screen, and also offer some options useful for scripting.

Output levels are configured with the `--print` option:

- `--print [ids|silent|info]`: Control output format

> **Note**: When specifying `--print silent` or `--print ids`, you must also provide either the `--yes` or the `--dry-run` flag, since any prompts would contradict the spirit of those options.

### Scripting

The `--print ids` option is especially interesting when used in conjunction with the `ids` arguments. By specifying `--print ids` you can use the output of one `rbe` command as the input to a second, e.g.:

```bash
# Convert all of the items found by the inital search command
rbe search --artist "Lauren Hill" --print ids | rbe convert
```

This is example is a bit contrived, but I have fun ideas for future commands that will make this much more interesting :)

## Safety & Best Practices

> **CAUTION**: This tool can modify your Rekordbox database and audio files. Always back up your data first.

**Before using this tool:**

1. **Back up your Rekordbox database**
   - Rekordbox creates backups on exit, but they get overwritten quickly on repetitive exits.
   - Manually copy all database backups before running this tool
   - Location: `~/Library/Pioneer/rekordbox/` (macOS) or `%APPDATA%\Pioneer\rekordbox\` (Windows)
2. **Back up your music library**
3. **Test on a subset first**
   - Use filters to target a few tracks: `--artist "Test" --limit 5`
   - Always run with `--dry-run` first
4. **Close Rekordbox before running commands**

**Use at your own risk.**

## Credits

This project exists thanks to [pyrekordbox](https://github.com/dylanljones/pyrekordbox), which provides the Python API for Rekordbox databases.

I built this tool to fix my own library management mistakes. If it helps you too, great. If you find issues or have ideas, contributions are welcome.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and contribution guidelines.
