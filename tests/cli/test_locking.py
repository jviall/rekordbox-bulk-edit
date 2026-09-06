"""Tests for the single-writer lock as wired into with_database."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from rekordbox_edit.cli.edit import edit_command
from rekordbox_edit.cli.search import search_command
from tests.test_locking import foreign_holder
from rekordbox_edit.models import (
    EditOp,
    EditResponse,
    EditResult,
    SearchResponse,
    Track,
)


@pytest.fixture(autouse=True)
def mock_rekordbox_not_running():
    with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
        yield


def _response():
    track = Track(ID="1", Title="New", FileNameL="x.wav", FolderPath="/x.wav")
    return EditResponse(
        result=EditResult(
            field="Title",
            dry_run=False,
            edits=[EditOp(id="1", new_value="New", track=track)],
            skipped=[],
        ),
    )


def _search_response():
    track = Track(ID="1", Title="New", FileNameL="x.wav", FolderPath="/x.wav")
    return SearchResponse(tracks=[track])


@pytest.fixture
def library(tmp_path):
    """A stand-in database directory that every command in a test shares."""
    return tmp_path / "rekordbox"


class TestWriteLock:
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_write_command_fails_when_lock_is_held(
        self, mock_db_class, mock_edit, library, caplog
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_edit.return_value = _response()

        with foreign_holder(library, command="convert"):
            result = CliRunner().invoke(edit_command, ["Title", "--replace", "New"])

        assert result.exit_code == 1
        assert "Another rekordbox-edit process" in caplog.text
        assert '"convert"' in caplog.text
        mock_edit.assert_not_called()

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_dry_run_proceeds_while_lock_is_held(
        self, mock_db_class, mock_edit, library
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_edit.return_value = _response()

        with foreign_holder(library, command="convert"):
            result = CliRunner().invoke(
                edit_command, ["Title", "--replace", "New", "--dry-run"]
            )

        assert result.exit_code == 0
        mock_edit.assert_called_once()

    @patch("rekordbox_edit.cli.search.search")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_read_command_proceeds_while_lock_is_held(
        self, mock_db_class, mock_search, library
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_search.return_value = _search_response()

        with foreign_holder(library, command="convert"):
            result = CliRunner().invoke(search_command, ["--title", "x"])

        assert result.exit_code == 0

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_lock_is_released_after_a_successful_run(
        self, mock_db_class, mock_edit, library
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_edit.return_value = _response()

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        with foreign_holder(library, command="convert"):
            pass

    @patch("rekordbox_edit.cli.edit.edit", side_effect=RuntimeError("boom"))
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_lock_is_released_when_the_command_raises(
        self, mock_db_class, mock_edit, library
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        with foreign_holder(library, command="convert"):
            pass


class TestWaitBudget:
    """Interactive runs fail on the spot; --yes runs wait for the lock."""

    @patch("rekordbox_edit.cli._utils.database_lock")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_scripted_run_waits(self, mock_db_class, mock_edit, mock_lock, library):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_edit.return_value = _response()

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        assert mock_lock.call_args.kwargs["timeout"] == 30.0

    @patch("rekordbox_edit.cli._utils.database_lock")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_interactive_run_does_not_wait(
        self, mock_db_class, mock_edit, mock_lock, library
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_edit.return_value = _response()

        CliRunner().invoke(edit_command, ["Title", "--replace", "New"], input="n\n")

        assert mock_lock.call_args.kwargs["timeout"] == 0

    @patch("rekordbox_edit.cli._utils.database_lock")
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_lock_records_the_subcommand_name(
        self, mock_db_class, mock_edit, mock_lock, library
    ):
        mock_db_class.return_value = Mock(session=Mock(), db_directory=library)
        mock_edit.return_value = _response()

        CliRunner().invoke(edit_command, ["Title", "--replace", "New", "--yes"])

        assert mock_lock.call_args.kwargs["command"] == "edit"


class TestBusyTimeout:
    def test_the_driver_supplies_a_busy_timeout_without_help(self, tmp_path):
        # rekordbox-edit used to install this pragma through a connect
        # listener. The DBAPI already sets it from sqlite3.connect's default
        # timeout=5.0, so the listener set a value that was already in effect
        # and was removed. Pinned here because dropping to 0 would quietly
        # take the retry window away.
        from sqlalchemy import create_engine, text

        engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA busy_timeout")).scalar() >= 5000
