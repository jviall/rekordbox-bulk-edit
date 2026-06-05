"""Shared CLI utilities: stdin handling, scripting guards, confirmation flows."""

import logging
import sys

import click

from rekordbox_edit._click import PrintChoice
from rekordbox_edit.api.convert import ConvertPlan
from rekordbox_edit.api.edit import EditPlan
from rekordbox_edit.args import ConvertCommandArgs, EditCommandArgs
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)


def _handle_stdin(args) -> bool:
    """Append track IDs from piped stdin to args.track_ids. Returns True if stdin was piped."""
    if sys.stdin.isatty():
        return False
    stdin_data = sys.stdin.read().strip()
    if stdin_data:
        args.track_ids = list(args.track_ids) + stdin_data.split()
    return True


def _validate_scripting_preconditions(print_opt, args, piped_stdin: bool) -> None:
    """Raise UsageError for invalid scripting mode combinations."""
    scripting_mode = print_opt in (PrintChoice.IDS, PrintChoice.SILENT)
    if scripting_mode and not (args.dry_run or args.yes):
        raise click.UsageError(
            "--print=ids or --print=silent requires --dry-run or --yes to skip confirmation"
        )
    if piped_stdin and not (args.dry_run or args.yes):
        raise click.UsageError("Piping track IDs requires --dry-run or --yes")


def _print_ids(print_opt, ids: list[str]) -> None:
    """Print space-separated IDs if print_opt is IDS."""
    if print_opt is PrintChoice.IDS:
        print(" ".join(ids))


def _confirm_edits(plan: EditPlan, args: EditCommandArgs) -> EditPlan | None:
    """Gate the edit plan through user confirmation. Returns None if cancelled."""
    if args.yes:
        return plan
    if args.interactive:
        return _interactive_filter_edits(plan)
    try:
        if not confirm(f"Apply {len(plan.edits)} edit(s)?", default=True):
            logger.info("Cancelled.")
            return None
    except UserQuit:
        return None
    return plan


def _interactive_filter_edits(plan: EditPlan) -> EditPlan:
    """Prompt for each edit individually and return a plan with only confirmed edits."""
    confirmed = []
    for track, new_val in plan.edits:
        try:
            if confirm(f"  Edit {track.ID}?", default=True):
                confirmed.append((track, new_val))
        except UserQuit:
            break
    return EditPlan(field=plan.field, edits=confirmed)


def _confirm_converts(plan: ConvertPlan, args: ConvertCommandArgs) -> ConvertPlan | None:
    """Gate the convert plan through user confirmation. Returns None if cancelled."""
    if args.yes:
        return plan
    if args.interactive:
        return _interactive_filter_converts(plan)
    try:
        if not confirm(
            f"Convert {len(plan.files)} files to {plan.format_out.upper()}?", default=True
        ):
            logger.info("Cancelled.")
            return None
    except UserQuit:
        return None
    return plan


def _interactive_filter_converts(plan: ConvertPlan) -> ConvertPlan:
    """Prompt for each file individually and return a plan with only confirmed files."""
    confirmed = []
    for track in plan.files:
        try:
            if confirm(f"  Convert {track.FileNameL}?", default=True):
                confirmed.append(track)
        except UserQuit:
            break
    return ConvertPlan(
        files=confirmed,
        skipped=plan.skipped,
        should_delete=plan.should_delete,
        format_out=plan.format_out,
    )
