"""Tests for cli/convert.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.api.convert import ConvertAborted
from rekordbox_edit.cli.convert import convert_command
from rekordbox_edit.models import (
    DEFAULT_THREADS,
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

    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345)
    def test_a_write_refuses_while_rekordbox_runs(self, _pid, mock_db_class):
        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 1
        mock_db_class.assert_not_called()

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345)
    def test_a_dry_run_runs_while_rekordbox_runs(
        self, _pid, mock_db_class, mock_convert
    ):
        # A preview writes nothing, so there is nothing to refuse.
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--dry-run"]
        )

        assert result.exit_code == 0
        mock_convert.assert_called_once()

    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_a_scripting_dry_run_is_not_blocked_either(self, mock_db_class):
        mock_db_class.return_value = Mock(session=Mock())
        with (
            patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345),
            patch("rekordbox_edit.cli.convert.convert", return_value=_response()),
        ):
            result = CliRunner().invoke(
                convert_command,
                ["--format-out", "aiff", "--dry-run", "--print", "ids"],
            )

        assert result.exit_code == 0

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
    @patch("rekordbox_edit.cli.convert.confirm", return_value=True)
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_default_flow_reports_live_codec_mismatch_once(
        self, _pid, mock_db_class, mock_convert, _confirm, _print, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        # The preview cannot detect codec_mismatch (dry runs never probe);
        # only the live run surfaces it. Both runs report the same
        # classification skip, which must not be warned about twice.
        preview_skips = [SkippedTrack(id="2", reason="already_target_format")]
        live_skips = preview_skips + [SkippedTrack(id="3", reason="codec_mismatch")]
        mock_convert.side_effect = [
            _response(skipped=preview_skips),
            _response(skipped=live_skips),
        ]

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        warnings = [c.args[0] for c in mock_logger.warning.call_args_list]
        assert sum("does not match" in w for w in warnings) == 1
        assert sum("already" in w for w in warnings) == 1

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

    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=12345)
    def test_yes_does_not_override_the_refusal(self, _pid, mock_db_class):
        result = CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        assert result.exit_code == 1
        mock_db_class.assert_not_called()


class TestPartialBatchReporting:
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_a_stopped_batch_reports_what_survived(
        self, _pid, mock_db_class, mock_convert, mock_logger
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.side_effect = ConvertAborted(
            "Conversion failed for /in7.wav",
            failed_path="/in7.wav",
            converted=6,
            not_attempted=3,
        )

        result = CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        assert result.exit_code == 1
        messages = " ".join(str(c) for c in mock_logger.error.call_args_list)
        assert "/in7.wav" in messages
        assert "6 file(s) converted and kept" in messages
        assert "3 not attempted" in messages


class TestMissingSourceReporting:
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_a_vanished_source_is_reported_from_the_live_pass(
        self, _pid, mock_db_class, mock_convert, mock_logger
    ):
        # A dry run cannot predict this one, so it has to survive the live-run
        # filter that drops skips the preview already reported.
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.side_effect = [
            _response(),
            _response(skipped=[SkippedTrack(id="9", reason="file_not_found")]),
        ]

        with patch("rekordbox_edit.cli.convert.confirm", return_value=True):
            result = CliRunner().invoke(convert_command, ["--format-out", "aiff"])

        assert result.exit_code == 0
        warnings = " ".join(str(c) for c in mock_logger.warning.call_args_list)
        assert "source file is gone" in warnings


class TestThreadsFlag:
    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_threads_reaches_the_request(self, _pid, mock_db_class, mock_convert):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--threads", "3", "--yes"]
        )

        assert result.exit_code == 0
        assert mock_convert.call_args.args[1].threads == 3

    @patch("rekordbox_edit.cli.convert.convert")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None)
    def test_omitting_threads_uses_the_conservative_default(
        self, _pid, mock_db_class, mock_convert
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_convert.return_value = _response()

        CliRunner().invoke(convert_command, ["--format-out", "aiff", "--yes"])

        assert mock_convert.call_args.args[1].threads == DEFAULT_THREADS

    def test_zero_threads_is_a_usage_error(self):
        result = CliRunner().invoke(
            convert_command, ["--format-out", "aiff", "--threads", "0", "--yes"]
        )

        assert result.exit_code != 0
