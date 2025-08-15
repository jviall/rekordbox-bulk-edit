"""Convert command for rekordbox-bulk-edit."""

import os
import sys
from pathlib import Path

import click
import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid

from rekordbox_bulk_edit.logger import Logger
from rekordbox_bulk_edit.utils import (
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    print_track_info,
)

logger = Logger()


def convert_to_lossless(input_path, output_path, output_format):
    """Convert lossless file to another lossless format using ffmpeg, preserving bit depth"""
    try:
        from rekordbox_bulk_edit.utils import (
            check_ffmpeg_available,
            get_ffmpeg_directions,
        )

        # Check if ffmpeg is available first
        if not check_ffmpeg_available():
            raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

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

        logger.info(f"  Converting with {bit_depth}-bit depth using codec: {codec}")

        # Build output options
        output_options = {"acodec": codec, "map_metadata": 0, "write_id3v2": 1}

        (
            ffmpeg.input(input_path)
            .output(output_path, **output_options)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except FfmpegError as e:
        logger.info(f"FFmpeg error converting {input_path}: {e}")
        if e.stderr:
            logger.info(f"FFmpeg stderr output:\n{e.stderr.encode()}")
        return False
    except Exception as e:
        logger.info(f"Error converting {input_path}: {e}")
        return False


def convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 using ffmpeg with 320kbps constant bitrate"""
    try:
        from rekordbox_bulk_edit.utils import (
            check_ffmpeg_available,
            get_ffmpeg_directions,
        )

        # Check if ffmpeg is available first
        if not check_ffmpeg_available():
            raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

        logger.info("Converting to MP3 320kbps CBR")

        (
            ffmpeg.input(input_path)
            .output(
                mp3_path,
                acodec="libmp3lame",
                audio_bitrate="320k",
                map_metadata=0,
                write_id3v2=1,
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except FfmpegError as e:
        logger.info(f"FFmpeg error converting {input_path}: {e}")
        if e.stderr:
            logger.info(f"FFmpeg stderr output:\n{e.stderr.encode()}")
        return False
    except Exception as e:
        logger.info(f"Error converting {input_path}: {e}")
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
        logger.info(
            f"  ✓ Bit depth verification passed: {converted_bit_depth}-bit matches database"
        )
    else:
        logger.info(
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
        file_type = get_file_type_for_format(output_format)
        if not file_type:
            raise Exception(f"Unsupported output format: {output_format}")

        # Handle format-specific verification
        if output_format.upper() in ["AIFF", "FLAC", "WAV"]:
            _verify_bit_depth(content, converted_audio_info)
        elif output_format.upper() == "MP3":
            logger.info(f"  ✓ MP3 conversion completed with {converted_bitrate} kbps")

        # Update relevant fields
        content.FileNameL = new_filename
        content.FolderPath = converted_full_path
        content.FileType = file_type

        # Set bitrate to 0 for FLAC files (like Rekordbox does), otherwise use detected bitrate
        if output_format == "FLAC":
            content.BitRate = 0
            logger.info(f"  ✓ Updated BitRate from {content.BitRate or 0} to 0 (FLAC)")
        else:
            content.BitRate = converted_bitrate
            logger.info(
                f"  ✓ Updated BitRate from {content.BitRate or 0} to {converted_bitrate}"
            )

        # Note: No commit here - will be done centrally
        return True

    except Exception as e:
        logger.info(f"Error updating database record {content_id}: {e}")
        raise e  # Re-raise to be handled by caller


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
        logger.info("Please enter 'y', 'n', or 'q' to quit")


def cleanup_converted_files(converted_files):
    """Clean up converted files on error or rollback"""
    for file_info in converted_files:
        try:
            os.remove(file_info["output_path"])
            logger.info(f"✓ Cleaned up {file_info['output_path']}")
        except Exception:
            pass


def handle_original_file_deletion(converted_files, auto_confirm):
    """Handle deletion of original files after successful conversion"""
    try:
        if auto_confirm or confirm("Delete original files?", default_yes=False):
            deleted_count = 0
            for file_info in converted_files:
                try:
                    os.remove(file_info["source_path"])
                    deleted_count += 1
                    logger.info(f"✓ Deleted {file_info['source_path']}")
                except Exception as e:
                    logger.info(f"⚠ Failed to delete {file_info['source_path']}: {e}")
            logger.info(
                f"Deleted {deleted_count} of {len(converted_files)} original files"
            )
        else:
            logger.info("Original files preserved")
    except UserQuit:
        logger.info("User quit. Original files preserved.")
        raise


def handle_user_quit_with_changes(db, converted_files, auto_confirm):
    """Handle user quit when there are uncommitted database changes"""
    logger.info("User quit. You have uncommitted database changes.")
    try:
        if confirm("Commit database changes before quitting?", default_yes=True):
            try:
                db.session.commit()
                logger.info("✓ Database changes committed successfully")
                handle_original_file_deletion(converted_files, auto_confirm)
            except Exception as e:
                logger.critical("Failed to commit database changes!", exc_info=e)
                db.session.rollback()
                sys.exit(1)
        else:
            logger.info("Rolling back database changes and cleaning up...")
            db.session.rollback()
            cleanup_converted_files(converted_files)
    except UserQuit:
        logger.info("User quit. Rolling back database changes and cleaning up...")
        db.session.rollback()
        cleanup_converted_files(converted_files)


def check_file_exists_and_confirm(output_full_path, output_format, auto_confirm):
    """Check if output file exists and get user confirmation for skipping conversion"""
    if not os.path.exists(output_full_path):
        return False  # File doesn't exist, proceed with conversion

    logger.info(f"WARNING: {output_format} file already exists: {output_full_path}")
    if auto_confirm or confirm(
        "File exists. Skip conversion but update database record?", default_yes=True
    ):
        logger.info("Skipping conversion, will update database record only...")
        return True  # Skip conversion but update database
    else:
        logger.info("Skipping this file...")
        return None  # Skip this file entirely


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
    "--output-format",
    type=click.Choice(["aiff", "flac", "wav", "alac", "mp3"], case_sensitive=False),
    default="aiff",
    help="Output format: 'aiff' / 'flac' / 'wav' / 'alac' / 'mp3' (default: aiff)",
)
@click.option(
    "--format",
    type=click.Choice(["flac", "aiff", "wav"], case_sensitive=False),
    help="Filter by input format: 'flac' / 'aiff' / 'wav' (only lossless formats supported)",
)
@click.option(
    "--playlist",
    help="Filter by playlist name (exact match, case-sensitive)",
)
@click.option(
    "--artist",
    help="Filter by artist name (exact match, case-sensitive)",
)
@click.option(
    "--album",
    help="Filter by album name (exact match, case-sensitive)",
)
def convert_command(
    dry_run, auto_confirm, output_format, format, playlist, artist, album
):
    """Convert lossless audio files between formats and update RekordBox database.

    Supports conversion from any lossless format (FLAC, AIFF, WAV) to:
    - AIFF: Preserves original bit depth (16/24/32-bit)
    - FLAC: Lossless compression, preserves bit depth
    - WAV: Uncompressed, preserves original bit depth
    - MP3: 320kbps constant bitrate using LAME encoder

    Supports filtering by:
    - Input format: Only convert files of specific format
    - Playlist: Only convert files in a specific playlist
    - Artist: Only convert files by a specific artist
    - Album: Only convert files from a specific album

    Skips all lossy formats (MP3/AAC), ALAC, and files already in the target format.
    """
    try:
        logger.info("Lossless Audio Format Converter")
        logger.info("=" * 32)
        logger.info()

        # Check if Rekordbox is running
        logger.verbose("Checking if Rekordbox is running...")
        rekordbox_pid = get_rekordbox_pid()
        if rekordbox_pid:
            logger.error(f"Rekordbox is currently running ({rekordbox_pid})")
            logger.info(
                "Please close Rekordbox before running the convert command to avoid database conflicts."
            )
            sys.exit(1)
        logger.verbose("✓ Rekordbox is not running")
        logger.info()

        if dry_run:
            logger.info("DRY RUN MODE - No files will be converted or modified")
            logger.info()

        # Check FFmpeg availability early
        from rekordbox_bulk_edit.utils import (
            check_ffmpeg_available,
            get_ffmpeg_directions,
        )

        if not check_ffmpeg_available():
            logger.error("FFmpeg is required but not found in PATH")
            logger.error(get_ffmpeg_directions())
            sys.exit(1)

        # Connect to RekordBox database
        logger.verbose("Connecting to RekordBox database...")
        db = Rekordbox6Database()

        # Check if we have a valid session early on
        if not db.session:
            raise Exception("No database session available")

        # Get filtered content based on user criteria
        logger.info("Finding audio files...")

        filtered_content = []

        if playlist:
            # Filter by playlist
            logger.info(f"Filtering by playlist: {playlist}")
            playlist_results = db.get_playlist().filter_by(Name=playlist)
            playlist_obj = playlist_results.first()
            if not playlist_obj:
                logger.info(f"ERROR: Playlist '{playlist}' not found")
                sys.exit(1)
            elif playlist_results.count() > 1:
                print(
                    f"Warning: more than one playlist matches '{playlist}'. Using the first result: {playlist_obj.Name} ({playlist_obj.Id})"
                )

            # Get content from playlist
            playlist_content = db.get_playlist_contents(playlist_obj).all()
            content_ids = [pc.ID for pc in playlist_content]
            filtered_content.extend(
                [db.get_content().filter_by(ID=cid).first() for cid in content_ids]
            )
        else:
            # Get all content if no playlist filter
            filtered_content.extend(db.get_content().all())

        # Apply artist filter if specified
        if artist:
            logger.info(f"Filtering by artist: {artist}")
            artist_obj = db.get_artist().filter_by(Name=artist).first()
            if not artist_obj:
                logger.info(f"ERROR: Artist '{artist}' not found")
                sys.exit(1)

            filtered_content = [
                c for c in filtered_content if c.ArtistID == artist_obj.ID
            ]

        # Apply album filter if specified
        if album:
            logger.info(f"Filtering by album: {album}")
            album_obj = db.get_album().filter_by(Name=album).first()
            if not album_obj:
                logger.info(f"ERROR: Album '{album}' not found")
                sys.exit(1)

            filtered_content = [
                c for c in filtered_content if c.AlbumID == album_obj.ID
            ]

        # Filter by input format if specified
        if format:
            if format.upper() == output_format.upper():
                raise Exception(
                    "--format filter matches --output-format. There will be nothing to convert"
                )
            input_file_type = get_file_type_for_format(format)
            logger.info(f"Filtering by input format: {format.upper()}")
            filtered_content = [
                c for c in filtered_content if c.FileType == input_file_type
            ]

        target_file_type = get_file_type_for_format(output_format)
        files_to_convert = [
            content
            for content in filtered_content
            if content.FileType != target_file_type
            and content.FileType != get_file_type_for_format("MP3")
            and content.FileType != get_file_type_for_format("M4A")
        ]

        logger.info(
            f"Found {len(files_to_convert)} files to convert to {output_format.upper()}"
        )

        if not files_to_convert:
            logger.info("No files need conversion. Exiting.")
            return

        if dry_run:
            logger.info("\nFiles that would be converted:")
            print_track_info(files_to_convert)
            return

        # Process each file
        converted_files = []  # Track converted files for potential deletion
        for i, content in enumerate(files_to_convert, 1):
            source_file_name = content.FileNameL or ""
            source_full_path = content.FolderPath or ""
            source_folder = os.path.dirname(source_full_path)
            source_format = get_file_type_name(content.FileType)
            output_format_upper = output_format.upper()

            logger.info(f"\nProcessing {i}/{len(files_to_convert)}")

            # Show detailed track information
            print_track_info([content])
            logger.info()

            # Check if source file exists
            if not os.path.exists(source_full_path):
                logger.info(
                    f"ERROR: {source_format} file not found: {source_full_path}"
                )
                logger.info("ABORTING: Cannot continue with missing files")
                db.session.rollback()
                sys.exit(1)

            # Generate output filename and path
            input_path_obj = Path(source_file_name)

            # Map format to file extension
            extension = get_extension_for_format(output_format_upper)
            output_filename = input_path_obj.stem + extension
            output_full_path = os.path.join(source_folder, output_filename)

            # Choose converter function
            def convert(inp, out):
                if output_format_upper == "MP3":
                    return convert_to_mp3(inp, out)
                else:
                    return convert_to_lossless(inp, out, output_format.lower())

            # Check if output file already exists and get user decision
            try:
                file_exists_result = check_file_exists_and_confirm(
                    output_full_path, output_format_upper, auto_confirm
                )
                if file_exists_result is None:  # User chose to skip this file
                    continue
                skip_conversion = file_exists_result  # True if skipping conversion, False if proceeding
            except UserQuit:
                if converted_files:
                    handle_user_quit_with_changes(db, converted_files, auto_confirm)
                else:
                    logger.info("User quit. No changes to commit.")
                sys.exit(0)

            # Ask for conversion confirmation (unless skipping conversion)
            if not skip_conversion:
                try:
                    if not auto_confirm and not confirm(
                        f"Convert {source_format} track {source_file_name} to {output_format_upper}?",
                        default_yes=True,
                    ):
                        logger.info("Skipping this file...")
                        continue
                except UserQuit:
                    if converted_files:
                        handle_user_quit_with_changes(db, converted_files, auto_confirm)
                    else:
                        logger.info("User quit. No changes to commit.")
                    sys.exit(0)

            # Convert file (unless skipping)
            if not skip_conversion:
                if not convert(source_full_path, output_full_path):
                    logger.info("ABORTING: Conversion failed")
                    db.session.rollback()
                    cleanup_converted_files(converted_files)
                    sys.exit(1)

                # Verify conversion was successful
                if not os.path.exists(output_full_path):
                    logger.info("ABORTING: Converted file not found after conversion")
                    db.session.rollback()
                    sys.exit(1)

            # Update database (but don't commit yet)
            logger.info("Updating database record...")
            try:
                update_database_record(
                    db,
                    content.ID,
                    output_filename,
                    source_folder,
                    output_format_upper,
                )
                converted_files.append(
                    {
                        "source_path": source_full_path,
                        "output_path": output_full_path,
                        "content_id": content.ID,
                    }
                )
                if skip_conversion:
                    logger.info(
                        "✓ Successfully updated database record (conversion skipped)"
                    )
                else:
                    logger.info("✓ Successfully converted and updated database record")
            except Exception as e:
                logger.info(f"ABORTING: Database update failed: {e}")
                db.session.rollback()
                # Clean up converted files
                try:
                    os.remove(output_full_path)
                    logger.info("Cleaned up converted file")
                except Exception as e:
                    logger.info(f"Failed to clean up converted file {e}")
                sys.exit(1)

        # Handle final commit and cleanup
        if converted_files:
            logger.info(
                f"\n🎉 Successfully converted {len(converted_files)} lossless files to {output_format_upper} format"
            )

            try:
                if confirm("Commit database changes?", default_yes=True):
                    try:
                        db.session.commit()
                        logger.info("✓ Database changes committed successfully")

                        handle_original_file_deletion(converted_files, auto_confirm)

                    except Exception as e:
                        logger.info(
                            f"FATAL ERROR: Failed to commit database changes: {e}"
                        )
                        db.session.rollback()
                        sys.exit(1)
                else:
                    logger.info("Database changes rolled back")
                    db.session.rollback()
                    cleanup_converted_files(converted_files)
            except UserQuit:
                logger.info(
                    "User quit. Rolling back database changes and cleaning up..."
                )
                db.session.rollback()
                cleanup_converted_files(converted_files)
                sys.exit(0)
        else:
            logger.info("No files were converted.")

    except Exception as e:
        try:
            if db.session:
                db.session.rollback()
        except Exception as _e:
            logger.critical("DATABASE ROLLBACK FAILED AFTER EXCEPTION")
            raise Exception(_e, e)
        raise e
