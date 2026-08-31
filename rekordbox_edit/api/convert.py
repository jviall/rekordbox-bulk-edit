"""Convert API for rekordbox-edit."""

import logging
import os
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, Tuple, cast

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
    file_size: int


def _probe_converted_file(
    converted_file_path: Path | str, output_format: str
) -> ConvertedFileProbe:
    """Probe a converted file for the values its content row needs."""
    audio_info = get_audio_info(converted_file_path)
    if output_format.upper() == "MP3" and audio_info["bitrate"] is None:
        logger.debug("MP3 bitrate not found in probe, assuming 320kbps")
        audio_info["bitrate"] = 320
    return ConvertedFileProbe(
        audio_info=audio_info,
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

    _sync_audio_columns(content, probe.audio_info, file_type, probe.file_size)


@dataclass(frozen=True)
class _EncodeJob:
    """One conversion's inputs, as plain values.

    Everything the encode needs is copied off the content row here, on the main
    thread. Nothing in this class may be a `DjmdContent` or hold a reference to
    one: reading an ORM attribute off the main thread would pull on a session
    that is not thread-safe.
    """

    op_id: str
    source_path: str
    file_name: str | None
    file_type: int | None
    output_path: str
    temp_path: str
    output_format: str


@dataclass
class _EncodeResult:
    """What an encode produced, or why it declined to run.

    `skipped` set means the file was passed over and nothing was written.
    Otherwise `probe` describes the finished temp file awaiting its move
    into place.
    """

    job: _EncodeJob
    skipped: SkippedTrack | None = None
    probe: ConvertedFileProbe | None = None
    is_lossless: bool = False
    output_sample_rate: int = TARGET_SAMPLE_RATE


def _job_for(content: DjmdContent, op: ConvertOp, output_format: str) -> _EncodeJob:
    """Copy what the encode needs off a content row, on the main thread."""
    return _EncodeJob(
        op_id=op.id,
        source_path=content.FolderPath or "",
        file_name=content.FileNameL,
        file_type=content.FileType,
        output_path=op.output_path,
        temp_path=_temp_output_path(op.output_path),
        output_format=output_format,
    )


def _encode_one(job: _EncodeJob) -> _EncodeResult:
    """Probe, encode, and probe again, touching no database state.

    Runs on a worker thread once encoding is parallel, so it reports a skip
    rather than mutating shared state, and cleans up its own temp file if the
    encode fails partway.
    """
    if not os.path.exists(job.source_path):
        # Classification and the encode are separated by a confirmation prompt,
        # so a source going missing is an expected outcome of that window
        # rather than a systemic failure worth abandoning the batch.
        logger.warning(f"Skipping {job.file_name}: {job.source_path} is gone")
        return _EncodeResult(
            job, skipped=SkippedTrack(id=job.op_id, reason="file_not_found")
        )

    audio_info = get_audio_info(job.source_path)
    if not probe_matches_file_type(
        job.file_type, audio_info["codec"], audio_info["container"]
    ):
        logger.warning(
            f"Skipping {job.file_name}: probed codec "
            f"{audio_info['codec']!r} does not match its Rekordbox "
            f"file type {get_file_type_name(job.file_type)!r}"
        )
        return _EncodeResult(
            job, skipped=SkippedTrack(id=job.op_id, reason="codec_mismatch")
        )

    if job.output_format == "MP3":
        # MP3 output always loses information, so it is never lossless.
        is_lossless = False
        output_sample_rate = TARGET_SAMPLE_RATE
        output_kwargs = _mp3_output_kwargs(output_sample_rate)
        label = "mp3"
    else:
        fidelity, output_sample_rate = _classify_fidelity(audio_info)
        is_lossless = fidelity == "lossless"
        output_format = OutputFormats(job.output_format.lower())
        output_kwargs = _hi_res_output_kwargs(output_format, output_sample_rate)
        label = output_format.value

    try:
        if not _run_ffmpeg(job.source_path, job.temp_path, output_kwargs, label):
            raise RuntimeError(f"Conversion failed for {job.source_path}")
        if not os.path.exists(job.temp_path):
            raise RuntimeError(f"Output file not created: {job.output_path}")
        probe = _probe_converted_file(job.temp_path, job.output_format)
    except BaseException:
        _remove_temp_file(job.temp_path)
        raise

    return _EncodeResult(
        job,
        probe=probe,
        is_lossless=is_lossless,
        output_sample_rate=output_sample_rate,
    )


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


class ConvertAborted(RuntimeError):
    """A conversion failed partway through a batch.

    Files converted before the failure are already committed, so the counts
    travel with the error rather than being recovered from the response the
    caller never receives.
    """

    def __init__(
        self,
        reason: str,
        *,
        failed_path: str,
        converted: int,
        not_attempted: int,
    ):
        self.failed_path = failed_path
        self.converted = converted
        self.not_attempted = not_attempted
        super().__init__(reason)


def _rollback_session(db) -> None:
    """Roll back whatever the failing file left uncommitted. Earlier files
    committed in their own transactions and are unaffected."""
    logger.debug("Attempting DB session rollback.")
    if not (db and db.session):
        return
    try:
        db.session.rollback()
    except Exception as e:
        logger.critical(f"Encountered error during session rollback: {e}")
        logger.critical(
            "Check the state of your rekordbox library and consider reverting to a backup database if something's not right"
        )
        raise


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


def _deletes_original(mode: str, is_lossless: bool) -> bool:
    """Whether this conversion's original should be deleted under `mode`."""
    if mode == "all":
        return True
    return mode == "lossless" and is_lossless


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

    Each file commits in its own transaction, so a failure raises
    ConvertAborted with the files already converted left committed. Only the
    failing file rolls back, and its post-commit work (the ANLZ path update and
    the original deletion) only warns.
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
    _sweep_orphan_temp_files(op.output_path for op in ops)

    output_format_name = args.format_out.upper()
    deletable = 0
    deleted = 0

    jobs = [_job_for(content_map[op.id], op, output_format_name) for op in ops]

    def _abort(exc: BaseException, job: _EncodeJob, attempted: int) -> ConvertAborted:
        """Give up on the batch, keeping every conversion already committed."""
        _rollback_session(db)
        logger.debug(
            f"convert aborted at {job.source_path} after "
            f"{len(converted_ops)} committed conversion(s)"
        )
        return ConvertAborted(
            str(exc),
            failed_path=job.source_path,
            converted=len(converted_ops),
            not_attempted=len(ops) - attempted,
        )

    workers = args.threads
    futures: dict[int, Future[_EncodeResult]] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:

        def _submit(index: int) -> None:
            if index < len(jobs):
                futures[index] = pool.submit(_encode_one, jobs[index])

        def _discard_outstanding() -> None:
            """Drop queued work and clean up temps from encodes already done.

            Encoding is the expensive half, so nothing beyond the pool's width
            is ever queued, and an abort wastes at most that many files.
            """
            for future in futures.values():
                future.cancel()
            for index, future in futures.items():
                if future.cancelled() or future.exception() is not None:
                    continue
                if future.result().skipped is None:
                    _remove_temp_file(jobs[index].temp_path)
            futures.clear()

        # Only `workers` jobs run ahead of the drain point, topped up as each
        # result lands, so a failure cannot burn the whole batch's CPU first.
        for index in range(min(workers, len(jobs))):
            _submit(index)

        # Drained in submission order, not completion order, so converted_ops,
        # the progress lines, and --print ids stay deterministic.
        for i, (op, job) in enumerate(zip(ops, jobs), 1):
            content = content_map[op.id]
            logger.info(f"[{i}/{len(ops)}] {job.file_name}")

            try:
                result = futures.pop(i - 1).result()
            except BaseException as e:
                _discard_outstanding()
                raise _abort(e, job, i) from e

            # Topped up only once this file cleared, so an abort never leaves
            # work queued that nobody will drain.
            _submit(i - 1 + workers)

            if result.skipped:
                skipped.append(result.skipped)
                continue

            try:
                os.replace(job.temp_path, job.output_path)
                _apply_converted_record(
                    content,
                    cast(ConvertedFileProbe, result.probe),
                    os.path.basename(job.output_path),
                    os.path.dirname(job.output_path),
                    output_format_name,
                )
                db.session.commit()
            except BaseException as e:
                _remove_temp_file(job.temp_path)
                _discard_outstanding()
                raise _abort(e, job, i) from e

            converted_ops.append(
                op.model_copy(
                    update={
                        "source_path": job.source_path,
                        "output_sample_rate": result.output_sample_rate,
                    }
                )
            )

            # Past this point the row is committed, so every failure only warns.
            try:
                _update_anlz_paths(db, content, os.path.basename(job.output_path))
            except Exception as e:
                logger.warning(
                    f"Failed to update ANLZ path tags for {job.file_name}: {e}"
                )

            if _deletes_original(args.delete_originals, result.is_lossless):
                deletable += 1
                try:
                    os.remove(job.source_path)
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {job.source_path}: {e}")

    logger.info(f"\nConverted {len(converted_ops)} files to {output_format_name}")
    logger.debug(f"convert committed {len(converted_ops)} conversion(s)")

    kept = len(converted_ops) - deletable
    if args.delete_originals == "lossless" and kept and output_format_name != "MP3":
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
