"""Convert command for rekordbox-bulk-edit."""

import os
import sys
from pathlib import Path

import click
import ffmpeg
from pyrekordbox import Rekordbox6Database

from rekordbox_bulk_edit.utils import (
    FILE_TYPE_TO_NAME,
    FORMAT_TO_FILE_TYPE,
    FORMAT_EXTENSIONS,
    get_audio_info,
    is_rekordbox_running,
    print_track_info,
)


def convert_flac_to_aiff(flac_path, aiff_path):
    """Convert FLAC file to AIFF using ffmpeg, preserving bit depth"""
    try:
        # Get original audio info
        audio_info = get_audio_info(flac_path)
        bit_depth = audio_info["bit_depth"]

        # Map bit depth to appropriate PCM codec
        codec_map = {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"}

        codec = codec_map.get(bit_depth, "pcm_s16be")  # Default to 16-bit if unknown

        click.echo(f"  Converting with {bit_depth}-bit depth using codec: {codec}")

        (
            ffmpeg.input(flac_path)
            .output(aiff_path, acodec=codec)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        click.echo(f"FFmpeg error converting {flac_path}: {e}")
        if e.stderr:
            click.echo(f"FFmpeg stderr output:\n{e.stderr.decode()}")
        return False
    except Exception as e:
        click.echo(f"Error converting {flac_path}: {e}")
        return False


def convert_to_lossless(input_path, output_path, output_format):
    """Convert lossless file to another lossless format using ffmpeg, preserving bit depth"""
    try:
        # Get original audio info
        audio_info = get_audio_info(input_path)
        bit_depth = audio_info["bit_depth"]

        # Configure codec based on output format
        if output_format == "aiff":
            codec_map = {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"}
            codec = codec_map.get(bit_depth, "pcm_s16be")
        elif output_format == "wav":
            codec_map = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}
            codec = codec_map.get(bit_depth, "pcm_s16le")
        elif output_format == "flac":
            codec = "flac"
        elif output_format == "alac":
            codec = "alac"
        else:
            raise Exception(f"Unsupported lossless format: {output_format}")

        click.echo(f"  Converting with {bit_depth}-bit depth using codec: {codec}")

        (
            ffmpeg.input(input_path)
            .output(output_path, acodec=codec)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        click.echo(f"FFmpeg error converting {input_path}: {e}")
        if e.stderr:
            click.echo(f"FFmpeg stderr output:\n{e.stderr.decode()}")
        return False
    except Exception as e:
        click.echo(f"Error converting {input_path}: {e}")
        return False


def convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 using ffmpeg with 320kbps constant bitrate"""
    try:
        click.echo("  Converting to MP3 320kbps CBR")

        (
            ffmpeg.input(input_path)
            .output(mp3_path, acodec="libmp3lame", audio_bitrate="320k")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except ffmpeg.Error as e:
        click.echo(f"FFmpeg error converting {input_path}: {e}")
        if e.stderr:
            click.echo(f"FFmpeg stderr output:\n{e.stderr.decode()}")
        return False
    except Exception as e:
        click.echo(f"Error converting {input_path}: {e}")
        return False


def _verify_bit_depth(content, converted_audio_info):
    """Helper function to verify bit depth matches between database and converted file"""
    converted_bit_depth = converted_audio_info["bit_depth"]
    database_bit_depth = None
    if hasattr(content, "BitDepth"):
        database_bit_depth = getattr(content, "BitDepth")

    if database_bit_depth and converted_bit_depth != database_bit_depth:
        raise Exception(
            f"Bit depth mismatch: database shows {database_bit_depth}-bit, converted file is {converted_bit_depth}-bit"
        )

    if database_bit_depth:
        click.echo(
            f"  ✓ Bit depth verification passed: {converted_bit_depth}-bit matches database"
        )
    else:
        click.echo(
            "  ⚠ Warning: Could not verify bit depth - no bit depth field found in database"
        )


def update_database_record(db, content_id, new_filename, new_folder, output_format):
    """Update database record with new file information"""
    try:
        # Get the content record
        content = db.get_content().filter_by(ID=content_id).first()
        if not content:
            raise Exception(f"Content record with ID {content_id} not found")

        # Get audio info of converted file
        converted_full_path = os.path.join(new_folder, new_filename)
        converted_audio_info = get_audio_info(converted_full_path)
        converted_bitrate = converted_audio_info["bitrate"]

        # Set file type based on output format
        file_type = FORMAT_TO_FILE_TYPE.get(output_format)
        if not file_type:
            raise Exception(f"Unsupported output format: {output_format}")

        # Handle format-specific verification
        if output_format in ["aiff", "flac", "wav"]:
            _verify_bit_depth(content, converted_audio_info)
        elif output_format == "mp3":
            click.echo(f"  ✓ MP3 conversion completed with {converted_bitrate} kbps")

        # Update relevant fields
        content.FileNameL = new_filename
        content.FolderPath = converted_full_path
        content.FileType = file_type
        content.BitRate = converted_bitrate

        click.echo(
            f"  ✓ Updated BitRate from {content.BitRate or 0} to {converted_bitrate}"
        )

        # Note: No commit here - will be done centrally
        return True

    except Exception as e:
        click.echo(f"Error updating database record {content_id}: {e}")
        raise  # Re-raise to be handled by caller


class UserQuit(Exception):
    """Exception raised when user chooses to quit"""

    pass


def confirm(question, default_yes=True):
    """Ask a yes/no question with default, or Q to quit"""
    default_prompt = "[Y/n/q]" if default_yes else "[y/N/q]"
    while True:
        response = (
            click.prompt(f"{question} {default_prompt}", default="", show_default=False)
            .strip()
            .lower()
        )
        if not response:
            return default_yes
        if response in ["y", "yes"]:
            return True
        if response in ["n", "no"]:
            return False
        if response in ["q", "quit"]:
            raise UserQuit("User chose to quit")
        click.echo("Please enter 'y', 'n', or 'q' to quit")


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be converted without actually doing it",
)
@click.option(
    "--auto-confirm", is_flag=True, help="Skip confirmation prompts (use with caution)"
)
@click.option(
    "--format",
    type=click.Choice(["aiff", "flac", "wav", "alac", "mp3"], case_sensitive=False),
    default="aiff",
    help="Output format: 'aiff' / 'flac' / 'wav' / 'alac' / 'mp3' (default: aiff)",
)
def convert_command(dry_run, auto_confirm, format):
    """Convert lossless audio files between formats and update RekordBox database.

    Supports conversion from any lossless format (FLAC, AIFF, WAV) to:
    - AIFF: Preserves original bit depth (16/24/32-bit)
    - FLAC: Lossless compression, preserves bit depth
    - WAV: Uncompressed, preserves original bit depth
    - MP3: 320kbps constant bitrate using LAME encoder

    Skips all lossy formats (MP3/AAC), ALAC, and files already in the target format.
    """
    try:
        click.echo("Lossless Audio Format Converter")
        click.echo("=" * 32)
        click.echo()

        # Check if Rekordbox is running
        click.echo("Checking if Rekordbox is running...")
        is_running, process_name = is_rekordbox_running()
        if is_running:
            click.echo(f"ERROR: Rekordbox is currently running ({process_name})")
            click.echo(
                "Please close Rekordbox before running the convert command to avoid database conflicts."
            )
            sys.exit(1)
        click.echo("✓ Rekordbox is not running")
        click.echo()

        if dry_run:
            click.echo("DRY RUN MODE - No files will be converted or modified")
            click.echo()

        # Connect to RekordBox database
        click.echo("Connecting to RekordBox database...")
        db = Rekordbox6Database()

        # Check if we have a valid session early on
        if not db.session:
            click.echo("ERROR: No database session available")
            click.echo("ABORTING: Cannot continue without database access")
            sys.exit(1)

        # Get all lossless files, excluding MP3s
        click.echo("Finding lossless audio files...")
        all_content = db.get_content()
        lossless_files = [
            content
            for content in all_content
            if content.FileType in [5, 12, 11]  # FLAC, AIFF, WAV
        ]

        # Filter out files already in target format
        target_file_type = FORMAT_TO_FILE_TYPE[format.lower()]
        files_to_convert = [
            content
            for content in lossless_files
            if content.FileType != target_file_type
        ]

        click.echo(f"Found {len(lossless_files)} lossless files total")
        click.echo(
            f"Found {len(files_to_convert)} files to convert to {format.upper()}"
        )

        if len(lossless_files) > len(files_to_convert):
            skipped_count = len(lossless_files) - len(files_to_convert)
            click.echo(
                f"Skipping {skipped_count} files already in {format.upper()} format"
            )

        if not files_to_convert:
            click.echo("No files need conversion. Exiting.")
            return

        if dry_run:
            click.echo("\nFiles that would be converted:")
            print_track_info(files_to_convert)
            return

        # Process each file
        converted_files = []  # Track converted files for potential deletion

        for i, content in enumerate(files_to_convert, 1):
            flac_file_name = content.FileNameL or ""
            flac_full_path = content.FolderPath or ""
            flac_folder = os.path.dirname(flac_full_path)

            click.echo(f"\nProcessing {i}/{len(files_to_convert)}")

            # Show detailed track information
            print_track_info([content])
            click.echo()

            # Check if source file exists
            if not os.path.exists(flac_full_path):
                source_format = FILE_TYPE_TO_NAME.get(content.FileType, "Unknown")
                click.echo(f"ERROR: {source_format} file not found: {flac_full_path}")
                click.echo("ABORTING: Cannot continue with missing files")
                db.session.rollback()
                sys.exit(1)

            # Generate output filename and path
            input_path_obj = Path(flac_file_name)
            output_format_lower = format.lower()

            # Map format to file extension
            extension = FORMAT_EXTENSIONS[output_format_lower]
            output_filename = input_path_obj.stem + extension
            output_full_path = os.path.join(flac_folder, output_filename)

            # Choose converter function
            def converter_func(inp, out):
                if output_format_lower == "mp3":
                    return convert_to_mp3(inp, out)
                else:
                    return convert_to_lossless(inp, out, output_format_lower)

            # Check if output file already exists
            if os.path.exists(output_full_path):
                click.echo(
                    f"WARNING: {format.upper()} file already exists: {output_full_path}"
                )
                click.echo("ABORTING: Cannot overwrite existing files")
                db.session.rollback()
                sys.exit(1)

            # Ask for confirmation
            source_format = FILE_TYPE_TO_NAME.get(content.FileType, "Unknown")
            try:
                if not auto_confirm and not confirm(
                    f"Convert {source_format} track {flac_file_name} to {format.upper()}?",
                    default_yes=True,
                ):
                    click.echo("Skipping this file...")
                    continue
            except UserQuit:
                if converted_files:
                    click.echo("User quit. You have uncommitted database changes.")
                    try:
                        if confirm(
                            "Commit database changes before quitting?", default_yes=True
                        ):
                            try:
                                db.session.commit()
                                click.echo("✓ Database changes committed successfully")

                                # Ask about deleting FLAC files
                                try:
                                    if auto_confirm or confirm(
                                        "Delete original FLAC files?", default_yes=False
                                    ):
                                        deleted_count = 0
                                        for file_info in converted_files:
                                            try:
                                                os.remove(file_info["flac_path"])
                                                deleted_count += 1
                                                click.echo(
                                                    f"✓ Deleted {file_info['flac_path']}"
                                                )
                                            except Exception as e:
                                                click.echo(
                                                    f"⚠ Failed to delete {file_info['flac_path']}: {e}"
                                                )
                                        click.echo(
                                            f"Deleted {deleted_count} of {len(converted_files)} FLAC files"
                                        )
                                    else:
                                        click.echo("Original FLAC files preserved")
                                except UserQuit:
                                    click.echo(
                                        "User quit. Original FLAC files preserved."
                                    )

                            except Exception as e:
                                click.echo(
                                    f"FATAL ERROR: Failed to commit database changes: {e}"
                                )
                                db.session.rollback()
                                sys.exit(1)
                        else:
                            click.echo(
                                "Rolling back database changes and cleaning up..."
                            )
                            db.session.rollback()
                            # Clean up converted files
                            for file_info in converted_files:
                                try:
                                    os.remove(file_info["output_path"])
                                    click.echo(
                                        f"✓ Cleaned up {file_info['output_path']}"
                                    )
                                except:
                                    pass
                    except UserQuit:
                        click.echo(
                            "User quit. Rolling back database changes and cleaning up..."
                        )
                        db.session.rollback()
                        # Clean up converted files
                        for file_info in converted_files:
                            try:
                                os.remove(file_info["output_path"])
                                click.echo(f"✓ Cleaned up {file_info['output_path']}")
                            except:
                                pass
                else:
                    click.echo("User quit. No changes to commit.")
                sys.exit(0)

            # Convert file
            source_format = FILE_TYPE_TO_NAME.get(content.FileType, "Unknown")
            click.echo(f"Converting {source_format} to {format.upper()}...")
            if not converter_func(flac_full_path, output_full_path):
                click.echo("ABORTING: Conversion failed")
                db.session.rollback()
                # Clean up any converted files
                for converted_file in converted_files:
                    try:
                        os.remove(converted_file["output_path"])
                    except:
                        pass
                sys.exit(1)

            # Verify conversion was successful
            if not os.path.exists(output_full_path):
                click.echo("ABORTING: Converted file not found after conversion")
                db.session.rollback()
                sys.exit(1)

            # Update database (but don't commit yet)
            click.echo("Updating database record...")
            try:
                update_database_record(
                    db, content.ID, output_filename, flac_folder, format.lower()
                )
                converted_files.append(
                    {
                        "flac_path": flac_full_path,
                        "output_path": output_full_path,
                        "content_id": content.ID,
                    }
                )
                click.echo("✓ Successfully converted and updated database record")
            except Exception as e:
                click.echo(f"ABORTING: Database update failed: {e}")
                db.session.rollback()
                # Clean up converted files
                try:
                    os.remove(output_full_path)
                    click.echo("Cleaned up converted file")
                except:
                    click.echo("Failed to clean up converted file")
                sys.exit(1)

        # Handle final commit and cleanup
        if converted_files:
            click.echo(
                f"\n🎉 Successfully converted {len(converted_files)} lossless files to {format.upper()} format"
            )

            try:
                if confirm("Commit database changes?", default_yes=True):
                    try:
                        db.session.commit()
                        click.echo("✓ Database changes committed successfully")

                        # Ask about deleting FLAC files
                        try:
                            if auto_confirm or confirm(
                                "Delete original FLAC files?", default_yes=False
                            ):
                                deleted_count = 0
                                for file_info in converted_files:
                                    try:
                                        os.remove(file_info["flac_path"])
                                        deleted_count += 1
                                        click.echo(
                                            f"✓ Deleted {file_info['flac_path']}"
                                        )
                                    except Exception as e:
                                        click.echo(
                                            f"⚠ Failed to delete {file_info['flac_path']}: {e}"
                                        )
                                click.echo(
                                    f"Deleted {deleted_count} of {len(converted_files)} FLAC files"
                                )
                            else:
                                click.echo("Original FLAC files preserved")
                        except UserQuit:
                            click.echo("User quit. Original FLAC files preserved.")
                            sys.exit(0)

                    except Exception as e:
                        click.echo(
                            f"FATAL ERROR: Failed to commit database changes: {e}"
                        )
                        db.session.rollback()
                        sys.exit(1)
                else:
                    click.echo("Database changes rolled back")
                    db.session.rollback()
                    # Clean up converted files
                    for file_info in converted_files:
                        try:
                            os.remove(file_info["output_path"])
                            click.echo(f"✓ Cleaned up {file_info['output_path']}")
                        except:
                            click.echo(
                                f"⚠ Failed to clean up {file_info['output_path']}"
                            )
            except UserQuit:
                click.echo(
                    "User quit. Rolling back database changes and cleaning up..."
                )
                db.session.rollback()
                # Clean up converted files
                for file_info in converted_files:
                    try:
                        os.remove(file_info["output_path"])
                        click.echo(f"✓ Cleaned up {file_info['output_path']}")
                    except:
                        pass
                sys.exit(0)
        else:
            click.echo("No files were converted.")

    except Exception as e:
        click.echo(f"FATAL ERROR: {e}")
        try:
            if db.session:
                db.session.rollback()
        except:
            pass
        sys.exit(1)
