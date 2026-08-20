from unittest.mock import MagicMock

from rekordbox_edit.api.field_handlers import (
    FIELD_HANDLERS,
    RelationalField,
    StringField,
)
from rekordbox_edit.models import EditRequest


def _artist_handler():
    return RelationalField("ArtistName", "ArtistID", "ArtistName", "artist")


class TestStringField:
    def test_current_value_reads_named_column(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        handler = StringField("Title", "Title")
        assert handler.current_value(content) == "Old"

    def test_compute_plain_replace(self):
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="New")
        assert handler.compute_new_value("Old", args) == "New"

    def test_compute_match_replace(self):
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="Earth", match_pattern="World")
        assert handler.compute_new_value("Hello World", args) == "Hello Earth"

    def test_compute_plain_replace_sets_from_none(self):
        # Plain --replace assigns a value even to an empty field.
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="New")
        assert handler.compute_new_value(None, args) == "New"

    def test_compute_match_skips_none(self):
        # --match has no text to search when the field is empty.
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="b", match_pattern="a")
        assert handler.compute_new_value(None, args) is None

    def test_apply_sets_column(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        StringField("Title", "Title").apply(db=None, content=content, new_value="New")
        assert content.Title == "New"


def _album_handler():
    return RelationalField("AlbumName", "AlbumID", "AlbumName", "album")


class TestCommentField:
    def test_registered_over_commnt_column(self):
        handler = FIELD_HANDLERS["Comment"]
        assert isinstance(handler, StringField)
        assert handler.column == "Commnt"

    def test_current_and_apply_use_commnt(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.Commnt = "old note"
        handler = FIELD_HANDLERS["Comment"]
        assert handler.current_value(content) == "old note"
        db = MagicMock()
        handler.apply(db=db, content=content, new_value="new note")
        assert content.Commnt == "new note"


class TestRegistry:
    def test_title_registered(self):
        assert FIELD_HANDLERS["Title"].name == "Title"
        assert FIELD_HANDLERS["Title"].supports_match is True


class TestRelationalArtist:
    def test_current_value_reads_name_proxy(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma")
        assert _artist_handler().current_value(content) == "Gamma"

    def test_compute_plain_replace(self):
        args = EditRequest(field="ArtistName", replace_value="Alpha")
        assert _artist_handler().compute_new_value("Gamma", args) == "Alpha"

    def test_apply_reuses_existing_artist_and_deletes_orphan(
        self, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma", ArtistID="G")
        db = MagicMock()
        existing = MagicMock(ID="A")
        # get-or-create finds the existing artist by name.
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = existing
        # orphan check: vacated artist "G" is referenced nowhere.
        db.session.query.return_value.filter.return_value.first.return_value = None
        old_row = MagicMock()
        db.get_artist.return_value = old_row

        _artist_handler().apply(db, content, "Alpha")

        assert content.ArtistID == "A"
        db.add_artist.assert_not_called()
        db.delete.assert_called_once_with(old_row)

    def test_apply_creates_artist_when_absent(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma", ArtistID="G")
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        db.add_artist.return_value = MagicMock(ID="NEW")
        db.session.query.return_value.filter.return_value.first.return_value = None
        db.get_artist.return_value = MagicMock()

        _artist_handler().apply(db, content, "Brand New")

        db.add_artist.assert_called_once_with("Brand New")
        assert content.ArtistID == "NEW"

    def test_apply_keeps_artist_still_referenced(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", ArtistName="Alpha", ArtistID="A")
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(
            ID="B"
        )
        # orphan check: vacated artist "A" still referenced by another row.
        db.session.query.return_value.filter.return_value.first.return_value = (
            MagicMock()
        )

        _artist_handler().apply(db, content, "Beta")

        db.delete.assert_not_called()

    def test_apply_clear_sets_empty_fk(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma", ArtistID="G")
        db = MagicMock()
        db.session.query.return_value.filter.return_value.first.return_value = None
        db.get_artist.return_value = MagicMock()

        _artist_handler().apply(db, content, "")

        assert content.ArtistID == ""
        db.add_artist.assert_not_called()

    def test_apply_skips_orphan_check_when_no_previous_artist(
        self, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma", ArtistID=None)
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        db.add_artist.return_value = MagicMock(ID="NEW")

        _artist_handler().apply(db, content, "Brand New")

        db.get_artist.assert_not_called()
        db.delete.assert_not_called()

    def test_apply_orphan_check_handles_missing_artist_row(
        self, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", ArtistName="Gamma", ArtistID="G")
        db = MagicMock()
        existing = MagicMock(ID="A")
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = existing
        # orphan check: vacated artist "G" is referenced nowhere, but its row
        # is already gone (e.g. deleted out-of-band).
        db.session.query.return_value.filter.return_value.first.return_value = None
        db.get_artist.return_value = None

        _artist_handler().apply(db, content, "Alpha")

        db.delete.assert_not_called()


class TestRelationalAlbum:
    def test_apply_reuses_existing_album(self, make_djmd_content_item):
        content = make_djmd_content_item(
            ID="1", AlbumName="AIFF Sampler", AlbumID="OLD"
        )
        db = MagicMock()
        existing = MagicMock(ID="TARGET")
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = existing
        db.session.query.return_value.filter.return_value.first.return_value = None
        db.get_album.return_value = MagicMock()

        _album_handler().apply(db, content, "Lossless Vol 1")

        # Reuse repoints the track and never creates a duplicate album. That the
        # reused album's album-artist is left untouched is verified end-to-end in
        # tests/e2e/test_edit_fields.py (a MagicMock cannot prove a non-write).
        assert content.AlbumID == "TARGET"
        db.add_album.assert_not_called()

    def test_apply_creates_album_without_album_artist(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", AlbumName="Old", AlbumID="OLD")
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        db.add_album.return_value = MagicMock(ID="NEW")
        db.session.query.return_value.filter.return_value.first.return_value = None
        db.get_album.return_value = MagicMock()

        _album_handler().apply(db, content, "Brand New Album")

        db.add_album.assert_called_once_with("Brand New Album")
        assert content.AlbumID == "NEW"

    def test_apply_deletes_orphaned_album(self, make_djmd_content_item):
        content = make_djmd_content_item(
            ID="1", AlbumName="AIFF Sampler", AlbumID="OLD"
        )
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(
            ID="TARGET"
        )
        db.session.query.return_value.filter.return_value.first.return_value = None
        old_row = MagicMock()
        db.get_album.return_value = old_row

        _album_handler().apply(db, content, "Lossless Vol 1")

        db.delete.assert_called_once_with(old_row)

    def test_apply_orphan_check_handles_missing_album_row(self, make_djmd_content_item):
        content = make_djmd_content_item(
            ID="1", AlbumName="AIFF Sampler", AlbumID="OLD"
        )
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(
            ID="TARGET"
        )
        # orphan check: vacated album "OLD" is referenced nowhere, but its row
        # is already gone (e.g. deleted out-of-band).
        db.session.query.return_value.filter.return_value.first.return_value = None
        db.get_album.return_value = None

        _album_handler().apply(db, content, "Lossless Vol 1")

        db.delete.assert_not_called()

    def test_apply_keeps_album_still_referenced(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", AlbumName="Old", AlbumID="OLD")
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(
            ID="TARGET"
        )
        # orphan check: vacated album "OLD" still referenced by another row.
        db.session.query.return_value.filter.return_value.first.return_value = (
            MagicMock()
        )

        _album_handler().apply(db, content, "New Name")

        db.delete.assert_not_called()
