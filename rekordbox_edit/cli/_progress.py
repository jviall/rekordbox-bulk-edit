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

from rekordbox_edit.logger import console

logger = logging.getLogger(__name__)


class _OverallCountColumn(MofNCompleteColumn):
    """The n-of-total count, shown only for the overall task.

    Per-file tasks have no total (see ConvertProgressDisplay), and rendering
    them as "0/?" is noise beside a bar that is already pulsing.
    """

    def render(self, task):
        return "" if task.total is None else super().render(task)


class ConvertProgressDisplay:
    """A line per file being encoded, above an overall bar.

    Finished files are not kept here. `convert()` already logs a line for each
    one, and those scroll above the live region on their way to the debug log,
    which leaves this display showing only what is still in flight.

    ffmpeg reports its position roughly twice a second and a track encodes in
    about two seconds, so a per-file percentage would show three or four
    frames. The per-file lines spin rather than fill for that reason: what is
    worth knowing is which files are being worked on, not how far into each.
    """

    def __init__(self, progress: Progress, total: int | None):
        self._progress = progress
        self._overall = progress.add_task("Converting", total=total)
        self._tasks: dict[int, TaskID] = {}

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
def convert_progress(
    total: int | None, *, enabled: bool
) -> Iterator[ConvertProgressDisplay | None]:
    """A live convert display, or nothing when the terminal cannot host one.

    Yields None when disabled, which `convert()` accepts as "report nothing".
    A `total` of None leaves the overall bar counting up without a target, for
    the `--yes` path where nothing has classified the batch yet.
    """
    if not enabled or not console.is_terminal or total == 0:
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
        yield ConvertProgressDisplay(progress, total)
