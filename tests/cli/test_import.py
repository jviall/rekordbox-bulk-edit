"""Tests for cli/import_.py."""

from unittest.mock import Mock, patch

import click
import pytest
from click.testing import CliRunner

from rekordbox_edit.api.import_ import (
    DirectoryConfirmationRequired,
    ImportInputError,
)
from rekordbox_edit.cli.import_ import _add_summary, import_command
from rekordbox_edit.models import (
    ImportOp,
    ImportResponse,
    ImportResult,
    SkippedTrack,
    Track,
)
from rekordbox_edit.utils import UserQuit


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.import_.logger") as mock_log:
        yield mock_log


@pytest.fixture(autouse=True)
def mock_rekordbox_not_running():
    with patch("rekordbox_edit.cli._utils.get_rekordbox_pid", return_value=None):
        yield


@pytest.fixture()
def runner():
    return CliRunner()


def _response(tracks=None, added=None, skipped=None, playlist=None):
    if tracks is None:
        tracks = [Track(ID="1", FileNameL="a.flac", FolderPath="/m/a.flac")]
    if added is None:
        added = [ImportOp(id=t.ID, path=t.FolderPath, action="create") for t in tracks]
    return ImportResponse(
        tracks=tracks,
        result=ImportResult(playlist=playlist, added=added, skipped=skipped or []),
    )


class TestImportCommand:
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_skips_confirmation_and_writes(self, mock_db_class, mock_import):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/a.flac", "--yes"])

        assert result.exit_code == 0
        mock_import.assert_called_once()
        assert mock_import.call_args.kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_dry_run_does_not_write(self, mock_db_class, mock_import):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/a.flac", "--dry-run"])

        assert result.exit_code == 0
        mock_import.assert_called_once()
        assert mock_import.call_args.kwargs["dry_run"] is True

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_scripting_mode_requires_yes_or_dry_run(self, mock_db_class, mock_import):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/a.flac", "--print", "json"])

        assert result.exit_code != 0
        assert "requires --dry-run or --yes" in result.output

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_surfaces_api_input_errors_as_usage_errors(
        self, mock_db_class, mock_import
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = ImportInputError("No playlist named 'Ghost'.")

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--yes", "--to-playlist", "Ghost"]
        )

        assert result.exit_code != 0
        assert "No playlist named" in result.output

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_write_phase_value_error_is_not_converted_to_usage_error(
        self, mock_db_class, mock_import
    ):
        # A ValueError from the write phase (e.g. a race-condition duplicate
        # path from db.add_content) is not bad input; import_tracks already
        # rolls back and logs it before re-raising, so the CLI must not
        # relabel it as a usage mistake.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = ValueError(
            "Track with path '/m/a.flac' already exists in database"
        )

        result = CliRunner().invoke(import_command, ["/m/a.flac", "--yes"])

        assert result.exit_code != 0
        assert not isinstance(result.exception, click.UsageError)

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_with_nothing_to_add_logs_the_same_message_as_interactive(
        self, mock_db_class, mock_import
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = ImportResponse(
            tracks=[], result=ImportResult(playlist=None, added=[], skipped=[])
        )

        with patch("rekordbox_edit.cli.import_.logger") as mock_log:
            result = CliRunner().invoke(import_command, ["/m/a.flac", "--yes"])

        assert result.exit_code == 0
        messages = [c.args[0] for c in mock_log.info.call_args_list]
        assert "Nothing to add." in messages

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_with_nothing_to_add_still_prints_json_envelope(
        self, mock_db_class, mock_import
    ):
        # Scripting output must stay valid JSON even when nothing happened.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = ImportResponse(
            tracks=[], result=ImportResult(playlist=None, added=[], skipped=[])
        )

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--yes", "--print", "json"]
        )

        assert result.exit_code == 0
        import json

        payload = json.loads(result.output.splitlines()[-1])
        assert payload["result"]["added"] == []

    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_prompts_to_walk_a_directory_then_retries_with_the_flag(
        self, mock_db_class, mock_import, _print
    ):
        # Interactive runs confirm instead of demanding --recurse.
        mock_db_class.return_value = Mock(session=Mock())
        response = _response()
        mock_import.side_effect = [
            DirectoryConfirmationRequired(1, 3),
            response,
            response,
        ]

        result = CliRunner().invoke(import_command, ["/m/crate"], input="y\ny\n")

        assert result.exit_code == 0
        assert mock_import.call_count == 3
        # The retried preview and the real write both used recurse=True.
        assert mock_import.call_args_list[1].args[1].recurse is True
        assert mock_import.call_args_list[2].args[1].recurse is True

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_directory_confirm_then_downstream_value_error_becomes_usage_error(
        self, mock_db_class, mock_import
    ):
        # import_tracks checks the recurse gate before resolving the
        # playlist, so confirming the directory walk can still surface a
        # second, unrelated ValueError on the retry. That retry must be
        # guarded the same way the first attempt is.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = [
            DirectoryConfirmationRequired(1, 3),
            ImportInputError("No playlist named 'Ghost'."),
        ]

        result = CliRunner().invoke(
            import_command, ["/m/crate", "--to-playlist", "Ghost"], input="y\n"
        )

        assert result.exit_code != 0
        assert "No playlist named" in result.output
        assert "Traceback" not in result.output
        assert mock_import.call_count == 2

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_dry_run_still_prompts_for_directory_confirmation(
        self, mock_db_class, mock_import
    ):
        # --dry-run only skips the write; the user is still at a terminal,
        # so the directory-walk gate still prompts rather than failing fast.
        mock_db_class.return_value = Mock(session=Mock())
        response = _response()
        mock_import.side_effect = [
            DirectoryConfirmationRequired(1, 3),
            response,
        ]

        result = CliRunner().invoke(
            import_command, ["/m/crate", "--dry-run"], input="y\n"
        )

        assert result.exit_code == 0
        assert mock_import.call_count == 2
        assert mock_import.call_args_list[1].kwargs.get("dry_run") is True
        assert mock_import.call_args_list[1].args[1].recurse is True

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_declining_the_directory_prompt_skips_the_write(
        self, mock_db_class, mock_import
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = DirectoryConfirmationRequired(1, 3)

        result = CliRunner().invoke(import_command, ["/m/crate"], input="n\n")

        assert result.exit_code == 0
        mock_import.assert_called_once()

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_yes_alone_authorizes_a_directory_walk(self, mock_db_class, mock_import):
        # --yes is the only authorization there is, so it has to reach the API
        # as recurse=True; otherwise the gate would raise with nobody to ask.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/crate", "--yes"])

        assert result.exit_code == 0
        assert mock_import.call_args.args[1].recurse is True

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_an_interactive_run_does_not_pre_authorize_the_walk(
        self, mock_db_class, mock_import
    ):
        # Without --yes the prompt is what authorizes it, so the first call
        # must arrive with recurse unset or the gate never fires.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/crate"], input="y\n")

        assert result.exit_code == 0
        assert mock_import.call_args_list[0].args[1].recurse is False

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_a_scripting_dry_run_cannot_prompt_so_it_demands_yes(
        self, mock_db_class, mock_import
    ):
        # The one combination that still reaches the gate without a prompt:
        # a scripting --print satisfies its precondition with --dry-run, so
        # --yes was never given and nothing authorized the walk.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = DirectoryConfirmationRequired(1, 3)

        result = CliRunner().invoke(
            import_command, ["/m/crate", "--dry-run", "--print", "json"]
        )

        assert result.exit_code != 0
        assert "Pass --yes to confirm" in result.output

    @patch("rekordbox_edit.cli.import_.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_quitting_the_directory_prompt_skips_the_write(
        self, mock_db_class, mock_import, _confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = DirectoryConfirmationRequired(1, 3)

        result = CliRunner().invoke(import_command, ["/m/crate"])

        assert result.exit_code == 0
        mock_import.assert_called_once()

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_declining_the_directory_prompt_in_a_dry_run_prints_nothing(
        self, mock_db_class, mock_import
    ):
        # --dry-run takes the early-return branch, which must handle a
        # declined prompt the same way the default flow does.
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.side_effect = DirectoryConfirmationRequired(1, 3)

        result = CliRunner().invoke(
            import_command, ["/m/crate", "--dry-run"], input="n\n"
        )

        assert result.exit_code == 0
        mock_import.assert_called_once()

    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_quitting_the_add_confirmation_skips_the_write(
        self, mock_db_class, mock_import, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        with patch("rekordbox_edit.cli.import_.confirm", side_effect=UserQuit):
            result = CliRunner().invoke(import_command, ["/m/a.flac"])

        assert result.exit_code == 0
        # Only the preview ran; the write call never happened.
        mock_import.assert_called_once()
        assert mock_import.call_args.kwargs["dry_run"] is True

    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.confirm", return_value=True)
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_the_write_pass_applies_the_previewed_ops(
        self, mock_db_class, mock_import, _confirm, _print
    ):
        # Passing ops means no second directory walk, so the recurse gate
        # cannot fire again and nothing created during the prompt joins in.
        mock_db_class.return_value = Mock(session=Mock())
        preview = _response()
        mock_import.side_effect = [preview, _response()]

        result = CliRunner().invoke(import_command, ["/m/crate"])

        assert result.exit_code == 0
        assert mock_import.call_count == 2
        assert mock_import.call_args.kwargs["ops"] == preview.result.added
        assert "dry_run" not in mock_import.call_args.kwargs

    def test_add_summary_leads_with_creates_when_a_batch_does_both(self):
        assert _add_summary(2, 3) == (
            "Add 2 track(s) and place 3 existing track(s) in the playlist"
        )

    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_missing_path_reaches_the_user_without_mocking_the_api(self, mock_db_class):
        # The one case where import_tracks is real: a typo'd path must read as
        # a usage error, not a crash telling the user to file a bug report.
        mock_db_class.return_value = Mock(session=Mock())

        result = CliRunner().invoke(
            import_command, ["/nonexistent/track.flac", "--yes"]
        )

        assert result.exit_code != 0
        assert "Path does not exist" in result.output
        assert "Traceback" not in result.output

    def test_no_interactive_flag_registered(self, runner):
        result = runner.invoke(import_command, ["--help"])
        assert "--interactive" not in result.output

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_print_ids_outputs_ids(self, mock_db_class, mock_import):
        mock_db_class.return_value = Mock(session=Mock())
        track = Track(ID="AAA", FileNameL="a.flac", FolderPath="/m/a.flac")
        mock_import.return_value = _response(
            tracks=[track],
            added=[ImportOp(id="AAA", path="/m/a.flac", action="create")],
        )

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--yes", "--print", "ids"]
        )

        assert result.exit_code == 0
        assert "AAA" in result.output

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_print_json_outputs_envelope(self, mock_db_class, mock_import):
        import json

        mock_db_class.return_value = Mock(session=Mock())
        track = Track(ID="AAA", FileNameL="a.flac", FolderPath="/m/a.flac")
        mock_import.return_value = _response(
            tracks=[track],
            added=[ImportOp(id="AAA", path="/m/a.flac", action="create")],
        )

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--yes", "--print", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output.splitlines()[-1])
        assert payload["result"]["added"] == [
            {"id": "AAA", "path": "/m/a.flac", "action": "create"}
        ]

    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.confirm", return_value=True)
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_previews_then_commits(
        self, mock_db_class, mock_import, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/a.flac"])

        assert result.exit_code == 0
        assert mock_import.call_count == 2  # dry-run preview + real run
        assert mock_import.call_args_list[0].kwargs.get("dry_run") is True
        assert mock_import.call_args_list[1].kwargs.get("dry_run", False) is False

    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.confirm", return_value=False)
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_user_declines_skips_commit(
        self, mock_db_class, mock_import, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/a.flac"])

        assert result.exit_code == 0
        mock_import.assert_called_once()  # only the dry-run preview

    @patch("rekordbox_edit.cli.import_.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_user_quit_skips_commit(
        self, mock_db_class, mock_import, _print, _confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(import_command, ["/m/a.flac"])

        assert result.exit_code == 0
        mock_import.assert_called_once()

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_default_flow_nothing_to_add_exits_cleanly(
        self, mock_db_class, mock_import
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = ImportResponse(
            tracks=[],
            result=ImportResult(
                playlist=None,
                added=[],
                skipped=[SkippedTrack(id="1", reason="already_exists")],
            ),
        )

        result = CliRunner().invoke(import_command, ["/m/a.flac"])

        assert result.exit_code == 0
        mock_import.assert_called_once()

    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_to_playlist_maps_to_playlist_field(self, mock_db_class, mock_import):
        mock_db_class.return_value = Mock(session=Mock())
        mock_import.return_value = _response()

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--yes", "--to-playlist", "My Set"]
        )

        assert result.exit_code == 0
        assert mock_import.call_args.args[1].playlist == "My Set"

    @patch("rekordbox_edit.cli.import_.logger")
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_playlist_only_add_does_not_report_zero_created(
        self, mock_db_class, mock_import, mock_log
    ):
        mock_db_class.return_value = Mock(session=Mock())
        track = Track(ID="1", FileNameL="a.flac", FolderPath="/m/a.flac")
        mock_import.return_value = _response(
            tracks=[track],
            added=[ImportOp(id="1", path="/m/a.flac", action="playlist_add")],
        )

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--yes", "--to-playlist", "Set"]
        )

        assert result.exit_code == 0
        messages = [c.args[0] for c in mock_log.info.call_args_list]
        assert "Placed 1 existing track(s) in the playlist." in messages
        assert not any(m.startswith("Added 0") for m in messages)

    @patch("rekordbox_edit.cli.import_.print_track_info")
    @patch("rekordbox_edit.cli.import_.confirm", return_value=True)
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_playlist_only_add_prompt_leads_with_placement(
        self, mock_db_class, mock_import, mock_confirm, _print
    ):
        mock_db_class.return_value = Mock(session=Mock())
        track = Track(ID="1", FileNameL="a.flac", FolderPath="/m/a.flac")
        mock_import.return_value = _response(
            tracks=[track],
            added=[ImportOp(id="1", path="/m/a.flac", action="playlist_add")],
        )

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "--to-playlist", "Set"]
        )

        assert result.exit_code == 0
        prompt = mock_confirm.call_args_list[0].args[0]
        assert prompt == "Place 1 existing track(s) in the playlist?"
        assert "Add 0" not in prompt

    @patch("rekordbox_edit.cli.import_.logger")
    @patch("rekordbox_edit.cli.import_.import_tracks")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_mixed_create_and_playlist_add_reports_both_counts(
        self, mock_db_class, mock_import, mock_log
    ):
        mock_db_class.return_value = Mock(session=Mock())
        tracks = [
            Track(ID="1", FileNameL="a.flac", FolderPath="/m/a.flac"),
            Track(ID="2", FileNameL="b.flac", FolderPath="/m/b.flac"),
        ]
        mock_import.return_value = _response(
            tracks=tracks,
            added=[
                ImportOp(id="1", path="/m/a.flac", action="create"),
                ImportOp(id="2", path="/m/b.flac", action="playlist_add"),
            ],
        )

        result = CliRunner().invoke(
            import_command, ["/m/a.flac", "/m/b.flac", "--yes", "--to-playlist", "Set"]
        )

        assert result.exit_code == 0
        messages = [c.args[0] for c in mock_log.info.call_args_list]
        assert "Added 1 track(s)." in messages
        assert "Placed 1 existing track(s) in the playlist." in messages
