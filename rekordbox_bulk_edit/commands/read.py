"""Read command for rekordbox-bulk-edit."""

import click

from rekordbox_bulk_edit.utils import get_track_info, print_track_info


@click.command()
@click.option(
    "--track-id",
    type=int,
    help="Specific track ID to read (if not provided, shows all FLAC files)",
)
@click.option(
    "--verbose", "-v", is_flag=True, help="Enable verbose output"
)
def read_command(track_id, verbose):
    """Read track information from RekordBox database."""
    if track_id:
        click.echo(f"Looking for track ID: {track_id}")
    else:
        click.echo("Reading all FLAC files from RekordBox database...")

    if verbose:
        click.echo("Connecting to RekordBox database...")

    content_list = get_track_info(track_id)

    if track_id and not content_list:
        click.echo(f"Track ID {track_id} not found.")
        return

    if not track_id:
        click.echo(f"Found {len(content_list)} FLAC files\n")
    else:
        click.echo()

    print_track_info(content_list)

    if not track_id:
        click.echo(f"\nTotal FLAC files: {len(content_list)}")
