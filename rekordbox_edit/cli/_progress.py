"""Live progress display for long-running CLI commands."""

import contextlib
import logging
from collections.abc import Iterator

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

from rekordbox_edit.logger import console

_logger = logging.getLogger(__name__)


#: Marks the one task that counts files, so the count column can tell it from
#: the per-file rows. Both can lack a total, so the total cannot distinguish
#: them: a `--yes` run has no count until convert() has classified the batch.
_OVERALL = "overall"


class _OverallCountColumn(MofNCompleteColumn):
    """The file count, shown only on the overall task.

    The overall row still reports a bare running count when its total is not yet known.
    """

    def render(self, task):
        if not task.fields.get(_OVERALL):
            return Text("")
        if task.total is None:
            return Text(str(int(task.completed)), style="rbe.count")
        return super().render(task)


class ConvertProgressDisplay:
    """A line per file being encoded, above an overall bar.

    Finished files are not kept here. `convert()` already logs a line for each
    one, and those scroll above the live region on their way to the debug log,
    which leaves this display showing only what is still in flight.
    """

    def __init__(self, progress: Progress):
        self._progress = progress
        # convert() reports the real count through batch_size() before it
        # encodes anything, so the bar starts without one rather than trusting
        # a preview that may no longer describe the run.
        self._overall = progress.add_task("Converting", total=None, **{_OVERALL: True})
        self._tasks: dict[int, TaskID] = {}

    def batch_size(self, total: int) -> None:
        self._progress.update(self._overall, total=total)

    def started(self, index: int, file_name: str | None) -> None:
        self._tasks[index] = self._progress.add_task(
            file_name or "", total=None, start=True
        )

    def finished(self, index: int, converted: bool) -> None:
        task = self._tasks.pop(index, None)
        if task is not None:
            self._progress.remove_task(task)
        self._progress.advance(self._overall)


@contextlib.contextmanager
def convert_progress(*, enabled: bool) -> Iterator[ConvertProgressDisplay | None]:
    """A live convert display, or nothing when the terminal cannot host one.

    Yields None when disabled, which `convert()` accepts as "report nothing".
    """
    if not enabled or not console.is_terminal:
        yield None
        return

    progress = Progress(
        SpinnerColumn(),
        # markup=False: a track named "Set [b].wav" would otherwise render as
        # "Set .wav", the same trap the log handler avoids.
        TextColumn("{task.description}", markup=False),
        BarColumn(),
        TaskProgressColumn(),
        _OverallCountColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    with progress:
        yield ConvertProgressDisplay(progress)
