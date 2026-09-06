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


class ConvertAborted(OperationAborted):
    """A conversion failed partway through a batch.

    Files converted before the failure are already committed, so the counts
    travel with the error rather than being recovered from the response the
    caller never receives.
    """

    def __init__(
        self,
        reason: str,
        *,
        failed_path: str,
        converted: int,
        not_attempted: int,
    ):
        self.failed_path = failed_path
        self.converted = converted
        self.not_attempted = not_attempted
        super().__init__(reason)


class ImportInputError(InputError):
    """The request itself is invalid: a path that does not exist, an
    unconfirmed directory argument, or a playlist name that matches no
    playlist or more than one. Distinct from a write-phase failure, which
    means the database failed and must not be reported as user error."""


class DirectoryConfirmationRequired(ImportInputError):
    """Directory arguments would be walked recursively without `recurse` set.

    Carries the counts so a caller can compose its own prompt, and its own
    hint about whatever it calls the authorization, rather than parsing
    either back out of the message.
    """

    def __init__(self, directories: int, files: int):
        self.directories = directories
        self.files = files
        super().__init__(
            f"{directories} directory argument(s) would be walked recursively, "
            f"adding {files} file(s)."
        )
