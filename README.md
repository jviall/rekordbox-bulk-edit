# Rekordbox Bulk Edit

[![Tests](https://img.shields.io/github/actions/workflow/status/jviall/rekordbox-bulk-edit/ci.yml?branch=main&logo=github&style=flat)](https://github.com/jviall/rekordbox-bulk-edit/blob/main/.github/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/jviall/rekordbox-bulk-edit/branch/main/graph/badge.svg)](https://app.codecov.io/gh/jviall/rekordbox-bulk-edit/tree/main)
[![Version](https://img.shields.io/pypi/v/rekordbox-bulk-edit?style=flat)](https://pypi.org/project/rekordbox-bulk-edit/)
[![Platforms](https://img.shields.io/badge/platform-win%20%7C%20osx-blue?style=flat)](https://pypi.org/project/rekordbox-bulk-edit/)
[![License](https://img.shields.io/pypi/l/rekordbox-bulk-edit?color=lightgrey)](https://github.com/jviall/rekordbox-bulk-edit/blob/main/LICENSE)

A command-line tool for bulk editing and managing Rekordbox music files and database records

[!CAUTION]
**ALWAYS BACK UP YOUR DATA BEFORE USING THIS TOOL!**

This tool directly modifies your Rekordbox database and can potentially move, rename, or delete your music files. While there are safety checks, unexpected issues could result in data loss. Before using this tool, consider some or all of the following:

- Always backup your Rekordbox database. While some versions of RB make backups for you, you'll likely be opening and closing RB often, which will make a new backup everytime, causing you to quickly lose your backup history and render them only as useful as the last time you opened RB. Before beginning development, I recommend you make copies of all the backups so that RB doesn't overwrite them.
- Creating a backup of your entire music library
- Test the tool on a small subset of files first using a filter option
- Use the `--dry-run` option to preview changes before applying them

**Use this tool at your own risk.**

## Credits

I made this project to help me correct poor decisions and bad habits in my library management, but it's only possible thanks to [pyrekordbox](https://github.com/dylanljones/pyrekordbox), which provides a comprehensive Python API into Rekordbox databases and XML files.

## Features

- **Convert**: Convert between lossless audio formats (FLAC, AIFF, WAV) and MP3, updating Rekordbox database records accordingly
- **Read**: Read and display track information from Rekordbox database with format filtering support

## Installation

```bash
pip install rekordbox-bulk-edit
```

**Requirements:**

- Python 3.11+
- FFmpeg (for audio conversion)

### Installing FFmpeg

Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use a package manager

**macOS (using Homebrew):**

```bash
brew install ffmpeg
```

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**

```bash
winget install --id=Gyan.FFmpeg  -e
```

## Usage

The tool provides a command-line interface with the following commands:

### Convert

Convert between lossless audio formats (FLAC, AIFF, WAV) or from lossless to 320 CBR MP3, and then update the Rekordbox database accordingly--keeping your analysis, cues, and track metadata intact

```bash
rekordbox-bulk-edit convert [OPTIONS]
```

**Supported Conversions:**

- **Input formats**: FLAC, AIFF, WAV
- **Output formats**: AIFF, FLAC, WAV, MP3

(It only makes sense to convert lossless files, else it's lossy-to-lossy compression)

**Options:**

- `--format [aiff|flac|wav|mp3]`: Choose output format (default: aiff)
- `--dry-run`: Preview changes without actually performing them
- `--auto-confirm`: Skip confirmation prompts (use with caution)

### Read Track Information

Display detailed information about tracks in your Rekordbox database:

```bash
rekordbox-bulk-edit read [OPTIONS]
```

**Options:**

- `--track-id ID`: Specify a particular track ID to read
- `--format [mp3|flac|aiff|wav|m4a]`: Filter by audio format (shows all formats if not specified)
- `--verbose, -v`: Show detailed information

### General Options

- `--version`: Show the version number
- `--help`: Show help information

## Contributing

Interested in contributing? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for development setup instructions, coding guidelines, and how to submit changes.

## Requirements

- Python 3.11+
- FFmpeg for audio conversion
- Rekordbox database access

```

```
