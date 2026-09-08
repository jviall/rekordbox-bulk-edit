"""Tests for api/_utils.py."""

import logging
import threading
from unittest.mock import Mock, patch

import pytest
from filelock import FileLock, Timeout
from pyrekordbox import Rekordbox6Database
from sqlalchemy import text

from tests.anlz_helpers import UNPARSED_TAG, anlz, path_tag
from tests.api.conftest import close_database

from rekordbox_edit.api._anlz import read_path
from rekordbox_edit.api._utils import (
    _update_anlz_paths,
    reserve_usns,
    stamp_usns,
    track_from_content,
    writing,
)
from rekordbox_edit.errors import DatabaseBusyError, RekordboxRunningError
from rekordbox_edit.locking import _lock_path, database_lock
from rekordbox_edit.models import Track
from rekordbox_edit.query import require_session


class TestTrackFromContent:
    def test_maps_all_fields(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="ABC123", Title="My Song")
        track = track_from_content(content)

        assert isinstance(track, Track)
        assert track.ID == "ABC123"
        assert track.Title == "My Song"
        assert track.ArtistName == "Test Artist"
        assert track.FileType == 11

    def test_id_is_always_string(self, make_djmd_content_item):
        content = make_djmd_content_item()
        content.ID = 99
        track = track_from_content(content)
        assert track.ID == "99"
        assert isinstance(track.ID, str)


_COUNTER = text(
    "SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'"
)


def current_usn(db):
    return db.session.execute(
        text("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'")
    ).scalar()


class TestReserveUsns:
    def test_reserve_usns_advances_the_counter(self, db):
        before = current_usn(db)
        last = reserve_usns(db, 5)
        assert last == before + 5
        assert current_usn(db) == before + 5

    def test_reserve_usns_is_a_noop_for_zero(self, db):
        before = current_usn(db)
        assert reserve_usns(db, 0) is None
        assert current_usn(db) == before


class TestStampUsns:
    def test_stamps_a_contiguous_block_ending_at_the_counter(self, db):
        start = require_session(db).execute(_COUNTER).scalar()
        rows = db.get_content().limit(3).all()

        last_usn = stamp_usns(db, rows)

        assert last_usn == start + 3
        assert [row.rb_local_usn for row in rows] == [start + 1, start + 2, start + 3]

    def test_the_counter_ends_where_the_last_stamp_did(self, db):
        rows = db.get_content().limit(2).all()

        last_usn = stamp_usns(db, rows)
        require_session(db).commit()

        assert require_session(db).execute(_COUNTER).scalar() == last_usn
        assert max(row.rb_local_usn for row in rows) == last_usn

    def test_nothing_to_stamp_leaves_the_counter_alone(self, db):
        start = require_session(db).execute(_COUNTER).scalar()

        assert stamp_usns(db, []) is None
        assert require_session(db).execute(_COUNTER).scalar() == start

    def test_rows_without_the_column_are_ignored(self, db):
        start = require_session(db).execute(_COUNTER).scalar()

        assert stamp_usns(db, [object(), object()]) is None
        assert require_session(db).execute(_COUNTER).scalar() == start

    def test_a_rollback_takes_the_reservation_with_it(self, db):
        # A counter advanced past unstamped rows would hide them from sync.
        start = require_session(db).execute(_COUNTER).scalar()
        rows = db.get_content().limit(2).all()

        stamp_usns(db, rows)
        require_session(db).rollback()

        assert require_session(db).execute(_COUNTER).scalar() == start

    def test_a_missing_counter_stamps_nothing(self, db, caplog):
        require_session(db).execute(
            text("DELETE FROM agentRegistry WHERE registry_id = 'localUpdateCount'")
        )
        rows = db.get_content().limit(2).all()
        before = [row.rb_local_usn for row in rows]

        with caplog.at_level(logging.WARNING, logger="rekordbox_edit.api.usn"):
            assert stamp_usns(db, rows) is None

        assert [row.rb_local_usn for row in rows] == before
        assert "localUpdateCount" in caplog.text

    def test_no_session_raises(self):
        db = Mock(session=None)
        row = Mock(rb_local_usn=1)

        with pytest.raises(RuntimeError, match="No Session"):
            stamp_usns(db, [row])


class TestStampUsnsUnderConcurrency:
    """Rekordbox writes to this counter too, and the advisory lock cannot stop
    it."""

    def test_concurrent_writers_lose_no_increments(self, library):
        rounds, writers = 15, 2

        def worker():
            database = Rekordbox6Database(path=str(library))
            try:
                for _ in range(rounds):
                    row = database.get_content().first()
                    stamp_usns(database, [row])
                    require_session(database).commit()
            finally:
                close_database(database)

        control = Rekordbox6Database(path=str(library))
        start = require_session(control).execute(_COUNTER).scalar()
        close_database(control)

        threads = [threading.Thread(target=worker) for _ in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        after = Rekordbox6Database(path=str(library))
        try:
            assert (
                require_session(after).execute(_COUNTER).scalar()
                == start + rounds * writers
            )
        finally:
            close_database(after)

    def test_an_outside_commit_between_read_and_stamp_is_not_lost(self, library):
        # Opens with a read, as a real command does, then another writer
        # commits before the reservation runs.
        ours = Rekordbox6Database(path=str(library))
        theirs = Rekordbox6Database(path=str(library))
        try:
            start = require_session(ours).execute(_COUNTER).scalar()
            rows = ours.get_content().limit(2).all()

            stamp_usns(theirs, theirs.get_content().limit(3).all())
            require_session(theirs).commit()

            last_usn = stamp_usns(ours, rows)
            require_session(ours).commit()

            assert last_usn == start + 3 + 2
            assert [row.rb_local_usn for row in rows] == [start + 4, start + 5]
        finally:
            close_database(ours)
            close_database(theirs)


class TestDriverTransactionAssumption:
    """The reservation needs no retry loop only because the driver opens no
    transaction for a SELECT. A driver change would reverse that quietly."""

    @staticmethod
    def _dbapi(db):
        return require_session(db).connection().connection.dbapi_connection

    def test_a_read_opens_no_driver_transaction(self, db):
        require_session(db).execute(_COUNTER)

        # SQLAlchemy believes a transaction is open; SQLite does not.
        assert require_session(db).in_transaction() is True
        assert self._dbapi(db).in_transaction is False

    def test_a_write_opens_one(self, db):
        require_session(db).execute(_COUNTER)
        stamp_usns(db, db.get_content().limit(1).all())

        assert self._dbapi(db).in_transaction is True


class TestWriting:
    """The guard every API write enters through."""

    def test_refuses_while_rekordbox_runs(self, tmp_path):
        db = Mock(db_directory=tmp_path)
        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=4321):
            with pytest.raises(RekordboxRunningError, match="4321"):
                with writing(db, "edit"):
                    pass

    def test_holds_the_write_lock_for_the_block(self, tmp_path):
        db = Mock(db_directory=tmp_path)
        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
            with writing(db, "edit"):
                # A separate FileLock instance is what another process's flock
                # looks like, so this is the exclusion that actually matters.
                foreign = FileLock(str(_lock_path(tmp_path)))
                with pytest.raises(Timeout):
                    foreign.acquire(timeout=0.1)

    def test_nests_inside_a_lock_the_caller_already_holds(self, tmp_path):
        # The CLI holds the lock across plan and apply while each API call it
        # makes takes it again.
        db = Mock(db_directory=tmp_path)
        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
            with database_lock(tmp_path, command="convert", timeout=0):
                with writing(db, "convert"):
                    pass

    def test_releases_the_lock_when_the_block_raises(self, tmp_path):
        db = Mock(db_directory=tmp_path)
        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
            with pytest.raises(RuntimeError):
                with writing(db, "edit"):
                    raise RuntimeError("boom")
            with writing(db, "edit"):
                pass

    def test_a_foreign_holder_is_reported_as_busy(self, tmp_path):
        db = Mock(db_directory=tmp_path)
        foreign = FileLock(str(_lock_path(tmp_path)))
        _lock_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        foreign.acquire(timeout=0)
        try:
            with (
                patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None),
                patch("rekordbox_edit.api._utils.SCRIPTED_TIMEOUT", 0),
            ):
                with pytest.raises(DatabaseBusyError):
                    with writing(db, "edit"):
                        pass
        finally:
            foreign.release()


class TestUpdateAnlzPaths:
    """The path rewrite must not disturb anything else in the file: these are
    the only copy of a track's analysis, and tags this codebase cannot parse
    still belong to Rekordbox."""

    @pytest.fixture()
    def analysed(self, tmp_path, make_djmd_content_item):
        """A track whose DAT and EXT files exist on disk, the EXT carrying a
        tag no parser here understands."""
        dat = tmp_path / "ANLZ0000.DAT"
        ext = tmp_path / "ANLZ0000.EXT"
        dat.write_bytes(anlz(path_tag("?/old name.flac")))
        ext.write_bytes(anlz(path_tag("?/old name.flac"), UNPARSED_TAG))

        db = Mock()
        db.get_anlz_paths.return_value = {"DAT": dat, "EXT": ext}
        content = make_djmd_content_item(ID=7)
        content.AnalysisDataPath = "share/PIONEER/USBANLZ/x/ANLZ0000.DAT"
        return db, content, dat, ext

    def test_rewrites_the_path_in_every_analysis_file(self, analysed):
        db, content, dat, ext = analysed

        _update_anlz_paths(db, content, "new song.mp3")

        assert read_path(dat.read_bytes()) == "?/new song.mp3"
        assert read_path(ext.read_bytes()) == "?/new song.mp3"

    def test_preserves_tags_the_parser_does_not_understand(self, analysed):
        db, content, _dat, ext = analysed

        _update_anlz_paths(db, content, "new song.mp3")

        assert UNPARSED_TAG in ext.read_bytes()

    def test_leaves_other_files_alone_when_one_is_malformed(self, analysed):
        db, content, dat, ext = analysed
        ext.write_bytes(b"not an anlz file at all")

        _update_anlz_paths(db, content, "new song.mp3")

        assert read_path(dat.read_bytes()) == "?/new song.mp3"

    def test_skips_a_track_without_analysis(self, make_djmd_content_item):
        db = Mock()
        content = make_djmd_content_item(ID=7)  # AnalysisDataPath defaults to None

        _update_anlz_paths(db, content, "new.mp3")

        db.get_anlz_paths.assert_not_called()

    def test_survives_a_missing_analysis_directory(self, analysed, caplog):
        """A row can name an analysis directory that was never created.
        pyrekordbox's get_anlz_paths scans that directory, so it raises rather
        than returning nothing, and an edit pass must not die on the row."""
        db, content, _dat, _ext = analysed
        db.get_anlz_paths.side_effect = FileNotFoundError(
            2, "The system cannot find the path specified", str(content.AnalysisDataPath)
        )

        _update_anlz_paths(db, content, "new song.mp3")

        assert "analysis directory" in caplog.text

    def test_skips_an_analysis_file_that_does_not_exist(self, analysed, tmp_path):
        db, content, dat, _ext = analysed
        db.get_anlz_paths.return_value = {"DAT": dat, "EXT": tmp_path / "absent.EXT"}

        _update_anlz_paths(db, content, "new song.mp3")

        assert read_path(dat.read_bytes()) == "?/new song.mp3"
