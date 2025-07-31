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

        # First, let's examine all available fields on a sample record
        if content_list:
            print("Examining all fields in content records...\n")
            sample_content = content_list[0]
            all_fields = [
                attr for attr in dir(sample_content) if not attr.startswith("_")
            ]

            # Identify potentially relevant fields for file conversion
            file_related_fields = []
            for field in all_fields:
                field_lower = field.lower()
                if any(
                    keyword in field_lower
                    for keyword in [
                        "file",
                        "path",
                        "type",
                        "format",
                        "extension",
                        "bit",
                        "sample",
                    ]
                ):
                    try:
                        value = getattr(sample_content, field)
                        if value is not None:
                            file_related_fields.append(field)
                    except:
                        pass

            print("File-related fields found:")
            for field in file_related_fields:
                print(f"  - {field}")
            print()

        # Build dynamic header
        base_columns = ["ID", "File Name", "Type", "Full Path"]
        additional_columns = [
            field
            for field in file_related_fields
            if field not in ["ID", "FileNameL", "FileType", "FolderPath"]
        ]

        # Print header
        header_parts = [
            f"{'ID':<10}",
            f"{'File Name':<30}",
            f"{'Type':<5}",
            f"{'Full Path':<40}",
        ]
        header_parts.extend([f"{field[:12]:<12}" for field in additional_columns])
        print(" ".join(header_parts))

        separator_length = (
            10 + 30 + 5 + 40 + (12 * len(additional_columns)) + len(header_parts) - 1
        )
        print("-" * separator_length)

        # Display information for each track
        for content in content_list:
            file_name = content.FileNameL or "N/A"
            file_type = format_file_type(content.FileType)
            full_path = content.FolderPath or "N/A"

            # Abbreviate middle of long strings to preserve important parts (like extensions)
            file_name = (
                (file_name[:12] + "..." + file_name[-15:])
                if len(file_name) > 30
                else file_name
            )
            full_path = (
                (full_path[:20] + "..." + full_path[-17:])
                if len(full_path) > 40
                else full_path
            )

            # Build row data
            row_parts = [
                f"{content.ID:<10}",
                f"{file_name:<30}",
                f"{file_type:<5}",
                f"{full_path:<40}",
            ]

            # Add additional field values
            for field in additional_columns:
                try:
                    value = getattr(content, field)
                    if value is None or "":
                        value = "--"
                    else:
                        value = str(value)

                    # Truncate to 20 characters
                    if len(value) > 12:
                        value = value[:9] + "..."

                    row_parts.append(f"{value:<12}")
                except:
                    row_parts.append(f"{'ERROR':<12}")

            print(" ".join(row_parts))

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
