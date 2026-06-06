"""Tests for models.py."""

import pytest
from pydantic import ValidationError

from rekordbox_edit.models import (
    ConfirmationArgs,
    ConvertArgs,
    ConvertCommandArgs,
    ConvertPlanArgs,
    EditArgs,
    EditCommandArgs,
    EditPlanArgs,
    FilterArgs,
    Track,
)


class TestTrack:
    def test_construction_with_required_fields(self):
        track = Track(ID="123", FileNameL="x.wav", FolderPath="/x.wav")
        assert track.ID == "123"
        assert track.Title is None
        assert track.ArtistName is None

    def test_all_fields(self):
        track = Track(
            ID="abc",
            Title="Song",
            ArtistName="Artist",
            AlbumName="Album",
            FileNameL="song.aif",
            FolderPath="/music/song.aif",
            FileType=11,
            SampleRate=44100,
            BitDepth=16,
            BitRate=1411,
        )
        assert track.FileType == 11
        assert track.SampleRate == 44100

    def test_extra_fields_allowed(self):
        track = Track.model_validate(
            {
                "ID": "1",
                "FileNameL": "x.wav",
                "FolderPath": "/x.wav",
                "unknown_field": "x",
            }
        )
        assert track.ID == "1"
        assert track.unknown_field == "x"


class TestFilterArgs:
    def test_defaults_are_empty(self):
        args = FilterArgs()
        assert args.track_id == []
        assert args.track_ids == []
        assert args.match_all is False

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            FilterArgs.model_validate({"unknown": "x"})


class TestConfirmationArgs:
    def test_defaults(self):
        args = ConfirmationArgs()
        assert args.dry_run is False
        assert args.yes is False
        assert args.interactive is False

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            ConfirmationArgs.model_validate({"unknown": "x"})


class TestEditArgs:
    def test_required_fields(self):
        args = EditArgs(field="Title", replace_value="New")
        assert args.field == "Title"
        assert args.replace_value == "New"
        assert args.match_pattern is None
        assert args.multi is False

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            EditArgs.model_validate(
                {"field": "Title", "replace_value": "x", "unknown": "y"}
            )


class TestConvertArgs:
    def test_defaults(self):
        args = ConvertArgs()
        assert args.format_out == "aiff"
        assert args.delete is None
        assert args.overwrite is False

    def test_delete_tri_state(self):
        assert ConvertArgs(delete=True).delete is True
        assert ConvertArgs(delete=False).delete is False
        assert ConvertArgs().delete is None


class TestEditPlanArgs:
    def test_inherits_filter_and_edit_fields(self):
        args = EditPlanArgs(field="Title", replace_value="New")
        assert args.field == "Title"
        assert args.match_all is False
        assert args.multi is False

    def test_no_confirmation_fields(self):
        assert "dry_run" not in EditPlanArgs.model_fields

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            EditPlanArgs.model_validate(
                {"field": "Title", "replace_value": "x", "dry_run": True}
            )


class TestConvertPlanArgs:
    def test_inherits_filter_and_convert_fields(self):
        args = ConvertPlanArgs(format_out="aiff")
        assert args.format_out == "aiff"
        assert args.match_all is False

    def test_no_confirmation_fields(self):
        assert "dry_run" not in ConvertPlanArgs.model_fields


class TestEditCommandArgs:
    def test_has_all_fields(self):
        args = EditCommandArgs(field="Title", replace_value="New")
        assert args.field == "Title"
        assert args.dry_run is False
        assert args.yes is False
        assert args.interactive is False

    def test_is_subtype_of_edit_plan_args(self):
        args = EditCommandArgs(field="Title", replace_value="X")
        assert isinstance(args, EditPlanArgs)

    def test_no_print_opt(self):
        assert "print_opt" not in EditCommandArgs.model_fields


class TestConvertCommandArgs:
    def test_has_all_fields(self):
        args = ConvertCommandArgs(format_out="mp3")
        assert args.format_out == "mp3"
        assert args.dry_run is False

    def test_is_subtype_of_convert_plan_args(self):
        args = ConvertCommandArgs(format_out="flac")
        assert isinstance(args, ConvertPlanArgs)

    def test_no_print_opt(self):
        assert "print_opt" not in ConvertCommandArgs.model_fields
