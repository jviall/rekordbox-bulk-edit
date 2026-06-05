"""Search command for rekordbox-edit."""

import logging
import sys

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.args import SearchCommandArgs
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.display import print_track_info

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
def search_command(**kwargs):
    """Search the RekordBox database."""
    _search(SearchCommandArgs(**kwargs))


def _search(args: SearchCommandArgs) -> None:
    """Run a read-only query matching `args` and emit results per `print_opt`."""
    print_opt = args.print_opt
    set_level(print_opt)

    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            args.track_ids = list(args.track_ids) + stdin_data.split()

    logger.debug(f"Search filters: {args}")
    logger.debug("Connecting to RekordBox database...")

    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    filtered_result = get_filtered_content(db, args)

    if print_opt is PrintChoice.SILENT:
        pass
    elif print_opt is PrintChoice.IDS:
        print(" ".join(content.ID for content in filtered_result.scalars().all()))
    else:
        print_track_info(filtered_result.scalars().all())
