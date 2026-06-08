"""Tests for cli/edit.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.edit import edit_command
from rekordbox_edit.models import EditOp, EditResponse, EditResult, Track


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.edit.logger") as mock_log:
        yield mock_log


def _response(tracks=None, edits=None, skipped=None):
    tracks = tracks or [
        Track(ID="1", Title="New", FileNameL="x.wav", FolderPath="/x.wav")
    ]
    edits = edits or [EditOp(id=t.ID, new_value="New") for t in tracks]
    return EditResponse(
        tracks=tracks,
        result=EditResult(field="Title", edits=edits, skipped=skipped or []),
    )


class TestEditCommand:
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_yes_calls_edit_once(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code == 0
        # exactly one call, dry_run not set
        mock_edit.assert_called_once()
        assert mock_edit.call_args.kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_dry_run_passes_flag_through(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--dry-run"]
        )

        assert result.exit_code == 0
        mock_edit.assert_called_once()
        assert mock_edit.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_empty_result_exits_cleanly(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response(tracks=[], edits=[])

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code == 0

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_value_error_becomes_usage_error(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = ValueError("Found 2 tracks that would be edited")

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_print_ids_outputs_ids(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        track = Track(ID="AAA", FileNameL="x.wav", FolderPath="/x.wav")
        mock_edit.return_value = _response(
            tracks=[track], edits=[EditOp(id="AAA", new_value="New")]
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes", "--print", "ids"]
        )

        assert result.exit_code == 0
        assert "AAA" in result.output

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_print_json_outputs_envelope(self, mock_db_class, mock_edit):
        import json

        mock_db_class.return_value = Mock(session=Mock())
        track = Track(ID="AAA", FileNameL="x.wav", FolderPath="/x.wav")
        mock_edit.return_value = _response(
            tracks=[track], edits=[EditOp(id="AAA", new_value="New")]
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes", "--print", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output.splitlines()[-1])
        assert payload["result"]["field"] == "Title"
        assert payload["result"]["edits"] == [{"id": "AAA", "new_value": "New"}]
