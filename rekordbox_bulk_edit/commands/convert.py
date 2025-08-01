"""Convert command for rekordbox-bulk-edit."""

import os
import sys
from pathlib import Path

import click
import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database

from rekordbox_bulk_edit.utils import (
    FILE_TYPE_TO_NAME,
    FORMAT_EXTENSIONS,
    FORMAT_TO_FILE_TYPE,
    get_audio_info,
    is_rekordbox_running,
    print_track_info,
)


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
        click.echo(f"FFmpeg error converting {input_path}: {e}")
        if e.stderr:
            click.echo(f"FFmpeg stderr output:\n{e.stderr.encode()}")
        return False
    except Exception as e:
        click.echo(f"Error converting {input_path}: {e}")
        return False


def convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 using ffmpeg with 320kbps constant bitrate"""
    try:
        click.echo("Converting to MP3 320kbps CBR")

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
        click.echo(f"FFmpeg error converting {input_path}: {e}")
        if e.stderr:
            click.echo(f"FFmpeg stderr output:\n{e.stderr.encode()}")
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
        converted_full_path = os.path.normpath(os.path.join(new_folder, new_filename))
        converted_audio_info = get_audio_info(converted_full_path)
        converted_bitrate = converted_audio_info["bitrate"]

        # Set file type based on output format
        file_type = FORMAT_TO_FILE_TYPE.get(output_format)
        if not file_type:
            raise Exception(f"Unsupported output format: {output_format}")

        # Handle format-specific verification
        if output_format.upper() in ["AIFF", "FLAC", "WAV"]:
            _verify_bit_depth(content, converted_audio_info)
        elif output_format.upper() == "MP3":
            click.echo(f"  ✓ MP3 conversion completed with {converted_bitrate} kbps")

        # Update relevant fields
        content.FileNameL = new_filename
        content.FolderPath = converted_full_path
        content.FileType = file_type

        # Set bitrate to 0 for FLAC files (like Rekordbox does), otherwise use detected bitrate
        if output_format == "FLAC":
            content.BitRate = 0
            click.echo(f"  ✓ Updated BitRate from {content.BitRate or 0} to 0 (FLAC)")
        else:
            content.BitRate = converted_bitrate
            click.echo(
                f"  ✓ Updated BitRate from {content.BitRate or 0} to {converted_bitrate}"
            )

        # Note: No commit here - will be done centrally
        return True

    except Exception as e:
        click.echo(f"Error updating database record {content_id}: {e}")
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
        click.echo("Please enter 'y', 'n', or 'q' to quit")


def cleanup_converted_files(converted_files):
    """Clean up converted files on error or rollback"""
    for file_info in converted_files:
        try:
            os.remove(file_info["output_path"])
            click.echo(f"✓ Cleaned up {file_info['output_path']}")
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
                    click.echo(f"✓ Deleted {file_info['source_path']}")
                except Exception as e:
                    click.echo(f"⚠ Failed to delete {file_info['source_path']}: {e}")
            click.echo(
                f"Deleted {deleted_count} of {len(converted_files)} original files"
            )
        else:
            click.echo("Original files preserved")
    except UserQuit:
        click.echo("User quit. Original files preserved.")
        raise


def handle_user_quit_with_changes(db, converted_files, auto_confirm):
    """Handle user quit when there are uncommitted database changes"""
    click.echo("User quit. You have uncommitted database changes.")
    try:
        if confirm("Commit database changes before quitting?", default_yes=True):
            try:
                db.session.commit()
                click.echo("✓ Database changes committed successfully")
                handle_original_file_deletion(converted_files, auto_confirm)
            except Exception as e:
                click.echo(f"FATAL ERROR: Failed to commit database changes: {e}")
                db.session.rollback()
                sys.exit(1)
        else:
            click.echo("Rolling back database changes and cleaning up...")
            db.session.rollback()
            cleanup_converted_files(converted_files)
    except UserQuit:
        click.echo("User quit. Rolling back database changes and cleaning up...")
        db.session.rollback()
        cleanup_converted_files(converted_files)


def check_file_exists_and_confirm(output_full_path, output_format, auto_confirm):
    """Check if output file exists and get user confirmation for skipping conversion"""
    if not os.path.exists(output_full_path):
        return False  # File doesn't exist, proceed with conversion

    click.echo(f"WARNING: {output_format} file already exists: {output_full_path}")
    if auto_confirm or confirm(
        "File exists. Skip conversion but update database record?", default_yes=True
    ):
        click.echo("Skipping conversion, will update database record only...")
        return True  # Skip conversion but update database
    else:
        click.echo("Skipping this file...")
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

        # Get filtered content based on user criteria
        click.echo("Finding audio files...")

        filtered_content = []

        if playlist:
            # Filter by playlist
            click.echo(f"Filtering by playlist: {playlist}")
            playlist_results = db.get_playlist().filter_by(Name=playlist)
            playlist_obj = playlist_results.first()
            if not playlist_obj:
                click.echo(f"ERROR: Playlist '{playlist}' not found")
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
            click.echo(f"Filtering by artist: {artist}")
            artist_obj = db.get_artist().filter_by(Name=artist).first()
            if not artist_obj:
                click.echo(f"ERROR: Artist '{artist}' not found")
                sys.exit(1)

            filtered_content = [
                c for c in filtered_content if c.ArtistID == artist_obj.ID
            ]

        # Apply album filter if specified
        if album:
            click.echo(f"Filtering by album: {album}")
            album_obj = db.get_album().filter_by(Name=album).first()
            if not album_obj:
                click.echo(f"ERROR: Album '{album}' not found")
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
            input_file_type = FORMAT_TO_FILE_TYPE[format.upper()]
            click.echo(f"Filtering by input format: {format.upper()}")
            filtered_content = [
                c for c in filtered_content if c.FileType == input_file_type
            ]

        # Filter out files already in target format
        target_file_type = FORMAT_TO_FILE_TYPE[output_format.upper()]
        files_to_convert = [
            content
            for content in filtered_content
            if content.FileType != target_file_type
        ]

        click.echo(
            f"Found {len(files_to_convert)} files to convert to {output_format.upper()}"
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
            source_file_name = content.FileNameL or ""
            source_full_path = os.path.normpath(content.FolderPath or "")
            source_folder = os.path.dirname(source_full_path)
            source_format = FILE_TYPE_TO_NAME.get(content.FileType, "Unknown")
            output_format_upper = output_format.upper()

            click.echo(f"\nProcessing {i}/{len(files_to_convert)}")

            # Show detailed track information
            print_track_info([content])
            click.echo()

            # Check if source file exists
            if not source_full_path or not os.path.exists(source_full_path):
                click.echo(f"ERROR: {source_format} file not found: {source_full_path}")
                click.echo("Path from database:", repr(content.FolderPath))
                click.echo("Normalized path:", repr(source_full_path))
                
                # Try alternative path handling for Windows
                if os.name == 'nt' and content.FolderPath:
                    alt_path = content.FolderPath.replace('/', '\\')
                    click.echo("Windows alternative path:", repr(alt_path))
                    if os.path.exists(alt_path):
                        click.echo("✓ Found file using backslash separators")
                        source_full_path = alt_path
                        source_folder = os.path.dirname(source_full_path)
                    else:
                        click.echo("File still not found with backslash separators")
                
                if not os.path.exists(source_full_path):
                    click.echo("ABORTING: Cannot continue with missing files")
                    db.session.rollback()
                    sys.exit(1)

            # Generate output filename and path
            input_path_obj = Path(source_file_name)

            # Map format to file extension
            extension = FORMAT_EXTENSIONS[output_format_upper]
            output_filename = input_path_obj.stem + extension
            output_full_path = os.path.normpath(os.path.join(source_folder, output_filename))

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
                    click.echo("User quit. No changes to commit.")
                sys.exit(0)

            # Ask for conversion confirmation (unless skipping conversion)
            if not skip_conversion:
                try:
                    if not auto_confirm and not confirm(
                        f"Convert {source_format} track {source_file_name} to {output_format_upper}?",
                        default_yes=True,
                    ):
                        click.echo("Skipping this file...")
                        continue
                except UserQuit:
                    if converted_files:
                        handle_user_quit_with_changes(db, converted_files, auto_confirm)
                    else:
                        click.echo("User quit. No changes to commit.")
                    sys.exit(0)

            # Convert file (unless skipping)
            if not skip_conversion:
                if not convert(source_full_path, output_full_path):
                    click.echo("ABORTING: Conversion failed")
                    db.session.rollback()
                    cleanup_converted_files(converted_files)
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
                    click.echo(
                        "✓ Successfully updated database record (conversion skipped)"
                    )
                else:
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
                f"\n🎉 Successfully converted {len(converted_files)} lossless files to {output_format_upper} format"
            )

            try:
                if confirm("Commit database changes?", default_yes=True):
                    try:
                        db.session.commit()
                        click.echo("✓ Database changes committed successfully")

                        handle_original_file_deletion(converted_files, auto_confirm)

                    except Exception as e:
                        click.echo(
                            f"FATAL ERROR: Failed to commit database changes: {e}"
                        )
                        db.session.rollback()
                        sys.exit(1)
                else:
                    click.echo("Database changes rolled back")
                    db.session.rollback()
                    cleanup_converted_files(converted_files)
            except UserQuit:
                click.echo(
                    "User quit. Rolling back database changes and cleaning up..."
                )
                db.session.rollback()
                cleanup_converted_files(converted_files)
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
