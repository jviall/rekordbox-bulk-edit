from unittest.mock import Mock, patch

import click
import pytest

from rekordbox_edit._click import PrintChoice
from rekordbox_edit.api.convert import ConvertPlan
from rekordbox_edit.api.edit import EditPlan
from rekordbox_edit.cli._utils import (
    _confirm_converts,
    _confirm_edits,
    _handle_stdin,
    _interactive_filter_converts,
    _interactive_filter_edits,
    _validate_scripting_preconditions,
)
from rekordbox_edit.models import Track
from rekordbox_edit.utils import UserQuit


def _edit_plan(edits=None):
    edits = edits or [
        (Track(ID="1", Title="Old", FileNameL="x.wav", FolderPath="/x.wav"), "New")
    ]
    return EditPlan(field="Title", edits=edits)


def _convert_plan(files=None):
    return ConvertPlan(
        files=files or [Track(ID="1", FileNameL="track.wav", FolderPath="/track.wav")],
        skipped=[],
        should_delete=True,
        format_out="aiff",
    )


class TestHandleStdin:
    def test_returns_false_when_tty(self):
        args = Mock()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = _handle_stdin(args)
        assert result is False

    def test_appends_ids_from_piped_stdin(self):
        args = Mock(track_ids=["existing"])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = b"AAA BBB"
            result = _handle_stdin(args)
        assert result is True
        assert args.track_ids == ["existing", "AAA", "BBB"]

    def test_strips_bom_from_piped_stdin(self):
        args = Mock(track_ids=[])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = bytes([0xEF, 0xBB, 0xBF]) + b"AAA BBB"
            result = _handle_stdin(args)
        assert result is True
        assert args.track_ids == ["AAA", "BBB"]

    def test_empty_piped_stdin_returns_false(self):
        args = Mock(track_ids=[])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = b"  "
            result = _handle_stdin(args)
        assert result is False
        assert args.track_ids == []

    def test_bom_only_piped_stdin_returns_false(self):
        args = Mock(track_ids=[])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = bytes([0xEF, 0xBB, 0xBF])
            result = _handle_stdin(args)
        assert result is False
        assert args.track_ids == []


class TestValidateScriptingPreconditions:
    def test_scripting_mode_without_confirmation_flag_raises(self):
        args = Mock(dry_run=False, yes=False)
        with pytest.raises(click.UsageError):
            _validate_scripting_preconditions(PrintChoice.IDS, args, piped_stdin=False)

    def test_scripting_mode_with_yes_does_not_raise(self):
        args = Mock(dry_run=False, yes=True)
        _validate_scripting_preconditions(PrintChoice.IDS, args, piped_stdin=False)

    def test_scripting_mode_with_dry_run_does_not_raise(self):
        args = Mock(dry_run=True, yes=False)
        _validate_scripting_preconditions(PrintChoice.SILENT, args, piped_stdin=False)

    def test_piped_stdin_without_confirmation_flag_raises(self):
        args = Mock(dry_run=False, yes=False)
        with pytest.raises(click.UsageError, match="Piping"):
            _validate_scripting_preconditions(None, args, piped_stdin=True)

    def test_piped_stdin_with_yes_does_not_raise(self):
        args = Mock(dry_run=False, yes=True)
        _validate_scripting_preconditions(None, args, piped_stdin=True)

    def test_normal_mode_no_stdin_does_not_raise(self):
        args = Mock(dry_run=False, yes=False)
        _validate_scripting_preconditions(None, args, piped_stdin=False)


class TestConfirmEdits:
    def test_yes_returns_plan_immediately(self):
        plan = _edit_plan()
        args = Mock(yes=True, interactive=False)
        assert _confirm_edits(plan, args) is plan

    def test_interactive_delegates_to_filter(self):
        plan = _edit_plan()
        args = Mock(yes=False, interactive=True)
        with patch(
            "rekordbox_edit.cli._utils._interactive_filter_edits", return_value=plan
        ) as mock_filter:
            result = _confirm_edits(plan, args)
        mock_filter.assert_called_once_with(plan)
        assert result is plan

    def test_user_declines_returns_none(self):
        args = Mock(yes=False, interactive=False)
        with patch("rekordbox_edit.cli._utils.confirm", return_value=False):
            result = _confirm_edits(_edit_plan(), args)
        assert result is None

    def test_user_quit_returns_none(self):
        args = Mock(yes=False, interactive=False)
        with patch("rekordbox_edit.cli._utils.confirm", side_effect=UserQuit):
            result = _confirm_edits(_edit_plan(), args)
        assert result is None

    def test_user_confirms_returns_plan(self):
        plan = _edit_plan()
        args = Mock(yes=False, interactive=False)
        with patch("rekordbox_edit.cli._utils.confirm", return_value=True):
            result = _confirm_edits(plan, args)
        assert result is plan


class TestInteractiveFilterEdits:
    def test_includes_confirmed_tracks_excludes_declined(self):
        track1 = Track(ID="1", Title="A", FileNameL="a.wav", FolderPath="/a.wav")
        track2 = Track(ID="2", Title="B", FileNameL="b.wav", FolderPath="/b.wav")
        plan = EditPlan(field="Title", edits=[(track1, "X"), (track2, "Y")])

        with patch("rekordbox_edit.cli._utils.confirm", side_effect=[True, False]):
            result = _interactive_filter_edits(plan)

        assert len(result.edits) == 1
        assert result.edits[0][0].ID == "1"

    def test_user_quit_stops_iteration_early(self):
        track1 = Track(ID="1", FileNameL="a.wav", FolderPath="/a.wav")
        track2 = Track(ID="2", FileNameL="b.wav", FolderPath="/b.wav")
        plan = EditPlan(field="Title", edits=[(track1, "X"), (track2, "Y")])

        with patch("rekordbox_edit.cli._utils.confirm", side_effect=UserQuit):
            result = _interactive_filter_edits(plan)

        assert result.edits == []


class TestConfirmConverts:
    def test_yes_returns_plan_immediately(self):
        plan = _convert_plan()
        args = Mock(yes=True, interactive=False)
        assert _confirm_converts(plan, args) is plan

    def test_interactive_delegates_to_filter(self):
        plan = _convert_plan()
        args = Mock(yes=False, interactive=True)
        with patch(
            "rekordbox_edit.cli._utils._interactive_filter_converts", return_value=plan
        ) as mock_filter:
            result = _confirm_converts(plan, args)
        mock_filter.assert_called_once_with(plan)
        assert result is plan

    def test_user_declines_returns_none(self):
        args = Mock(yes=False, interactive=False)
        with patch("rekordbox_edit.cli._utils.confirm", return_value=False):
            result = _confirm_converts(_convert_plan(), args)
        assert result is None

    def test_user_quit_returns_none(self):
        args = Mock(yes=False, interactive=False)
        with patch("rekordbox_edit.cli._utils.confirm", side_effect=UserQuit):
            result = _confirm_converts(_convert_plan(), args)
        assert result is None

    def test_user_confirms_returns_plan(self):
        plan = _convert_plan()
        args = Mock(yes=False, interactive=False)
        with patch("rekordbox_edit.cli._utils.confirm", return_value=True):
            result = _confirm_converts(plan, args)
        assert result is plan


class TestInteractiveFilterConverts:
    def test_includes_confirmed_tracks_excludes_declined(self):
        track1 = Track(ID="1", FileNameL="a.wav", FolderPath="/a.wav")
        track2 = Track(ID="2", FileNameL="b.wav", FolderPath="/b.wav")
        plan = _convert_plan([track1, track2])

        with patch("rekordbox_edit.cli._utils.confirm", side_effect=[True, False]):
            result = _interactive_filter_converts(plan)

        assert len(result.files) == 1
        assert result.files[0].ID == "1"

    def test_user_quit_stops_iteration_early(self):
        track1 = Track(ID="1", FileNameL="a.wav", FolderPath="/a.wav")
        plan = _convert_plan([track1])

        with patch("rekordbox_edit.cli._utils.confirm", side_effect=UserQuit):
            result = _interactive_filter_converts(plan)

        assert result.files == []

    def test_preserves_plan_metadata(self):
        plan = ConvertPlan(
            files=[Track(ID="1", FileNameL="a.wav", FolderPath="/a.wav")],
            skipped=[Track(ID="2", FileNameL="b.wav", FolderPath="/b.wav")],
            should_delete=False,
            format_out="mp3",
        )
        with patch("rekordbox_edit.cli._utils.confirm", return_value=True):
            result = _interactive_filter_converts(plan)

        assert result.should_delete is False
        assert result.format_out == "mp3"
        assert result.skipped == plan.skipped
