"""Read command for rekordbox-bulk-edit."""

import click

from rekordbox_bulk_edit.logger import Logger
from rekordbox_bulk_edit.utils import get_track_info, print_track_info

logger = Logger()


@click.command()
@click.option(
    "--track-id",
    type=int,
    help="Specific track ID to read (if not provided, shows all files or filtered files)",
)
@click.option(
    "--format",
    type=click.Choice(["mp3", "flac", "aiff", "wav", "m4a"], case_sensitive=False),
    help="Filter by audio format (shows all formats if not specified)",
)
def read_command(track_id, format):
    """Read track information from RekordBox database."""
    if track_id:
        logger.info(f"Looking for track ID: {track_id}")
    else:
        if format:
            logger.info(
                f"Reading all {format.upper()} files from RekordBox database..."
            )
        else:
            logger.info("Reading all audio files from RekordBox database...")

    logger.verbose("Connecting to RekordBox database...")

    content_list = get_track_info(track_id, format)

    if track_id and not content_list:
        logger.info(f"Track ID {track_id} not found.")
        return

    if not track_id:
        if format:
            logger.info(f"Found {len(content_list)} {format.upper()} files\n")
        else:
            logger.info(f"Found {len(content_list)} audio files\n")

    print_track_info(content_list)

    if not track_id:
        if format:
            logger.info(f"\nTotal {format.upper()} files: {len(content_list)}")
        else:
            logger.info(f"\nTotal audio files: {len(content_list)}")
