"""Exception hierarchy for rekordbox-edit.

Exports a top-level `RekordboxEditError`, from which all other internal
errors descend.

The CLI maps these to exit codes in one place, `cli._utils.with_database`.
"""


class RekordboxEditError(Exception):
    """Base for every error rekordbox-edit raises on purpose."""


class InputError(RekordboxEditError, ValueError):
    """The request itself is invalid, and no amount of retrying will help.

    The CLI reports these as usage errors.
    """


class DependencyMissingError(RekordboxEditError):
    """A required external program (e.g. ffmpeg) is not installed."""


class RekordboxRunningError(RekordboxEditError):
    """Rekordbox holds the library open.

    Writing underneath it risks losing changes: it keeps rows in memory and can
    write its own copy back over ours.
    """


class DatabaseNotConnectedError(RekordboxEditError, RuntimeError):
    """The database has no open session.

    Usually a database that was never opened, or one closed early. Keeps
    RuntimeError in its MRO, which is what this raised before the hierarchy.
    """


class DatabaseBusyError(RekordboxEditError, TimeoutError):
    """Another rekordbox-edit process holds the write lock for this database.

    A TimeoutError because that is literally what happened: the lock did not
    come free within the caller's timeout. This mirrors filelock.Timeout, the
    exception it translates, which is itself a TimeoutError, so catching it as
    one keeps working. Note that makes it an OSError too.
    """


class OperationAborted(RekordboxEditError):
    """A write gave up partway. Work committed before the failure is kept."""
