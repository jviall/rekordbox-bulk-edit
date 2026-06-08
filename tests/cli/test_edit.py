"""Tests for cli/edit.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.edit import edit_command
from rekordbox_edit.models import EditOp, EditResponse, EditResult, Track
from rekordbox_edit.utils import UserQuit


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

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", return_value=True)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_default_flow_previews_then_commits(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code == 0
        assert mock_edit.call_count == 2  # dry-run preview + real run
        assert mock_edit.call_args_list[0].kwargs.get("dry_run") is True
        assert mock_edit.call_args_list[1].kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", return_value=False)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_default_flow_user_declines_skips_commit(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code == 0
        mock_edit.assert_called_once()  # only the dry-run preview
        assert mock_edit.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.edit.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_default_flow_user_quit_skips_commit(
        self, mock_db_class, mock_edit, _print, _confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code == 0
        mock_edit.assert_called_once()  # preview only

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_default_flow_empty_preview_exits_cleanly(
        self, mock_db_class, mock_edit, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = EditResponse(
            tracks=[],
            result=EditResult(field="Title", edits=[], skipped=[]),
        )

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code == 0
        mock_edit.assert_called_once()

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_interactive_narrows_to_confirmed_tracks(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        tracks = [
            Track(ID="A", Title="OldA", FileNameL="a.wav", FolderPath="/a.wav"),
            Track(ID="B", Title="OldB", FileNameL="b.wav", FolderPath="/b.wav"),
        ]
        edits = [
            EditOp(id="A", new_value="NewA"),
            EditOp(id="B", new_value="NewB"),
        ]
        mock_edit.return_value = _response(tracks=tracks, edits=edits)
        # Confirm A, decline B.
        mock_confirm.side_effect = [True, False]

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "NewA", "--interactive"]
        )

        assert result.exit_code == 0
        assert mock_edit.call_count == 2
        narrowed_args = mock_edit.call_args_list[1].args[1]
        assert narrowed_args.track_ids == ["A"]

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_interactive_user_quit_skips_commit(
        self, mock_db_class, mock_edit, _confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        tracks = [Track(ID="A", Title="O", FileNameL="a.wav", FolderPath="/a.wav")]
        mock_edit.return_value = _response(
            tracks=tracks, edits=[EditOp(id="A", new_value="N")]
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "N", "--interactive"]
        )

        assert result.exit_code == 0
        mock_edit.assert_called_once()  # preview only — UserQuit on first track
