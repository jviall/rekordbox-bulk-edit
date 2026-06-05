import logging

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.search import search
from rekordbox_edit.args import FilterArgs
from rekordbox_edit.cli._utils import _handle_stdin, _print_ids
from rekordbox_edit.display import print_track_info
from rekordbox_edit.logger import get_debug_file_path, set_level

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
def search_command(**kwargs):
    """Search the RekordBox database."""
    print_opt = kwargs.pop("print_opt", None)
    args = FilterArgs(**kwargs)
    set_level(print_opt)
    _handle_stdin(args)

    db = Rekordbox6Database()
    tracks = search(db, args)

    if print_opt is PrintChoice.SILENT:
        return
    if print_opt is PrintChoice.IDS:
        _print_ids(print_opt, [t.ID for t in tracks])
        return
    print_track_info(tracks)
