#!/usr/bin/env python3
"""
FLAC to AIFF Converter

Converts FLAC files to AIFF format using ffmpeg and updates RekordBox database.
"""

import os
import sys
from pathlib import Path

import ffmpeg
from pyrekordbox import Rekordbox6Database

from reader import print_track_info


def get_audio_info(file_path):
    """Get audio information from file using ffmpeg probe"""
    try:
        probe = ffmpeg.probe(file_path)
        audio_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "audio"),
            None,
        )
        if audio_stream:
            # Try multiple ways to get bit depth
            bit_depth = 16  # default

            # Method 1: bits_per_sample
            if (
                "bits_per_sample" in audio_stream
                and audio_stream["bits_per_sample"] != 0
            ):
                bit_depth = int(audio_stream["bits_per_sample"])
            # Method 2: bits_per_raw_sample
            elif (
                "bits_per_raw_sample" in audio_stream
                and audio_stream["bits_per_raw_sample"] != 0
            ):
                bit_depth = int(audio_stream["bits_per_raw_sample"])
            # Method 3: parse from sample_fmt (e.g., "s16", "s24", "s32")
            elif "sample_fmt" in audio_stream:
                sample_fmt = audio_stream["sample_fmt"]
                if "16" in sample_fmt:
                    bit_depth = 16
                elif "24" in sample_fmt:
                    bit_depth = 24
                elif "32" in sample_fmt:
                    bit_depth = 32

            return {
                "bit_depth": bit_depth,
                "sample_rate": int(audio_stream.get("sample_rate", 44100)),
                "channels": int(audio_stream.get("channels", 2)),
            }
    except Exception as e:
        print(f"Warning: Could not probe {file_path}: {e}")

    # Return defaults if probe fails
    return {"bit_depth": 16, "sample_rate": 44100, "channels": 2}


def convert_flac_to_aiff(flac_path, aiff_path):
    """Convert FLAC file to AIFF using ffmpeg, preserving bit depth"""
    try:
        # Get original audio info
        audio_info = get_audio_info(flac_path)
        bit_depth = audio_info["bit_depth"]

        # Map bit depth to appropriate PCM codec
        codec_map = {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"}

        codec = codec_map.get(bit_depth, "pcm_s16be")  # Default to 16-bit if unknown

        print(f"  Converting with {bit_depth}-bit depth using codec: {codec}")

        (
            ffmpeg.input(flac_path)
            .output(aiff_path, acodec=codec)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        print(f"FFmpeg error converting {flac_path}: {e}")
        if e.stderr:
            print(f"FFmpeg stderr output:\n{e.stderr.decode()}")
        return False
    except Exception as e:
        print(f"Error converting {flac_path}: {e}")
        return False


def update_database_record(db, content_id, new_filename, new_folder):
    """Update database record with new AIFF file information"""
    try:
        # Get the content record
        content = db.get_content().filter_by(ID=content_id).first()
        if not content:
            raise Exception(f"Content record with ID {content_id} not found")

        # Get bit depth of converted AIFF file
        aiff_full_path = os.path.join(new_folder, new_filename)
        converted_audio_info = get_audio_info(aiff_full_path)
        converted_bit_depth = converted_audio_info["bit_depth"]

        # Compare with bit depth stored in database
        # Try common field names for bit depth
        database_bit_depth = None
        if hasattr(content, "BitDepth"):
            database_bit_depth = getattr(content, "BitDepth")

        if database_bit_depth and converted_bit_depth != database_bit_depth:
            raise Exception(
                f"Bit depth mismatch: database shows {database_bit_depth}-bit, converted file is {converted_bit_depth}-bit"
            )

        if database_bit_depth:
            print(
                f"  ✓ Bit depth verification passed: {converted_bit_depth}-bit matches database"
            )
        else:
            print(
                f"  ⚠ Warning: Could not verify bit depth - no bit depth field found in database"
            )

        # Update relevant fields
        content.FileNameL = new_filename
        content.FolderPath = aiff_full_path
        content.FileType = 12  # AIFF file type

        # Note: No commit here - will be done centrally
        return True

    except Exception as e:
        print(f"Error updating database record {content_id}: {e}")
        raise  # Re-raise to be handled by caller


class UserQuit(Exception):
    """Exception raised when user chooses to quit"""
    pass


def confirm(question, default_yes=True):
    """Ask a yes/no question with default, or Q to quit"""
    default_prompt = "[Y/n/q]" if default_yes else "[y/N/q]"
    while True:
        response = input(f"{question} {default_prompt}: ").strip().lower()
        if not response:
            return default_yes
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        if response in ["q", "quit"]:
            raise UserQuit("User chose to quit")
        print("Please enter 'y', 'n', or 'q' to quit")


def main():
    """Main conversion function"""
    try:
        print("FLAC to AIFF Converter")
        print("=" * 21)
        print()

        # Connect to RekordBox database
        print("Connecting to RekordBox database...")
        db = Rekordbox6Database()

        # Check if we have a valid session early on
        if not db.session:
            print("ERROR: No database session available")
            print("ABORTING: Cannot continue without database access")
            sys.exit(1)

        # Get all FLAC files
        print("Finding FLAC files...")
        all_content = db.get_content()
        flac_files = [content for content in all_content if content.FileType == 5]

        print(f"Found {len(flac_files)} FLAC files to convert")

        if not flac_files:
            print("No FLAC files found. Exiting.")
            return

        # Process each file
        converted_files = []  # Track converted files for potential deletion

        for i, content in enumerate(flac_files, 1):
            flac_file_name = content.FileNameL or ""
            flac_full_path = content.FolderPath or ""
            flac_folder = os.path.dirname(flac_full_path)

            print(f"\nProcessing {i}/{len(flac_files)}")

            # Show detailed track information
            print_track_info([content])
            print()

            # Check if FLAC file exists
            if not os.path.exists(flac_full_path):
                print(f"ERROR: FLAC file not found: {flac_full_path}")
                print("ABORTING: Cannot continue with missing files")
                db.session.rollback()
                sys.exit(1)

            # Generate AIFF filename and path
            flac_path_obj = Path(flac_file_name)
            aiff_filename = flac_path_obj.stem + ".aiff"
            aiff_full_path = os.path.join(flac_folder, aiff_filename)

            # Check if AIFF already exists
            if os.path.exists(aiff_full_path):
                print(f"WARNING: AIFF file already exists: {aiff_full_path}")
                print("ABORTING: Cannot overwrite existing files")
                db.session.rollback()
                sys.exit(1)

            # Ask for confirmation
            try:
                if not confirm(
                    f"Convert track {flac_file_name} to AIFF?", default_yes=True
                ):
                    print("Skipping this file...")
                    continue
            except UserQuit:
                print("User quit. Rolling back database changes and cleaning up...")
                db.session.rollback()
                # Clean up any converted files
                for converted_file in converted_files:
                    try:
                        os.remove(converted_file["aiff_path"])
                        print(f"✓ Cleaned up {converted_file['aiff_path']}")
                    except:
                        pass
                sys.exit(0)

            # Convert file
            print(f"Converting...")
            if not convert_flac_to_aiff(flac_full_path, aiff_full_path):
                print("ABORTING: Conversion failed")
                db.session.rollback()
                # Clean up any converted files
                for converted_file in converted_files:
                    try:
                        os.remove(converted_file["aiff_path"])
                    except:
                        pass
                sys.exit(1)

            # Verify conversion was successful
            if not os.path.exists(aiff_full_path):
                print("ABORTING: Converted file not found after conversion")
                db.session.rollback()
                sys.exit(1)

            # Update database (but don't commit yet)
            print("Updating database record...")
            try:
                update_database_record(db, content.ID, aiff_filename, flac_folder)
                converted_files.append(
                    {
                        "flac_path": flac_full_path,
                        "aiff_path": aiff_full_path,
                        "content_id": content.ID,
                    }
                )
                print(f"✓ Successfully converted and updated database record")
            except Exception as e:
                print(f"ABORTING: Database update failed: {e}")
                db.session.rollback()
                # Clean up converted files
                try:
                    os.remove(aiff_full_path)
                    print("Cleaned up converted file")
                except:
                    print("Failed to clean up converted file")
                sys.exit(1)

        # Handle final commit and cleanup
        if converted_files:
            print(
                f"\n🎉 Successfully converted {len(converted_files)} FLAC files to AIFF format"
            )

            try:
                if confirm("Commit database changes?", default_yes=True):
                    try:
                        db.session.commit()
                        print("✓ Database changes committed successfully")

                        # Ask about deleting FLAC files
                        try:
                            if confirm("Delete original FLAC files?", default_yes=False):
                                deleted_count = 0
                                for file_info in converted_files:
                                    try:
                                        os.remove(file_info["flac_path"])
                                        deleted_count += 1
                                        print(f"✓ Deleted {file_info['flac_path']}")
                                    except Exception as e:
                                        print(
                                            f"⚠ Failed to delete {file_info['flac_path']}: {e}"
                                        )
                                print(
                                    f"Deleted {deleted_count} of {len(converted_files)} FLAC files"
                                )
                            else:
                                print("Original FLAC files preserved")
                        except UserQuit:
                            print("User quit. Original FLAC files preserved.")
                            sys.exit(0)

                    except Exception as e:
                        print(f"FATAL ERROR: Failed to commit database changes: {e}")
                        db.session.rollback()
                        sys.exit(1)
                else:
                    print("Database changes rolled back")
                    db.session.rollback()
                    # Clean up converted AIFF files
                    for file_info in converted_files:
                        try:
                            os.remove(file_info["aiff_path"])
                            print(f"✓ Cleaned up {file_info['aiff_path']}")
                        except:
                            print(f"⚠ Failed to clean up {file_info['aiff_path']}")
            except UserQuit:
                print("User quit. Rolling back database changes and cleaning up...")
                db.session.rollback()
                # Clean up converted AIFF files
                for file_info in converted_files:
                    try:
                        os.remove(file_info["aiff_path"])
                        print(f"✓ Cleaned up {file_info['aiff_path']}")
                    except:
                        pass
                sys.exit(0)
        else:
            print("No files were converted.")

    except Exception as e:
        print(f"FATAL ERROR: {e}")
        try:
            if db.session:
                db.session.rollback()
        except:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
