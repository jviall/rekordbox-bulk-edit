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
    
    # Check command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "read":
            print("Running database reader...")
            try:
                from rekordbox_reader import main as reader_main
                reader_main()
            except ImportError as e:
                print(f"Error importing rekordbox_reader: {e}")
                print("Make sure you've installed the dependencies with: pip install -r requirements.txt")
            except Exception as e:
                print(f"Error running database reader: {e}")
                
        elif command == "convert":
            print("Running FLAC to AIFF converter...")
            try:
                from converter import main as converter_main
                converter_main()
            except ImportError as e:
                print(f"Error importing converter: {e}")
                print("Make sure you've installed the dependencies with: pip install -r requirements.txt")
                print("You may need to install ffmpeg on your system as well.")
            except Exception as e:
                print(f"Error running converter: {e}")
        else:
            print(f"Unknown command: {command}")
            print("Available commands:")
            print("  python main.py read     - Read and display RekordBox database content")
            print("  python main.py convert  - Convert FLAC files to AIFF format")
    else:
        print("Available commands:")
        print("  python main.py read     - Read and display RekordBox database content") 
        print("  python main.py convert  - Convert FLAC files to AIFF format")
        print()
        print("Requirements:")
        print("  - ffmpeg must be installed on your system")
        print("  - RekordBox must be closed during conversion")

if __name__ == "__main__":
    main()
