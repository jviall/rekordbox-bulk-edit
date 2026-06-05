"""Search command for rekordbox-edit."""

import logging
import sys
from typing import List

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import (
    PrintChoice,
    add_click_options,
    global_click_filters,
    print_option,
    track_ids_argument,
)
from rekordbox_edit.args import filter_args_from_kwargs
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.display import print_track_info

logger = logging.getLogger(__name__)


@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options([*global_click_filters, print_option, track_ids_argument])
def search_command(
    track_id: List[str] | None,
    track_ids: List[str] | None,
    playlist: List[str] | None,
    exact_playlist: List[str] | None,
    album: List[str] | None,
    exact_album: List[str] | None,
    artist: List[str] | None,
    exact_artist: List[str] | None,
    title: List[str] | None,
    exact_title: List[str] | None,
    path: List[str] | None,
    exact_path: List[str] | None,
    format: List[str] | None,
    match_all: bool,
    print_opt: PrintChoice | None,
):
    """Search the RekordBox database."""

    set_level(print_opt)

    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            track_ids = list(track_ids or []) + stdin_data.split()

    filters = filter_args_from_kwargs(
        track_id=track_id,
        track_ids=track_ids,
        playlist=playlist,
        exact_playlist=exact_playlist,
        album=album,
        exact_album=exact_album,
        artist=artist,
        exact_artist=exact_artist,
        title=title,
        exact_title=exact_title,
        path=path,
        exact_path=exact_path,
        format=format,
        match_all=match_all,
    )

    logger.debug(f"Search filters: {filters}")
    logger.debug("Connecting to RekordBox database...")

    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    filtered_result = get_filtered_content(db, filters)

    if print_opt is PrintChoice.SILENT:
        pass
    elif print_opt is PrintChoice.IDS:
        print(" ".join(content.ID for content in filtered_result.scalars().all()))
    else:
        print_track_info(filtered_result.scalars().all())
