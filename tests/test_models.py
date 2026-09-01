"""Tests for models.py."""

import pytest
from pydantic import ValidationError

from rekordbox_edit.models import (
    ConvertRequest,
    ConvertOp,
    ConvertResponse,
    ConvertResult,
    EditRequest,
    EditOp,
    EditResponse,
    EditResult,
    FilterArgs,
    ImportOp,
    ImportRequest,
    ImportResponse,
    ImportResult,
    SearchRequest,
    SearchResponse,
    SkippedTrack,
    Track,
)


class TestTrack:
    def test_construction_with_required_fields(self):
        track = Track(ID="123", FileNameL="x.wav", FolderPath="/x.wav")
        assert track.ID == "123"
        assert track.Title is None
        assert track.ArtistName is None

    def test_extra_fields_allowed(self):
        track = Track.model_validate(
            {"ID": "1", "FileNameL": "x.wav", "FolderPath": "/x.wav", "extra": "x"}
        )
        assert getattr(track, "extra") == "x"


class TestFilterArgs:
    def test_defaults_are_empty(self):
        args = FilterArgs()
        assert args.track_id == []
        assert args.track_ids == []
        assert args.match_all is False

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            FilterArgs.model_validate({"unknown": "x"})

    def test_first_defaults_to_none(self):
        assert FilterArgs().first is None

    def test_first_accepts_positive_int(self):
        assert FilterArgs(first=5).first == 5

    def test_first_rejects_zero_and_negative(self):
        with pytest.raises(ValidationError):
            FilterArgs(first=0)
        with pytest.raises(ValidationError):
            FilterArgs(first=-3)

    def test_last_defaults_to_none(self):
        assert FilterArgs().last is None

    def test_last_accepts_positive_int(self):
        assert FilterArgs(last=3).last == 3

    def test_last_rejects_zero_and_negative(self):
        with pytest.raises(ValidationError):
            FilterArgs(last=0)
        with pytest.raises(ValidationError):
            FilterArgs(last=-1)

    def test_first_and_last_mutually_exclusive(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            FilterArgs(first=2, last=3)

    def test_match_any_defaults_false(self):
        assert FilterArgs().match_any is False

    def test_match_all_and_match_any_mutually_exclusive(self):
        with pytest.raises(ValidationError, match="mutually exclusive"):
            FilterArgs(match_all=True, match_any=True)


class TestSearchRequest:
    def test_is_filter_args(self):
        args = SearchRequest(artist=["X"])
        assert isinstance(args, FilterArgs)
        assert args.artist == ["X"]


class TestEditRequest:
    def test_has_filter_and_edit_fields(self):
        args = EditRequest(field="Title", replace_value="New", artist=["X"])
        assert isinstance(args, FilterArgs)
        assert args.field == "Title"
        assert args.replace_value == "New"
        assert args.artist == ["X"]
        assert args.force is False


class TestConvertRequest:
    def test_has_filter_and_convert_fields(self):
        args = ConvertRequest(format_out="mp3", overwrite=True, artist=["X"])
        assert isinstance(args, FilterArgs)
        assert args.format_out == "mp3"
        assert args.overwrite is True
        assert args.delete_originals == "lossless"
        assert args.artist == ["X"]


class TestSkippedTrack:
    def test_known_reasons_accepted(self):
        assert SkippedTrack(id="1", reason="no_change").reason == "no_change"
        assert (
            SkippedTrack(id="1", reason="already_target_format").reason
            == "already_target_format"
        )
        assert (
            SkippedTrack(id="1", reason="output_file_exists").reason
            == "output_file_exists"
        )
        assert SkippedTrack(id="1", reason="file_not_found").reason == "file_not_found"
        assert (
            SkippedTrack(id="1", reason="length_mismatch").reason == "length_mismatch"
        )
        assert (
            SkippedTrack(id="1", reason="unknown_file_type").reason
            == "unknown_file_type"
        )

    def test_unknown_reason_rejected(self):
        with pytest.raises(ValidationError):
            SkippedTrack(id="1", reason="nope")  # ty: ignore[invalid-argument-type]


class TestEditResponseAlignment:
    def test_rejects_mismatched_lengths(self):
        track = Track(ID="1", FileNameL="x.wav", FolderPath="/x.wav")
        with pytest.raises(ValidationError, match="align"):
            EditResponse(
                tracks=[track, track],
                result=EditResult(
                    field="Title",
                    edits=[EditOp(id="1", new_value="X")],
                    skipped=[],
                ),
            )

    def test_accepts_matched_lengths(self):
        track = Track(ID="1", FileNameL="x.wav", FolderPath="/x.wav")
        EditResponse(
            tracks=[track],
            result=EditResult(
                field="Title",
                edits=[EditOp(id="1", new_value="X")],
                skipped=[],
            ),
        )


class TestConvertResponseAlignment:
    def test_rejects_mismatched_lengths(self):
        track = Track(ID="1", FileNameL="x.aif", FolderPath="/x.aif")
        with pytest.raises(ValidationError, match="align"):
            ConvertResponse(
                tracks=[track, track],
                result=ConvertResult(
                    format_out="aiff",
                    converted=[
                        ConvertOp(id="1", source_path="/x.wav", output_path="/x.aif")
                    ],
                    deleted=0,
                    skipped=[],
                ),
            )

    def test_accepts_matched_lengths(self):
        track = Track(ID="1", FileNameL="x.aif", FolderPath="/x.aif")
        ConvertResponse(
            tracks=[track],
            result=ConvertResult(
                format_out="aiff",
                converted=[
                    ConvertOp(id="1", source_path="/x.wav", output_path="/x.aif")
                ],
                deleted=0,
                skipped=[],
            ),
        )


class TestEditResultCarriesField:
    def test_field_required(self):
        with pytest.raises(ValidationError):
            EditResult(edits=[], skipped=[])  # ty: ignore[missing-argument]  # missing field

    def test_field_accessible(self):
        r = EditResult(field="Title", edits=[], skipped=[])
        assert r.field == "Title"


class TestConvertResultCarriesFormatOut:
    def test_format_out_required(self):
        with pytest.raises(ValidationError):
            ConvertResult(converted=[], deleted=0, skipped=[])  # ty: ignore[missing-argument]  # missing format_out

    def test_format_out_accessible(self):
        r = ConvertResult(format_out="aiff", converted=[], deleted=0, skipped=[])
        assert r.format_out == "aiff"


class TestSearchResponse:
    def test_construction(self):
        track = Track(ID="1", FileNameL="x.wav", FolderPath="/x.wav")
        resp = SearchResponse(tracks=[track])
        assert resp.tracks[0].ID == "1"


class TestImportRequest:
    def test_defaults_to_empty(self):
        args = ImportRequest()
        assert args.paths == []
        assert args.playlist is None
        assert args.recurse is False

    def test_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            ImportRequest.model_validate({"nonsense": True})


class TestImportResponse:
    def test_rejects_misaligned_tracks_and_ops(self):
        with pytest.raises(ValidationError):
            ImportResponse(
                tracks=[],
                result=ImportResult(
                    playlist=None,
                    added=[ImportOp(id="1", path="/a.flac", action="create")],
                    skipped=[],
                ),
            )

    def test_accepts_aligned_tracks_and_ops(self):
        response = ImportResponse(
            tracks=[Track(ID="1", FileNameL="a.flac", FolderPath="/a.flac")],
            result=ImportResult(
                playlist=None,
                added=[ImportOp(id="1", path="/a.flac", action="create")],
                skipped=[],
            ),
        )
        assert len(response.tracks) == 1
