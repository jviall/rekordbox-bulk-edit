"""Edit CLI command."""

import logging

import click

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    edit_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.edit import edit
from rekordbox_edit.api.field_handlers import FIELD_HANDLERS
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
from rekordbox_edit.models import EditRequest
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)

# Skip reasons a user can override with --force; other reasons stay skipped.
_GATED_SKIP_REASONS = frozenset({"file_not_found", "length_mismatch"})


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options(
    [
        *edit_click_options,
        *global_click_confirmations,
        *global_click_filters,
        print_option,
    ]
)
@track_ids_argument
@click.argument(
    "field",
    type=click.Choice(list(FIELD_HANDLERS.keys()), case_sensitive=False),
)
@with_database(writes=True)
def edit_command(db, **kwargs):
    """Edit a metadata field on tracks in the RekordBox database."""
    print_opt = kwargs.pop("print_opt", None)
    # CLI-only flags pulled out of kwargs before constructing EditRequest.
    dry_run = kwargs.pop("dry_run", False)
    yes = kwargs.pop("yes", False)
    interactive = kwargs.pop("interactive", False)
    args = _build_args(EditRequest, kwargs)
    set_level(print_opt)
    piped_stdin = _handle_stdin(args)

    # Sentinel object mirrors the old ConfirmationArgs shape for the validator.
    _validate_scripting_preconditions(
        print_opt,
        type("_S", (), {"dry_run": dry_run, "yes": yes})(),
        piped_stdin,
    )

    if yes or dry_run:
        try:
            response = edit(db, args, dry_run=dry_run)
        except ValueError as e:
            raise click.UsageError(str(e)) from e

        if not response.result.edits and not dry_run:
            logger.info("No changes to make.")
            return

        _print_edit_result(response, print_opt, dry_run=dry_run)
        return

    # Default / interactive: preview first.
    try:
        preview = edit(db, args, dry_run=True)
    except ValueError as e:
        raise click.UsageError(str(e)) from e

    gated = [s for s in preview.result.skipped if s.reason in _GATED_SKIP_REASONS]
    if gated and not args.force:
        logger.info(f"{len(gated)} track(s) were held back by safety checks:")
        for s in gated:
            logger.info(f"  {s.id}: {s.reason}")
        try:
            if confirm(
                f"Include {len(gated)} held-back track(s) anyway (--force)?",
                default=False,
            ):
                args = args.model_copy(update={"force": True})
                try:
                    preview = edit(db, args, dry_run=True)
                except ValueError as e:
                    raise click.UsageError(str(e)) from e
        except UserQuit:
            return

    if not preview.result.edits:
        logger.info("No changes to make.")
        return

    if print_opt not in SCRIPTING_MODES:
        print_track_info(
            preview.tracks,
            changed_field=PrintableField[preview.result.field],
            new_values=[op.new_value for op in preview.result.edits],
        )

    if interactive:
        selected_ids = []
        for track, op in zip(preview.tracks, preview.result.edits):
            try:
                if confirm(f"  Edit {track.ID}?", default=True):
                    selected_ids.append(op.id)
            except UserQuit:
                break
        if not selected_ids:
            logger.info("Cancelled.")
            return
        narrowed = _narrow_to_track_ids(args, selected_ids)
        response = edit(db, narrowed)
    else:
        try:
            if not confirm(f"Apply {len(preview.result.edits)} edit(s)?", default=True):
                logger.info("Cancelled.")
                return
        except UserQuit:
            return
        response = edit(db, args)

    _print_edit_result(response, print_opt, dry_run=False)


def _print_edit_result(response, print_opt, *, dry_run: bool) -> None:
    if not dry_run:
        logger.info(f"Applied {len(response.result.edits)} edit(s).")
    if print_opt == PrintChoice.IDS:
        _print_response_ids(response)
    elif print_opt == PrintChoice.JSON:
        _print_response_json(response)
    elif print_opt not in SCRIPTING_MODES and dry_run:
        # Preview already rendered above in default flow; explicit --dry-run
        # path with no print_opt renders here.
        print_track_info(
            response.tracks,
            changed_field=PrintableField[response.result.field],
            new_values=[op.new_value for op in response.result.edits],
        )
