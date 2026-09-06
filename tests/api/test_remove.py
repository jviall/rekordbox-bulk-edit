"""Tests for the remove API."""

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from pyrekordbox.db6 import tables as tb
from sqlalchemy import text

from rekordbox_edit.api._remove import (
    _content_child_tables,
    _remove_on_disk_artifacts,
    _sweep_orphans,
    remove,
    remove_analysis_files,
    remove_artwork_files,
)
from rekordbox_edit.models import RemoveOp, RemoveRequest


def current_usn(db):
    return db.session.execute(
        text("SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'")
    ).scalar()


def test_child_tables_include_the_cloud_sync_tables():
    """A hand-written list omitted these two during the research, and the
    omission is invisible until a dangling row causes a problem elsewhere."""
    found = set(_content_child_tables())
    assert tb.ContentCue in found
    assert tb.ContentFile in found


def test_child_tables_cover_the_familiar_ones():
    found = set(_content_child_tables())
    for table in (
        tb.DjmdCue,
        tb.DjmdSongPlaylist,
        tb.DjmdSongMyTag,
        tb.DjmdMixerParam,
        tb.DjmdSongHistory,
    ):
        assert table in found


def test_child_tables_exclude_the_content_table_itself():
    assert tb.DjmdContent not in _content_child_tables()


def test_sweep_collects_an_unreferenced_artist(db):
    artist = db.add_artist("RBE Sweep Orphan")
    db.session.flush()
    collected = _sweep_orphans(db, {"artist": {str(artist.ID)}})
    assert collected == 1
    assert db.get_artist(ID=artist.ID) is None


def test_sweep_spares_a_referenced_artist(db):
    content = (
        db.session.query(tb.DjmdContent)
        .filter(tb.DjmdContent.ArtistID.isnot(None))
        .first()
    )
    assert content is not None, "fixture library has no track with an artist"
    collected = _sweep_orphans(db, {"artist": {str(content.ArtistID)}})
    assert collected == 0
    assert db.get_artist(ID=content.ArtistID) is not None


def test_sweep_reaches_a_fixpoint(db):
    """The divergence from rekordbox: collecting the album must re-examine the
    artist that album's AlbumArtistID pointed at."""
    artist = db.add_artist("RBE Sweep Cascade Artist")
    album = db.add_album("RBE Sweep Cascade Album", artist=artist)
    db.session.flush()
    collected = _sweep_orphans(
        db, {"artist": {str(artist.ID)}, "album": {str(album.ID)}}
    )
    assert collected == 2
    assert db.get_album(ID=album.ID) is None
    assert db.get_artist(ID=artist.ID) is None


def test_sweep_never_touches_keys(db):
    key = db.session.query(tb.DjmdKey).first()
    assert key is not None, "fixture library has no keys"
    collected = _sweep_orphans(db, {"key": {str(key.ID)}})
    assert collected == 0
    assert db.session.query(tb.DjmdKey).filter_by(ID=key.ID).first() is not None


@pytest.fixture
def share(tmp_path):
    """A share tree shaped like rekordbox's, with one analysed track in it."""
    root = tmp_path / "share"
    anlz = root / "PIONEER/USBANLZ/1c0/012d4-4636-45c1-9f09-b22809858a48"
    art = root / "PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48"
    anlz.mkdir(parents=True)
    art.mkdir(parents=True)
    (anlz / "ANLZ0000.DAT").write_bytes(b"dat")
    (anlz / "ANLZ0000.EXT").write_bytes(b"ext")
    for name in ("artwork.jpg", "artwork_m.jpg", "artwork_s.jpg"):
        (art / name).write_bytes(b"jpg")
    return root


@pytest.fixture
def share_db(share):
    """A mock database exposing only what the file helpers touch."""
    from unittest.mock import MagicMock

    db = MagicMock()
    db.share_directory = share
    db.get_anlz_dir.side_effect = lambda content: (
        share / Path(content.AnalysisDataPath.strip("\\/")).parent
    )
    return db


ANLZ_PATH = "/PIONEER/USBANLZ/1c0/012d4-4636-45c1-9f09-b22809858a48/ANLZ0000.DAT"
ART_PATH = "/PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48/artwork.jpg"


def test_analysis_directory_and_prefix_are_removed(share_db, share):
    remove_analysis_files(share_db, ANLZ_PATH)
    assert not (share / "PIONEER/USBANLZ/1c0").exists()


def test_empty_analysis_path_never_touches_the_share_root(share_db, share, caplog):
    """The landmine: get_anlz_dir on an empty AnalysisDataPath resolves to the
    share root, so a recursive delete there would destroy the whole library.

    Asserts on the debug log rather than only the surviving tree, so the test
    distinguishes the emptiness guard firing from containment (or anything
    else downstream) happening to save the fixture instead.
    """
    with caplog.at_level(logging.DEBUG, logger="rekordbox_edit.api._remove"):
        remove_analysis_files(share_db, "")
    assert "no analysis to remove" in caplog.text
    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger="rekordbox_edit.api._remove"):
        remove_analysis_files(share_db, None)
    assert "no analysis to remove" in caplog.text

    assert share.exists()
    assert (share / "PIONEER/USBANLZ/1c0/012d4-4636-45c1-9f09-b22809858a48").exists()
    assert (share / "PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48").exists()


def test_shallow_analysis_path_is_refused(share_db, share, caplog):
    """A malformed AnalysisDataPath shallower than PIONEER/USBANLZ/<xxx>/<uuid>
    resolves to an ancestor directory shared by every other track's analysis
    (or, one level shallower still, by every track's analysis AND artwork).
    Corrupt, truncated, or foreign-tool-written data could produce this; real
    rekordbox never does. Either way the depth check must refuse it rather
    than rmtree an ancestor tier."""
    with caplog.at_level(logging.WARNING, logger="rekordbox_edit.api._remove"):
        remove_analysis_files(share_db, "/PIONEER/USBANLZ/x.DAT")
    assert "did not have the expected" in caplog.text
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="rekordbox_edit.api._remove"):
        remove_analysis_files(share_db, "/PIONEER/x.DAT")
    assert "did not have the expected" in caplog.text

    assert share.exists()
    assert (share / "PIONEER/USBANLZ/1c0/012d4-4636-45c1-9f09-b22809858a48").exists()
    assert (share / "PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48").exists()


def test_artwork_files_and_directory_are_removed(share_db, share):
    remove_artwork_files(share_db, ART_PATH)
    assert not (share / "PIONEER/Artwork/1c0").exists()


def test_empty_image_path_never_touches_the_share_root(share_db, share, caplog):
    """Asserts on the debug log rather than only the surviving tree, so the
    test distinguishes the emptiness guard firing from containment (which
    would resolve an empty ImagePath to db_directory, not the share root)
    happening to save the fixture instead.
    """
    with caplog.at_level(logging.DEBUG, logger="rekordbox_edit.api._remove"):
        remove_artwork_files(share_db, "")
    assert "no artwork to remove" in caplog.text
    caplog.clear()

    with caplog.at_level(logging.DEBUG, logger="rekordbox_edit.api._remove"):
        remove_artwork_files(share_db, None)
    assert "no artwork to remove" in caplog.text

    assert share.exists()
    assert (share / "PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48").exists()


def test_shallow_artwork_path_is_refused(share_db, share, caplog):
    """A malformed ImagePath shallower than PIONEER/Artwork/<xxx>/<uuid>
    resolves to an ancestor directory shared by every other track's artwork,
    or, one level shallower still, to a Rekordbox-managed file that has
    nothing to do with artwork at all, like Rekordbox's own playlist export.
    Corrupt, truncated, or foreign-tool-written data could produce this
    shape; real rekordbox never does. Either way the depth check must refuse
    it rather than delete a file it does not own."""
    playlist_file = share / "PIONEER/masterPlaylists6.xml"
    playlist_file.write_bytes(b"<playlists/>")

    with caplog.at_level(logging.WARNING, logger="rekordbox_edit.api._remove"):
        remove_artwork_files(share_db, "/PIONEER/masterPlaylists6.xml")
    assert "did not have the expected" in caplog.text

    assert playlist_file.exists()
    assert (share / "PIONEER").is_dir()


def test_artwork_outside_the_share_tree_is_skipped(share_db, tmp_path):
    """A cover.jpg in the user's own music folder is not ours to delete, and no
    reference count would catch it: one imported track from an album folder has
    exactly one referent."""
    outside = tmp_path / "music/Some Album/cover.jpg"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"jpg")
    remove_artwork_files(share_db, "/../music/Some Album/cover.jpg")
    assert outside.exists()


def test_analysis_outside_the_share_tree_is_skipped(share_db, tmp_path, caplog):
    """The counterpart to the artwork check above. A stored path that walks out
    of the share tree names something rekordbox does not manage, and a
    recursive delete there would take the user's own files with it."""
    outside = tmp_path / "music/Some Album/anlz"
    outside.mkdir(parents=True)
    (outside / "ANLZ0000.DAT").write_bytes(b"dat")

    with caplog.at_level(logging.WARNING, logger="rekordbox_edit.api._remove"):
        remove_analysis_files(share_db, "/../music/Some Album/anlz/ANLZ0000.DAT")

    assert "Refusing to delete outside the share tree" in caplog.text
    assert (outside / "ANLZ0000.DAT").exists()


@pytest.mark.parametrize("failing", ["analysis", "artwork"])
def test_file_work_warns_rather_than_raising(share_db, failing, caplog, monkeypatch):
    """The database write has already committed by the time this runs, so an
    escaping exception would report a failed write for one that landed. A
    malformed stored path raises ValueError from Path.resolve() rather than
    OSError, which is why both handlers catch Exception."""
    monkeypatch.setattr(
        f"rekordbox_edit.api._remove.remove_{failing}_files",
        Mock(side_effect=ValueError("embedded NUL")),
    )

    with caplog.at_level(logging.WARNING, logger="rekordbox_edit.api._remove"):
        deleted = _remove_on_disk_artifacts(
            [
                {
                    "id": "7",
                    "analysis_data_path": ANLZ_PATH,
                    "image_path": ART_PATH,
                    "folder_path": None,
                    "other_referents": False,
                }
            ],
            share_db,
            delete_source=False,
        )

    assert deleted == set()
    assert f"could not clean up {failing} files for track 7" in caplog.text


def test_artwork_with_another_referent_is_kept(share_db, share):
    _remove_on_disk_artifacts(
        [
            {
                "id": "1",
                "analysis_data_path": None,
                "image_path": ART_PATH,
                "folder_path": None,
                "other_referents": True,
            }
        ],
        share_db,
        delete_source=False,
    )
    art = share / "PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48"
    assert (art / "artwork.jpg").exists()


def test_unexpected_file_in_the_artwork_directory_stops_the_cleanup(share_db, share):
    """rmdir rather than a recursive delete, so a stranger survives."""
    art = share / "PIONEER/Artwork/1c0/012d4-4636-45c1-9f09-b22809858a48"
    (art / "notes.txt").write_bytes(b"mine")
    remove_artwork_files(share_db, ART_PATH)
    assert not (art / "artwork.jpg").exists()
    assert (art / "notes.txt").exists()


def _any_track_id(db):
    content = db.session.query(tb.DjmdContent).first()
    assert content is not None, "fixture library is empty"
    return str(content.ID)


def test_dry_run_touches_neither_the_usn_counter_nor_any_file(db, tmp_path):
    track_id = _any_track_id(db)
    before_usn = current_usn(db)
    content = db.get_content(ID=track_id)
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    content.FolderPath = str(audio)
    db.session.flush()

    response = remove(
        db, RemoveRequest(track_id=[track_id], delete_source=True), dry_run=True
    )

    assert [op.id for op in response.result.removed] == [track_id]
    assert db.get_content(ID=track_id) is not None
    assert current_usn(db) == before_usn
    assert audio.exists()
    assert response.result.deleted_relatives == 0


def _track_with_children(db):
    """A track that actually occupies several ContentID tables.

    Picking an arbitrary row would let this test pass against a track with no
    child rows at all, which proves nothing about the sweep.
    """
    tables = _content_child_tables()
    for content in db.session.query(tb.DjmdContent).all():
        occupied = sum(
            1
            for table in tables
            if db.session.query(table)
            .filter(table.__table__.c.ContentID == content.ID)
            .first()
            is not None
        )
        if occupied >= 2:
            return content, occupied
    pytest.skip("fixture library has no track occupying two child tables")


def test_remove_deletes_the_row_and_its_children(db):
    content, occupied = _track_with_children(db)
    track_id = str(content.ID)
    assert occupied >= 2

    remove(db, RemoveRequest(track_id=[track_id]))

    assert db.get_content(ID=track_id) is None
    for table in _content_child_tables():
        remaining = (
            db.session.query(table)
            .filter(table.__table__.c.ContentID == track_id)
            .count()
        )
        assert remaining == 0, f"{table.__tablename__} still references the track"


def test_removed_track_is_reported_as_it_stood(db):
    content = db.session.query(tb.DjmdContent).first()
    track_id, title = str(content.ID), content.Title
    response = remove(db, RemoveRequest(track_id=[track_id]))
    assert response.tracks[0].ID == track_id
    assert response.tracks[0].Title == title


def test_remove_advances_the_usn_counter(db):
    # At least one for the DjmdContent row; the first fixture row may also
    # carry child rows of its own, which reserve further USNs -- see
    # test_usn_counter_advances_past_every_deleted_child_row for that case
    # pinned precisely.
    before = current_usn(db)
    remove(db, RemoveRequest(track_id=[_any_track_id(db)]))
    assert current_usn(db) >= before + 1


def test_usn_counter_advances_past_every_deleted_child_row(db):
    """A track occupying two child tables must reserve more than one USN: one
    for the DjmdContent row, and at least one per child row deleted alongside
    it. Reserving only for the DjmdContent row would reuse a stamp, which
    hides a row from a syncing peer -- the dangerous direction per
    research/remove-track-impact/decisions/remove-command-behavior.md."""
    content, occupied = _track_with_children(db)
    track_id = str(content.ID)
    before = current_usn(db)

    remove(db, RemoveRequest(track_id=[track_id]))

    assert current_usn(db) >= before + 1 + occupied


def test_a_vanished_row_is_skipped_not_crashed(db, make_track):
    ghost = RemoveOp(id="99999999", track=make_track(ID="99999999"))
    response = remove(
        db,
        RemoveRequest(
            title=["x"],
        ),
        ops=[ghost],
    )
    assert response.result.removed == []
    assert [s.reason for s in response.result.skipped] == ["db_or_fs_changed"]


def test_duplicate_ops_are_removed_once(db, make_track):
    track_id = _any_track_id(db)
    track = make_track(ID=track_id)
    dup = [RemoveOp(id=track_id, track=track), RemoveOp(id=track_id, track=track)]

    response = remove(
        db,
        RemoveRequest(
            title=["x"],
        ),
        ops=dup,
    )

    assert [op.id for op in response.result.removed] == [track_id]
    assert response.result.removed[0].source_deleted is False
    assert db.get_content(ID=track_id) is None


def test_missing_source_file_still_removes_the_row(db, monkeypatch):
    track_id = _any_track_id(db)
    monkeypatch.setattr(
        "rekordbox_edit.api._remove.os.remove",
        lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
    )
    response = remove(db, RemoveRequest(track_id=[track_id], delete_source=True))
    assert [op.id for op in response.result.removed] == [track_id]
    assert response.result.removed[0].source_deleted is False
    assert db.get_content(ID=track_id) is None


def test_delete_source_unlinks_the_file(db, tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    content = db.session.query(tb.DjmdContent).first()
    content.FolderPath = str(audio)
    db.session.flush()
    response = remove(db, RemoveRequest(track_id=[str(content.ID)], delete_source=True))
    assert response.result.removed[0].source_deleted is True
    assert not audio.exists()


def test_source_survives_without_the_flag(db, tmp_path):
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"audio")
    content = db.session.query(tb.DjmdContent).first()
    content.FolderPath = str(audio)
    db.session.flush()
    response = remove(db, RemoveRequest(track_id=[str(content.ID)]))
    assert response.result.removed[0].source_deleted is False
    assert audio.exists()


def test_remove_deletes_analysis_and_artwork_files_on_disk(db):
    """End-to-end check that a real removal deletes the real analysis and
    artwork directories a fixture row points at, not just the database rows.

    This does NOT defend the read-before-delete ordering in remove(): a
    mutation that read AnalysisDataPath/ImagePath after the delete/commit
    instead of before still passes this test, because a deleted-then-
    committed SQLAlchemy instance is expunged rather than expired (regardless
    of `expire_on_commit`), so its already-loaded attributes stay readable in
    Python. Verified directly by moving the read and confirming every test in
    this module, this one included, kept passing. That ordering is called out
    as load-bearing and untested in a comment at the `file_work` construction
    in remove.py instead.
    """
    content = db.session.query(tb.DjmdContent).first()
    assert content is not None

    anlz_dir = db.share_directory / "PIONEER/USBANLZ/1c0/e2e-test-uuid"
    art_dir = db.share_directory / "PIONEER/Artwork/1c0/e2e-test-uuid"
    anlz_dir.mkdir(parents=True)
    art_dir.mkdir(parents=True)
    (anlz_dir / "ANLZ0000.DAT").write_bytes(b"dat")
    (anlz_dir / "ANLZ0000.EXT").write_bytes(b"ext")
    for name in ("artwork.jpg", "artwork_m.jpg", "artwork_s.jpg"):
        (art_dir / name).write_bytes(b"jpg")

    content.AnalysisDataPath = "/PIONEER/USBANLZ/1c0/e2e-test-uuid/ANLZ0000.DAT"
    content.ImagePath = "/PIONEER/Artwork/1c0/e2e-test-uuid/artwork.jpg"
    db.session.flush()

    remove(db, RemoveRequest(track_id=[str(content.ID)]))

    assert not anlz_dir.exists()
    assert not art_dir.exists()


def test_deleted_relatives_reports_a_swept_record(db):
    artist = db.add_artist("RBE Remove Sweep Report Artist")
    artist_id = str(artist.ID)
    content = db.session.query(tb.DjmdContent).first()
    assert content is not None
    content.ArtistID = artist_id
    db.session.flush()

    response = remove(db, RemoveRequest(track_id=[str(content.ID)]))

    # Read via a fresh query, not the `artist` instance: the commit inside
    # remove() expires it, and re-reading an attribute off a row the sweep
    # just deleted raises ObjectDeletedError rather than returning None.
    assert response.result.deleted_relatives >= 1
    assert db.get_artist(ID=artist_id) is None


def test_artwork_survives_when_another_row_shares_the_image_path(db):
    art_dir = db.share_directory / "PIONEER/Artwork/1c0/shared-uuid"
    art_dir.mkdir(parents=True)
    (art_dir / "artwork.jpg").write_bytes(b"jpg")
    image_path = "/PIONEER/Artwork/1c0/shared-uuid/artwork.jpg"

    contents = db.session.query(tb.DjmdContent).limit(2).all()
    assert len(contents) == 2, "fixture library needs at least two tracks"
    first, second = contents
    first.ImagePath = image_path
    second.ImagePath = image_path
    db.session.flush()

    remove(db, RemoveRequest(track_id=[str(first.ID)]))

    assert db.get_content(ID=first.ID) is None
    assert (art_dir / "artwork.jpg").exists()
