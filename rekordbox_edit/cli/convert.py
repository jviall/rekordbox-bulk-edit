"""Convert CLI command."""

import logging

import click

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    convert_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.convert import convert
from rekordbox_edit.cli._utils import (
    SCRIPTING_MODES,
    _build_args,
    _handle_stdin,
    _narrow_to_track_ids,
    _print_response_ids,
    _print_response_json,
    _validate_scripting_preconditions,
    with_database,
)
from rekordbox_edit.display import PrintableField, print_track_info
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.models import ConvertRequest
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)


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
        type("_S", (), {"dry_run": dry_run, "yes": yes})(),
        piped_stdin,
    )

    scripting_mode = print_opt in SCRIPTING_MODES

    if yes or dry_run:
        response = convert(db, args, dry_run=dry_run)
        _report_skips(response.result.skipped)
        _print_convert_result(response, print_opt, scripting_mode, dry_run=dry_run)
        return

    # Default / interactive: preview first.
    preview = convert(db, args, dry_run=True)
    _report_skips(preview.result.skipped)

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
        narrowed = _narrow_to_track_ids(args, selected_ids)
        response = convert(db, narrowed)
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
        response = convert(db, args)

    # The preview cannot surface codec_mismatch (dry runs never probe), so
    # report skips found only during the live run.
    _report_skips([s for s in response.result.skipped if s.reason == "codec_mismatch"])
    _print_convert_result(response, print_opt, scripting_mode, dry_run=False)


def _report_skips(skipped) -> None:
    already_target = sum(1 for s in skipped if s.reason == "already_target_format")
    unsupported = sum(1 for s in skipped if s.reason == "unsupported_source_format")
    conflicts = sum(1 for s in skipped if s.reason == "output_file_exists")
    mismatches = sum(1 for s in skipped if s.reason == "codec_mismatch")
    if already_target:
        logger.warning(f"Skipping {already_target} file(s): already in target format")
    if unsupported:
        logger.warning(
            f"Skipping {unsupported} file(s): unsupported source format "
            "(only FLAC, ALAC, AIFF, WAV are converted)"
        )
    if conflicts:
        logger.warning(
            f"Skipping {conflicts} file(s): output exists (use --overwrite to convert)"
        )
    if mismatches:
        logger.warning(
            f"Skipping {mismatches} file(s): file content does not match its "
            "Rekordbox file type"
        )


def _print_convert_result(
    response, print_opt, scripting_mode, *, dry_run: bool
) -> None:
    if not dry_run:
        logger.info(
            f"Converted {len(response.result.converted)} files to "
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
