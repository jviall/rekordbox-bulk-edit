"""Edit CLI command."""

import logging

import click

from rekordbox_edit.api.edit import edit
from rekordbox_edit.api.field_handlers import FIELD_HANDLERS
from rekordbox_edit.cli._click import (
    add_click_options,
    edit_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.cli._utils import (
    SCRIPTING_MODES,
    UserQuit,
    _build_args,
    _handle_stdin,
    _print_response_ids,
    _print_response_json,
    _validate_scripting_preconditions,
    confirm,
    with_database,
)
from rekordbox_edit.display import PrintableField, print_track_info
from rekordbox_edit.logger import PrintChoice, get_debug_file_path, set_level
from rekordbox_edit.models import EditRequest

logger = logging.getLogger(__name__)

# Skips a preview cannot predict: they surface only when the approved plan is
# re-checked against the database and filesystem at write time.
_LIVE_ONLY_SKIPS = frozenset({"db_or_fs_changed"})


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

    _validate_scripting_preconditions(
        print_opt,
        piped_stdin=piped_stdin,
        dry_run=dry_run,
        yes=yes,
        interactive=interactive,
    )

    if yes or dry_run:
        response = edit(db, args, dry_run=dry_run)
        _report_skips(response.result.skipped)

        if not response.result.edits and not dry_run:
            logger.info("No changes to make.")
            return

        _print_edit_result(response, print_opt, dry_run=dry_run)
        return

    # Default / interactive: preview first.
    preview = edit(db, args, dry_run=True)

    forceable = FIELD_HANDLERS[args.field].forceable_skip_reasons
    gated = [s for s in preview.result.skipped if s.reason in forceable]
    # Reasons the prompt below spells out per track, so the summary does not
    # repeat them.
    reported_individually: frozenset[str] = frozenset()
    if gated and not args.force:
        reported_individually = forceable
        logger.info(f"{len(gated)} track(s) were held back by safety checks:")
        for s in gated:
            logger.info(f"  {s.id}: {s.reason}")
        try:
            if confirm(
                f"Include {len(gated)} held-back track(s) anyway (--force)?",
                default=False,
            ):
                args = args.model_copy(update={"force": True})
                preview = edit(db, args, dry_run=True)
                reported_individually = frozenset()
        except UserQuit:
            return

    _report_skips(preview.result.skipped, exclude=reported_individually)

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
        chosen = set(selected_ids)
        selected = [op for op in preview.result.edits if op.id in chosen]
        response = edit(db, args, ops=selected)
    else:
        try:
            if not confirm(f"Apply {len(preview.result.edits)} edit(s)?", default=True):
                logger.info("Cancelled.")
                return
        except UserQuit:
            return
        response = edit(db, args, ops=preview.result.edits)

    _report_skips([s for s in response.result.skipped if s.reason in _LIVE_ONLY_SKIPS])
    _print_edit_result(response, print_opt, dry_run=False)


#: How each skip reason reads as a one-line summary. Phrased as a reason rather
#: than a reason code, since these are the only account a user gets of tracks
#: their filters matched but the command did not touch.
_SKIP_MESSAGES: dict[str, str] = {
    "no_change": "existing value already matches the requested value",
    "file_not_found": "file does not exist",
    "length_mismatch": (
        "file's duration contradicts the stored length (override with --force)"
    ),
    "unknown_file_type": "file is in format Rekordbox doesn't support",
    "db_or_fs_changed": "changed since the preview",
}


def _report_skips(skipped, *, exclude: frozenset[str] = frozenset()) -> None:
    """Say what was passed over and why, one line per reason.

    Without this a run reports only what it changed, so a filter that matched
    30 tracks and edited 4 looks like it found 4.
    """
    for reason, message in _SKIP_MESSAGES.items():
        if reason in exclude:
            continue
        count = sum(1 for s in skipped if s.reason == reason)
        if count:
            logger.warning(f"Skipping {count} track(s): {message}")


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
