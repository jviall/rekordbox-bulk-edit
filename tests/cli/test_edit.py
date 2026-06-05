"""Tests for cli/edit.py."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.api.edit import EditPlan
from rekordbox_edit.args import Track
from rekordbox_edit.cli.edit import edit_command


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.cli.edit.logger") as mock_log:
        yield mock_log


def _make_plan(field="Title", edits=None):
    edits = edits or [(Track(ID="1", Title="Old"), "New")]
    return EditPlan(field=field, edits=edits)


class TestEditCommand:
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.plan_edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_calls_edit_on_confirmation(self, mock_db_class, mock_plan_edit, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan_edit.return_value = _make_plan()
        mock_edit.return_value = Mock(applied=1)

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        assert result.exit_code == 0
        mock_edit.assert_called_once()

    @patch("rekordbox_edit.cli.edit.plan_edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_dry_run_does_not_call_edit(self, mock_db_class, mock_plan_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan_edit.return_value = _make_plan()

        with patch("rekordbox_edit.cli.edit.edit") as mock_edit:
            result = CliRunner().invoke(
                edit_command, ["Title", "--replace", "New", "--dry-run"]
            )

        assert result.exit_code == 0
        mock_edit.assert_not_called()

    @patch("rekordbox_edit.cli.edit.plan_edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_empty_plan_exits_early(self, mock_db_class, mock_plan_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan_edit.return_value = EditPlan(field="Title", edits=[])

        with patch("rekordbox_edit.cli.edit.edit") as mock_edit:
            result = CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        assert result.exit_code == 0
        mock_edit.assert_not_called()

    @patch("rekordbox_edit.cli.edit.plan_edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_value_error_becomes_usage_error(self, mock_db_class, mock_plan_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan_edit.side_effect = ValueError("Found 2 tracks that would be edited")

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code != 0
        assert "Error" in result.output

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli.edit.plan_edit")
    @patch("rekordbox_edit.cli.edit.Rekordbox6Database")
    def test_print_ids_outputs_applied_ids(self, mock_db_class, mock_plan_edit, mock_edit):
        mock_db_class.return_value = Mock(session=Mock())
        mock_plan_edit.return_value = _make_plan(edits=[(Track(ID="AAA"), "New")])
        mock_edit.return_value = Mock(applied=1)

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes", "--print", "ids"]
        )

        assert result.exit_code == 0
        assert "AAA" in result.output
