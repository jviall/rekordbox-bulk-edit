"""Tests for api/_utils.py."""

from rekordbox_edit.api._utils import _order_tracks_by_op, _track_from_content
from rekordbox_edit.models import ConvertOp, Track


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
