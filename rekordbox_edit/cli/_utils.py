"""CLI-private helpers: stdin handling, scripting guards, args narrowing, print emitters."""

import functools
import logging
import sys
from copy import copy
from typing import TypeVar

import click
from pydantic import BaseModel, ValidationError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid

from rekordbox_edit._click import PrintChoice, database_path_option
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)

SCRIPTING_MODES = (PrintChoice.IDS, PrintChoice.SILENT, PrintChoice.JSON)

_ArgsT = TypeVar("_ArgsT", bound=BaseModel)


def _build_args(model_cls: type[_ArgsT], kwargs: dict) -> _ArgsT:
    """Construct the command's args model, surfacing validation failures as usage errors."""
    try:
        return model_cls(**kwargs)
    except ValidationError as e:
        raise click.UsageError("; ".join(err["msg"] for err in e.errors())) from e


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
        "resolved_path",
        "format",
    ):
        if hasattr(narrowed, field_name):
            setattr(narrowed, field_name, [])
    narrowed.track_ids = list(ids)
    narrowed.match_all = False
    narrowed.match_any = False
    narrowed.first = None
    narrowed.last = None
    return narrowed


def _print_response_ids(response) -> None:
    """Print space-separated IDs from response.tracks."""
    print(" ".join(t.ID for t in response.tracks))


def _print_response_json(response: BaseModel) -> None:
    """Print the response envelope as JSON."""
    print(response.model_dump_json())


def _rekordbox_running_confirm(print_opt) -> bool:
    rekordbox_pid = get_rekordbox_pid()
    if not rekordbox_pid:
        return True
    if print_opt in SCRIPTING_MODES:
        logger.error(
            f"Rekordbox is running (PID {rekordbox_pid}). Cannot proceed in scripting mode."
        )
        sys.exit(1)
    logger.warning(
        f"Rekordbox is running (PID {rekordbox_pid}). Modifying the database while "
        "Rekordbox is open can cause conflicts."
    )
    try:
        return confirm("Continue anyway?", default=False)
    except UserQuit:
        return False


def with_database(*, writes: bool = False):
    """Inject an opened Rekordbox6Database as `db` and close it on exit.

    Pass writes=True for commands that modify the DB: the wrapper aborts when
    Rekordbox is running (or prompts to continue in interactive modes).
    """

    def decorator(func):
        @database_path_option
        @functools.wraps(func)
        def wrapper(**kwargs):
            if writes and not _rekordbox_running_confirm(kwargs.get("print_opt")):
                return
            database_path: str | None = kwargs.pop("database_path", None)
            db = Rekordbox6Database(path=database_path)  # ty: ignore[invalid-argument-type]
            try:
                return func(db=db, **kwargs)
            finally:
                db.close()

        return wrapper

    return decorator
