"""Tests for cli/edit.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.edit import edit_command
from rekordbox_edit.models import EditOp, EditResponse, EditResult, SkippedTrack, Track
from rekordbox_edit.cli._utils import UserQuit
from rekordbox_edit.errors import InputError


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.edit.logger") as mock_log:
        yield mock_log


@pytest.fixture(autouse=True)
def mock_rekordbox_not_running():
    with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
        yield


def _response(tracks=None, edits=None, skipped=None):
    if tracks is None:
        tracks = [Track(ID="1", Title="New", FileNameL="x.wav", FolderPath="/x.wav")]
    if edits is None:
        edits = [EditOp(id=t.ID, new_value="New") for t in tracks]
    return EditResponse(
        tracks=tracks,
        result=EditResult(field="Title", edits=edits, skipped=skipped or []),
    )


class TestEditCommand:
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_empty_result_exits_cleanly(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response(tracks=[], edits=[])

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code == 0

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_value_error_becomes_usage_error(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = InputError("Found 2 tracks that would be edited")

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_value_error_becomes_usage_error(
        self, mock_db_class, mock_edit
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = InputError("Found 2 tracks that would be edited")

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", return_value=True)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_apply_pass_input_error_becomes_usage_error(
        self, mock_db_class, mock_edit, _confirm, _print
    ):
        # The preview passes the --multi guard and the apply pass does not.
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = [
            _response(),
            InputError("Found 2 tracks that would be edited"),
        ]

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", return_value=True)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_interactive_apply_value_error_becomes_usage_error(
        self, mock_db_class, mock_edit, _confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = [
            _response(),
            InputError("Found 2 tracks that would be edited"),
        ]

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--interactive"]
        )

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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
        applied = mock_edit.call_args_list[1].kwargs["ops"]
        assert [op.id for op in applied] == ["A"]

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
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


def _gated_response(tracks=None, edits=None):
    tracks = (
        tracks
        if tracks is not None
        else [Track(ID="1", Title="T", FileNameL="x.wav", FolderPath="/x.wav")]
    )
    edits = (
        edits
        if edits is not None
        else [EditOp(id=t.ID, new_value="/new/x.wav") for t in tracks]
    )
    return EditResponse(
        tracks=tracks,
        result=EditResult(
            field="FolderPath",
            edits=edits,
            skipped=[SkippedTrack(id="9", reason="file_not_found")],
        ),
    )


class TestEditForceFlow:
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_force_flag_passes_through(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes", "--force"]
        )

        assert result.exit_code == 0
        assert mock_edit.call_args.args[1].force is True

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_includes_gated_on_confirm(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()
        # Include the gated track, then apply.
        mock_confirm.side_effect = [True, True]

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav"]
        )

        assert result.exit_code == 0
        # preview, forced re-preview, real run
        assert mock_edit.call_count == 3
        assert mock_edit.call_args_list[0].args[1].force is False
        assert mock_edit.call_args_list[1].args[1].force is True
        assert mock_edit.call_args_list[1].kwargs.get("dry_run") is True
        assert mock_edit.call_args_list[2].args[1].force is True
        assert mock_edit.call_args_list[2].kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_gated_declined_stays_unforced(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()
        # Leave the gated track skipped, then apply the rest.
        mock_confirm.side_effect = [False, True]

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav"]
        )

        assert result.exit_code == 0
        assert mock_edit.call_count == 2  # preview + real run
        assert mock_edit.call_args_list[1].args[1].force is False

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_no_gated_prompt_when_forced(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()
        mock_confirm.side_effect = [True]  # only the apply prompt

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav", "--force"]
        )

        assert result.exit_code == 0
        assert mock_edit.call_count == 2
        assert mock_confirm.call_count == 1

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_gated_prompt_user_quit_skips_commit(
        self, mock_db_class, mock_edit, _confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav"]
        )

        assert result.exit_code == 0
        mock_edit.assert_called_once()  # preview only

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_including_gated_tracks_can_trip_multi_guard(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        # Including the held-back track widens the edit past one track, which
        # the single-track guard rejects on the re-preview.
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = [
            _gated_response(),
            InputError("Found 2 tracks that would be edited"),
        ]
        mock_confirm.side_effect = [True]

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav"]
        )

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_mode_leaves_gated_skipped(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav", "--yes"]
        )

        assert result.exit_code == 0
        mock_edit.assert_called_once()
        assert mock_edit.call_args.args[1].force is False


def _warnings(mock_logger) -> str:
    return "\n".join(str(c.args[0]) for c in mock_logger.warning.call_args_list)


def _infos(mock_logger) -> str:
    return "\n".join(str(c.args[0]) for c in mock_logger.info.call_args_list)


class TestEditSkipReporting:
    """A run used to report only what it changed, so a filter matching 30
    tracks and editing 4 looked like it found 4."""

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_reports_why_tracks_were_passed_over(
        self, mock_db_class, mock_edit, _print, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response(
            skipped=[
                SkippedTrack(id="2", reason="no_change"),
                SkippedTrack(id="3", reason="no_change"),
                SkippedTrack(id="4", reason="unknown_file_type"),
            ]
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code == 0
        warnings = _warnings(mock_logger)
        assert "Skipping 2 track(s): already hold the requested value" in warnings
        assert "Skipping 1 track(s): name a file in no format" in warnings

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_dry_run_reports_them_too(
        self, mock_db_class, mock_edit, _print, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response(
            skipped=[SkippedTrack(id="2", reason="no_change")]
        )

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--dry-run"])

        assert "already hold the requested value" in _warnings(mock_logger)

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_gated_reasons_are_not_reported_twice(
        self, mock_db_class, mock_edit, mock_confirm, _print, mock_logger
    ):
        # The force prompt names those tracks individually, so the summary
        # must leave that reason out.
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = [_gated_response(), _gated_response()]
        mock_confirm.side_effect = [False, True]

        CliRunner().invoke(edit_command, ["FolderPath", "--replace", "/new/x.wav"])

        assert "were held back by safety checks" in _infos(mock_logger)
        assert "name a file that does not exist" not in _warnings(mock_logger)

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", return_value=True)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_a_track_that_changed_after_the_preview_is_reported(
        self, mock_db_class, mock_edit, _confirm, _print, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        applied = _response(skipped=[SkippedTrack(id="2", reason="db_or_fs_changed")])
        mock_edit.side_effect = [_response(), applied]

        CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert "Skipping 1 track(s): changed since the preview" in _warnings(
            mock_logger
        )
