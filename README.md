# Rekordbox Bulk Edit

A command-line tool for bulk editing and managing Rekordbox music files and database records.

## Features

- **Convert**: Convert FLAC files to AIFF or MP3 format and update Rekordbox database records accordingly
- **Read**: Read and display track information from Rekordbox database
- **Audio Analysis**: Get detailed audio file information including format, bitrate, and metadata

## Installation

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   ```

2. Activate the virtual environment:
   ```bash
   source venv/bin/activate  # On macOS/Linux
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Install the package:
   ```bash
   pip install -e .
   ```

## Usage

The tool provides a command-line interface with the following commands:

### Convert FLAC to AIFF/MP3
Convert FLAC files to AIFF or MP3 format and update the Rekordbox database:

```bash
rekordbox-bulk-edit convert [OPTIONS]
```

Options:
- `--format [aiff|mp3]`: Choose output format (default: aiff)
- `--dry-run`: Preview changes without actually performing them
- `--auto-confirm`: Skip confirmation prompts (use with caution)

### Read Track Information
Display detailed information about tracks in your Rekordbox database:

```bash
rekordbox-bulk-edit read [OPTIONS]
```

Options:
- `--track-id ID`: Specify a particular track ID to read
- `--verbose`: Show detailed information

### General Options
- `--version`: Show the version number
- `--help`: Show help information

## Examples

```bash
# Preview FLAC to AIFF conversion without making changes
rekordbox-bulk-edit convert --dry-run

# Convert FLAC files to MP3 format
rekordbox-bulk-edit convert --format mp3

# Convert files with automatic confirmation
rekordbox-bulk-edit convert --auto-confirm

# Read information for a specific track
rekordbox-bulk-edit read --track-id 12345 --verbose

# Show all available commands
rekordbox-bulk-edit --help
```

## Development

- Add new dependencies to `requirements.txt`
- Activate your virtual environment before working: `source venv/bin/activate`
- Deactivate when done: `deactivate`
- Install in development mode: `pip install -e .`

## Requirements

- Python 3.6+
- Rekordbox database access
- Audio processing capabilities for FLAC/AIFF conversion
