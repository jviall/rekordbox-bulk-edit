"""Edit command for rekordbox-edit."""

import logging
import sys

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    edit_click_options,
    global_click_confirmations,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.args import EditCommandArgs
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.display import PrintableField, print_track_info
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)

# Maps CLI field names to DjmdContent column attribute names.
FIELD_COLUMNS = {
    "Title": "Title",
}


def _compute_new_value(
    current: str | int | None,
    match_pattern: str | None,
    replace_value: str | int,
) -> str | int | None:
    """Derive the new field value."""
    if current is None:
        return None
    if match_pattern is not None:
        return str(current).replace(match_pattern, str(replace_value))
    return replace_value


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
    _edit(EditCommandArgs(**kwargs))


def _edit(args: EditCommandArgs) -> None:
    """Apply a field edit to tracks matching `args`."""
    dry_run, yes, interactive = args.dry_run, args.yes, args.interactive
    field, replace_value, match_pattern, multi = (
        args.field,
        args.replace_value,
        args.match_pattern,
        args.multi,
    )
    print_opt = args.print_opt
    set_level(print_opt)

    piped_stdin = False
    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            piped_stdin = True
            args.track_ids = list(args.track_ids) + stdin_data.split()

    scripting_mode = print_opt in (PrintChoice.IDS, PrintChoice.SILENT)
    if scripting_mode and not (dry_run or yes):
        raise click.UsageError(
            "--print=ids or --print=silent requires --dry-run or --yes to skip confirmation"
        )

    if piped_stdin and not (dry_run or yes):
        raise click.UsageError("Piping track IDs into edit requires --dry-run or --yes")

    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    result = get_filtered_content(db, args)
    tracks = result.scalars().all()

    col_name = FIELD_COLUMNS[field]
    edits = []
    for track in tracks:
        current = getattr(track, col_name)
        new_value = _compute_new_value(current, match_pattern, replace_value)
        if new_value is None or new_value == current:
            continue
        edits.append((track, new_value))

    if not edits:
        logger.info("No changes to make.")
        return

    if len(edits) > 1 and not multi:
        raise click.UsageError(
            f"Found {len(edits)} tracks that would be edited. "
            "Refine your filters, use --dry-run to inspect, or pass --multi to edit all."
        )

    print_track_info(
        [t for t, _ in edits],
        changed_field=PrintableField[field],
        new_values=[str(v) for _, v in edits],
    )

    if dry_run:
        if print_opt is PrintChoice.IDS:
            print(" ".join(str(t.ID) for t, _ in edits))
        return

    if not yes and not interactive:
        try:
            if not confirm(f"Apply {len(edits)} edit(s)?", default=True):
                logger.info("Cancelled.")
                return
        except UserQuit:
            return

    for track, new_value in edits:
        if interactive and not yes:
            try:
                if not confirm(f"  Edit {track.ID}?", default=True):
                    continue
            except UserQuit:
                logger.info("Cancelled.")
                return
        setattr(track, col_name, new_value)

    db.session.commit()
    logger.info(f"Applied {len(edits)} edit(s).")

    if print_opt is PrintChoice.IDS:
        print(" ".join(str(t.ID) for t, _ in edits))
