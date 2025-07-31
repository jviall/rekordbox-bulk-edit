# Rekordbox Bulk Edit

A command-line tool for bulk editing and managing Rekordbox music files and database records.

## Features

- **Convert**: Convert between lossless audio formats (FLAC, AIFF, WAV) and MP3, updating Rekordbox database records accordingly
- **Read**: Read and display track information from Rekordbox database with format filtering support
- **Audio Analysis**: Get detailed audio file information including format, bitrate, and metadata
- **Safety Checks**: Automatically detects running Rekordbox instances to prevent database corruption
- **Smart Filtering**: Skips files already in target format and excludes lossy formats from conversion input
- **Bit Depth Preservation**: Maintains original bit depth (16/24/32-bit) for lossless conversions

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

### Convert Audio Formats

Convert between lossless audio formats (FLAC, AIFF, WAV) and MP3, updating the Rekordbox database:

```bash
rekordbox-bulk-edit convert [OPTIONS]
```

**Supported Conversions:**

- **Input formats**: FLAC, AIFF, WAV (lossless formats only)
- **Output formats**: AIFF, FLAC, WAV, MP3
- **Automatic detection**: Skips MP3/M4A files and files already in target format
- **Safety check**: Exits if Rekordbox is running to prevent database conflicts

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

## Examples

```bash
# Preview lossless to AIFF conversion without making changes
rekordbox-bulk-edit convert --dry-run

# Convert lossless files to MP3 format
rekordbox-bulk-edit convert --format mp3

# Convert lossless files to FLAC format
rekordbox-bulk-edit convert --format flac

# Convert files with automatic confirmation
rekordbox-bulk-edit convert --auto-confirm

# Read information for a specific track
rekordbox-bulk-edit read --track-id 12345 --verbose

# Show only FLAC files in database
rekordbox-bulk-edit read --format flac

# Show only MP3 files in database
rekordbox-bulk-edit read --format mp3

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
