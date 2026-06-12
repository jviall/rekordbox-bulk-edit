from typing import cast
from unittest.mock import MagicMock

import pytest
from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.models import Track


@pytest.fixture
def mock_db():
    """A mock Rekordbox6Database instance with an active session."""
    db = MagicMock()
    db.session = MagicMock()
    return db


@pytest.fixture()
def make_djmd_content_item():
    """Create a factory that returns a single mock row of the DjmdContent table."""
    ID = 0

    def factory(id: str | None = None, **kwargs) -> DjmdContent:
        nonlocal ID
        id = id or str(ID)

        item_mock = MagicMock()
        # Default every real column to None so bulk-copy in _track_from_content
        # sees a clean row instead of MagicMock placeholders.
        for col in DjmdContent.__table__.columns:
            setattr(item_mock, col.key, None)
        item: DjmdContent = cast(DjmdContent, item_mock)
        item.ID = kwargs.get("ID", id)
        item.Title = kwargs.get("Title", "Test Song")
        item.ArtistID = kwargs.get("ArtistID", "Artist" + str(id))
        item.ArtistName = kwargs.get("ArtistName", "Test Artist")
        item.AlbumID = kwargs.get("AlbumID", "Album" + str(id))
        item.AlbumName = kwargs.get("AlbumName", "Test Album")
        item.FileNameL = kwargs.get("FileNameL", "test-song.wav")
        item.FolderPath = kwargs.get(
            "FolderPath",
            "/super/very/extra/unnecessarily/long/path/to/music/test_track.wav",
        )
        item.SampleRate = kwargs.get("SampleRate", 44100)
        item.BitDepth = kwargs.get("BitDepth", 16)
        item.BitRate = kwargs.get("BitRate", 2113)
        item.FileType = kwargs.get("FileType", 11)
        ID += 1
        return item

    yield factory


@pytest.fixture()
def make_track():
    """Factory that returns a Track with sensible defaults."""

    def factory(**kwargs) -> Track:
        return Track(
            ID=kwargs.get("ID", "0"),
            Title=kwargs.get("Title", "Test Song"),
            ArtistName=kwargs.get("ArtistName", "Test Artist"),
            AlbumName=kwargs.get("AlbumName", "Test Album"),
            FileNameL=kwargs.get("FileNameL", "test-song.wav"),
            FolderPath=kwargs.get(
                "FolderPath",
                "/super/very/extra/unnecessarily/long/path/to/music/test_track.wav",
            ),
            SampleRate=kwargs.get("SampleRate", 44100),
            BitDepth=kwargs.get("BitDepth", 16),
            BitRate=kwargs.get("BitRate", 2113),
            FileType=kwargs.get("FileType", 11),
        )

    return factory
