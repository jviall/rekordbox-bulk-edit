from unittest.mock import MagicMock, patch

import pytest

from rekordbox_edit.api.field_handlers import (
    FIELD_HANDLERS,
    FolderPathField,
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


class TestRatingField:
    def test_no_match_support(self):
        assert FIELD_HANDLERS["Rating"].supports_match is False

    def test_validate_rejects_out_of_range(self):
        args = EditRequest(field="Rating", replace_value="9")
        with pytest.raises(ValueError):
            FIELD_HANDLERS["Rating"].validate_request(args)

    def test_validate_warns_and_ignores_match(self):
        args = EditRequest(field="Rating", replace_value="3", match_pattern="x")
        # Must not raise; --match is ignored for Rating.
        FIELD_HANDLERS["Rating"].validate_request(args)

    def test_current_value_is_star_string(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.Rating = 153
        assert FIELD_HANDLERS["Rating"].current_value(content) == "3"

    def test_compute_and_apply_star_to_stored(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        content.Rating = 0
        handler = FIELD_HANDLERS["Rating"]
        args = EditRequest(field="Rating", replace_value="4")
        new_value = handler.compute_new_value(handler.current_value(content), args)
        assert new_value == "4"
        handler.apply(db=MagicMock(), content=content, new_value=new_value)
        assert content.Rating == 204


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


def _folder_handler():
    return FolderPathField()


def _probe(**overrides):
    info = {
        "bit_depth": 16,
        "sample_rate": 44100,
        "channels": 2,
        "bitrate": 1411,
        "codec": "pcm_s16le",
        "container": "wav",
        "duration": 214.4,
    }
    info.update(overrides)
    return info


def _no_cues(db):
    db.session.query.return_value.filter_by.return_value.first.return_value = None


class TestFolderPathField:
    def test_registered(self):
        handler = FIELD_HANDLERS["FolderPath"]
        assert isinstance(handler, FolderPathField)
        assert handler.supports_match is True

    def test_compute_normalizes_backslashes(self):
        args = EditRequest(field="FolderPath", replace_value=r"C:\Music\song.wav")
        assert (
            _folder_handler().compute_new_value("/old/song.wav", args)
            == "C:/Music/song.wav"
        )

    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=False)
    def test_validate_missing_file_skips(self, _exists, make_djmd_content_item):
        content = make_djmd_content_item(ID="1")
        args = EditRequest(field="FolderPath", replace_value="/new/song.wav")

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason == "file_not_found"

    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=False)
    def test_validate_missing_file_forced_proceeds(
        self, _exists, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        args = EditRequest(
            field="FolderPath", replace_value="/new/song.wav", force=True
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason is None

    @patch("rekordbox_edit.api.field_handlers.get_audio_info")
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=1000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_validate_same_size_skips_probe(
        self, _exists, _getsize, mock_probe, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", FileSize=1000)
        content.FileSize = 1000
        args = EditRequest(field="FolderPath", replace_value="/new/song.wav")

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason is None
        mock_probe.assert_not_called()

    @patch(
        "rekordbox_edit.api.field_handlers.get_audio_info",
        return_value=_probe(codec="vorbis", container="ogg"),
    )
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_validate_unknown_codec_skips_even_forced(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        args = EditRequest(
            field="FolderPath", replace_value="/new/song.ogg", force=True
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.ogg", args
        )

        assert reason == "unknown_file_type"

    @patch(
        "rekordbox_edit.api.field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_with_analysis_skips(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = "/PIONEER/USBANLZ/x/ANLZ0000.DAT"
        args = EditRequest(field="FolderPath", replace_value="/new/song.wav")

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason == "length_mismatch"

    @patch(
        "rekordbox_edit.api.field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_with_cues_skips(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = None
        db = MagicMock()
        db.session.query.return_value.filter_by.return_value.first.return_value = (
            MagicMock()  # a cue row exists
        )
        args = EditRequest(field="FolderPath", replace_value="/new/song.wav")

        reason = _folder_handler().validate_track(db, content, "/new/song.wav", args)

        assert reason == "length_mismatch"

    @patch(
        "rekordbox_edit.api.field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_without_analysis_warns_only(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = None
        db = MagicMock()
        _no_cues(db)
        args = EditRequest(field="FolderPath", replace_value="/new/song.wav")

        reason = _folder_handler().validate_track(db, content, "/new/song.wav", args)

        assert reason is None

    @patch(
        "rekordbox_edit.api.field_handlers.get_audio_info",
        return_value=_probe(duration=300.0),
    )
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_validate_length_mismatch_forced_proceeds(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1")
        content.FileSize = 1000
        content.Length = 214
        content.AnalysisDataPath = "/PIONEER/USBANLZ/x/ANLZ0000.DAT"
        args = EditRequest(
            field="FolderPath", replace_value="/new/song.wav", force=True
        )

        reason = _folder_handler().validate_track(
            MagicMock(), content, "/new/song.wav", args
        )

        assert reason is None

    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=1000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_apply_relocation_updates_paths_only(
        self, _exists, _getsize, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav"
        )
        content.FileSize = 1000
        content.OrgFolderPath = "/old/dir/song.wav"
        content.SampleRate = 44100
        content.BitDepth = 16
        content.BitRate = 1411
        content.FileType = 11
        db = MagicMock()
        args = EditRequest(field="FolderPath", replace_value="/new/dir/song.wav")
        assert handler.validate_track(db, content, "/new/dir/song.wav", args) is None

        handler.apply(db, content, "/new/dir/song.wav")

        assert content.FolderPath == "/new/dir/song.wav"
        assert content.FileNameL == "song.wav"
        assert content.OrgFolderPath == "/new/dir/song.wav"
        # Same bytes: technical columns stay as they were.
        assert content.SampleRate == 44100
        assert content.FileSize == 1000

    @patch(
        "rekordbox_edit.api.field_handlers.get_audio_info",
        return_value=_probe(
            codec="flac",
            container="flac",
            bit_depth=24,
            sample_rate=48000,
            bitrate=2304,
            duration=214.9,
        ),
    )
    @patch("rekordbox_edit.api.field_handlers.os.path.getsize", return_value=2000)
    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=True)
    def test_apply_replaced_file_syncs_metadata(
        self, _exists, _getsize, _probe_fn, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav", FileType=11
        )
        content.FileSize = 1000
        content.Length = 214
        content.OrgFolderPath = "/elsewhere/song.wav"
        db = MagicMock()
        _no_cues(db)
        args = EditRequest(field="FolderPath", replace_value="/new/dir/song.flac")
        assert handler.validate_track(db, content, "/new/dir/song.flac", args) is None

        handler.apply(db, content, "/new/dir/song.flac")

        assert content.FolderPath == "/new/dir/song.flac"
        assert content.FileNameL == "song.flac"
        # OrgFolderPath did not match the old path, so it stays put.
        assert content.OrgFolderPath == "/elsewhere/song.wav"
        assert content.FileType == 5
        assert content.SampleRate == 48000
        assert content.BitDepth == 24
        assert content.BitRate == 0  # FLAC stores VBR as 0
        assert content.FileSize == 2000
        assert content.Length == 214

    @patch("rekordbox_edit.api.field_handlers.os.path.exists", return_value=False)
    def test_apply_forced_missing_file_writes_paths_only(
        self, _exists, make_djmd_content_item
    ):
        handler = _folder_handler()
        content = make_djmd_content_item(
            ID="1", FolderPath="/old/dir/song.wav", FileNameL="song.wav", FileType=11
        )
        content.FileSize = 1000
        db = MagicMock()
        args = EditRequest(
            field="FolderPath", replace_value="/gone/dir/song.wav", force=True
        )
        assert handler.validate_track(db, content, "/gone/dir/song.wav", args) is None

        handler.apply(db, content, "/gone/dir/song.wav")

        assert content.FolderPath == "/gone/dir/song.wav"
        assert content.FileNameL == "song.wav"
        assert content.FileSize == 1000
        assert content.FileType == 11

    @patch("rekordbox_edit.api.field_handlers._update_anlz_paths")
    def test_post_commit_rewrites_ppth_on_rename(
        self, mock_anlz, make_djmd_content_item
    ):
        content = make_djmd_content_item(
            ID="1", FolderPath="/new/dir/song.flac", FileNameL="song.flac"
        )
        db = MagicMock()

        _folder_handler().post_commit(db, content, "/old/dir/song.wav")

        mock_anlz.assert_called_once_with(db, content, "song.flac")

    @patch("rekordbox_edit.api.field_handlers._update_anlz_paths")
    def test_post_commit_skips_when_basename_unchanged(
        self, mock_anlz, make_djmd_content_item
    ):
        content = make_djmd_content_item(
            ID="1", FolderPath="/new/dir/song.wav", FileNameL="song.wav"
        )

        _folder_handler().post_commit(MagicMock(), content, "/old/dir/song.wav")

        mock_anlz.assert_not_called()

    @patch("rekordbox_edit.api.field_handlers._update_anlz_paths")
    def test_post_commit_swallows_anlz_errors(self, mock_anlz, make_djmd_content_item):
        mock_anlz.side_effect = OSError("disk full")
        content = make_djmd_content_item(
            ID="1", FolderPath="/new/dir/song.flac", FileNameL="song.flac"
        )

        # Must not raise: the row commit already succeeded.
        _folder_handler().post_commit(MagicMock(), content, "/old/dir/song.wav")
