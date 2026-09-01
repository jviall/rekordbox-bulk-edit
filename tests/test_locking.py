import json
import logging
import os
from contextlib import contextmanager

import pytest
from filelock import FileLock

from rekordbox_edit import locking
from rekordbox_edit.locking import (
    DatabaseBusyError,
    _holder_path,
    _lock_path,
    database_lock,
)


@contextmanager
def foreign_holder(db_directory, command="convert"):
    """Hold the lock the way a second rekordbox-edit process would.

    A separate FileLock instance takes its own flock, which is what another
    process does at the OS level. database_lock's own instances are per-path
    singletons and so re-enter instead of blocking, which is deliberate but
    makes them useless for simulating contention.
    """
    path = _lock_path(db_directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path))
    lock.acquire(timeout=0)
    _holder_path(path).write_text(
        json.dumps({"pid": os.getpid(), "command": command, "started": "00:00:00"}),
        encoding="utf-8",
    )
    try:
        yield path
    finally:
        lock.release()


class TestLockPath:
    def test_distinct_directories_get_distinct_locks(self):
        assert _lock_path("/a/rekordbox") != _lock_path("/b/rekordbox")

    def test_same_directory_is_stable(self):
        assert _lock_path("/a/rekordbox") == _lock_path("/a/rekordbox")


class TestDatabaseLock:
    def test_another_process_is_refused_while_held(self, tmp_path):
        with foreign_holder(tmp_path):
            with pytest.raises(DatabaseBusyError):
                with database_lock(tmp_path, command="edit", timeout=0):
                    pass

    def test_nesting_within_one_process_re_enters(self, tmp_path):
        # A CLI run holds this across plan and apply while each API call it
        # makes takes it again; only the outermost release frees it.
        with database_lock(tmp_path, command="convert", timeout=0):
            with database_lock(tmp_path, command="convert", timeout=0):
                pass
        with foreign_holder(tmp_path):
            pass  # fully released once the outer block exits

    def test_lock_is_released_on_exit(self, tmp_path):
        with database_lock(tmp_path, command="convert", timeout=0):
            pass
        with database_lock(tmp_path, command="edit", timeout=0):
            pass

    def test_lock_is_released_when_body_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            with database_lock(tmp_path, command="convert", timeout=0):
                raise RuntimeError("boom")
        with database_lock(tmp_path, command="edit", timeout=0):
            pass

    def test_different_directories_do_not_contend(self, tmp_path):
        with database_lock(tmp_path / "a", command="convert", timeout=0):
            with database_lock(tmp_path / "b", command="edit", timeout=0):
                pass

    def test_busy_message_names_the_holder(self, tmp_path):
        with foreign_holder(tmp_path, command="convert"):
            with pytest.raises(DatabaseBusyError) as excinfo:
                with database_lock(tmp_path, command="edit", timeout=0):
                    pass
        message = str(excinfo.value)
        assert f"PID {os.getpid()}" in message
        assert '"convert"' in message

    def test_busy_message_falls_back_when_holder_unreadable(self, tmp_path):
        with foreign_holder(tmp_path) as path:
            _holder_path(path).write_text("not json", encoding="utf-8")
            with pytest.raises(DatabaseBusyError) as excinfo:
                with database_lock(tmp_path, command="edit", timeout=0):
                    pass
        assert "Another rekordbox-edit process" in str(excinfo.value)
        assert "PID" not in str(excinfo.value)

    def test_an_unwritable_holder_record_does_not_cost_the_lock(
        self, tmp_path, monkeypatch, caplog
    ):
        # The sidecar only enriches the busy message, so a filesystem that
        # refuses it must not stop the caller from holding the lock.
        monkeypatch.setattr(
            locking, "_holder_path", lambda path: tmp_path / "absent" / "holder.json"
        )

        held = False
        with caplog.at_level(logging.DEBUG, logger="rekordbox_edit.locking"):
            with database_lock(tmp_path, command="convert", timeout=0):
                held = True

        assert held
        assert "Could not record lock holder" in caplog.text
        # The release path still ran, so the next acquisition succeeds.
        with database_lock(tmp_path, command="edit", timeout=0):
            pass

    def test_holder_payload_records_the_command(self, tmp_path):
        with database_lock(tmp_path, command="import", timeout=0):
            holder = json.loads(
                _holder_path(_lock_path(tmp_path)).read_text(encoding="utf-8")
            )
        assert holder["command"] == "import"
        assert holder["pid"] == os.getpid()
