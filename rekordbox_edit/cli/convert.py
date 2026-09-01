"""Convert CLI command."""

import logging
import sys

import click

from rekordbox_edit.cli._click import (
    add_click_options,
    convert_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.convert import ConvertAborted, convert
from rekordbox_edit.cli._progress import convert_progress
from rekordbox_edit.cli._utils import (
    SCRIPTING_MODES,
    _build_args,
    _handle_stdin,
    _print_response_ids,
    _print_response_json,
    UserQuit,
    _validate_scripting_preconditions,
    confirm,
    with_database,
)
from rekordbox_edit.display import PrintableField, print_track_info
from rekordbox_edit.logger import PrintChoice, get_debug_file_path, set_level
from rekordbox_edit.models import ConvertRequest

logger = logging.getLogger(__name__)

# Skips a dry run cannot predict: it neither probes a source nor re-stats one,
# so these surface only from the live pass.
_LIVE_ONLY_SKIPS = frozenset({"codec_mismatch", "file_not_found", "db_or_fs_changed"})


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options(
    [
        *convert_click_options,
        *global_click_confirmations,
        *global_click_filters,
        print_option,
        track_ids_argument,
    ]
)
@with_database(writes=True)
def convert_command(db, **kwargs):
    """Convert hi-res audio files between formats and update RekordBox database.

    Supports conversion from any hi-res format (FLAC, ALAC, AIFF, WAV) to:
    AIFF, FLAC, WAV, or MP3. Skips lossy formats, video, and files already
    in the target format. Each source's codec is verified against its
    database file type before converting; mismatches are skipped.

    Lossless conversions target 16-bit/44.1 kHz: higher-resolution sources
    are down-sampled, and sources below the target keep their own sample
    rate rather than being up-sampled.
    """
    print_opt = kwargs.pop("print_opt", None)
    dry_run = kwargs.pop("dry_run", False)
    yes = kwargs.pop("yes", False)
    interactive = kwargs.pop("interactive", False)
    args = _build_args(ConvertRequest, kwargs)
    set_level(print_opt)
    piped_stdin = _handle_stdin(args)
    _validate_scripting_preconditions(
        print_opt,
        piped_stdin=piped_stdin,
        dry_run=dry_run,
        yes=yes,
        interactive=interactive,
    )

    scripting_mode = print_opt in SCRIPTING_MODES

    if yes or dry_run:
        with convert_progress(enabled=not scripting_mode and not dry_run) as progress:
            response = _convert_reporting_partials(
                db, args, dry_run=dry_run, progress=progress
            )
        _report_skips(response.result.skipped)
        _print_convert_result(response, print_opt, scripting_mode, dry_run=dry_run)
        return

    # Default / interactive: preview first.
    preview = convert(db, args, dry_run=True)

    try:
        args, preview, named = _prompt_overwrite(db, args, preview)
    except UserQuit:
        return

    _report_skips(preview.result.skipped, exclude=named)

    if not preview.result.converted:
        logger.info("No files need conversion.")
        return

    logger.info(
        f"Found {len(preview.result.converted)} files to convert to "
        f"{preview.result.format_out.upper()}"
    )
    if not scripting_mode:
        print_track_info(
            preview.tracks,
            changed_field=PrintableField.FileType,
            new_values=[preview.result.format_out.upper()] * len(preview.tracks),
        )

    if interactive:
        selected_ids = []
        for track, op in zip(preview.tracks, preview.result.converted):
            try:
                if confirm(f"  Convert {track.FileNameL}?", default=True):
                    selected_ids.append(op.id)
            except UserQuit:
                break
        if not selected_ids:
            logger.info("Cancelled.")
            return
        chosen = set(selected_ids)
        selected = [op for op in preview.result.converted if op.id in chosen]
        with convert_progress(enabled=True) as progress:
            response = _convert_reporting_partials(
                db, args, ops=selected, progress=progress
            )
    else:
        try:
            if not confirm(
                f"Convert {len(preview.result.converted)} files to "
                f"{preview.result.format_out.upper()}?",
                default=True,
            ):
                logger.info("Cancelled.")
                return
        except UserQuit:
            return
        with convert_progress(enabled=True) as progress:
            response = _convert_reporting_partials(
                db, args, ops=preview.result.converted, progress=progress
            )

    _report_skips([s for s in response.result.skipped if s.reason in _LIVE_ONLY_SKIPS])
    _print_convert_result(response, print_opt, scripting_mode, dry_run=False)


def _convert_reporting_partials(
    db, args, *, dry_run: bool = False, progress=None, ops=None
):
    """Convert, reporting a batch that stopped partway as a plain result rather
    than as a crash. The committed conversions are real and are kept."""
    try:
        return convert(db, args, dry_run=dry_run, progress=progress, ops=ops)
    except ConvertAborted as e:
        logger.error(f"Conversion stopped at {e.failed_path}: {e}")
        logger.error(
            f"{e.converted} file(s) converted and kept, 1 failed, "
            f"{e.not_attempted} not attempted."
        )
        sys.exit(1)


def _prompt_overwrite(db, args, preview):
    """Offer to clobber output files that already exist, which are skipped by
    default.

    Returns the request and preview to carry forward, and the skip reason this
    prompt accounted for so the summary does not repeat it. Passing
    `--overwrite` answers the question up front, so no prompt appears.
    """
    if args.overwrite:
        return args, preview, frozenset()
    conflicts = [s for s in preview.result.skipped if s.reason == "output_file_exists"]
    if not conflicts:
        return args, preview, frozenset()

    logger.info(
        f"{len(conflicts)} file(s) already have a {args.format_out.upper()} file "
        "at the path this would write."
    )
    if not confirm(
        f"Overwrite {len(conflicts)} existing output file(s)?", default=False
    ):
        return args, preview, frozenset({"output_file_exists"})

    args = args.model_copy(update={"overwrite": True})
    return args, convert(db, args, dry_run=True), frozenset()


#: How each skip reason reads as a one-line summary, so a run that converted 4
#: of the 30 files a filter matched accounts for the other 26.
_SKIP_MESSAGES: dict[str, str] = {
    "already_target_format": "already in target format",
    "unsupported_source_format": (
        "unsupported source format (only FLAC, ALAC, AIFF, WAV are converted)"
    ),
    "output_file_exists": "output exists (use --overwrite to convert)",
    "codec_mismatch": "file content does not match its Rekordbox file type",
    "file_not_found": "source file is gone",
    "db_or_fs_changed": "changed since the preview",
}


def _report_skips(skipped, *, exclude: frozenset[str] = frozenset()) -> None:
    for reason, message in _SKIP_MESSAGES.items():
        if reason in exclude:
            continue
        count = sum(1 for s in skipped if s.reason == reason)
        if count:
            logger.warning(f"Skipping {count} file(s): {message}")


def _print_convert_result(
    response, print_opt, scripting_mode, *, dry_run: bool
) -> None:
    if not dry_run:
        logger.info(
            f"\nConverted {len(response.result.converted)} files to "
            f"{response.result.format_out.upper()}"
        )
        if response.result.deleted:
            logger.info(f"Deleted {response.result.deleted} original file(s)")
    if print_opt == PrintChoice.IDS:
        _print_response_ids(response)
    elif print_opt == PrintChoice.JSON:
        _print_response_json(response)
    elif not scripting_mode and dry_run:
        print_track_info(
            response.tracks,
            changed_field=PrintableField.FileType,
            new_values=[response.result.format_out.upper()] * len(response.tracks),
        )
