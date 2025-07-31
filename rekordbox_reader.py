#!/usr/bin/env python3
"""
RekordBox Database Reader

This script reads the djmdContent table from RekordBox database
and displays file information including file names, track names, and file formats.
"""

from pyrekordbox import Rekordbox6Database


def format_file_type(file_type_code):
    """Convert file type code to human readable format"""
    file_type_map = {0: "MP3", 1: "MP3", 4: "M4A", 5: "FLAC", 11: "WAV", 12: "AIFF"}
    return file_type_map.get(file_type_code, f"Unknown ({file_type_code})")


def main():
    try:
        # Connect to RekordBox database
        print("Connecting to RekordBox database...")
        db = Rekordbox6Database()

        print("Reading djmdContent table...")

        # Get all content from the database
        all_content = db.get_content()

        # Filter to only include FLAC files (FileType == 5)
        content_list = [content for content in all_content if content.FileType == 5]

        print(
            f"Found {len(content_list)} FLAC files in database (out of {all_content.count()} total tracks)\n"
        )

        # Print header
        print(
            f"{'ID':<10} {'File Name':<30} {'Track Title':<30} {'Type':<5} {'Full Path':<40}"
        )
        print("-" * 120)

        # Display information for each track
        for content in content_list:
            file_name = content.FileNameL or "N/A"
            track_title = content.Title or "N/A"
            file_type = format_file_type(content.FileType)
            full_path = content.FolderPath or "N/A"

            # Abbreviate middle of long strings to preserve important parts (like extensions)
            file_name = (
                (file_name[:12] + "..." + file_name[-15:])
                if len(file_name) > 30
                else file_name
            )
            track_title = (
                (track_title[:15] + "..." + track_title[-12:])
                if len(track_title) > 30
                else track_title
            )
            full_path = (
                (full_path[:20] + "..." + full_path[-17:])
                if len(full_path) > 40
                else full_path
            )

            print(
                f"{content.ID:<10} {file_name:<30} {track_title:<30} {file_type:<5} {full_path:<40}"
            )

        # Summary
        print(f"\nTotal FLAC files found: {len(content_list)}")

        if not content_list:
            print("No FLAC files found in the database.")

    except Exception as e:
        print(f"Error accessing RekordBox database: {e}")
        print("\nTroubleshooting tips:")
        print("1. Make sure RekordBox is closed")
        print("2. Ensure you have the correct database key (for RekordBox 6.6.5+)")
        print("3. Check if pyrekordbox can find your RekordBox installation")

        # Try to show configuration
        try:
            from pyrekordbox import show_config

            print("\nCurrent pyrekordbox configuration:")
            show_config()
        except:
            pass


if __name__ == "__main__":
    main()
