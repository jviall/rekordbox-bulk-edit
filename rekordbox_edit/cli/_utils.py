"""CLI-private helpers: stdin handling, scripting guards, args narrowing, print emitters."""

import contextlib
import functools
import logging
import sys
from copy import copy
from typing import TypeVar

import click
from pydantic import BaseModel, ValidationError
from pyrekordbox import Rekordbox6Database
from pyrekordbox.utils import get_rekordbox_pid
from sqlalchemy import event
from sqlalchemy.engine import Engine

from rekordbox_edit._click import PrintChoice, database_path_option
from rekordbox_edit.locking import SCRIPTED_TIMEOUT, DatabaseBusyError, database_lock
from rekordbox_edit.utils import UserQuit, confirm

logger = logging.getLogger(__name__)

SCRIPTING_MODES = (PrintChoice.IDS, PrintChoice.SILENT, PrintChoice.JSON)

#: How long SQLite retries when another connection (typically Rekordbox
#: itself) holds the write lock, before raising OperationalError.
BUSY_TIMEOUT_MS = 5000

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


def _validate_scripting_preconditions(
    print_opt, *, piped_stdin: bool, dry_run: bool, yes: bool
) -> None:
    """Raise UsageError for invalid scripting-mode combinations."""
    confirmed = dry_run or yes
    if print_opt in SCRIPTING_MODES and not confirmed:
        raise click.UsageError(
            "--print=ids, --print=silent, or --print=json requires --dry-run or --yes to skip confirmation"
        )
    if piped_stdin and not confirmed:
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


@event.listens_for(Engine, "connect")
def _set_busy_timeout(dbapi_connection, _record) -> None:
    """Make SQLite wait instead of failing immediately on a contended write lock.

    Bound to the Engine class rather than an instance because pyrekordbox
    builds the engine itself and connects lazily on the first query, leaving
    no point at which to attach a per-engine listener.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def _write_lock(db, kwargs):
    """Return the advisory lock context for a write command.

    Dry runs never write, so they stay usable while another command holds the
    lock. Interactive runs fail immediately rather than hanging on a prompt
    the user cannot see; --yes runs are scripted and can afford to wait.
    """
    if kwargs.get("dry_run"):
        return contextlib.nullcontext()
    ctx = click.get_current_context(silent=True)
    return database_lock(
        db.db_directory,
        command=(ctx.info_name if ctx else None) or "rbe",
        timeout=SCRIPTED_TIMEOUT if kwargs.get("yes") else 0,
    )


def with_database(*, writes: bool = False):
    """Inject an opened Rekordbox6Database as `db` and close it on exit.

    Pass writes=True for commands that modify the DB: the wrapper aborts when
    Rekordbox is running (or prompts to continue in interactive modes), and
    holds the single-writer advisory lock for the whole run.
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
                if not writes:
                    return func(db=db, **kwargs)
                with _write_lock(db, kwargs):
                    return func(db=db, **kwargs)
            except DatabaseBusyError as e:
                logger.error(str(e))
                sys.exit(1)
            finally:
                db.close()

        return wrapper

    return decorator
