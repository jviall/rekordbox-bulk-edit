import logging

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import (
    add_click_options,
    edit_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.edit import FIELD_COLUMNS, edit, plan_edit
from rekordbox_edit.models import EditCommandArgs
from rekordbox_edit.cli._utils import (
    SCRIPTING_MODES,
    _confirm_edits,
    _handle_stdin,
    _print_ids,
    _print_tracks_json,
    _validate_scripting_preconditions,
)
from rekordbox_edit.display import PrintableField, print_track_info
from rekordbox_edit.logger import get_debug_file_path, set_level

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options(
    [
        *global_click_filters,
        *global_click_confirmations,
        *edit_click_options,
        print_option,
    ]
)
@track_ids_argument
@click.argument(
    "field",
    type=click.Choice(list(FIELD_COLUMNS.keys()), case_sensitive=False),
)
def edit_command(**kwargs):
    """Edit a metadata field on tracks in the RekordBox database."""
    print_opt = kwargs.pop("print_opt", None)
    args = EditCommandArgs(**kwargs)
    set_level(print_opt)
    piped_stdin = _handle_stdin(args)
    _validate_scripting_preconditions(print_opt, args, piped_stdin)

    db = Rekordbox6Database()
    try:
        plan = plan_edit(db, args)
    except ValueError as e:
        raise click.UsageError(str(e)) from e

    if not plan.edits:
        logger.info("No changes to make.")
        return

    if print_opt not in SCRIPTING_MODES:
        print_track_info(
            [t for t, _ in plan.edits],
            changed_field=PrintableField[plan.field],
            new_values=[v for _, v in plan.edits],
        )

    if args.dry_run:
        _print_ids(print_opt, [t.ID for t, _ in plan.edits])
        _print_tracks_json(print_opt, [t for t, _ in plan.edits])
        return

    confirmed = _confirm_edits(plan, args)
    if confirmed is None:
        return

    result = edit(db, confirmed)
    logger.info(f"Applied {result.applied} edit(s).")
    _print_ids(print_opt, [t.ID for t, _ in confirmed.edits])
    _print_tracks_json(print_opt, [t for t, _ in confirmed.edits])
