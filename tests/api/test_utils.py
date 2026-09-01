"""Tests for api/_utils.py."""

import logging
import threading
from unittest.mock import Mock

import pytest
from pyrekordbox import Rekordbox6Database
from sqlalchemy import text

from tests.api.conftest import close_database

from rekordbox_edit.api._utils import (
    _order_tracks_by_op,
    _track_from_content,
    stamp_usns,
)
from rekordbox_edit.models import ConvertOp, Track
from rekordbox_edit.query import require_session


class TestTrackFromContent:
    def test_maps_all_fields(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="ABC123", Title="My Song")
        track = _track_from_content(content)

        assert isinstance(track, Track)
        assert track.ID == "ABC123"
        assert track.Title == "My Song"
        assert track.ArtistName == "Test Artist"
        assert track.FileType == 11

    def test_id_is_always_string(self, make_djmd_content_item):
        content = make_djmd_content_item()
        content.ID = 99
        track = _track_from_content(content)
        assert track.ID == "99"
        assert isinstance(track.ID, str)


class TestOrderTracksByOp:
    def test_orders_tracks_to_match_ops(self, make_djmd_content_item):
        # contents arrive in C,A,B order; ops in A,B,C order
        contents = [
            make_djmd_content_item(ID="C"),
            make_djmd_content_item(ID="A"),
            make_djmd_content_item(ID="B"),
        ]
        ops = [
            ConvertOp(id="A", source_path="/a", output_path="/a.aif"),
            ConvertOp(id="B", source_path="/b", output_path="/b.aif"),
            ConvertOp(id="C", source_path="/c", output_path="/c.aif"),
        ]

        tracks = _order_tracks_by_op(contents, ops)

        assert [t.ID for t in tracks] == ["A", "B", "C"]

    def test_skips_ops_with_no_matching_content(self, make_djmd_content_item):
        contents = [make_djmd_content_item(ID="A")]
        ops = [
            ConvertOp(id="A", source_path="/a", output_path="/a.aif"),
            ConvertOp(id="MISSING", source_path="/x", output_path="/y"),
        ]

        tracks = _order_tracks_by_op(contents, ops)

        assert [t.ID for t in tracks] == ["A"]

    def test_empty_inputs_return_empty(self):
        assert _order_tracks_by_op([], []) == []


_COUNTER = text(
    "SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'"
)


class TestStampUsns:
    def test_stamps_a_contiguous_block_ending_at_the_counter(self, db):
        start = require_session(db).execute(_COUNTER).scalar()
        rows = db.get_content().limit(3).all()

        high = stamp_usns(db, rows)

        assert high == start + 3
        assert [row.rb_local_usn for row in rows] == [start + 1, start + 2, start + 3]

    def test_the_counter_ends_where_the_last_stamp_did(self, db):
        rows = db.get_content().limit(2).all()

        high = stamp_usns(db, rows)
        require_session(db).commit()

        assert require_session(db).execute(_COUNTER).scalar() == high
        assert max(row.rb_local_usn for row in rows) == high

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

            high = stamp_usns(ours, rows)
            require_session(ours).commit()

            assert high == start + 3 + 2
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
