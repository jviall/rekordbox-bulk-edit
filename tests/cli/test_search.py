"""Tests for cli/search.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.search import search_command


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.search.logger") as mock_log:
        yield mock_log


class TestSearchCommand:
    @patch("rekordbox_edit.cli.search.print_track_info")
    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli.search.Rekordbox6Database")
    def test_calls_print_track_info_by_default(
        self, mock_db_class, mock_search, mock_print, make_track
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = [make_track(ID="AAA111")]

        result = CliRunner().invoke(search_command, [])

        assert result.exit_code == 0
        mock_print.assert_called_once()

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli.search.Rekordbox6Database")
    def test_print_ids_outputs_space_separated_ids(
        self, mock_db_class, mock_search, make_track
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = [make_track(ID="AAA111"), make_track(ID="BBB222")]

        result = CliRunner().invoke(search_command, ["--print", "ids"])

        assert result.exit_code == 0
        assert "AAA111 BBB222" in result.output

    @patch("rekordbox_edit.cli.search.print_track_info")
    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli.search.Rekordbox6Database")
    def test_print_silent_produces_no_output(
        self, mock_db_class, mock_search, mock_print, make_track
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = [make_track(ID="AAA111")]

        result = CliRunner().invoke(search_command, ["--print", "silent"])

        assert result.exit_code == 0
        assert result.output.strip() == ""
        mock_print.assert_not_called()

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli.search.Rekordbox6Database")
    def test_filters_forwarded_to_search(self, mock_db_class, mock_search):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = []

        CliRunner().invoke(
            search_command,
            ["--artist", "Daft Punk", "--format", "flac", "--match-all"],
        )

        args = mock_search.call_args.args[1]
        assert args.artist == ["Daft Punk"]
        assert args.format == ["flac"]
        assert args.match_all is True

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli.search.Rekordbox6Database")
    def test_reads_track_ids_from_stdin(self, mock_db_class, mock_search):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = []

        CliRunner().invoke(search_command, [], input="AAA111 BBB222")

        args = mock_search.call_args.args[1]
        assert "AAA111" in args.track_ids
        assert "BBB222" in args.track_ids
