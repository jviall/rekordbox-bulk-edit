"""Convert API for rekordbox-edit."""

import logging
import os
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, Protocol, Tuple, cast

import ffmpeg
from ffmpeg import Error as FfmpegError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.api._utils import (
    _sync_audio_columns,
    _update_anlz_paths,
    stamp_usns,
    track_from_content,
    writing,
)
from rekordbox_edit.errors import OperationAborted
from rekordbox_edit.models import (
    ConvertOp,
    ConvertRequest,
    ConvertResponse,
    ConvertResult,
    SkippedTrack,
    Track,
)
from rekordbox_edit.query import find_content_by_ids, get_filtered_content
from rekordbox_edit.utils import (
    FILE_TYPES,
    AudioInfo,
    OutputFormats,
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    probe_matches_file_type,
    require_ffmpeg,
)

_logger = logging.getLogger(__name__)

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
    _logger.debug(
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
    require_ffmpeg()

    try:
        (
            ffmpeg.input(input_path)
            .output(output_path, **output_kwargs)
            .overwrite_output()
            # ffmpeg-python leaves the child on the parent's stdin, and ffmpeg
            # then puts the terminal in non-canonical mode to watch for keys
            # like "q". Concurrent encodes race on saving and restoring that
            # state, and the loser restores raw mode, leaving the shell echoing
            # ^M instead of accepting Enter.
            .global_args("-nostdin")
            .run(capture_stdout=True, capture_stderr=True)
        )
        _logger.debug(f"Conversion to {label} succeeded: {output_path}")
        return True
    except FfmpegError as e:
        _logger.error(f"FFmpeg conversion failed for {input_path}: {e}")
        if e.stderr:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr
            _logger.debug(f"FFmpeg stderr:\n{stderr}")
        return False
    except Exception as e:
        _logger.error(f"Conversion failed for {input_path}: {e}")
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
        _logger.debug("MP3 bitrate not found in probe, assuming 320kbps")
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

    source_path: str
    file_name: str | None
    file_type: int | None
    output_path: str
    temp_path: str
    output_format: str
    track: Track | None = None


class ConvertProgress(Protocol):
    """Reports which files are being encoded, for a caller that wants to show it.

    `convert()` knows when an encode starts and finishes; how that is displayed
    belongs to the caller. Implementations must tolerate calls from any order
    of starts and finishes, and must not raise.
    """

    def batch_size(self, total: int) -> None:
        """How many files this run will encode, known once classification has
        dropped the ones it will not touch."""

    def started(self, index: int, file_name: str | None) -> None:
        """An encode for `index` has been handed to a worker."""

    def finished(self, index: int, converted: bool) -> None:
        """The encode for `index` was collected. `converted` is False when the
        file was skipped rather than encoded."""


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


def _encode_job_for(
    content: DjmdContent, op: ConvertOp, output_format: str
) -> _EncodeJob:
    """Copy what the encode needs off a content row, on the main thread."""
    return _EncodeJob(
        source_path=content.FolderPath or "",
        file_name=content.FileNameL,
        file_type=content.FileType,
        output_path=op.output_path,
        temp_path=_temp_output_path(op.output_path),
        output_format=output_format,
        track=op.track,
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
        _logger.warning(f"Skipping {job.file_name}: {job.source_path} is gone")
        return _EncodeResult(
            job,
            skipped=SkippedTrack(reason="file_not_found", track=job.track),
        )

    audio_info = get_audio_info(job.source_path)
    if not probe_matches_file_type(
        job.file_type, audio_info["codec"], audio_info["container"]
    ):
        _logger.warning(
            f"Skipping {job.file_name}: probed codec "
            f"{audio_info['codec']!r} does not match its Rekordbox "
            f"file type {get_file_type_name(job.file_type)!r}"
        )
        return _EncodeResult(
            job,
            skipped=SkippedTrack(reason="codec_mismatch", track=job.track),
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
        _logger.debug(f"Removed temp output {temp_path}")
    except OSError as e:
        _logger.debug(f"Could not remove temp output {temp_path}: {e}")


def _sweep_orphan_temp_files(output_paths: Iterable[str]) -> None:
    """Remove temp files a killed run left behind, in the directories this run
    is about to write to. Only those directories are read, so the sweep never
    walks the library."""
    removed = 0
    for directory in {os.path.dirname(path) for path in output_paths}:
        try:
            names = os.listdir(directory)
        except OSError as e:
            _logger.debug(f"Could not sweep {directory}: {e}")
            continue
        for name in names:
            if name.startswith(TEMP_PREFIX):
                _remove_temp_file(os.path.join(directory, name))
                removed += 1
    if removed:
        _logger.debug(f"convert swept {removed} orphaned temp file(s)")


class ConvertAborted(OperationAborted):
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
    _logger.debug("Attempting DB session rollback.")
    if not (db and db.session):
        return
    try:
        db.session.rollback()
    except Exception as e:
        _logger.critical(f"Encountered error during session rollback: {e}")
        _logger.critical(
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
    track = track_from_content(content)
    target = get_file_type_for_format(args.format_out)
    if content.FileType == target:
        _logger.debug(
            f"skip convert id={content.ID} reason=already_target_format "
            f"file_type={content.FileType} target={target}"
        )
        return SkippedTrack(reason="already_target_format", track=track)
    if content.FileType not in _INPUT_FILE_TYPES:
        _logger.debug(
            f"skip convert id={content.ID} reason=unsupported_source_format "
            f"file_type={content.FileType}"
        )
        return SkippedTrack(reason="unsupported_source_format", track=track)
    output_path, _, _ = _get_output_path(content, args.format_out)
    if not args.overwrite and os.path.exists(output_path):
        _logger.debug(
            f"skip convert id={content.ID} reason=output_file_exists path={output_path}"
        )
        return SkippedTrack(reason="output_file_exists", track=track)
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
        track=track,
    )


def _recheck_convert(op: ConvertOp, args: ConvertRequest) -> ConvertOp | SkippedTrack:
    """Confirm an already-approved conversion still holds.

    The op cleared classification during the preview, so a path that reads
    differently now changed while the user was deciding. A `db_or_fs_changed`
    skip reports `op.track`, the plan-time snapshot, rather than re-reading
    the row: unlike edit, convert has no live row on hand here to refresh it
    from.
    """
    if not os.path.exists(op.source_path):
        _logger.debug(
            f"skip convert id={op.id} reason=db_or_fs_changed "
            f"source_gone={op.source_path}"
        )
        return SkippedTrack(reason="db_or_fs_changed", track=op.track)
    if not args.overwrite and os.path.exists(op.output_path):
        _logger.debug(
            f"skip convert id={op.id} reason=db_or_fs_changed "
            f"output_appeared={op.output_path}"
        )
        return SkippedTrack(reason="db_or_fs_changed", track=op.track)
    return op


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
    progress: ConvertProgress | None = None,
    ops: list[ConvertOp] | None = None,
) -> ConvertResponse:
    """Convert audio files to a target format and update the Rekordbox database.

    With `dry_run=True`, returns the planned conversions without any ffmpeg or
    DB writes. With `dry_run=False` (default), commits the changes.

    Each file commits in its own transaction, so a failure raises
    ConvertAborted with the files already converted left committed. Only the
    failing file rolls back, and its post-commit work (the ANLZ path update and
    the original deletion) only warns.

    Pass `ops` to convert an already-approved plan. No filter runs, so a track
    that started matching since the plan was made cannot join the batch; each
    op's paths are re-checked and reported as `db_or_fs_changed` if they no
    longer hold.
    """
    _logger.debug(f"convert start format_out={args.format_out} dry_run={dry_run}")
    require_ffmpeg()

    planned: list[ConvertOp] = []
    skipped: list[SkippedTrack] = []

    if ops is None:
        contents = get_filtered_content(db, args).scalars().all()
        _logger.debug(f"convert fetched {len(contents)} candidate(s) from filter")
        for c in contents:
            result = _classify_convert(c, args)
            if isinstance(result, ConvertOp):
                planned.append(result)
            else:
                skipped.append(result)
        _logger.debug(f"convert classified ops={len(planned)} skipped={len(skipped)}")
    else:
        rows = find_content_by_ids(db, [op.id for op in ops])
        contents = []
        for op in ops:
            content = rows.get(op.id)
            if content is None:
                _logger.debug(
                    f"skip convert id={op.id} reason=db_or_fs_changed row_gone"
                )
                skipped.append(SkippedTrack(reason="db_or_fs_changed", track=op.track))
                continue
            result = _recheck_convert(op, args)
            if isinstance(result, ConvertOp):
                planned.append(result)
                contents.append(content)
            else:
                skipped.append(result)
        _logger.debug(f"convert re-checked ops={len(planned)} skipped={len(skipped)}")

    ops = planned

    if dry_run:
        _logger.debug(f"convert dry-run return with {len(ops)} planned conversion(s)")
        return ConvertResponse(
            result=ConvertResult(
                format_out=args.format_out,
                dry_run=True,
                converted=ops,
                deleted=0,
                skipped=skipped,
            ),
        )

    if not ops:
        return ConvertResponse(
            result=ConvertResult(
                format_out=args.format_out,
                dry_run=dry_run,
                converted=[],
                deleted=0,
                skipped=skipped,
            ),
        )

    assert db.session is not None

    # Guards the sweep as well as the encode loop: the sweep deletes temp
    # files, which a concurrent run would still be writing into.
    with writing(db, "convert"):
        # content_map enables per-op live FolderPath / FileNameL reads in the loop.
        content_map = {str(c.ID): c for c in contents}
        converted_ops: list[ConvertOp] = []
        _sweep_orphan_temp_files(op.output_path for op in ops)

        output_format_name = args.format_out.upper()
        deletable = 0
        deleted = 0

        jobs = [
            _encode_job_for(content_map[op.id], op, output_format_name) for op in ops
        ]
        if progress:
            progress.batch_size(len(jobs))

        def _abort_batch(
            exc: BaseException, job: _EncodeJob, attempted: int
        ) -> ConvertAborted:
            """Give up on the batch, keeping every conversion already committed."""
            _rollback_session(db)
            _logger.debug(
                f"convert aborted at {job.source_path} after "
                f"{len(converted_ops)} committed conversion(s)"
            )
            return ConvertAborted(
                str(exc),
                failed_path=job.source_path,
                converted=len(converted_ops),
                not_attempted=len(ops) - attempted,
            )

        # Encoding runs on worker threads; every database touch stays here on the
        # main thread. `encoding` maps a job's position in `jobs` to the worker
        # currently handling it.
        thread_count = args.threads
        encoding: dict[int, Future[_EncodeResult]] = {}

        with ThreadPoolExecutor(max_workers=thread_count) as pool:

            def _start_encode(index: int) -> None:
                """Hand job `index` to a worker, if the batch runs that far."""
                if index < len(jobs):
                    encoding[index] = pool.submit(_encode_one, jobs[index])
                    if progress:
                        progress.started(index, jobs[index].file_name)

            def _stop_pending_encodes() -> None:
                """Give up on everything still in flight, leaving no stray files.

                Cancelling only stops work no worker has picked up yet, so an
                encode that already finished holds a temp file nobody will move
                into place. Those are deleted here rather than left for the next
                run's sweep.
                """
                for future in encoding.values():
                    future.cancel()
                for index, future in encoding.items():
                    if future.cancelled() or future.exception() is not None:
                        continue
                    if future.result().skipped is None:
                        _remove_temp_file(jobs[index].temp_path)
                encoding.clear()

            # Prime the pool with one file per worker. Nothing more starts until a
            # result is collected below, so at most `thread_count` files are ever
            # in flight, and an abort has wasted at most that many encodes.
            for index in range(min(thread_count, len(jobs))):
                _start_encode(index)

            # Collect results in the order the files were listed rather than the
            # order they happen to finish: waiting on `encoding[index]` blocks
            # until that particular file is done, so one that finished early simply
            # waits its turn. `index` walks `jobs`; `position` is the same count
            # from one, for the progress line. Predictable order matters because
            # `rbe convert --print ids` feeds other commands.
            for index, (op, job) in enumerate(zip(ops, jobs)):
                position = index + 1
                content = content_map[op.id]

                try:
                    result = encoding.pop(index).result()
                except KeyboardInterrupt as e:
                    _stop_pending_encodes()
                    _logger.warning("Interrupted; keeping the files already converted.")
                    raise _abort_batch(e, job, position) from e
                except BaseException as e:
                    _stop_pending_encodes()
                    raise _abort_batch(e, job, position) from e

                # A worker just came free, so give it the next file nobody has
                # started. Starting one only after a successful collection is what
                # keeps the in-flight count capped and leaves no queued work behind
                # on an abort.
                _start_encode(index + thread_count)

                if progress:
                    progress.finished(index, converted=result.skipped is None)

                if result.skipped:
                    skipped.append(result.skipped)
                    continue

                # Printed on completion rather than at dispatch: with several
                # encodes in flight, a line printed at dispatch would name a file
                # that is not the one being worked on next.
                _logger.info(f"[{position}/{len(ops)}] converted {job.file_name}")

                try:
                    os.replace(job.temp_path, job.output_path)
                    _apply_converted_record(
                        content,
                        cast(ConvertedFileProbe, result.probe),
                        os.path.basename(job.output_path),
                        os.path.dirname(job.output_path),
                        output_format_name,
                    )
                    stamp_usns(db, [content])
                    db.session.commit()
                except BaseException as e:
                    _remove_temp_file(job.temp_path)
                    _stop_pending_encodes()
                    raise _abort_batch(e, job, position) from e

                # Refreshed post-commit: op.track up to now is the
                # pre-conversion classification snapshot, and
                # _apply_converted_record() just mutated the row's file
                # location and audio columns in place.
                converted_ops.append(
                    op.model_copy(
                        update={
                            "source_path": job.source_path,
                            "output_sample_rate": result.output_sample_rate,
                            "track": track_from_content(content),
                        }
                    )
                )

                # Past this point the row is committed, so every failure only warns.
                try:
                    _update_anlz_paths(db, content, os.path.basename(job.output_path))
                except Exception as e:
                    _logger.warning(
                        f"Failed to update ANLZ path tags for {job.file_name}: {e}"
                    )

                if _deletes_original(args.delete_originals, result.is_lossless):
                    deletable += 1
                    try:
                        os.remove(job.source_path)
                        deleted += 1
                    except Exception as e:
                        _logger.warning(f"Failed to delete {job.source_path}: {e}")

    _logger.debug(f"convert committed {len(converted_ops)} conversion(s)")

    kept = len(converted_ops) - deletable
    if args.delete_originals == "lossless" and kept and output_format_name != "MP3":
        _logger.info(f"Kept {kept} original file(s) whose conversion was lossy")

    return ConvertResponse(
        result=ConvertResult(
            format_out=args.format_out,
            dry_run=dry_run,
            converted=converted_ops,
            deleted=deleted,
            skipped=skipped,
        ),
    )
