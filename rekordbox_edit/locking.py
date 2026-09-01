"""Single-writer advisory lock over a rekordbox database directory.

Concurrent rbe processes are not supported: two commands writing the same
library can interleave their plan and apply phases and invalidate each
other's operations. A write command holds this lock for its whole run, and
a second process either waits briefly or fails with a message naming the
holder.
"""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from filelock import FileLock, Timeout
from platformdirs import PlatformDirs

from rekordbox_edit.errors import DatabaseBusyError

logger = logging.getLogger(__name__)

__all__ = ["DatabaseBusyError", "SCRIPTED_TIMEOUT", "database_lock"]

#: How long a non-interactive command waits for the lock. Interactive
#: commands pass 0 so a user at a terminal fails fast instead of hanging.
SCRIPTED_TIMEOUT = 30.0

_LOCK_DIR = (
    Path(PlatformDirs(appname="rekordbox-edit", ensure_exists=True).user_data_dir)
    / "locks"
)


def _lock_path(db_directory) -> Path:
    """Return the lock file for a database directory.

    Keyed by a digest of the directory so that --database-path targets and
    the e2e fixture copies never contend with a real library.
    """
    digest = hashlib.sha256(str(db_directory).encode("utf-8")).hexdigest()[:16]
    return _LOCK_DIR / f"{digest}.lock"


def _holder_path(lock_path: Path) -> Path:
    """Return the sidecar recording who holds `lock_path`.

    Kept out of the lock file itself because filelock opens that file with
    O_TRUNC, so a contending process would erase the record before its own
    acquisition fails.
    """
    return lock_path.with_suffix(".holder.json")


def _describe_holder(lock_path: Path) -> str:
    """Describe the process holding `lock_path`, or "" if it cannot be read.

    The holder may exit between the timeout and this read, so a missing or
    malformed file is expected rather than exceptional.
    """
    try:
        holder = json.loads(_holder_path(lock_path).read_text(encoding="utf-8"))
        return f' (PID {holder["pid"]}, "{holder["command"]}", started {holder["started"]})'
    except (OSError, ValueError, KeyError):
        return ""


@contextmanager
def database_lock(db_directory, command: str, timeout: float) -> Iterator[None]:
    """Hold the single-writer lock for `db_directory` for the duration of the block.

    Raises DatabaseBusyError if the lock is not free within `timeout` seconds.

    Re-entrant within one process, via filelock's per-path singleton: a CLI run
    holds this for its whole plan/apply span while each API call it makes takes
    it again, and only the outermost release frees it. A lock held by another
    process is still refused, which is the exclusion that matters.
    """
    path = _lock_path(db_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path), is_singleton=True)
    try:
        lock.acquire(timeout=timeout)
    except Timeout as e:
        raise DatabaseBusyError(
            f"Another rekordbox-edit process is writing to this library"
            f"{_describe_holder(path)}. Wait for it to finish, then try again."
        ) from e
    logger.debug(f"Acquired write lock: {path}")
    try:
        # Best effort: the lock itself is the OS file lock, and this payload
        # only exists to make the busy message name the holder.
        _holder_path(path).write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "command": command,
                    "started": datetime.now().strftime("%H:%M:%S"),
                }
            ),
            encoding="utf-8",
        )
    except OSError as e:
        logger.debug(f"Could not record lock holder: {e}")
    try:
        yield
    finally:
        lock.release()
        logger.debug(f"Released write lock: {path}")
