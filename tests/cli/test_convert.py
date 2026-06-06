"""Tests for cli/convert.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.api.convert import ConvertPlan
from rekordbox_edit.models import Track
from rekordbox_edit.cli.convert import convert_command


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.convert.logger") as mock_log:
        yield mock_log


def _make_plan(files=None, skipped=None, format_out="aiff", should_delete=True):
    return ConvertPlan(
        files=files or [Track(ID="1", FileNameL="track.wav", FolderPath="/track.wav")],
        skipped=skipped or [],
        should_delete=should_delete,
        format_out=format_out,
    )


class TestConvertCommand:
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_calls_convert_on_confirmation(
        self, mock_pid, mock_db_class, mock_plan, mock_convert
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = _make_plan()
        mock_convert.return_value = Mock(converted=[{"content_id": "1"}], deleted=0)

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        assert result.exit_code == 0
        mock_convert.assert_called_once()

    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_dry_run_does_not_call_convert(self, mock_pid, mock_db_class, mock_plan):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = _make_plan()

        with patch("rekordbox_edit.cli.convert.convert") as mock_convert:
            result = CliRunner().invoke(
                convert_command, ["--format-out", "aiff", "--dry-run"]
            )

        assert result.exit_code == 0
        mock_convert.assert_not_called()

    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_warns_about_skipped_files(
        self, mock_pid, mock_db_class, mock_plan, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        skipped = [Track(ID="2", FileNameL="conflict.wav", FolderPath="/conflict.wav")]
        mock_plan.return_value = _make_plan(skipped=skipped)

        with patch("rekordbox_edit.cli.convert.convert") as mock_convert:
            mock_convert.return_value = Mock(converted=[], deleted=0)
            CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        mock_logger.warning.assert_called()

    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_empty_plan_exits_early(self, mock_pid, mock_db_class, mock_plan):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = ConvertPlan(
            files=[], skipped=[], should_delete=True, format_out="aiff"
        )

        with patch("rekordbox_edit.cli.convert.convert") as mock_convert:
            result = CliRunner().invoke(
                convert_command, ["--format-out", "aiff", "--yes"]
            )

        assert result.exit_code == 0
        mock_convert.assert_not_called()

    @patch("rekordbox_edit.cli.convert._handle_stdin", return_value=False)
    @patch("rekordbox_edit.cli.convert._confirm_converts")
    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_cancellation_skips_convert(
        self, mock_pid, mock_db_class, mock_plan, mock_confirm, _
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = _make_plan()
        mock_confirm.return_value = None

        with patch("rekordbox_edit.cli.convert.convert") as mock_convert:
            result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        mock_convert.assert_not_called()

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_logs_deleted_count(
        self, mock_pid, mock_db_class, mock_plan, mock_convert, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = _make_plan()
        mock_convert.return_value = Mock(converted=[{"content_id": "1"}], deleted=2)

        CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        mock_logger.info.assert_any_call("Deleted 2 original file(s)")

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.confirm")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=12345)
    def test_rekordbox_running_user_accepts_continues(
        self, mock_pid, mock_confirm, mock_db_class, mock_plan, mock_convert
    ):
        mock_confirm.return_value = True
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = _make_plan()
        mock_convert.return_value = Mock(converted=[], deleted=0)

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        assert result.exit_code == 0
        mock_db_class.assert_called_once()

    @patch("rekordbox_edit.cli.convert._handle_stdin", return_value=False)
    @patch("rekordbox_edit.cli.convert.confirm")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=12345)
    def test_rekordbox_running_user_declines_returns_early(
        self, mock_pid, mock_confirm, _
    ):
        mock_confirm.return_value = False

        with patch("rekordbox_edit.cli.convert.Rekordbox6Database") as mock_db_class:
            result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        mock_db_class.assert_not_called()

    @patch("rekordbox_edit.cli.convert.plan_convert")
    @patch("rekordbox_edit.cli.convert.Rekordbox6Database")
    @patch("rekordbox_edit.cli.convert.get_rekordbox_pid", return_value=None)
    def test_aborts_when_rekordbox_running_in_scripting_mode(
        self, mock_pid, mock_db_class, mock_plan
    ):
        mock_pid.return_value = 12345
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan.return_value = _make_plan()

        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--yes", "--print", "silent"]
        )

        assert result.exit_code != 0
