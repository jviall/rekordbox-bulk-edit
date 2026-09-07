"""Tests for the shared-record relation helpers."""

from pyrekordbox.db6 import tables as tb

from rekordbox_edit.api._relations import (
    sweep_orphans,
)


def test_sweep_collects_an_unreferenced_artist(db):
    artist = db.add_artist("RBE Sweep Orphan")
    db.session.flush()
    collected = sweep_orphans(db, {"artist": {str(artist.ID)}})
    assert collected == 1
    assert db.get_artist(ID=artist.ID) is None


def test_sweep_spares_a_referenced_artist(db):
    content = (
        db.session.query(tb.DjmdContent)
        .filter(tb.DjmdContent.ArtistID.isnot(None))
        .first()
    )
    assert content is not None, "fixture library has no track with an artist"
    collected = sweep_orphans(db, {"artist": {str(content.ArtistID)}})
    assert collected == 0
    assert db.get_artist(ID=content.ArtistID) is not None


def test_sweep_reaches_a_fixpoint(db):
    """The divergence from rekordbox: collecting the album must re-examine the
    artist that album's AlbumArtistID pointed at."""
    artist = db.add_artist("RBE Sweep Cascade Artist")
    album = db.add_album("RBE Sweep Cascade Album", artist=artist)
    db.session.flush()
    collected = sweep_orphans(
        db, {"artist": {str(artist.ID)}, "album": {str(album.ID)}}
    )
    assert collected == 2
    assert db.get_album(ID=album.ID) is None
    assert db.get_artist(ID=artist.ID) is None


def test_sweep_never_touches_keys(db):
    key = db.session.query(tb.DjmdKey).first()
    assert key is not None, "fixture library has no keys"
    collected = sweep_orphans(db, {"key": {str(key.ID)}})
    assert collected == 0
    assert db.session.query(tb.DjmdKey).filter_by(ID=key.ID).first() is not None
