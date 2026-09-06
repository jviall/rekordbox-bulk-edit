"""Search CLI command."""

import logging

import click

from rekordbox_edit.cli._click import (
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.api.search import search
from rekordbox_edit.cli._utils import (
    _build_args,
    _handle_stdin,
    _print_response_ids,
    _print_response_json,
    with_database,
)
from rekordbox_edit.display import print_track_info
from rekordbox_edit.logger import PrintChoice, get_debug_file_path, set_level
from rekordbox_edit.models import SearchRequest

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
@with_database()
def search_command(db, **kwargs):
    """Search the RekordBox database."""
    print_opt = kwargs.pop("print_opt", None)
    args = _build_args(SearchRequest, kwargs)
    set_level(print_opt)
    _handle_stdin(args)

    response = search(db, args)

    if print_opt is PrintChoice.SILENT:
        return
    if print_opt is PrintChoice.IDS:
        _print_response_ids([t.ID for t in response.tracks])
        return
    if print_opt is PrintChoice.JSON:
        _print_response_json(response)
        return
    print_track_info(response.tracks)
