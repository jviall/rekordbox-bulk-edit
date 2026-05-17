"""Unit tests for the display module."""

from typing import Callable

import pytest
from pyrekordbox.db6 import DjmdContent
from rich.console import Console

from rekordbox_edit import display
from rekordbox_edit.display import (
    PRINT_WIDTHS,
    PrintableField,
    print_track_info,
    truncate_field,
)
from rekordbox_edit.utils import get_file_type_name


@pytest.fixture
def wide_console(monkeypatch):
    """Swap the module console for one wide enough to render without truncation.

    Rich's default non-TTY width is 80 cols, which truncates long values
    (e.g. FolderPath) with an ellipsis and makes substring assertions flaky.
    """
    monkeypatch.setattr(display, "console", Console(record=True, width=400))


class TestTruncateField:
    """Test truncate_field function."""

    def test_truncate_field_none_value(self):
        """Test truncate_field returns empty string for None value."""
        result = truncate_field(PrintableField.Title, None)
        assert result == ""

    def test_truncate_field_empty_string(self):
        """Test truncate_field with empty string."""
        result = truncate_field(PrintableField.Title, "")
        assert result == ""

    def test_truncate_field_short_value(self):
        """Test truncate_field returns value as-is when it fits."""
        short_title = "Short Title"
        result = truncate_field(PrintableField.Title, short_title)
        assert result == short_title

    def test_truncate_field_exact_width(self):
        """Test truncate_field with value exactly at width limit."""
        # Create a value exactly the width of Title field (25 chars)
        exact_width_title = "X" * PRINT_WIDTHS[PrintableField.Title]
        result = truncate_field(PrintableField.Title, exact_width_title)
        assert result == exact_width_title

    def test_truncate_field_long_value(self):
        """Test truncate_field truncates long values with ellipsis."""
        long_title = "This is a very long title that exceeds the width limit"
        result = truncate_field(PrintableField.Title, long_title)

        assert "..." in result
        assert len(result) == PRINT_WIDTHS[PrintableField.Title]

    def test_truncate_field_minimal_truncation(self):
        """Test truncate_field with value just over the limit."""
        # Create a value just 1 char over the limit
        over_limit_title = "X" * (PRINT_WIDTHS[PrintableField.Title] + 1)
        result = truncate_field(PrintableField.Title, over_limit_title)

        assert "..." in result
        assert len(result) == PRINT_WIDTHS[PrintableField.Title]


class TestPrintTrackInfo:
    """Test print_track_info function."""

    TEST_PRINT_COLUMNS = [
        PrintableField.ID,
        PrintableField.FileNameL,
        PrintableField.Title,
        PrintableField.ArtistName,
        PrintableField.AlbumName,
        PrintableField.FileType,
        PrintableField.SampleRate,
        PrintableField.BitDepth,
        PrintableField.BitRate,
        PrintableField.FolderPath,
    ]

    def test_empty_content_list(self, capsys):
        """Test printing with empty content list."""
        print_track_info([])

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_default_columns(
        self,
        capsys,
        wide_console,
        make_djmd_content_item: Callable[[], DjmdContent],
    ):
        """Test printing a single track with the default print_columns.

        Default columns are: ID, Title, FileType, SampleRate, BitDepth, FolderPath
        (ArtistName and AlbumName are NOT included by default)
        """
        # Setup mock content
        mock_content = make_djmd_content_item()

        print_track_info([mock_content])

        captured = capsys.readouterr()
        # Check default columns are present
        assert mock_content.Title in captured.out
        assert get_file_type_name(mock_content.FileType) in captured.out
        assert str(mock_content.SampleRate) in captured.out
        assert str(mock_content.BitDepth) in captured.out
        # FolderPath should be in output (may or may not be truncated depending on length)
        # The default test path is 66 chars, column width is 80, so no truncation
        assert "test_track.wav" in captured.out

    def test_track_with_zero_values(self, capsys, wide_console, make_djmd_content_item):
        """Test printing track with zero values."""
        # Setup mock content with zero values
        mock_content = make_djmd_content_item(
            ID=123,
            SampleRate=0,
            BitRate=0,
            BitDepth=0,
        )

        print_track_info([mock_content], self.TEST_PRINT_COLUMNS)

        captured = capsys.readouterr()
        lines = captured.out.split("\n")
        data_line = [line for line in lines if "test" in line][0]
        assert data_line.count("0") == 3

    def test_multiple_tracks(self, capsys, wide_console, make_djmd_content_item):
        """Test printing multiple tracks."""
        mock_content1 = make_djmd_content_item(
            ID=123,
            FileNameL="track1.flac",
            FileType=5,
            FolderPath="/path/track1.flac",
        )

        mock_content2 = make_djmd_content_item(
            ID=456,
            FileNameL="track2.mp3",
            FileType=1,
            FolderPath="/path/track2.mp3",
        )

        print_track_info([mock_content1, mock_content2])

        captured = capsys.readouterr()
        assert "track1.flac" in captured.out
        assert "track2.mp3" in captured.out
        assert "FLAC" in captured.out
        assert "MP3" in captured.out
