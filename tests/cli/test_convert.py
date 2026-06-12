"""Tests for cli/convert.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.convert import convert_command
from rekordbox_edit.models import (
    ConvertOp,
    ConvertResponse,
    ConvertResult,
    SkippedTrack,
    Track,
)
from rekordbox_edit.utils import UserQuit


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.convert.logger") as mock_log:
        yield mock_log


def _response(tracks=None, converted=None, deleted=0, skipped=None, format_out="aiff"):
    tracks = tracks or [Track(ID="1", FileNameL="t.aiff", FolderPath="/t.aiff")]
    converted = converted or [
        ConvertOp(id=t.ID, source_path="/t.wav", output_path="/t.aiff") for t in tracks
    ]
    return ConvertResponse(
        tracks=tracks,
        result=ConvertResult(
            format_out=format_out,
            converted=converted,
            deleted=deleted,
            skipped=skipped or [],
        ),
    )


class TestConvertCommand:
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_yes_calls_convert_once(self, _pid, mock_db_class, mock_convert):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        assert result.exit_code == 0
        mock_convert.assert_called_once()

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_dry_run(self, _pid, mock_db_class, mock_convert):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--dry-run"]
        )

        assert result.exit_code == 0
        mock_convert.assert_called_once()
        assert mock_convert.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_warns_already_target_skip(
        self, _pid, mock_db_class, mock_convert, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response(
            skipped=[SkippedTrack(id="2", reason="already_target_format")]
        )

        CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        warnings = [c.args[0] for c in mock_logger.warning.call_args_list]
        assert any("already" in w and "1" in w for w in warnings)
        assert not any("--overwrite" in w for w in warnings)

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_warns_output_conflict_skip(
        self, _pid, mock_db_class, mock_convert, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response(
            skipped=[SkippedTrack(id="2", reason="output_file_exists")]
        )

        CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        warnings = [c.args[0] for c in mock_logger.warning.call_args_list]
        assert any("--overwrite" in w for w in warnings)

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_warns_unsupported_source_skip(
        self, _pid, mock_db_class, mock_convert, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response(
            skipped=[SkippedTrack(id="2", reason="unsupported_source_format")]
        )

        CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        warnings = [c.args[0] for c in mock_logger.warning.call_args_list]
        assert any("unsupported" in w.lower() and "1" in w for w in warnings)

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_logs_deleted_count(self, _pid, mock_db_class, mock_convert, mock_logger):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response(deleted=2)

        CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        mock_logger.info.assert_any_call("Deleted 2 original file(s)")

    @patch("rekordbox_edit.cli._utils.confirm")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345)
    def test_rekordbox_running_user_declines(self, _pid, mock_db_class, mock_confirm):
        mock_confirm.return_value = False

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        mock_db_class.assert_not_called()

    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_aborts_in_scripting_mode_when_rekordbox_running(self, mock_db_class):
        with patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345):
            result = CliRunner().invoke(
                convert_command,
                ["--format-out", "aiff", "--yes", "--print", "silent"],
            )

        assert result.exit_code != 0

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_print_json_emits_envelope(self, _pid, mock_db_class, mock_convert):
        import json

        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--yes", "--print", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output.splitlines()[-1])
        assert payload["result"]["format_out"] == "aiff"

    @patch("rekordbox_edit.cli.convert.print_track_info")
    @patch("rekordbox_edit.cli.convert.confirm", return_value=True)
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_default_flow_previews_then_commits(
        self, _pid, mock_db_class, mock_convert, _confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        assert mock_convert.call_count == 2
        assert mock_convert.call_args_list[0].kwargs.get("dry_run") is True
        assert mock_convert.call_args_list[1].kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.convert.print_track_info")
    @patch("rekordbox_edit.cli.convert.confirm", return_value=False)
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_default_flow_user_declines_skips_commit(
        self, _pid, mock_db_class, mock_convert, _confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        mock_convert.assert_called_once()  # preview only
        assert mock_convert.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.convert.print_track_info")
    @patch("rekordbox_edit.cli.convert.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_default_flow_user_quit_skips_commit(
        self, _pid, mock_db_class, mock_convert, _confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        mock_convert.assert_called_once()  # preview only

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_default_flow_empty_preview_exits_cleanly(
        self, _pid, mock_db_class, mock_convert
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = ConvertResponse(
            tracks=[],
            result=ConvertResult(
                format_out="aiff", converted=[], deleted=0, skipped=[]
            ),
        )

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        mock_convert.assert_called_once()  # preview only

    @patch("rekordbox_edit.cli.convert.print_track_info")
    @patch("rekordbox_edit.cli.convert.confirm")
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_interactive_narrows_to_confirmed_tracks(
        self, _pid, mock_db_class, mock_convert, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        tracks = [
            Track(ID="A", FileNameL="a.aiff", FolderPath="/a.aiff"),
            Track(ID="B", FileNameL="b.aiff", FolderPath="/b.aiff"),
        ]
        ops = [
            ConvertOp(id="A", source_path="/a.wav", output_path="/a.aiff"),
            ConvertOp(id="B", source_path="/b.wav", output_path="/b.aiff"),
        ]
        mock_convert.return_value = _response(tracks=tracks, converted=ops)
        # Confirm A, decline B.
        mock_confirm.side_effect = [True, False]

        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--interactive"]
        )

        assert result.exit_code == 0
        assert mock_convert.call_count == 2
        narrowed_args = mock_convert.call_args_list[1].args[1]
        assert narrowed_args.track_ids == ["A"]

    @patch("rekordbox_edit.cli._utils.confirm", return_value=True)
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345)
    def test_rekordbox_running_user_accepts_continues(
        self, _pid, mock_db_class, _confirm
    ):
        with patch("rekordbox_edit.cli.convert.convert") as mock_convert:
            mock_db_class.return_value = Mock(session=Mock())
            mock_convert.return_value = _response()

            result = CliRunner().invoke(
                convert_command, ["--format-out", "aiff", "--yes"]
            )

        assert result.exit_code == 0
        mock_db_class.assert_called_once()
