"""Convert API for rekordbox-edit."""

import logging
import os
import posixpath
from pathlib import Path
from typing import Tuple

import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent
from sqlalchemy import select

from rekordbox_edit.api._utils import _order_tracks_by_op
from rekordbox_edit.models import (
    ConvertArgs,
    ConvertOp,
    ConvertResponse,
    ConvertResult,
    SkippedTrack,
)
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.utils import (
    OutputFormats,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
)

logger = logging.getLogger(__name__)


# ── ffmpeg helpers ────────────────────────────────────────────────────────


def _convert_to_lossless(input_path, output_path, output_format):
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

    try:
        (
            ffmpeg.input(input_path)
            .output(output_path, acodec=codec, map_metadata=0, write_id3v2=1)
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


def _convert_to_mp3(input_path, mp3_path):
    """Convert lossless file to MP3 320kbps CBR."""
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

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


def _update_database_record(
    db, content_id, new_filename, new_folder, output_format
) -> None:
    """Update database record with new file information."""
    content = db.get_content().filter_by(ID=content_id).first()
    if not content:
        raise Exception(f"Content record with ID {content_id} not found")

    converted_full_path = posixpath.join(new_folder, new_filename)
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
        if (
            database_bit_depth
            and converted_bit_depth
            and converted_bit_depth != database_bit_depth
        ):
            raise Exception(
                f"Bit depth mismatch for lossless transcode: "
                f"database={database_bit_depth}, file={converted_bit_depth}"
            )

    content.FileNameL = new_filename
    content.FolderPath = converted_full_path
    content.FileType = file_type

    # FLAC stores bitrate as 0 in Rekordbox to represent VBR
    if output_format.upper() == "FLAC":
        content.BitRate = 0
    else:
        content.BitRate = converted_bitrate


def _cleanup_converted_files(converted_ops: list[ConvertOp]) -> None:
    """Clean up converted output files on error or rollback."""
    logger.debug("Cleaning up converted files due to aborted conversion.")
    for op in converted_ops:
        try:
            os.remove(op.output_path)
            logger.debug(f"Cleaned up {op.output_path}")
        except Exception:
            pass


def _rollback_and_cleanup(db, converted_ops: list[ConvertOp]) -> None:
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
    if converted_ops:
        _cleanup_converted_files(converted_ops)
    if rollback_error:
        raise rollback_error


def _get_output_path(content, output_format) -> Tuple[str, str, str]:
    """Calculate output path for a content item."""
    src_folder_path = os.path.normpath(content.FolderPath or "")
    src_file_name = content.FileNameL or ""
    src_dirname = os.path.dirname(src_folder_path)

    extension = get_extension_for_format(output_format.upper())
    output_filename = Path(src_file_name).stem + extension
    output_path = os.path.join(src_dirname, output_filename)
    return output_path, output_filename, src_dirname


# ── Classifier ────────────────────────────────────────────────────────────


def _classify_convert(content, args: ConvertArgs) -> ConvertOp | SkippedTrack:
    """Return ConvertOp if this track should be converted, or SkippedTrack with
    reason if not."""
    target = get_file_type_for_format(args.format_out)
    mp3 = get_file_type_for_format("MP3")
    m4a = get_file_type_for_format("M4A")
    if content.FileType in (target, mp3, m4a):
        logger.debug(
            f"skip convert id={content.ID} reason=already_target_format "
            f"file_type={content.FileType} target={target}"
        )
        return SkippedTrack(id=str(content.ID), reason="already_target_format")
    output_path, _, _ = _get_output_path(content, args.format_out)
    if not args.overwrite and os.path.exists(output_path):
        logger.debug(
            f"skip convert id={content.ID} reason=output_file_exists path={output_path}"
        )
        return SkippedTrack(id=str(content.ID), reason="output_file_exists")
    return ConvertOp(
        id=str(content.ID),
        source_path=content.FolderPath or "",
        output_path=output_path,
    )


# ── Public API ────────────────────────────────────────────────────────────


def convert(
    db: Rekordbox6Database,
    args: ConvertArgs,
    *,
    dry_run: bool = False,
) -> ConvertResponse:
    """Convert audio files to a target format and update the Rekordbox database.

    With `dry_run=True`, returns the planned conversions without any ffmpeg or
    DB writes. With `dry_run=False` (default), commits the changes.

    The rollback block protects only pre-commit work; once commit lands, the
    transaction is honoured even if the delete-originals loop or response
    re-query later fails.
    """
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    logger.debug(f"convert start format_out={args.format_out} dry_run={dry_run}")

    if not ffmpeg_in_path():
        logger.debug("convert aborted: FFmpeg not in PATH")
        raise RuntimeError(
            f"FFmpeg is required but not found in PATH.{get_ffmpeg_directions()}"
        )

    contents = get_filtered_content(db, args).scalars().all()
    logger.debug(f"convert fetched {len(contents)} candidate(s) from filter")

    ops: list[ConvertOp] = []
    skipped: list[SkippedTrack] = []
    for c in contents:
        result = _classify_convert(c, args)
        if isinstance(result, ConvertOp):
            ops.append(result)
        else:
            skipped.append(result)
    logger.debug(f"convert classified ops={len(ops)} skipped={len(skipped)}")

    if dry_run:
        logger.debug(f"convert dry-run return with {len(ops)} planned conversion(s)")
        return ConvertResponse(
            tracks=_order_tracks_by_op(contents, ops),
            result=ConvertResult(
                format_out=args.format_out,
                converted=ops,
                deleted=0,
                skipped=skipped,
            ),
        )

    if not ops:
        return ConvertResponse(
            tracks=[],
            result=ConvertResult(
                format_out=args.format_out,
                converted=[],
                deleted=0,
                skipped=skipped,
            ),
        )

    assert db.session is not None

    should_delete = (
        args.delete if args.delete is not None else args.format_out.upper() != "MP3"
    )
    logger.debug(
        f"convert should_delete={should_delete} "
        f"(args.delete={args.delete}, format_out={args.format_out})"
    )

    # content_map enables per-op live FolderPath / FileNameL reads in the loop.
    content_map = {str(c.ID): c for c in contents}
    converted_ops: list[ConvertOp] = []
    try:
        for i, op in enumerate(ops, 1):
            content = content_map[op.id]
            src = content.FolderPath or ""
            logger.info(f"[{i}/{len(ops)}] {content.FileNameL}")

            if not os.path.exists(src):
                raise RuntimeError(f"Source not found: {src}")

            if args.format_out.upper() == "MP3":
                success = _convert_to_mp3(src, op.output_path)
            else:
                success = _convert_to_lossless(
                    src, op.output_path, OutputFormats(args.format_out.lower())
                )

            if not success:
                raise RuntimeError(f"Conversion failed for {src}")
            if not os.path.exists(op.output_path):
                raise RuntimeError(f"Output file not created: {op.output_path}")

            _update_database_record(
                db,
                op.id,
                os.path.basename(op.output_path),
                os.path.dirname(op.output_path),
                args.format_out.upper(),
            )
            converted_ops.append(
                ConvertOp(id=op.id, source_path=src, output_path=op.output_path)
            )

        db.session.commit()
        logger.info(
            f"\nConverted {len(converted_ops)} files to {args.format_out.upper()}"
        )
        logger.debug(f"convert committed {len(converted_ops)} conversion(s)")
    except BaseException:
        logger.debug(
            f"convert rolling back after {len(converted_ops)} partial conversion(s)"
        )
        _rollback_and_cleanup(db, converted_ops)
        raise

    deleted = 0
    if should_delete:
        for op in converted_ops:
            try:
                os.remove(op.source_path)
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete {op.source_path}: {e}")
        logger.debug(f"convert deleted {deleted}/{len(converted_ops)} source file(s)")

    converted_ids = [op.id for op in converted_ops]
    try:
        post_contents = (
            db.session.execute(
                select(DjmdContent).where(DjmdContent.ID.in_(converted_ids))
            )
            .scalars()
            .all()
        )
        logger.debug(
            f"convert post-commit re-query returned {len(post_contents)} track(s)"
        )
        tracks = _order_tracks_by_op(post_contents, converted_ops)
    except Exception as e:
        # Fall back to pre-mutation snapshots so the response stays valid;
        # the commit succeeded, the caller should not see an alignment error.
        logger.warning(
            f"Failed to re-query tracks after commit; falling back to "
            f"pre-mutation snapshots: {e}"
        )
        tracks = _order_tracks_by_op(list(content_map.values()), converted_ops)

    return ConvertResponse(
        tracks=tracks,
        result=ConvertResult(
            format_out=args.format_out,
            converted=converted_ops,
            deleted=deleted,
            skipped=skipped,
        ),
    )
