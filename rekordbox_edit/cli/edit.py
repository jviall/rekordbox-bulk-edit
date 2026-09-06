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

    try:
        args, preview, reported_individually = _prompt_gates(db, args, preview)
    except UserQuit:
        return

    _report_skips(preview.result.skipped, exclude=reported_individually)

    if not preview.result.edits:
        logger.info("No changes to make.")
        return

    if print_opt not in SCRIPTING_MODES:
        print_track_info(
            [op.track for op in preview.result.edits],
            changed_field=PrintableField[preview.result.field],
            new_values=[op.new_value for op in preview.result.edits],
        )

    if interactive:
        selected_ids = []
        for op in preview.result.edits:
            try:
                if confirm(f"  Edit {op.track.ID}?", default=True):
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


def _prompt_gates(db, args, preview):
    """Offer to lift each safety gate holding tracks back, one prompt per gate.

    Gates ask about a condition the user did not ask for, so each defaults to
    no and each is asked separately: authorizing a path with no file behind it
    is a different decision from authorizing cues that may land misaligned.
    A gate whose flag is already set is not re-asked.

    Returns the request and preview to carry forward, and the reasons these
    prompts already spelled out track by track so the summary skips them.
    """
    lifted: dict[str, bool] = {}
    named: set[str] = set()
    for reason, field in FIELD_HANDLERS[args.field].gated_skip_reasons.items():
        if getattr(args, field):
            continue
        held = [s for s in preview.result.skipped if s.reason == reason]
        if not held:
            continue
        named.add(reason)
        logger.info(f"{len(held)} track(s) held back: {_SKIP_MESSAGES[reason]}")
        for s in held:
            logger.info(f"  {s.track.FileNameL if s.track else '(unknown file)'}")
        if confirm(f"Include {len(held)} held-back track(s) anyway?", default=False):
            lifted[field] = True
            named.discard(reason)

    if lifted:
        args = args.model_copy(update=lifted)
        preview = edit(db, args, dry_run=True)
    return args, preview, frozenset(named)


#: How each skip reason reads as a one-line summary. Phrased as a reason rather
#: than a reason code, since these are the only account a user gets of tracks
#: their filters matched but the command did not touch.
_SKIP_MESSAGES: dict[str, str] = {
    "no_change": "existing value already matches the requested value",
    "file_not_found": "file does not exist (override with --allow-missing)",
    "length_mismatch": (
        "file's duration contradicts the stored length (override with --allow-mismatch)"
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
        _print_response_ids([op.id for op in response.result.edits])
    elif print_opt == PrintChoice.JSON:
        _print_response_json(response)
    elif print_opt not in SCRIPTING_MODES and dry_run:
        # Preview already rendered above in default flow; explicit --dry-run
        # path with no print_opt renders here.
        print_track_info(
            [op.track for op in response.result.edits],
            changed_field=PrintableField[response.result.field],
            new_values=[op.new_value for op in response.result.edits],
        )
