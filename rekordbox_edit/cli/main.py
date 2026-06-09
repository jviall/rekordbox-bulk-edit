#!/usr/bin/env python3
"""Command line interface for rekordbox-edit."""

import io
import logging
import sys

import click

from rekordbox_edit.cli.convert import convert_command
from rekordbox_edit.cli.edit import edit_command
from rekordbox_edit.cli.search import search_command
from rekordbox_edit.logger import get_debug_file_path, setup_logging

logger = logging.getLogger(__name__)


@click.group(
    epilog=f"Debug logs for each run can be found at:\n{get_debug_file_path().parent}"
)
@click.version_option()
def cli():
    """RekordBox Bulk Edit - Tools for bulk editing RekordBox database records."""
    pass


cli.add_command(search_command)
cli.add_command(edit_command)
cli.add_command(convert_command)


def main():
    """Entry point for the CLI."""
    # Force UTF-8 on the standard streams so non-ASCII titles, paths, and
    # artist names survive piping on Windows (default cp1252 mangles them to
    # '?'). This is the in-script equivalent of running with PYTHONUTF8=1.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        setup_logging()
        logger.debug(f"Running with input: {' '.join(sys.argv)}")
        cli()
    except KeyboardInterrupt:
        logger.debug("User killed the process.")
    except Exception as e:
        logger.critical("Unhandled exception occured:", exc_info=e)
        logger.info(
            f"Please report this issue to https://github.com/jviall/rekordbox-edit/issues "
            f"with the debug file for this run: {get_debug_file_path().absolute().as_uri()}",
        )
        sys.exit(1)
