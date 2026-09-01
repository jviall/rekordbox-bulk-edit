"""Tests for the live convert progress display."""

import io
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.progress import Progress

from rekordbox_edit.cli._progress import (
    ConvertProgressDisplay,
    _OverallCountColumn,
    convert_progress,
)


class _Task:
    def __init__(self, total):
        self.total = total
        self.completed = 0


class TestOverallCountColumn:
    def test_renders_the_count_for_a_task_with_a_total(self):
        assert str(_OverallCountColumn().render(_Task(total=9))) == "0/9"

    def test_renders_nothing_for_a_file_task(self):
        # File tasks have no total, and "0/?" beside a pulsing bar is noise.
        assert _OverallCountColumn().render(_Task(total=None)) == ""


class TestConvertProgressDisplay:
    @pytest.fixture
    def display(self):
        progress = Progress()
        return progress, ConvertProgressDisplay(progress, total=3)

    def test_a_line_appears_per_file_in_flight(self, display):
        progress, d = display

        d.started(0, "a.flac")
        d.started(1, "b.flac")

        descriptions = [t.description for t in progress.tasks]
        assert "a.flac" in descriptions
        assert "b.flac" in descriptions

    def test_a_finished_file_gives_up_its_line(self, display):
        progress, d = display
        d.started(0, "a.flac")
        d.started(1, "b.flac")

        d.finished(0, converted=True)

        assert [t.description for t in progress.tasks] == ["Converting", "b.flac"]

    def test_the_overall_bar_advances_on_every_file(self, display):
        progress, d = display
        for index in range(3):
            d.started(index, f"{index}.flac")

        d.finished(0, converted=True)
        d.finished(1, converted=False)  # a skip still consumes a file

        assert progress.tasks[0].completed == 2

    def test_a_file_with_no_name_does_not_break_the_line(self, display):
        progress, d = display

        d.started(0, None)

        assert progress.tasks[-1].description == ""

    def test_finishing_an_unknown_index_is_harmless(self, display):
        progress, d = display

        d.finished(99, converted=True)

        assert progress.tasks[0].completed == 1


class TestConvertProgressEnabling:
    def _console(self, is_terminal):
        # is_terminal is a read-only property, so swap the console itself for
        # one built to answer the way this case needs.
        return patch(
            "rekordbox_edit.cli._progress.console",
            Console(file=io.StringIO(), force_terminal=is_terminal),
        )

    def test_disabled_yields_nothing(self):
        with self._console(True), convert_progress(5, enabled=False) as progress:
            assert progress is None

    def test_a_non_terminal_yields_nothing(self):
        # Piping into another command must not emit control codes.
        with self._console(False), convert_progress(5, enabled=True) as progress:
            assert progress is None

    def test_an_empty_batch_yields_nothing(self):
        with self._console(True), convert_progress(0, enabled=True) as progress:
            assert progress is None

    def test_an_unknown_total_still_displays(self):
        with self._console(True), convert_progress(None, enabled=True) as progress:
            assert isinstance(progress, ConvertProgressDisplay)

    def test_a_known_total_gives_the_overall_bar_a_target(self):
        with self._console(True), convert_progress(5, enabled=True) as progress:
            assert isinstance(progress, ConvertProgressDisplay)
            assert progress._progress.tasks[0].total == 5
