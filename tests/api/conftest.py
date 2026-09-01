"""Fixtures backed by the committed Rekordbox database.

Most API tests mock the database away. USN stamping cannot be tested that way:
it turns on SQLite's behavior under a concurrent writer.
"""

import shutil
from pathlib import Path

import pytest
from pyrekordbox import Rekordbox6Database

FIXTURE = Path(__file__).parent.parent / "e2e/fixtures/macos/master.6.8.6.db"


def close_database(database: Rekordbox6Database) -> None:
    """Close a database and release its pooled connections.

    Rekordbox6Database.close() closes the session but leaves the engine's pool
    holding the file open, which Windows will not let anyone delete.
    """
    database.close()
    database.engine.dispose()


@pytest.fixture
def library(tmp_path):
    """A throwaway copy of the committed fixture database.

    Nothing is cleaned up here: tmp_path is unique per test, so the WAL
    sidecars cannot carry state into another one, and pytest reaps the
    directory itself.
    """
    if not FIXTURE.is_file():
        pytest.skip(f"fixture database missing: {FIXTURE}")
    path = tmp_path / FIXTURE.name
    shutil.copy(FIXTURE, path)
    return path


@pytest.fixture
def db(library):
    database = Rekordbox6Database(path=str(library))
    yield database
    close_database(database)
