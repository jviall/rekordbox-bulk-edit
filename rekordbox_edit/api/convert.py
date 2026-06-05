"""Convert API for rekordbox-edit."""

import logging
import os
from pathlib import Path
from typing import Tuple

import ffmpeg
from ffmpeg import Error as FfmpegError
from pydantic import BaseModel
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent
from sqlalchemy import select

from rekordbox_edit.api._utils import _track_from_content
from rekordbox_edit.models import ConvertPlanArgs, Track
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.utils import (
    OutputFormats,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
)

logger = logging.getLogger(__name__)


# ── Helpers (moved from commands/convert.py) ──────────────────────────────

def convert_to_lossless(input_path, output_path, output_format):
    """Convert lossless file to another lossless format, preserving bit depth."""
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    audio_info = get_audio_info(input_path)
    bit_depth = audio_info["bit_depth"]
    logger.debug(
        f"Source audio: bit_depth={bit_depth}, sample_rate={audio_info.get('sample_rate')}, channels={audio_info.get('channels')}"
    )

    codec_maps = {
        "aiff": {16: "pcm_s16be", 24: "pcm_s24be", 32: "pcm_s32be"},
        "wav": {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"},
        "flac": None,
    }

    if output_format.value not in codec_maps:
        raise Exception(f"Unsupported lossless format: {output_format}")

    codec_map = codec_maps[output_format.value]
    if codec_map is None:
        codec = output_format.value
    elif bit_depth in codec_map:
        codec = codec_map[bit_depth]
    else:
        codec = list(codec_map.values())[0]
        logger.debug(f"bit_depth={bit_depth} not in codec map, falling back to {codec}")

    logger.debug(f"Selected codec: {codec} (bit_depth={bit_depth})")

    output_options = {"acodec": codec, "map_metadata": 0, "write_id3v2": 1}

    try:
        (
            ffmpeg.input(input_path)
            .output(output_path, **output_options)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.debug(f"Conversion to {output_format.value} succeeded: {output_path}")
        return True
    except FfmpegError as e:
        logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {e}")
        raise e


def convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 320kbps CBR."""
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    try:
        acodec = "libmp3lame"
        audio_bitrate = "320k"
        map_metadata = 0
        write_id3v2 = 1

        (
            ffmpeg.input(input_path)
            .output(
                mp3_path,
                acodec=acodec,
                audio_bitrate=audio_bitrate,
                map_metadata=map_metadata,
                write_id3v2=write_id3v2,
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )

        logger.debug(f"Conversion to mp3 succeeded: {mp3_path}")
        return True
    except FfmpegError as e:
        logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        logger.error(f"Conversion failed for {input_path}: {e}")
        raise e


def update_database_record(
    db, content_id, new_filename, new_folder, output_format
) -> None:
    """Update database record with new file information."""
    content = db.get_content().filter_by(ID=content_id).first()
    if not content:
        raise Exception(f"Content record with ID {content_id} not found")

    converted_full_path = os.path.join(new_folder, new_filename)
    converted_audio_info = get_audio_info(converted_full_path)
    converted_bitrate = converted_audio_info["bitrate"]

    if output_format.upper() == "MP3" and converted_bitrate is None:
        logger.debug("MP3 bitrate not found in probe, assuming 320kbps")
        converted_bitrate = 320

    file_type = get_file_type_for_format(output_format)
    if not file_type:
        raise Exception(f"Unsupported output format: {output_format}")

    if output_format.upper() in ["AIFF", "FLAC", "WAV"]:
        converted_bit_depth = converted_audio_info["bit_depth"]
        database_bit_depth = getattr(content, "BitDepth", None)
        logger.debug(
            f"Bit depth check: database={database_bit_depth}, file={converted_bit_depth}"
        )

        if (
            database_bit_depth
            and converted_bit_depth
            and converted_bit_depth != database_bit_depth
        ):
            raise Exception(
                f"Bit depth mismatch for lossless transcode: database={database_bit_depth}, file={converted_bit_depth}"
            )

    content.FileNameL = new_filename
    content.FolderPath = converted_full_path
    content.FileType = file_type

    # FLAC stores bitrate as 0 in Rekordbox to represent VBR
    if output_format.upper() == "FLAC":
        content.BitRate = 0
        logger.debug(
            f"Set FileType={file_type}, BitRate=0 (FLAC), FolderPath={converted_full_path}"
        )
    else:
        content.BitRate = converted_bitrate
        logger.debug(
            f"Set FileType={file_type}, BitRate={converted_bitrate}, FolderPath={converted_full_path}"
        )


def cleanup_converted_files(converted_files) -> None:
    """Clean up converted files on error or rollback."""
    logger.debug("Cleaning up converted files due to aborted conversion.")
    for file_info in converted_files:
        try:
            os.remove(file_info["output_path"])
            logger.debug(f"Cleaned up {file_info['output_path']}")
        except Exception:
            pass


def rollback_and_cleanup(db, converted_files) -> None:
    """Roll back the database session and clean up any converted files."""
    logger.debug("Attempting DB session rollback.")
    rollback_error = None
    if db and db.session:
        try:
            db.session.rollback()
        except Exception as e:
            logger.critical(f"Encountered error during session rollback: {e}")
            logger.critical(
                "Check the state of your rekordbox library and consider reverting to a backup database if something's not right"
            )
            rollback_error = e
    else:
        logger.debug("No DB session to rollback.")
    if converted_files:
        cleanup_converted_files(converted_files)
    if rollback_error:
        raise rollback_error


def get_output_path(content, output_format) -> Tuple[str, str, str]:
    """Calculate output path for a content item."""
    src_folder_path = os.path.normpath(content.FolderPath or "")
    src_file_name = content.FileNameL or ""
    src_dirname = os.path.dirname(src_folder_path)

    extension = get_extension_for_format(output_format.upper())
    output_filename = Path(src_file_name).stem + extension
    output_path = os.path.join(src_dirname, output_filename)
    return output_path, output_filename, src_dirname


# ── Result types ──────────────────────────────────────────────────────────

class ConvertPlan(BaseModel):
    files: list[Track]
    skipped: list[Track]  # files skipped due to existing output (no overwrite)
    should_delete: bool
    format_out: str


class ConvertResult(BaseModel):
    converted: list[dict]  # {source_path, output_path, content_id}
    deleted: int


# ── API functions ─────────────────────────────────────────────────────────

def plan_convert(db: Rekordbox6Database, args: ConvertPlanArgs) -> ConvertPlan:
    """Determine which tracks need conversion and resolve delete behaviour."""
    should_delete = args.delete if args.delete is not None else args.format_out.upper() != "MP3"

    result = get_filtered_content(db, args)
    filtered_content = result.scalars().all()

    target_file_type = get_file_type_for_format(args.format_out)
    mp3_type = get_file_type_for_format("MP3")
    m4a_type = get_file_type_for_format("M4A")

    needs_conversion = [
        c for c in filtered_content
        if c.FileType != target_file_type
        and c.FileType != mp3_type
        and c.FileType != m4a_type
    ]

    if args.overwrite:
        files = needs_conversion
        skipped = []
    else:
        files, skipped = [], []
        for content in needs_conversion:
            output_path, _, _ = get_output_path(content, args.format_out)
            if os.path.exists(output_path):
                skipped.append(content)
            else:
                files.append(content)

    logger.debug(f"plan_convert: {len(files)} to convert, {len(skipped)} skipped (conflict)")

    return ConvertPlan(
        files=[_track_from_content(c) for c in files],
        skipped=[_track_from_content(c) for c in skipped],
        should_delete=should_delete,
        format_out=args.format_out,
    )


def convert(db: Rekordbox6Database, plan: ConvertPlan) -> ConvertResult:
    """Execute a ConvertPlan: convert files and update the database.

    Uses try/except BaseException so KeyboardInterrupt triggers rollback before
    the exception propagates to the caller.
    """
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    if not plan.files:
        return ConvertResult(converted=[], deleted=0)

    if not ffmpeg_in_path():
        raise RuntimeError(f"FFmpeg is required but not found in PATH.{get_ffmpeg_directions()}")

    assert db.session is not None

    ids = [t.ID for t in plan.files]
    contents = (
        db.session.execute(select(DjmdContent).where(DjmdContent.ID.in_(ids)))
        .scalars()
        .all()
    )
    content_map = {str(c.ID): c for c in contents}

    converted_files: list[dict] = []
    try:
        for i, track in enumerate(plan.files, 1):
            content = content_map[track.ID]
            src_folder_path = content.FolderPath or ""
            output_path, output_filename, src_dirname = get_output_path(content, plan.format_out)

            logger.info(f"[{i}/{len(plan.files)}] {content.FileNameL}")

            if not os.path.exists(src_folder_path):
                raise RuntimeError(f"Source not found: {src_folder_path}")

            if plan.format_out.upper() == "MP3":
                success = convert_to_mp3(src_folder_path, output_path)
            else:
                success = convert_to_lossless(
                    src_folder_path, output_path, OutputFormats(plan.format_out.lower())
                )

            if not success:
                raise RuntimeError(f"Conversion failed for {src_folder_path}")

            if not os.path.exists(output_path):
                raise RuntimeError(f"Output file not created: {output_path}")

            update_database_record(
                db, content.ID, output_filename, src_dirname, plan.format_out.upper()
            )
            converted_files.append({
                "source_path": src_folder_path,
                "output_path": output_path,
                "content_id": content.ID,
            })

        db.session.commit()
        logger.info(f"\nConverted {len(converted_files)} files to {plan.format_out.upper()}")

        deleted = 0
        if plan.should_delete:
            for file_info in converted_files:
                try:
                    os.remove(file_info["source_path"])
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file_info['source_path']}: {e}")

        return ConvertResult(converted=converted_files, deleted=deleted)

    except BaseException:
        rollback_and_cleanup(db, converted_files)
        raise
