"""CLI-private helpers: stdin handling, scripting guards, args narrowing, print emitters."""

import logging
import sys
from copy import copy

import click
from pydantic import BaseModel

from rekordbox_edit._click import PrintChoice

logger = logging.getLogger(__name__)

SCRIPTING_MODES = (PrintChoice.IDS, PrintChoice.SILENT, PrintChoice.JSON)


def _handle_stdin(args) -> bool:
    """Append track IDs from piped stdin to args.track_ids. Returns True if IDs were piped."""
    if sys.stdin.isatty():
        return False
    # PowerShell pipes data as UTF-8-with-BOM, but Python decodes stdin with the
    # locale codepage (e.g. cp1252 on Windows), which would leave BOM bytes glued to
    # the first track ID. Read raw bytes and decode as UTF-8, dropping any BOM.
    tokens = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace").split()
    if not tokens:
        return False
    args.track_ids = list(args.track_ids) + tokens
    return True


def _validate_scripting_preconditions(print_opt, args, piped_stdin: bool) -> None:
    """Raise UsageError for invalid scripting-mode combinations."""
    if print_opt in SCRIPTING_MODES and not (args.dry_run or args.yes):
        raise click.UsageError(
            "--print=ids, --print=silent, or --print=json requires --dry-run or --yes to skip confirmation"
        )
    if piped_stdin and not (args.dry_run or args.yes):
        raise click.UsageError("Piping track IDs requires --dry-run or --yes")


def _narrow_to_track_ids(args, ids: list[str]):
    """Return a new args of the same type with track_ids=ids and all other
    FilterArgs criteria cleared, preserving command-specific fields.

    Used when the CLI's interactive mode has trimmed the planned operation
    to a user-selected subset. The narrowed args is passed to the real-run
    call so the second pass only considers the chosen track IDs.
    """
    narrowed = copy(args)
    for field_name in (
        "track_id",
        "track_ids",
        "title",
        "exact_title",
        "playlist",
        "exact_playlist",
        "artist",
        "exact_artist",
        "album",
        "exact_album",
        "path",
        "exact_path",
        "format",
    ):
        if hasattr(narrowed, field_name):
            setattr(narrowed, field_name, [])
    narrowed.track_ids = list(ids)
    narrowed.match_all = False
    return narrowed


def _print_response_ids(response) -> None:
    """Print space-separated IDs from response.tracks."""
    print(" ".join(t.ID for t in response.tracks))


def _print_response_json(response: BaseModel) -> None:
    """Print the response envelope as JSON."""
    print(response.model_dump_json())
