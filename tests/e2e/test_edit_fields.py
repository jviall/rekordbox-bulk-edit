"""Real-DB integration net for the new edit fields.

Each test copies the committed fixture DB to its own tmp path and drives the
`edit` API against it, so the relational apply and orphan-delete paths are
exercised against a real SQLite database with real relationships. Order-
independent: shares nothing with the ordered journey suite.
"""

import shutil

import pytest
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb

from rekordbox_edit.api.edit import edit
from rekordbox_edit.models import EditRequest

pytestmark = pytest.mark.e2e


@pytest.fixture
def fresh_db(_db_source, tmp_path):
    dst = tmp_path / _db_source.name
    shutil.copy(_db_source, dst)
    return str(dst)


def test_artist_reuse_deletes_orphan(fresh_db):
    db = Rekordbox6Database(fresh_db)
    assert db.session is not None
    before = db.session.query(tb.DjmdArtist).count()

    # Interchange is Gamma's only track; move it to the existing Alpha.
    edit(
        db,
        EditRequest(
            exact_title=["Interchange"], field="ArtistName", replace_value="Alpha"
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert moved.ArtistName == "Alpha"
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Gamma").first() is None
    assert db.session.query(tb.DjmdArtist).count() == before - 1
    db.close()


def test_artist_reassign_keeps_shared_artist(fresh_db):
    db = Rekordbox6Database(fresh_db)
    assert db.session is not None
    before = db.session.query(tb.DjmdArtist).count()

    # Apple Alpha shares Alpha with Wave Alpha, so Alpha survives the move.
    edit(
        db,
        EditRequest(
            exact_title=["Apple Alpha"], field="ArtistName", replace_value="Beta"
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Apple Alpha").one()
    assert moved.ArtistName == "Beta"
    assert db.session.query(tb.DjmdArtist).filter_by(Name="Alpha").first() is not None
    assert db.session.query(tb.DjmdArtist).count() == before
    db.close()


def test_album_reuse_deletes_orphan_and_keeps_album_artist(fresh_db):
    db = Rekordbox6Database(fresh_db)
    assert db.session is not None
    before = db.session.query(tb.DjmdAlbum).count()
    target = db.session.query(tb.DjmdAlbum).filter_by(Name="Lossless Vol 1").first()
    assert target is not None
    album_artist_before = target.AlbumArtistID

    # Interchange is the only track on "AIFF Sampler"; move it to a shared album.
    edit(
        db,
        EditRequest(
            exact_title=["Interchange"],
            field="AlbumName",
            replace_value="Lossless Vol 1",
        ),
    )

    moved = db.session.query(tb.DjmdContent).filter_by(Title="Interchange").one()
    assert moved.AlbumName == "Lossless Vol 1"
    assert db.session.query(tb.DjmdAlbum).filter_by(Name="AIFF Sampler").first() is None
    assert db.session.query(tb.DjmdAlbum).count() == before - 1
    # The reused album's album-artist is left untouched (deliberate divergence).
    after = db.session.query(tb.DjmdAlbum).filter_by(Name="Lossless Vol 1").first()
    assert after is not None
    assert after.AlbumArtistID == album_artist_before
    db.close()


def test_album_create_new_has_no_album_artist(fresh_db):
    db = Rekordbox6Database(fresh_db)
    assert db.session is not None

    # Apple Alpha shares "Apple Lossless" with Apple Beta, so nothing orphans.
    edit(
        db,
        EditRequest(
            exact_title=["Apple Alpha"],
            field="AlbumName",
            replace_value="Fresh Album ZZZ",
        ),
    )

    album = db.session.query(tb.DjmdAlbum).filter_by(Name="Fresh Album ZZZ").first()
    assert album is not None
    moved = db.session.query(tb.DjmdContent).filter_by(Title="Apple Alpha").one()
    assert moved.AlbumID == album.ID
    assert album.AlbumArtistID in (None, "")
    assert album.SearchStr is None
    db.close()
