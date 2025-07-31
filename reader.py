#!/usr/bin/env python3
"""
RekordBox Database Reader

This script reads the djmdContent table from RekordBox database
and displays file information for specific fields.
"""

import sys

from pyrekordbox import Rekordbox6Database


def format_file_type(file_type_code):
    """Convert file type code to human readable format"""
    file_type_map = {0: "MP3", 1: "MP3", 4: "M4A", 5: "FLAC", 11: "WAV", 12: "AIFF"}
    return file_type_map.get(file_type_code, f"Unk({file_type_code})")


def print_track_info(content_list):
    """Print formatted track information"""
    if not content_list:
        print("No tracks found.")
        return

    # Column widths (total ≈ 240 chars with spacing)
    widths = {
        "id": 10,
        "filename": 40,
        "type": 8,
        "sample_rate": 14,
        "bitrate": 8,
        "bit_depth": 8,
        "location": 70,
    }

    # Print header
    header = (
        f"{'ID':<{widths['id']}}   "
        f"{'File Name':<{widths['filename']}}   "
        f"{'Type':<{widths['type']}}   "
        f"{'Sample Rate':<{widths['sample_rate']}}   "
        f"{'BtRt':<{widths['bitrate']}}   "
        f"{'BDp':<{widths['bit_depth']}}   "
        f"{'Location':<{widths['location']}}"
    )

    print(header)
    print("-" * len(header))

    # Print each track
    for content in content_list:
        # Get values with fallbacks
        track_id = str(content.ID or "")
        filename = content.FileNameL or "N/A"
        file_type = format_file_type(content.FileType)

        # Get sample rate
        value = content.SampleRate
        if value and value != 0:
            sample_rate = str(value)
        else:
            sample_rate = "--"

        # Get bitrate
        value = content.BitRate
        if value or value == 0:
            bitrate = str(value)
        else:
            bitrate = "--"

        # Get bit depth
        value = content.BitDepth
        if value or value == 0:
            bit_depth = str(value)
        else:
            bit_depth = "--"

        location = content.FolderPath or "N/A"

        # Truncate long values in the middle
        if len(filename) > widths["filename"]:
            available = widths["filename"] - 3  # Reserve 3 chars for "..."
            start_chars = available // 2
            end_chars = available - start_chars
            filename = filename[:start_chars] + "..." + filename[-end_chars:]
        if len(location) > widths["location"]:
            available = widths["location"] - 3  # Reserve 3 chars for "..."
            start_chars = available // 2
            end_chars = available - start_chars
            location = location[:start_chars] + "..." + location[-end_chars:]

        # Print row
        row = (
            f"{track_id:<{widths['id']}}   "
            f"{filename:<{widths['filename']}}   "
            f"{file_type:<{widths['type']}}   "
            f"{sample_rate:<{widths['sample_rate']}}   "
            f"{bitrate:<{widths['bitrate']}}   "
            f"{bit_depth:<{widths['bit_depth']}}   "
            f"{location:<{widths['location']}}"
        )

        print(row)


def get_track_info(track_id=None):
    """Get track information from database. Returns list of matching tracks."""
    try:
        db = Rekordbox6Database()
        all_content = db.get_content()

        if track_id:
            # Find specific track
            content_list = [
                content for content in all_content if content.ID == int(track_id)
            ]
        else:
            # Get all FLAC files
            content_list = [content for content in all_content if content.FileType == 5]

        return content_list

    except Exception as e:
        print(f"Error accessing RekordBox database: {e}")
        return []


def main():
    """Main function with optional trackId argument"""
    track_id = None

    # Check for trackId argument
    if len(sys.argv) > 1:
        try:
            track_id = int(sys.argv[1])
            print(f"Looking for track ID: {track_id}")
        except ValueError:
            print(f"Error: '{sys.argv[1]}' is not a valid track ID")
            sys.exit(1)
    else:
        print("Reading all FLAC files from RekordBox database...")

    print("Connecting to RekordBox database...")

    content_list = get_track_info(track_id)

    if track_id and not content_list:
        print(f"Track ID {track_id} not found.")
        return

    if not track_id:
        print(f"Found {len(content_list)} FLAC files\n")
    else:
        print()

    print_track_info(content_list)

    if not track_id:
        print(f"\nTotal FLAC files: {len(content_list)}")


if __name__ == "__main__":
    main()
