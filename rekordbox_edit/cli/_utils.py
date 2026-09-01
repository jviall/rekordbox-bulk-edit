"""CLI-private helpers: stdin handling, scripting guards, prompts, print emitters."""

import contextlib
import functools
import logging
import sys
from enum import Enum
from typing import TypeVar

import click
from pydantic import BaseModel, ValidationError
from pyrekordbox import Rekordbox6Database

from rekordbox_edit._click import PrintChoice, database_path_option
from rekordbox_edit.errors import (
    DatabaseBusyError,
    DependencyMissingError,
    InputError,
    RekordboxRunningError,
)
from rekordbox_edit.locking import SCRIPTED_TIMEOUT, database_lock

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


def _validate_scripting_preconditions(
    print_opt, *, piped_stdin: bool, dry_run: bool, yes: bool, interactive: bool = False
) -> None:
    """Raise UsageError for invalid confirmation and scripting combinations.

    --interactive contradicts both of the others: --yes means do not ask, and a
    dry run applies nothing for a per-item answer to change. Rejecting the
    combination keeps the flag from being silently discarded, which is what
    used to happen.
    """
    if interactive and yes:
        raise click.UsageError(
            "--interactive and --yes are mutually exclusive: one asks about "
            "every item, the other asks about none"
        )
    if interactive and dry_run:
        raise click.UsageError(
            "--interactive and --dry-run are mutually exclusive: a dry run "
            "applies nothing, so there is nothing to confirm"
        )
    confirmed = dry_run or yes
    if print_opt in SCRIPTING_MODES and not confirmed:
        raise click.UsageError(
            "--print=ids, --print=silent, or --print=json requires --dry-run or --yes to skip confirmation"
        )
    if piped_stdin and not confirmed:
        raise click.UsageError("Piping track IDs requires --dry-run or --yes")


def _print_response_ids(response) -> None:
    """Print space-separated IDs from response.tracks."""
    print(" ".join(t.ID for t in response.tracks))


def _print_response_json(response: BaseModel) -> None:
    """Print the response envelope as JSON."""
    print(response.model_dump_json())


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

    Pass writes=True for commands that modify the DB: the wrapper holds the
    single-writer advisory lock across the whole run, so the plan and apply
    passes cannot be interleaved by another process. The API takes that lock
    again per write, which nests harmlessly, and owns the refusal to run while
    Rekordbox is open.

    Also the one place API errors become CLI ones, so no command repeats the
    mapping: bad input is a usage error, and an unusable environment logs and
    exits 1.
    """

    def decorator(func):
        @database_path_option
        @functools.wraps(func)
        def wrapper(**kwargs):
            database_path: str | None = kwargs.pop("database_path", None)
            db = Rekordbox6Database(path=database_path)  # ty: ignore[invalid-argument-type]
            try:
                if not writes:
                    return func(db=db, **kwargs)
                with _write_lock(db, kwargs):
                    return func(db=db, **kwargs)
            except InputError as e:
                raise click.UsageError(str(e)) from e
            except (
                DatabaseBusyError,
                DependencyMissingError,
                RekordboxRunningError,
            ) as e:
                logger.error(str(e))
                sys.exit(1)
            finally:
                db.close()

        return wrapper

    return decorator


class UserQuit(Exception):
    """Raised when the user answers a prompt with 'q'."""


def confirm(
    prompt: str,
    default: bool = False,
    binary: bool = False,
    abort: bool = False,
):
    """Prompts the user to prompt [y]es/[n]o/[q]uit

    Args:
        prompt: The question to ask the user
        default: Default response (True for y, False for n)
        binary: If True, prompt a simple y/n
        abort: If True, prompt a simple y/n where 'n' raises a UserQuit Exception
    """

    class ConfirmChoice(Enum):
        YES = "y"
        NO = "n"
        QUIT = "q"

    if abort or binary:
        choices = [ConfirmChoice.YES.value, ConfirmChoice.NO.value]
        default_choice = ConfirmChoice.YES.value if default else ConfirmChoice.NO.value
    else:
        choices = [
            ConfirmChoice.YES.value,
            ConfirmChoice.NO.value,
            ConfirmChoice.QUIT.value,
        ]
        default_choice = ConfirmChoice.YES.value if default else ConfirmChoice.NO.value

    response: str = click.prompt(
        prompt,
        type=click.Choice(choices, case_sensitive=False),
        default=default_choice,
    )

    if response.lower() == ConfirmChoice.YES.value:
        logger.debug(f"User confirmed: {prompt}")
        return True
    elif response.lower() == ConfirmChoice.NO.value:
        logger.debug(f"User declined: {prompt}")
        if abort:
            raise UserQuit("User declined to continue")
        else:
            return False
    elif response.lower()[0] == ConfirmChoice.QUIT.value:
        logger.debug("User quit.")
        raise UserQuit("User quit")
