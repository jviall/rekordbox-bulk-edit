"""Unit tests for the display module."""

import pytest
from rich.console import Console

from rekordbox_edit import display
from rekordbox_edit.display import (
    PrintableField,
    print_track_info,
)
from rekordbox_edit.utils import get_file_type_name


@pytest.fixture
def wide_console(monkeypatch):
    """Swap the module console for one wide enough to render without truncation.

    Rich's default non-TTY width is 80 cols, which truncates long values
    (e.g. FolderPath) with an ellipsis and makes substring assertions flaky.
    """
    monkeypatch.setattr(display, "console", Console(record=True, width=400))


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
        make_track,
    ):
        """Default columns include ID, Title, FileType, SampleRate, BitDepth, FileNameL, FolderPath."""
        mock_content = make_track(
            FileNameL="my-song.flac",
            FolderPath="/music/library/my-song.flac",
        )

        print_track_info([mock_content])

        captured = capsys.readouterr()
        assert mock_content.Title in captured.out
        assert get_file_type_name(mock_content.FileType) in captured.out
        assert str(mock_content.SampleRate) in captured.out
        assert str(mock_content.BitDepth) in captured.out
        assert "my-song.flac" in captured.out
        # FolderPath renders the directory portion, not the full path
        assert "/music/library" in captured.out

    def test_track_with_zero_values(self, capsys, wide_console, make_track):
        """Test printing track with zero values."""
        mock_content = make_track(
            ID="123",
            SampleRate=0,
            BitRate=0,
            BitDepth=0,
        )

        print_track_info([mock_content], self.TEST_PRINT_COLUMNS)

        captured = capsys.readouterr()
        lines = captured.out.split("\n")
        data_line = [line for line in lines if "test" in line][0]
        assert data_line.count("0") == 3

    def test_change_preview_renders_old_struck_through_with_new(
        self, capsys, wide_console, make_track
    ):
        """When changed_field + new_values are provided, both old and new appear in the cell."""
        mock_content = make_track(Title="Old Name")

        print_track_info(
            [mock_content],
            print_columns=[PrintableField.Title],
            changed_field=PrintableField.Title,
            new_values=["New Name"],
        )

        captured = capsys.readouterr()
        assert "Old Name" in captured.out
        assert "New Name" in captured.out

    def test_change_preview_requires_both_args(self, make_track):
        """Providing only one of changed_field/new_values raises ValueError."""
        mock_content = make_track()

        with pytest.raises(ValueError, match="must be provided together"):
            print_track_info([mock_content], changed_field=PrintableField.Title)

        with pytest.raises(ValueError, match="must be provided together"):
            print_track_info([mock_content], new_values=["x"])

    def test_change_preview_length_mismatch_raises(self, make_track):
        """new_values length must match content_list length."""
        mock_content = make_track()

        with pytest.raises(ValueError, match="length"):
            print_track_info(
                [mock_content],
                changed_field=PrintableField.Title,
                new_values=["a", "b"],
            )

    def test_multiple_tracks(self, capsys, wide_console, make_track):
        """Test printing multiple tracks."""
        mock_content1 = make_track(
            ID="123",
            FileNameL="track1.flac",
            FileType=5,
            FolderPath="/path/track1.flac",
        )

        mock_content2 = make_track(
            ID="456",
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

    def test_track_with_unknown_file_type(self, capsys, wide_console, make_track):
        """Test printing track with unknown file type."""
        mock_content = make_track(
            ID="123",
            FileType=6,
        )

        print_track_info([mock_content], self.TEST_PRINT_COLUMNS)

        captured = capsys.readouterr()
        assert "UNKNOWN" in captured.out
