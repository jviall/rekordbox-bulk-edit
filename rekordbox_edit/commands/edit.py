"""Edit command for rekordbox-edit."""

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
from rekordbox_edit.logger import get_debug_file_path, set_level
from rekordbox_edit.query import get_filtered_content
from rekordbox_edit.utils import UserQuit, confirm, print_track_info

logger = logging.getLogger(__name__)

# Maps CLI field names to DjmdContent column attribute names.
FIELD_COLUMNS = {
    "Title": "Title",
}



@click.command(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@add_click_options([*global_click_filters, print_option])
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Confirm each track individually before editing",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing to the database",
)
@click.option(
    "--replace",
    "replace_value",
    required=True,
    help="The new value to write to the field",
)
@track_ids_argument
@click.argument(
    "field",
    type=click.Choice(list(FIELD_COLUMNS.keys()), case_sensitive=False),
)
def edit_command(
    field: str,
    replace_value: str,
    dry_run: bool,
    yes: bool,
    interactive: bool,
    track_ids: tuple,
    track_id: List[str] | None,
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
    """Edit a metadata field on tracks in the RekordBox database."""

    set_level(print_opt)

    piped_stdin = False
    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            piped_stdin = True
            track_ids = list(track_ids or []) + stdin_data.split()

    scripting_mode = print_opt in (PrintChoice.IDS, PrintChoice.SILENT)
    if scripting_mode and not (dry_run or yes):
        raise click.UsageError(
            "--print=ids or --print=silent requires --dry-run or --yes to skip confirmation"
        )

    if piped_stdin and not (dry_run or yes):
        raise click.UsageError(
            "Piping track IDs into edit requires --dry-run or --yes"
        )

    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    result = get_filtered_content(
        db,
        track_id_args=track_ids,
        track_ids=track_id,
        playlists=playlist,
        exact_playlists=exact_playlist,
        artists=artist,
        exact_artists=exact_artist,
        albums=album,
        exact_albums=exact_album,
        titles=title,
        exact_titles=exact_title,
        paths=path,
        exact_paths=exact_path,
        formats=format,
        match_all=match_all,
    )
    tracks = result.scalars().all()

    col_name = FIELD_COLUMNS[field]
    edits = [
        (track, replace_value)
        for track in tracks
        if getattr(track, col_name) != replace_value
    ]

    if not edits:
        logger.info("No changes to make.")
        return

    if len(edits) > 1:
        raise click.UsageError(
            f"Found {len(edits)} tracks that would be edited. "
            "Refine your filters, or use --dry-run to inspect."
        )

    print_track_info([t for t, _ in edits])

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
