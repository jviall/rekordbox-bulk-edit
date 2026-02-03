"""Convert command for rekordbox-bulk-edit."""

import logging
import os
import signal
import sys
from pathlib import Path
from typing import List

import click
import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid

from rekordbox_bulk_edit._click import (
    PrintChoice,
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_bulk_edit.logger import Logger
from rekordbox_bulk_edit.query import get_filtered_content
from rekordbox_bulk_edit.utils import (
    UserQuit,
    confirm,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    print_track_info,
)

logger = Logger()


def convert_to_lossless(input_path, output_path, output_format):
    """Convert lossless file to another lossless format, preserving bit depth."""
    from rekordbox_bulk_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    audio_info = get_audio_info(input_path)
    bit_depth = audio_info["bit_depth"]

    codec_maps = {
        "aiff": {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"},
        "wav": {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"},
        "flac": None,
        "alac": None,
    }

    if output_format not in codec_maps:
        raise Exception(f"Unsupported lossless format: {output_format}")

    codec_map = codec_maps[output_format]
    codec = (
        output_format
        if codec_map is None
        else codec_map.get(bit_depth, list(codec_map.values())[0])
    )

    logger.debug(f"Converting {bit_depth}-bit using codec: {codec}")

    output_options = {"acodec": codec, "map_metadata": 0, "write_id3v2": 1}

    try:
        (
            ffmpeg.input(input_path)
            .output(output_path, **output_options)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return True
    except FfmpegError as e:
        logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {e}")
        return False


def convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 320kbps CBR."""
    from rekordbox_bulk_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    try:
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
        logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {e}")
        return False


def update_database_record(db, content_id, new_filename, new_folder, output_format):
    """Update database record with new file information."""
    content = db.get_content().filter_by(ID=content_id).first()
    if not content:
        raise Exception(f"Content record with ID {content_id} not found")

    converted_full_path = os.path.join(new_folder, new_filename)
    converted_audio_info = get_audio_info(converted_full_path)
    converted_bitrate = converted_audio_info["bitrate"]

    file_type = get_file_type_for_format(output_format)
    if not file_type:
        raise Exception(f"Unsupported output format: {output_format}")

    if output_format.upper() in ["AIFF", "FLAC", "WAV"]:
        converted_bit_depth = converted_audio_info["bit_depth"]
        database_bit_depth = getattr(content, "BitDepth", None)

        if database_bit_depth and converted_bit_depth != database_bit_depth:
            raise Exception(
                f"Bit depth mismatch: database={database_bit_depth}, file={converted_bit_depth}"
            )

    content.FileNameL = new_filename
    content.FolderPath = converted_full_path
    content.FileType = file_type

    # FLAC stores bitrate as 0 in Rekordbox
    if output_format.upper() == "FLAC":
        content.BitRate = 0
    else:
        content.BitRate = converted_bitrate

    return True


def cleanup_converted_files(converted_files):
    """Clean up converted files on error or rollback."""
    for file_info in converted_files:
        try:
            os.remove(file_info["output_path"])
            logger.debug(f"Cleaned up {file_info['output_path']}")
        except Exception:
            pass


def get_output_path(content, output_format):
    """Calculate output path for a content item."""
    src_folder_path = content.FolderPath or ""
    src_file_name = content.FileNameL or ""
    src_dirname = os.path.dirname(src_folder_path)
    extension = get_extension_for_format(output_format.upper())
    output_filename = Path(src_file_name).stem + extension
    return os.path.join(src_dirname, output_filename), output_filename, src_dirname


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be converted without making changes",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Auto-confirm the batch conversion (skip confirmation prompt)",
)
@click.option(
    "--delete/--keep",
    default=None,
    help="Delete or keep original files after conversion (default: delete for lossless, keep for MP3)",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing output files instead of skipping them",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Confirm each file individually before converting",
)
@click.option(
    "--format-out",
    type=click.Choice(["aiff", "flac", "wav", "alac", "mp3"], case_sensitive=False),
    default="aiff",
    help="Output format (default: aiff)",
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
def convert_command(
    dry_run,
    yes,
    delete,
    overwrite,
    interactive,
    format_out,
    track_id: List[str] | None,
    track_ids: List[str] | None,
    title: List[str] | None,
    exact_title: List[str] | None,
    album: List[str] | None,
    exact_album: List[str] | None,
    artist: List[str] | None,
    exact_artist: List[str] | None,
    playlist: List[str] | None,
    exact_playlist: List[str] | None,
    format: List[str] | None,
    match_all: bool,
    print_opt: PrintChoice | None,
):
    """Convert lossless audio files between formats and update RekordBox database.

    Supports conversion from any lossless format (FLAC, AIFF, WAV) to:
    AIFF, FLAC, WAV, ALAC, or MP3.

    Skips lossy formats and files already in the target format.
    """
    from rekordbox_bulk_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    # Validate --print option requirements
    scripting_mode = print_opt in (PrintChoice.IDS, PrintChoice.SILENT)
    if scripting_mode:
        if not (dry_run or yes):
            raise click.UsageError(
                "--print=ids or --print=silent requires --dry-run or --yes"
            )
        logger.set_level(logging.ERROR)

    # Determine delete behavior: smart default based on output format
    if delete is None:
        should_delete = format_out.upper() != "MP3"
    else:
        should_delete = delete

    db = None
    converted_files = []

    def rollback_and_cleanup():
        if db and db.session:
            try:
                db.session.rollback()
            except Exception:
                pass
        if converted_files:
            cleanup_converted_files(converted_files)

    def signal_handler(_signum, frame):
        logger.info("\nInterrupted. Rolling back...")
        rollback_and_cleanup()
        sys.exit(1)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # === PRECONDITIONS ===
        rekordbox_pid = get_rekordbox_pid()
        if rekordbox_pid:
            if scripting_mode:
                logger.error(
                    f"Rekordbox is running (PID {rekordbox_pid}). "
                    "Cannot proceed in scripting mode."
                )
                sys.exit(1)
            logger.warning(f"Rekordbox is running (PID {rekordbox_pid})")
            logger.warning(
                "Modifying the database while Rekordbox is open can cause conflicts."
            )
            try:
                if not confirm("Continue anyway?", default=False):
                    return
            except UserQuit:
                return

        if not ffmpeg_in_path():
            logger.error("FFmpeg is required but not found in PATH")
            logger.error(get_ffmpeg_directions())
            sys.exit(1)

        db = Rekordbox6Database()
        if not db.session:
            raise Exception("No database session available")

        # === QUERY & FILTER ===
        result = get_filtered_content(
            db,
            track_id_args=track_ids,
            track_ids=track_id,
            formats=format,
            playlists=playlist,
            exact_playlists=exact_playlist,
            artists=artist,
            exact_artists=exact_artist,
            albums=album,
            exact_albums=exact_album,
            titles=title,
            exact_titles=exact_title,
            match_all=match_all,
        )
        filtered_content = result.scalars().all()

        target_file_type = get_file_type_for_format(format_out)
        mp3_type = get_file_type_for_format("MP3")
        m4a_type = get_file_type_for_format("M4A")

        files_to_convert = [
            content
            for content in filtered_content
            if content.FileType != target_file_type
            and content.FileType != mp3_type
            and content.FileType != m4a_type
        ]

        if not files_to_convert:
            logger.info("No files need conversion.")
            return

        # === CONFLICT CHECK ===
        conflicts = []
        convertible = []
        for content in files_to_convert:
            output_path, _, _ = get_output_path(content, format_out)
            if os.path.exists(output_path):
                conflicts.append(content)
            else:
                convertible.append(content)

        if conflicts:
            if overwrite:
                logger.info(f"{len(conflicts)} output files exist (will overwrite)")
                convertible = files_to_convert
            elif yes:
                # Silent skip when --yes without --overwrite
                if not convertible:
                    return
            else:
                logger.warning(
                    f"Skipping {len(conflicts)} files (output exists, use --overwrite)"
                )
                if not convertible:
                    logger.info("No files to convert.")
                    return

        files_to_process = convertible if not overwrite else files_to_convert

        # === PREVIEW ===
        logger.info(
            f"Found {len(files_to_process)} files to convert to {format_out.upper()}"
        )
        print_track_info(files_to_process)

        if dry_run:
            if print_opt is PrintChoice.IDS:
                print(" ".join(str(c.ID) for c in files_to_process))
            return

        # === CONFIRM ===
        if not yes and not interactive:
            try:
                if not confirm(
                    f"Convert {len(files_to_process)} files to {format_out.upper()}?",
                    default=True,
                ):
                    logger.info("Cancelled.")
                    return
            except UserQuit:
                return

        # === CONVERT ===
        for i, content in enumerate(files_to_process, 1):
            src_folder_path = content.FolderPath or ""
            src_file_name = content.FileNameL or ""
            src_format = get_file_type_name(content.FileType)
            output_path, output_filename, src_dirname = get_output_path(
                content, format_out
            )

            logger.info(f"[{i}/{len(files_to_process)}] {src_file_name}")

            if interactive:
                try:
                    if not confirm(
                        f"  Convert {src_format} to {format_out.upper()}?", default=True
                    ):
                        continue
                except UserQuit:
                    logger.info("User quit. Rolling back...")
                    rollback_and_cleanup()
                    return

            if not os.path.exists(src_folder_path):
                logger.error(f"  Source not found: {src_folder_path}")
                rollback_and_cleanup()
                sys.exit(1)

            if os.path.exists(output_path) and not overwrite:
                continue

            if format_out.upper() == "MP3":
                success = convert_to_mp3(src_folder_path, output_path)
            else:
                success = convert_to_lossless(
                    src_folder_path, output_path, format_out.lower()
                )

            if not success:
                logger.error("  Conversion failed. Aborting.")
                rollback_and_cleanup()
                sys.exit(1)

            if not os.path.exists(output_path):
                logger.error("  Output file not created. Aborting.")
                rollback_and_cleanup()
                sys.exit(1)

            try:
                update_database_record(
                    db, content.ID, output_filename, src_dirname, format_out.upper()
                )
                converted_files.append(
                    {
                        "source_path": src_folder_path,
                        "output_path": output_path,
                        "content_id": content.ID,
                    }
                )
                logger.verbose("  Done")
            except Exception as e:
                logger.error(f"  Database update failed: {e}")
                rollback_and_cleanup()
                sys.exit(1)

        # === COMMIT ===
        if not converted_files:
            logger.info("No files were converted.")
            return

        try:
            db.session.commit()
            logger.info(
                f"\nConverted {len(converted_files)} files to {format_out.upper()}"
            )
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            rollback_and_cleanup()
            sys.exit(1)

        # === OUTPUT ===
        if print_opt is PrintChoice.IDS:
            print(" ".join(str(f["content_id"]) for f in converted_files))

        # === DELETE ORIGINALS ===
        if should_delete:
            deleted_count = 0
            for file_info in converted_files:
                try:
                    os.remove(file_info["source_path"])
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file_info['source_path']}: {e}")
            logger.info(f"Deleted {deleted_count} original files")

    except Exception as e:
        rollback_and_cleanup()
        raise e
