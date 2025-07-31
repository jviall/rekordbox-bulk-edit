#!/usr/bin/env python3
"""
RekordBox FLAC to AIFF Converter

Main entry point for the application.
This tool helps convert FLAC files to AIFF format and updates RekordBox database accordingly.
"""

import sys
import os

def main():
    print("RekordBox FLAC to AIFF Converter")
    print("=" * 35)
    print()
    
    # Check if we should run the database reader
    if len(sys.argv) > 1 and sys.argv[1] == "read":
        print("Running database reader...")
        try:
            # Import and run the reader
            from rekordbox_reader import main as reader_main
            reader_main()
        except ImportError as e:
            print(f"Error importing rekordbox_reader: {e}")
            print("Make sure you've installed the dependencies with: pip install -r requirements.txt")
        except Exception as e:
            print(f"Error running database reader: {e}")
    else:
        print("Available commands:")
        print("  python main.py read    - Read and display RekordBox database content")
        print()
        print("Future functionality:")
        print("  - Convert FLAC files to AIFF using ffmpeg")
        print("  - Update RekordBox database file paths and types")
        print("  - Backup and restore database functionality")

if __name__ == "__main__":
    main()
