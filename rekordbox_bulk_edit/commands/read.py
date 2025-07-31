"""Read command for rekordbox-bulk-edit."""

import click

from rekordbox_bulk_edit.utils import get_track_info, print_track_info, FORMAT_TO_FILE_TYPE


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
@click.option(
    "--verbose", "-v", is_flag=True, help="Enable verbose output"
)
def read_command(track_id, format, verbose):
    """Read track information from RekordBox database."""
    if track_id:
        click.echo(f"Looking for track ID: {track_id}")
    else:
        if format:
            click.echo(f"Reading all {format.upper()} files from RekordBox database...")
        else:
            click.echo("Reading all audio files from RekordBox database...")

    if verbose:
        click.echo("Connecting to RekordBox database...")

    content_list = get_track_info(track_id, format)

    if track_id and not content_list:
        click.echo(f"Track ID {track_id} not found.")
        return

    if not track_id:
        if format:
            click.echo(f"Found {len(content_list)} {format.upper()} files\n")
        else:
            click.echo(f"Found {len(content_list)} audio files\n")
    else:
        click.echo()

    print_track_info(content_list)

    if not track_id:
        if format:
            click.echo(f"\nTotal {format.upper()} files: {len(content_list)}")
        else:
            click.echo(f"\nTotal audio files: {len(content_list)}")
