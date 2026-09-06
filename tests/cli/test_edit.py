"""Tests for cli/edit.py."""

from typing import get_args
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli._utils import UserQuit
from rekordbox_edit.cli.edit import _SKIP_MESSAGES, edit_command
from rekordbox_edit.errors import InputError
from rekordbox_edit.models import (
    EditOp,
    EditResponse,
    EditResult,
    SkippedTrack,
    SkipReason,
    Track,
)


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.edit.logger") as mock_log:
        yield mock_log


@pytest.fixture(autouse=True)
def mock_rekordbox_not_running():
    with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
        yield


def _response(tracks=None, edits=None, skipped=None, dry_run=False):
    if tracks is None:
        tracks = [Track(ID="1", Title="New", FileNameL="x.wav", FolderPath="/x.wav")]
    if edits is None:
        edits = [EditOp(id=t.ID, new_value="New", track=t) for t in tracks]
    return EditResponse(
        result=EditResult(
            field="Title", dry_run=dry_run, edits=edits, skipped=skipped or []
        ),
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
        # The preview succeeds and the apply pass raises.
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
            tracks=[track],
            edits=[EditOp(id="AAA", new_value="New", track=track)],
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
            tracks=[track],
            edits=[EditOp(id="AAA", new_value="New", track=track)],
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes", "--print", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output.splitlines()[-1])
        assert payload["result"]["field"] == "Title"
        assert [e["id"] for e in payload["result"]["edits"]] == ["AAA"]
        assert payload["result"]["edits"][0]["track"]["ID"] == "AAA"

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
            result=EditResult(field="Title", dry_run=True, edits=[], skipped=[]),
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
            EditOp(id="A", new_value="NewA", track=tracks[0]),
            EditOp(id="B", new_value="NewB", track=tracks[1]),
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
            tracks=tracks, edits=[EditOp(id="A", new_value="N", track=tracks[0])]
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "N", "--interactive"]
        )

        assert result.exit_code == 0
        mock_edit.assert_called_once()  # preview only — UserQuit on first track


def _gated_response(tracks=None, edits=None, skipped=None, dry_run=False):
    tracks = (
        tracks
        if tracks is not None
        else [Track(ID="1", Title="T", FileNameL="x.wav", FolderPath="/x.wav")]
    )
    edits = (
        edits
        if edits is not None
        else [EditOp(id=t.ID, new_value="/new/x.wav", track=t) for t in tracks]
    )
    return EditResponse(
        result=EditResult(
            field="FolderPath",
            dry_run=dry_run,
            edits=edits,
            skipped=(
                skipped
                if skipped is not None
                else [SkippedTrack(reason="file_not_found")]
            ),
        ),
    )


class TestEditGateFlow:
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_gate_flags_pass_through(self, mock_db_class, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response()

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "New", "--yes", "--allow-missing"],
        )

        assert result.exit_code == 0
        assert mock_edit.call_args.args[1].allow_missing is True
        assert mock_edit.call_args.args[1].allow_mismatch is False

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
        # preview, re-preview with the gate lifted, real run
        assert mock_edit.call_count == 3
        assert mock_edit.call_args_list[0].args[1].allow_missing is False
        assert mock_edit.call_args_list[1].args[1].allow_missing is True
        assert mock_edit.call_args_list[1].kwargs.get("dry_run") is True
        assert mock_edit.call_args_list[2].args[1].allow_missing is True
        assert mock_edit.call_args_list[2].kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_each_gate_is_asked_and_lifted_on_its_own(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        # Authorizing a path with no file behind it is a different decision
        # from authorizing cues that may land misaligned.
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response(
            skipped=[
                SkippedTrack(reason="file_not_found"),
                SkippedTrack(reason="length_mismatch"),
            ]
        )
        # Missing: yes. Mismatch: no. Then apply.
        mock_confirm.side_effect = [True, False, True]

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav"]
        )

        assert result.exit_code == 0
        assert mock_confirm.call_count == 3
        applied = mock_edit.call_args_list[-1].args[1]
        assert applied.allow_missing is True
        assert applied.allow_mismatch is False

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_gated_declined_leaves_the_gate_shut(
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
        assert mock_edit.call_args_list[1].args[1].allow_missing is False

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_no_gate_prompt_when_its_flag_is_already_set(
        self, mock_db_class, mock_edit, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()
        mock_confirm.side_effect = [True]  # only the apply prompt

        result = CliRunner().invoke(
            edit_command,
            ["FolderPath", "--replace", "/new/x.wav", "--allow-missing"],
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

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_alone_leaves_gated_skipped(self, mock_db_class, mock_edit):
        # --yes takes the default answer to every prompt, and a gate's default
        # is no, so only the flag itself lets the held-back tracks through.
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _gated_response()

        result = CliRunner().invoke(
            edit_command, ["FolderPath", "--replace", "/new/x.wav", "--yes"]
        )

        assert result.exit_code == 0
        mock_edit.assert_called_once()
        assert mock_edit.call_args.args[1].allow_missing is False


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
                SkippedTrack(reason="no_change"),
                SkippedTrack(reason="no_change"),
                SkippedTrack(reason="unknown_file_type"),
            ]
        )

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code == 0
        warnings = _warnings(mock_logger)
        assert "Skipping 2 track(s): existing value already matches" in warnings
        assert (
            "Skipping 1 track(s): file is in format Rekordbox doesn't support"
            in warnings
        )

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_dry_run_reports_them_too(
        self, mock_db_class, mock_edit, _print, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response(skipped=[SkippedTrack(reason="no_change")])

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--dry-run"])

        assert "existing value already matches" in _warnings(mock_logger)

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_gated_reasons_are_not_reported_twice(
        self, mock_db_class, mock_edit, mock_confirm, _print, mock_logger
    ):
        # The gate prompt names those tracks individually, so the summary
        # must leave that reason out.
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = [_gated_response(), _gated_response()]
        mock_confirm.side_effect = [False, True]

        CliRunner().invoke(edit_command, ["FolderPath", "--replace", "/new/x.wav"])

        assert "track(s) held back" in _infos(mock_logger)
        assert "file does not exist" not in _warnings(mock_logger)

    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.confirm", return_value=True)
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_a_track_that_changed_after_the_preview_is_reported(
        self, mock_db_class, mock_edit, _confirm, _print, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        applied = _response(skipped=[SkippedTrack(reason="db_or_fs_changed")])
        mock_edit.side_effect = [_response(), applied]

        CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert "Skipping 1 track(s): changed since the preview" in _warnings(
            mock_logger
        )

    def test_no_message_is_keyed_on_a_reason_that_cannot_occur(self):
        # _report_skips matches on equality with SkippedTrack.reason, so a key
        # that is not a SkipReason is silently never emitted.
        assert set(_SKIP_MESSAGES) <= set(get_args(SkipReason))

    @pytest.mark.parametrize("reason", sorted(_SKIP_MESSAGES))
    @patch("rekordbox_edit.cli.edit.print_track_info")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_every_reason_in_the_table_is_emitted(
        self, mock_db_class, mock_edit, _print, reason, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.return_value = _response(skipped=[SkippedTrack(reason=reason)])

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        assert f"Skipping 1 track(s): {_SKIP_MESSAGES[reason]}" in _warnings(
            mock_logger
        )
