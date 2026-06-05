"""Convert CLI command."""

import logging
import sys

import click
from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    convert_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.convert import convert, plan_convert
from rekordbox_edit.models import ConvertCommandArgs
from rekordbox_edit.cli._utils import (
    _confirm_converts,
    _handle_stdin,
    _print_ids,
    _validate_scripting_preconditions,
)
from rekordbox_edit.display import PrintableField, print_track_info
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options(
    [
        *global_click_filters,
        *global_click_confirmations,
        *convert_click_options,
        print_option,
        track_ids_argument,
    ]
)
def convert_command(**kwargs):
    """Convert lossless audio files between formats and update RekordBox database.

    Supports conversion from any lossless format (FLAC, AIFF, WAV) to:
    AIFF, FLAC, WAV, ALAC, or MP3.

    Skips lossy formats and files already in the target format.
    """
    print_opt = kwargs.pop("print_opt", None)
    args = ConvertCommandArgs(**kwargs)
    set_level(print_opt)
    piped_stdin = _handle_stdin(args)
    _validate_scripting_preconditions(print_opt, args, piped_stdin)

    scripting_mode = print_opt in (PrintChoice.IDS, PrintChoice.SILENT)

    rekordbox_pid = get_rekordbox_pid()
    if rekordbox_pid:
        if scripting_mode:
            logger.error(
                f"Rekordbox is running (PID {rekordbox_pid}). Cannot proceed in scripting mode."
            )
            sys.exit(1)
        logger.warning(
            f"Rekordbox is running (PID {rekordbox_pid}). Modifying the database while "
            "Rekordbox is open can cause conflicts."
        )
        try:
            if not confirm("Continue anyway?", default=False):
                return
        except UserQuit:
            return

    db = Rekordbox6Database()
    plan = plan_convert(db, args)

    if plan.skipped:
        logger.warning(
            f"Skipping {len(plan.skipped)} file(s) (output exists, use --overwrite)"
        )

    if not plan.files:
        logger.info("No files need conversion.")
        return

    logger.info(f"Found {len(plan.files)} files to convert to {plan.format_out.upper()}")
    print_track_info(
        plan.files,
        changed_field=PrintableField.FileType,
        new_values=[plan.format_out.upper()] * len(plan.files),
    )

    if args.dry_run:
        _print_ids(print_opt, [t.ID for t in plan.files])
        return

    confirmed = _confirm_converts(plan, args)
    if confirmed is None:
        return

    result = convert(db, confirmed)
    logger.info(f"Converted {len(result.converted)} files to {plan.format_out.upper()}")
    if result.deleted:
        logger.info(f"Deleted {result.deleted} original file(s)")
    _print_ids(print_opt, [str(f["content_id"]) for f in result.converted])
