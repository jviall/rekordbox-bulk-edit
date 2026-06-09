"""Tests for cli/search.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.search import search_command
from rekordbox_edit.models import SearchResponse


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.search.logger") as mock_log:
        yield mock_log


def _response(*tracks):
    return SearchResponse(tracks=list(tracks))


class TestSearchCommand:
    @patch("rekordbox_edit.cli.search.print_track_info")
    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_calls_print_track_info_by_default(
        self, mock_db_class, mock_search, mock_print, make_track
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = _response(make_track(ID="AAA111"))

        result = CliRunner().invoke(search_command, [])

        assert result.exit_code == 0
        mock_print.assert_called_once()

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_print_ids(self, mock_db_class, mock_search, make_track):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = _response(make_track(ID="A"), make_track(ID="B"))

        result = CliRunner().invoke(search_command, ["--print", "ids"])

        assert result.exit_code == 0
        assert "A B" in result.output

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_print_json_emits_envelope(self, mock_db_class, mock_search, make_track):
        import json

        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = _response(make_track(ID="A"))

        result = CliRunner().invoke(search_command, ["--print", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["tracks"][0]["ID"] == "A"

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_print_silent_produces_no_output(
        self, mock_db_class, mock_search, make_track
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_search.return_value = _response(make_track(ID="A"))

        result = CliRunner().invoke(search_command, ["--print", "silent"])

        assert result.exit_code == 0
        assert result.output.strip() == ""
