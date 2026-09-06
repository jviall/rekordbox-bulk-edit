"""Tests for models.py."""

import pytest
from pydantic import ValidationError

from rekordbox_edit.models import (
    ConvertOp,
    ConvertRequest,
    ConvertResponse,
    ConvertResult,
    EditOp,
    EditRequest,
    EditResponse,
    EditResult,
    FilterArgs,
    ImportOp,
    ImportRequest,
    ImportResponse,
    ImportResult,
    RemoveOp,
    RemoveRequest,
    RemoveResponse,
    RemoveResult,
    SearchRequest,
    SearchResponse,
    SkippedTrack,
    Track,
)


def test_ops_carry_their_track(make_track):
    track = make_track(ID="7", Title="Gravity")
    op = EditOp(id="7", new_value="Bassline", track=track)
    assert op.track is not None
    assert op.track.Title == "Gravity"


def test_skipped_track_carries_its_track(make_track):
    track = make_track(ID="9", FileNameL="held.flac")
    skipped = SkippedTrack(reason="no_change", track=track)
    assert skipped.track is not None
    assert skipped.track.FileNameL == "held.flac"


def test_tracks_is_derived_from_the_ops(make_track):
    first, second = make_track(ID="1"), make_track(ID="2")
    response = EditResponse(
        result=EditResult(
            field="Title",
            dry_run=False,
            edits=[
                EditOp(id="1", new_value="A", track=first),
                EditOp(id="2", new_value="B", track=second),
            ],
            skipped=[],
        )
    )
    assert [t.ID for t in response.tracks] == ["1", "2"]


def test_tracks_is_empty_on_a_dry_run_even_with_edits(make_track):
    track = make_track(ID="1")
    response = EditResponse(
        result=EditResult(
            field="Title",
            dry_run=True,
            edits=[EditOp(id="1", new_value="A", track=track)],
            skipped=[],
        )
    )
    assert response.tracks == []
    assert response.result.edits[0].track.ID == "1"


def _edit_response(tracks, *, dry_run):
    return EditResponse(
        result=EditResult(
            field="Title",
            dry_run=dry_run,
            edits=[
                EditOp(id=str(i), new_value="x", track=t) for i, t in enumerate(tracks)
            ],
            skipped=[],
        )
    )


def _convert_response(tracks, *, dry_run):
    return ConvertResponse(
        result=ConvertResult(
            format_out="AIFF",
            dry_run=dry_run,
            converted=[
                ConvertOp(id=str(i), source_path="/a", output_path="/b", track=t)
                for i, t in enumerate(tracks)
            ],
            deleted=0,
            skipped=[],
        )
    )


def _import_response(tracks, *, dry_run):
    return ImportResponse(
        result=ImportResult(
            playlist=None,
            dry_run=dry_run,
            added=[
                ImportOp(id=str(i), path="/a", action="create", track=t)
                for i, t in enumerate(tracks)
            ],
            skipped=[],
        )
    )


def _remove_response(tracks, *, dry_run):
    return RemoveResponse(
        result=RemoveResult(
            dry_run=dry_run,
            removed=[RemoveOp(id=str(i), track=t) for i, t in enumerate(tracks)],
            skipped=[],
            deleted_relatives=0,
        )
    )


@pytest.mark.parametrize(
    "build_response",
    [_edit_response, _convert_response, _import_response, _remove_response],
    ids=["edit", "convert", "import", "remove"],
)
def test_computed_tracks_field_is_serialized_at_top_level(build_response, make_track):
    """`tracks` is a computed field: it must survive model_dump(), not just
    attribute access, on every response that carries one."""
    tracks = [make_track(ID="1", Title="A"), make_track(ID="2", Title="B")]
    response = build_response(tracks, dry_run=False)

    payload = response.model_dump()

    assert [t["ID"] for t in payload["tracks"]] == ["1", "2"]
    assert [t["Title"] for t in payload["tracks"]] == ["A", "B"]


@pytest.mark.parametrize(
    "build_response",
    [_edit_response, _convert_response, _import_response, _remove_response],
    ids=["edit", "convert", "import", "remove"],
)
def test_computed_tracks_field_is_present_but_empty_on_a_dry_run(
    build_response, make_track
):
    """The `tracks` key must still serialize at the top level on a dry run,
    holding an empty list rather than disappearing."""
    tracks = [make_track(ID="1", Title="A")]
    response = build_response(tracks, dry_run=True)

    payload = response.model_dump()

    assert payload["tracks"] == []


def test_skipped_rows_are_not_mixed_into_tracks(make_track):
    response = EditResponse(
        result=EditResult(
            field="Title",
            dry_run=False,
            edits=[],
            skipped=[
                SkippedTrack(reason="no_change", track=make_track(ID="3")),
            ],
        )
    )
    assert response.tracks == []
    skipped_track = response.result.skipped[0].track
    assert skipped_track is not None
    assert skipped_track.ID == "3"


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
        assert args.allow_missing is False
        assert args.allow_mismatch is False


class TestConvertRequest:
    def test_has_filter_and_convert_fields(self):
        args = ConvertRequest(format_out="mp3", overwrite=True, artist=["X"])
        assert isinstance(args, FilterArgs)
        assert args.format_out == "mp3"
        assert args.overwrite is True
        assert args.delete_originals == "none"
        assert args.artist == ["X"]

    def test_format_out_is_required(self):
        with pytest.raises(ValidationError):
            ConvertRequest(
                title=["x"],
            )  # ty: ignore[missing-argument]  # missing format_out


class TestWriteRequestsRequireAFilter:
    """An unfiltered write would match the whole library, and remove() cannot
    be undone."""

    @pytest.fixture(params=["edit", "convert", "remove"])
    def build(self, request):
        """Build the request under test with `filters` and nothing else."""
        builders = {
            "edit": lambda **f: EditRequest(field="Title", replace_value="New", **f),
            "convert": lambda **f: ConvertRequest(format_out="mp3", **f),
            "remove": lambda **f: RemoveRequest(**f),
        }
        return builders[request.param]

    def test_no_filter_is_rejected(self, build):
        with pytest.raises(ValidationError, match="at least one filter"):
            build()

    def test_one_filter_is_enough(self, build):
        assert build(artist=["X"]).artist == ["X"]

    def test_track_ids_count_as_a_filter(self, build):
        assert build(track_ids=["1"]).track_ids == ["1"]

    def test_a_limit_alone_is_not_a_filter(self, build):
        """`first` bounds how many tracks a selection returns; it selects none."""
        with pytest.raises(ValidationError, match="at least one filter"):
            build(first=10)

    def test_a_match_mode_alone_is_not_a_filter(self, build):
        with pytest.raises(ValidationError, match="at least one filter"):
            build(match_any=True)


class TestUnfilteredReadsStayAllowed:
    def test_search_takes_no_filters(self):
        assert SearchRequest().artist == []

    def test_import_takes_no_filters(self):
        assert ImportRequest(paths=["/x.mp3"]).paths == ["/x.mp3"]


class TestSkippedTrack:
    def test_known_reasons_accepted(self):
        assert SkippedTrack(reason="no_change").reason == "no_change"
        assert (
            SkippedTrack(reason="already_target_format").reason
            == "already_target_format"
        )
        assert SkippedTrack(reason="output_file_exists").reason == "output_file_exists"
        assert SkippedTrack(reason="file_not_found").reason == "file_not_found"
        assert SkippedTrack(reason="length_mismatch").reason == "length_mismatch"
        assert SkippedTrack(reason="unknown_file_type").reason == "unknown_file_type"

    def test_unknown_reason_rejected(self):
        with pytest.raises(ValidationError):
            SkippedTrack(reason="nope")  # ty: ignore[invalid-argument-type]


class TestEditResultCarriesField:
    def test_field_required(self):
        with pytest.raises(ValidationError):
            EditResult(dry_run=False, edits=[], skipped=[])  # ty: ignore[missing-argument]  # missing field

    def test_field_accessible(self):
        r = EditResult(field="Title", dry_run=False, edits=[], skipped=[])
        assert r.field == "Title"

    def test_dry_run_required(self):
        with pytest.raises(ValidationError):
            EditResult(field="Title", edits=[], skipped=[])  # ty: ignore[missing-argument]  # missing dry_run


class TestConvertResultCarriesFormatOut:
    def test_format_out_required(self):
        with pytest.raises(ValidationError):
            ConvertResult(dry_run=False, converted=[], deleted=0, skipped=[])  # ty: ignore[missing-argument]  # missing format_out

    def test_format_out_accessible(self):
        r = ConvertResult(
            format_out="aiff", dry_run=False, converted=[], deleted=0, skipped=[]
        )
        assert r.format_out == "aiff"

    def test_dry_run_required(self):
        with pytest.raises(ValidationError):
            ConvertResult(format_out="aiff", converted=[], deleted=0, skipped=[])  # ty: ignore[missing-argument]  # missing dry_run


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
    def test_tracks_derived_from_added_ops(self):
        track = Track(ID="1", FileNameL="a.flac", FolderPath="/a.flac")
        response = ImportResponse(
            result=ImportResult(
                playlist=None,
                dry_run=False,
                added=[ImportOp(id="1", path="/a.flac", action="create", track=track)],
                skipped=[],
            ),
        )
        assert len(response.tracks) == 1

    def test_tracks_empty_on_dry_run(self):
        track = Track(ID="", FileNameL="a.flac", FolderPath="/a.flac")
        response = ImportResponse(
            result=ImportResult(
                playlist=None,
                dry_run=True,
                added=[ImportOp(id="", path="/a.flac", action="create", track=track)],
                skipped=[],
            ),
        )
        assert response.tracks == []
        assert response.result.added[0].track.FileNameL == "a.flac"


def test_remove_response_tracks_are_the_removed_rows(make_track):
    response = RemoveResponse(
        result=RemoveResult(
            dry_run=False,
            removed=[RemoveOp(id="4", track=make_track(ID="4"))],
            skipped=[],
            deleted_relatives=2,
        )
    )
    assert [t.ID for t in response.tracks] == ["4"]
    assert response.result.deleted_relatives == 2
    assert response.result.removed[0].source_deleted is False


def test_remove_response_tracks_empty_on_dry_run(make_track):
    response = RemoveResponse(
        result=RemoveResult(
            dry_run=True,
            removed=[RemoveOp(id="4", track=make_track(ID="4"))],
            skipped=[],
            deleted_relatives=0,
        )
    )
    assert response.tracks == []
    assert response.result.removed[0].track.ID == "4"


def test_remove_request_defaults_to_keeping_the_source():
    assert (
        RemoveRequest(
            title=["x"],
        ).delete_source
        is False
    )
