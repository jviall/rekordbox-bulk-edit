#!/usr/bin/env python3
"""Command line interface for rekordbox-bulk-edit."""

import sys
import click

from rekordbox_bulk_edit.commands.read import read_command
from rekordbox_bulk_edit.commands.convert import convert_command


@click.group()
@click.version_option()
def cli():
    """RekordBox Bulk Edit - Tools for bulk editing RekordBox database records."""
    pass


cli.add_command(read_command, name="read")
cli.add_command(convert_command, name="convert")


def main():
    """Entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
