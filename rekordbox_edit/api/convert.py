"""Convert API for rekordbox-edit."""

import logging
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, NamedTuple, Tuple

import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent
from sqlalchemy import select

from rekordbox_edit.api._utils import (
    _order_tracks_by_op,
    _sync_audio_columns,
    _update_anlz_paths,
)
from rekordbox_edit.models import (
    ConvertOp,
    ConvertRequest,
    ConvertResponse,
    ConvertResult,
    SkippedTrack,
)
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.utils import (
    FILE_TYPES,
    AudioInfo,
    OutputFormats,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    probe_matches_file_type,
)

logger = logging.getLogger(__name__)

TARGET_BIT_DEPTH = 16
TARGET_SAMPLE_RATE = 44100

# Rekordbox FileType codes RBE converts from: the lossless whitelist.
_INPUT_FILE_TYPES = {info.code for info in FILE_TYPES.items() if info.convertable}

# Encoding writes here first, so a hard kill leaves a recognizable orphan
# rather than a truncated file at the name the database will point at.
TEMP_PREFIX = ".rbe-convert-"

_HI_RES_CODECS = {
    "aiff": "pcm_s16be",
    "wav": "pcm_s16le",
    "flac": "flac",
}


# ── ffmpeg helpers ────────────────────────────────────────────────────────


def _effective_sample_rate(source_rate: int | None) -> int:
    """The output sample rate for a conversion: the target, clamped to the
    source rate so a conversion never up-samples."""
    if source_rate and source_rate < TARGET_SAMPLE_RATE:
        return source_rate
    return TARGET_SAMPLE_RATE


def _classify_fidelity(
    audio_info: AudioInfo,
) -> Tuple[Literal["lossless", "lossy"], int]:
    """The conversion's fidelity and effective sample rate for a probed
    source. "lossless" means no audio information is lost: the source is at
    the target bit depth and at or below the target sample rate. An unknown
    bit depth counts as lossy so originals are kept when in doubt.
    """
    bit_depth = audio_info["bit_depth"]
    sample_rate = audio_info["sample_rate"]
    logger.debug(
        f"Source audio: bit_depth={bit_depth}, sample_rate={sample_rate}, "
        f"channels={audio_info.get('channels')}"
    )
    effective_rate = _effective_sample_rate(sample_rate)
    if bit_depth == TARGET_BIT_DEPTH and sample_rate == effective_rate:
        return "lossless", effective_rate
    return "lossy", effective_rate


def _hi_res_output_kwargs(output_format, sample_rate) -> dict:
    """ffmpeg output kwargs for a hi-res conversion at the target bit depth and
    the given sample rate."""
    codec = _HI_RES_CODECS.get(output_format.value)
    if codec is None:
        raise Exception(f"Unsupported hi-res format: {output_format}")
    kwargs = {
        "acodec": codec,
        "ar": sample_rate,
        "map_metadata": 0,
        "write_id3v2": 1,
    }
    # PCM codecs fix the bit depth by name; the flac encoder needs it spelled out.
    if output_format.value == "flac":
        kwargs["sample_fmt"] = "s16"
    return kwargs


def _mp3_output_kwargs(sample_rate) -> dict:
    """ffmpeg output kwargs for MP3 320kbps CBR at the given sample rate."""
    return {
        "acodec": "libmp3lame",
        "audio_bitrate": "320k",
        "ar": sample_rate,
        # libmp3lame takes planar input; s16p quantizes to 16-bit before encoding.
        "sample_fmt": "s16p",
        "map_metadata": 0,
        "write_id3v2": 1,
    }


def _run_ffmpeg(input_path, output_path, output_kwargs: dict, label: str) -> bool:
    """Run a single ffmpeg conversion. Returns True on success, False on an
    ffmpeg error; re-raises anything else. `label` names the target for logs."""
    from rekordbox_edit.utils import ffmpeg_in_path, get_ffmpeg_directions

    if not ffmpeg_in_path():
        raise Exception(f"FFmpeg not found in PATH.{get_ffmpeg_directions()}")

    try:
        (
            ffmpeg.input(input_path)
            .output(output_path, **output_kwargs)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.debug(f"Conversion to {label} succeeded: {output_path}")
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


class ConvertedFileProbe(NamedTuple):
    """What a finished conversion looks like on disk.

    Gathered without touching the session so the work can move off the main
    thread, where an ORM attribute read would not be safe.
    """

    audio_info: AudioInfo
    bitrate: int | None
    file_size: int


def _probe_converted_file(
    converted_file_path: Path | str, output_format: str
) -> ConvertedFileProbe:
    """Probe a converted file for the values its content row needs."""
    audio_info = get_audio_info(converted_file_path)
    bitrate = audio_info["bitrate"]
    if output_format.upper() == "MP3" and bitrate is None:
        logger.debug("MP3 bitrate not found in probe, assuming 320kbps")
        bitrate = 320
    return ConvertedFileProbe(
        audio_info=audio_info,
        bitrate=bitrate,
        file_size=os.path.getsize(converted_file_path),
    )


def _apply_converted_record(
    content: DjmdContent,
    probe: ConvertedFileProbe,
    new_filename: str,
    new_folder: str,
    output_format: str,
) -> None:
    """Write a finished conversion's file location and audio columns onto its
    content row. Performs no filesystem work."""
    file_type = get_file_type_for_format(output_format)
    old_path = content.FolderPath
    converted_db_path = str(Path(new_folder, new_filename)).replace("\\", "/")

    content.FileNameL = new_filename
    content.FolderPath = converted_db_path

    # Original location: only update if it matches FolderPath
    if content.OrgFolderPath == old_path:
        content.OrgFolderPath = converted_db_path

    _sync_audio_columns(
        content,
        {**probe.audio_info, "bitrate": probe.bitrate},
        file_type,
        probe.file_size,
    )


def _update_database_record(
    content: DjmdContent,
    new_filename: str,
    new_folder: str,
    output_format: str,
) -> None:
    """Probe a converted file and write its values onto the content row."""
    probe = _probe_converted_file(Path(new_folder, new_filename), output_format)
    _apply_converted_record(content, probe, new_filename, new_folder, output_format)


def _temp_output_path(output_path: str) -> str:
    """A sibling of `output_path` to encode into. Keeping it in the destination
    directory means the move into place never crosses a filesystem, so it stays
    atomic. The extension is preserved because ffmpeg reads the output format
    from it."""
    directory, filename = os.path.split(output_path)
    return os.path.join(directory, f"{TEMP_PREFIX}{os.getpid()}-{filename}")


def _remove_temp_file(temp_path: str) -> None:
    try:
        os.remove(temp_path)
        logger.debug(f"Removed temp output {temp_path}")
    except OSError as e:
        logger.debug(f"Could not remove temp output {temp_path}: {e}")


def _sweep_orphan_temp_files(output_paths: Iterable[str]) -> None:
    """Remove temp files a killed run left behind, in the directories this run
    is about to write to. Only those directories are read, so the sweep never
    walks the library."""
    removed = 0
    for directory in {os.path.dirname(path) for path in output_paths}:
        try:
            names = os.listdir(directory)
        except OSError as e:
            logger.debug(f"Could not sweep {directory}: {e}")
            continue
        for name in names:
            if name.startswith(TEMP_PREFIX):
                _remove_temp_file(os.path.join(directory, name))
                removed += 1
    if removed:
        logger.debug(f"convert swept {removed} orphaned temp file(s)")


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


def _classify_convert(content, args: ConvertRequest) -> ConvertOp | SkippedTrack:
    """Return ConvertOp if this track should be converted, or SkippedTrack with
    reason if not."""
    target = get_file_type_for_format(args.format_out)
    if content.FileType == target:
        logger.debug(
            f"skip convert id={content.ID} reason=already_target_format "
            f"file_type={content.FileType} target={target}"
        )
        return SkippedTrack(id=str(content.ID), reason="already_target_format")
    if content.FileType not in _INPUT_FILE_TYPES:
        logger.debug(
            f"skip convert id={content.ID} reason=unsupported_source_format "
            f"file_type={content.FileType}"
        )
        return SkippedTrack(id=str(content.ID), reason="unsupported_source_format")
    output_path, _, _ = _get_output_path(content, args.format_out)
    if not args.overwrite and os.path.exists(output_path):
        logger.debug(
            f"skip convert id={content.ID} reason=output_file_exists path={output_path}"
        )
        return SkippedTrack(id=str(content.ID), reason="output_file_exists")
    # The DB SampleRate stands in for the probe here so dry-run previews match;
    # the convert loop re-probes and reconciles. MP3 always encodes at the target.
    if args.format_out.upper() == "MP3":
        output_sample_rate = TARGET_SAMPLE_RATE
    else:
        output_sample_rate = _effective_sample_rate(content.SampleRate)
    return ConvertOp(
        id=str(content.ID),
        source_path=content.FolderPath or "",
        output_path=output_path,
        source_file_type=get_file_type_name(content.FileType),
        source_bit_depth=content.BitDepth,
        source_sample_rate=content.SampleRate,
        output_file_type=args.format_out.upper(),
        output_bit_depth=TARGET_BIT_DEPTH,
        output_sample_rate=output_sample_rate,
    )


# ── Public API ────────────────────────────────────────────────────────────


def convert(
    db: Rekordbox6Database,
    args: ConvertRequest,
    *,
    dry_run: bool = False,
) -> ConvertResponse:
    """Convert audio files to a target format and update the Rekordbox database.

    With `dry_run=True`, returns the planned conversions without any ffmpeg or
    DB writes. With `dry_run=False` (default), commits the changes.

    The rollback block protects only pre-commit work; once a database commit lands,
    the transaction is honoured even if the delete-originals loop or response
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

    # content_map enables per-op live FolderPath / FileNameL reads in the loop.
    content_map = {str(c.ID): c for c in contents}
    converted_ops: list[ConvertOp] = []
    lossless_op_ids: set[str] = set()
    _sweep_orphan_temp_files(op.output_path for op in ops)

    pending_temp: str | None = None
    try:
        for i, op in enumerate(ops, 1):
            content = content_map[op.id]
            src = content.FolderPath or ""
            logger.info(f"[{i}/{len(ops)}] {content.FileNameL}")

            if not os.path.exists(src):
                raise RuntimeError(f"Source not found: {src}")

            audio_info = get_audio_info(src)
            if not probe_matches_file_type(
                content.FileType, audio_info["codec"], audio_info["container"]
            ):
                logger.warning(
                    f"Skipping {content.FileNameL}: probed codec "
                    f"{audio_info['codec']!r} does not match its Rekordbox "
                    f"file type {get_file_type_name(content.FileType)!r}"
                )
                skipped.append(SkippedTrack(id=op.id, reason="codec_mismatch"))
                continue

            pending_temp = _temp_output_path(op.output_path)
            if args.format_out.upper() == "MP3":
                output_sample_rate = TARGET_SAMPLE_RATE
                success = _run_ffmpeg(
                    src, pending_temp, _mp3_output_kwargs(output_sample_rate), "mp3"
                )
            else:
                fidelity, output_sample_rate = _classify_fidelity(audio_info)
                if fidelity == "lossless":
                    lossless_op_ids.add(op.id)
                output_format = OutputFormats(args.format_out.lower())
                success = _run_ffmpeg(
                    src,
                    pending_temp,
                    _hi_res_output_kwargs(output_format, output_sample_rate),
                    output_format.value,
                )

            if not success:
                raise RuntimeError(f"Conversion failed for {src}")
            if not os.path.exists(pending_temp):
                raise RuntimeError(f"Output file not created: {op.output_path}")

            os.replace(pending_temp, op.output_path)
            pending_temp = None

            _update_database_record(
                content,
                os.path.basename(op.output_path),
                os.path.dirname(op.output_path),
                args.format_out.upper(),
            )
            converted_ops.append(
                op.model_copy(
                    update={
                        "source_path": src,
                        "output_sample_rate": output_sample_rate,
                    }
                )
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
        if pending_temp:
            _remove_temp_file(pending_temp)
        _rollback_and_cleanup(db, converted_ops)
        raise

    for op in converted_ops:
        content = content_map[op.id]
        try:
            _update_anlz_paths(db, content, os.path.basename(op.output_path))
        except Exception as e:
            logger.warning(
                f"Failed to update ANLZ path tags for {content.FileNameL}: {e}"
            )

    if args.delete_originals == "all":
        deletable_ops = converted_ops
    elif args.delete_originals == "lossless":
        deletable_ops = [op for op in converted_ops if op.id in lossless_op_ids]
    else:
        deletable_ops = []
    logger.debug(
        f"convert delete_originals={args.delete_originals}: deleting "
        f"{len(deletable_ops)}/{len(converted_ops)} source file(s)"
    )

    deleted = 0
    for op in deletable_ops:
        try:
            os.remove(op.source_path)
            deleted += 1
        except Exception as e:
            logger.warning(f"Failed to delete {op.source_path}: {e}")

    kept = len(converted_ops) - len(deletable_ops)
    if (
        args.delete_originals == "lossless"
        and kept
        and args.format_out.upper() != "MP3"
    ):
        logger.info(f"Kept {kept} original file(s) whose conversion was lossy")

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
