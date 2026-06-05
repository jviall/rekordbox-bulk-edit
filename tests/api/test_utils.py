"""Tests for api/_utils.py."""

from rekordbox_edit.api._utils import _track_from_content
from rekordbox_edit.args import Track


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
