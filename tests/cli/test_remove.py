"""Tests for cli/remove.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli._utils import UserQuit
from rekordbox_edit.cli.remove import remove_command
from rekordbox_edit.models import (
    RemoveOp,
    RemoveResponse,
    RemoveResult,
    Track,
)


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.remove.logger") as mock_log:
        yield mock_log


def _response(count=1, skipped=None, orphans=0, source_deleted=False, dry_run=False):
    removed = [
        RemoveOp(
            id=str(i),
            track=Track(ID=str(i), FileNameL=f"t{i}.mp3", FolderPath=f"/t{i}.mp3"),
            source_deleted=source_deleted,
        )
        for i in range(count)
    ]
    return RemoveResponse(
        result=RemoveResult(
            dry_run=dry_run,
            removed=removed,
            skipped=skipped or [],
            deleted_relatives=orphans,
        )
    )


def _defaults_by_prompt(mock_confirm):
    """Map each prompt's text to the `default` it was asked with."""
    return {
        call.args[0]: call.kwargs.get("default") for call in mock_confirm.call_args_list
    }


class TestRemoveCommand:
    @patch("rekordbox_edit.cli.remove.confirm", return_value=True)
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_source_prompt_defaults_to_no(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        """The prompt offers a destructive step the user did not ask for, so it
        matches convert's --overwrite prompt rather than its apply
        confirmation."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(remove_command, ["--title", "x"])

        assert result.exit_code == 0
        defaults = _defaults_by_prompt(mock_confirm)
        source_prompt = next(p for p in defaults if "source file" in p)
        assert defaults[source_prompt] is False

    @patch("rekordbox_edit.cli.remove.confirm", return_value=True)
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_removal_confirmation_defaults_to_yes(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        """Applying what the user invoked, so it matches edit and convert."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(remove_command, ["--title", "x"])

        assert result.exit_code == 0
        defaults = _defaults_by_prompt(mock_confirm)
        apply_prompt = next(p for p in defaults if p.startswith("Remove "))
        assert defaults[apply_prompt] is True

    @patch("rekordbox_edit.cli.remove.confirm", return_value=True)
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_delete_source_flag_suppresses_the_prompt(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response(source_deleted=True)

        result = CliRunner().invoke(remove_command, ["--title", "x", "--delete-source"])

        assert result.exit_code == 0
        assert not any("source file" in p for p in _defaults_by_prompt(mock_confirm))

    @patch("rekordbox_edit.cli.remove.confirm")
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_scripting_mode_never_prompts(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        """No prompt can be shown, so --delete-source is the only route to
        deleting sources."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(
            remove_command, ["--title", "x", "--yes", "--print", "ids"]
        )

        assert result.exit_code == 0
        mock_confirm.assert_not_called()
        assert mock_remove.call_args.kwargs.get("ops") is None

    @patch("rekordbox_edit.cli.remove.confirm", return_value=False)
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_declining_the_confirmation_removes_nothing(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(remove_command, ["--title", "x"])

        assert result.exit_code == 0
        # Only the dry-run preview ran; nothing was applied.
        assert mock_remove.call_count == 1
        assert mock_remove.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.remove.confirm")
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_interactive_applies_only_the_confirmed_tracks(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        """The one path where the answers do not map onto the whole preview, so
        a mistake here removes a track the user declined."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response(count=3)
        # t0 yes, t1 no, t2 yes, then no to deleting the sources.
        mock_confirm.side_effect = [True, False, True, False]

        result = CliRunner().invoke(remove_command, ["--title", "x", "--interactive"])

        assert result.exit_code == 0
        assert [op.id for op in mock_remove.call_args.kwargs["ops"]] == ["0", "2"]
        # The per-track prompts replace the bulk one rather than adding to it.
        assert not any(
            p.startswith("Remove 2") for p in _defaults_by_prompt(mock_confirm)
        )
        assert mock_remove.call_args.args[1].delete_source is False

    @patch("rekordbox_edit.cli.remove.confirm")
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_quitting_the_interactive_loop_keeps_the_earlier_answers(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        """Quitting stops the questions rather than discarding the answers
        already given, so t0 is still removed and t2 is never asked about."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response(count=3)
        # t0 yes, quit at t1, then no to deleting the sources.
        mock_confirm.side_effect = [True, UserQuit, False]

        result = CliRunner().invoke(remove_command, ["--title", "x", "--interactive"])

        assert result.exit_code == 0
        assert [op.id for op in mock_remove.call_args.kwargs["ops"]] == ["0"]
        assert not any("t2.mp3" in p for p in _defaults_by_prompt(mock_confirm))

    @patch("rekordbox_edit.cli.remove.confirm")
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_declining_every_track_removes_nothing(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        """An empty selection cancels rather than falling through to a removal
        with no ops, which would report success having done nothing."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response(count=3)
        mock_confirm.side_effect = [False, False, False]

        result = CliRunner().invoke(remove_command, ["--title", "x", "--interactive"])

        assert result.exit_code == 0
        assert mock_remove.call_count == 1
        assert mock_remove.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.remove.confirm", side_effect=UserQuit)
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_quitting_the_confirmation_removes_nothing(
        self, _pid, mock_db_class, mock_remove, _confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(remove_command, ["--title", "x"])

        assert result.exit_code == 0
        assert mock_remove.call_count == 1
        assert mock_remove.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.remove.confirm", side_effect=[True, UserQuit])
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_quitting_the_source_prompt_abandons_the_removal(
        self, _pid, mock_db_class, mock_remove, _confirm
    ):
        """The source prompt comes after the removal is confirmed, so quitting
        there abandons a removal the user already said yes to rather than
        applying it with the sources kept."""
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(remove_command, ["--title", "x"])

        assert result.exit_code == 0
        assert mock_remove.call_count == 1
        assert mock_remove.call_args.kwargs.get("dry_run") is True

    @patch("rekordbox_edit.cli.remove.confirm", return_value=True)
    @patch("rekordbox_edit.cli.remove.remove")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    @patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None)
    def test_dry_run_applies_nothing(
        self, _pid, mock_db_class, mock_remove, mock_confirm
    ):
        mock_db_class.return_value = Mock(session=Mock())
        mock_remove.return_value = _response()

        result = CliRunner().invoke(remove_command, ["--title", "x", "--dry-run"])

        assert result.exit_code == 0
        mock_confirm.assert_not_called()
        assert mock_remove.call_args.kwargs.get("dry_run") is True
