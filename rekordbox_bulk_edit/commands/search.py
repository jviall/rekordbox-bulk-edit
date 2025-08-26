"""Read command for rekordbox-bulk-edit."""

import logging
from typing import List

import click
from pyrekordbox import Rekordbox6Database

from rekordbox_bulk_edit.filters import (
    OutputChoice,
    add_click_options,
    global_click_filters,
    output_option,
    track_ids_argument,
)
from rekordbox_bulk_edit.logger import Logger
from rekordbox_bulk_edit.query import get_filtered_content
from rekordbox_bulk_edit.utils import (
    print_track_info,
)

logger = Logger()


@click.command()
@add_click_options([output_option, *global_click_filters, track_ids_argument])
def search_command(
    track_id: List[str] | None,
    format: List[str] | None,
    playlist: List[str] | None,
    album: List[str] | None,
    exact_album: List[str] | None,
    artist: List[str] | None,
    track: List[str] | None,
    exact_track: List[str] | None,
    track_ids: List[str] | None,
    match_all: bool,
    output: OutputChoice | None,
):
    """Search the RekordBox database."""

    if output is OutputChoice.IDS or output is OutputChoice.SILENT:
        logger.set_level(logging.ERROR)

    logger.verbose("Connecting to RekordBox database...")

    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    filtered_result = get_filtered_content(
        db,
        track_ids=track_id,
        formats=format,
        track_id_args=track_ids,
        playlists=playlist,
        artists=artist,
        albums=album,
        exact_albums=exact_album,
        tracks=track,
        match_all=match_all,
    )

    if output is OutputChoice.SILENT:
        pass
    elif output is OutputChoice.IDS:
        print(" ".join(content.ID for content in filtered_result.scalars().all()))
    else:
        print_track_info(filtered_result.scalars().all())
