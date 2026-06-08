from unittest.mock import Mock, patch

import click
import pytest

from rekordbox_edit._click import PrintChoice
from rekordbox_edit.cli._utils import (
    _handle_stdin,
    _narrow_to_track_ids,
    _print_response_ids,
    _print_response_json,
    _validate_scripting_preconditions,
)
from rekordbox_edit.models import (
    ConvertArgs,
    ConvertOp,
    ConvertResponse,
    ConvertResult,
    EditArgs,
    EditOp,
    EditResponse,
    EditResult,
    SearchResponse,
    Track,
)


class TestHandleStdin:
    def test_returns_false_when_tty(self):
        args = Mock()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert _handle_stdin(args) is False

    def test_appends_ids_from_piped_stdin(self):
        args = Mock(track_ids=["existing"])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = b"AAA BBB"
            result = _handle_stdin(args)
        assert result is True
        assert args.track_ids == ["existing", "AAA", "BBB"]

    def test_strips_bom_from_piped_stdin(self):
        args = Mock(track_ids=[])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = bytes([0xEF, 0xBB, 0xBF]) + b"AAA BBB"
            result = _handle_stdin(args)
        assert result is True
        assert args.track_ids == ["AAA", "BBB"]

    def test_empty_piped_stdin_returns_false(self):
        args = Mock(track_ids=[])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = b"  "
            result = _handle_stdin(args)
        assert result is False
        assert args.track_ids == []

    def test_bom_only_piped_stdin_returns_false(self):
        args = Mock(track_ids=[])
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = bytes([0xEF, 0xBB, 0xBF])
            result = _handle_stdin(args)
        assert result is False
        assert args.track_ids == []


class TestValidateScriptingPreconditions:
    def test_scripting_mode_without_confirmation_raises(self):
        args = Mock(dry_run=False, yes=False)
        with pytest.raises(click.UsageError):
            _validate_scripting_preconditions(PrintChoice.IDS, args, piped_stdin=False)

    def test_scripting_mode_with_yes_ok(self):
        args = Mock(dry_run=False, yes=True)
        _validate_scripting_preconditions(PrintChoice.IDS, args, piped_stdin=False)

    def test_piped_stdin_without_confirmation_raises(self):
        args = Mock(dry_run=False, yes=False)
        with pytest.raises(click.UsageError, match="Piping"):
            _validate_scripting_preconditions(None, args, piped_stdin=True)


class TestNarrowToTrackIds:
    def test_clears_other_filter_criteria(self):
        args = ConvertArgs(
            artist=["X"],
            format=["flac"],
            format_out="aiff",
            overwrite=True,
            delete=True,
        )

        narrowed = _narrow_to_track_ids(args, ["a", "b"])

        assert narrowed.track_ids == ["a", "b"]
        assert narrowed.artist == []
        assert narrowed.format == []
        # Convert-specific fields preserved
        assert narrowed.format_out == "aiff"
        assert narrowed.overwrite is True
        assert narrowed.delete is True

    def test_works_for_edit_args(self):
        args = EditArgs(
            artist=["X"],
            field="Title",
            replace_value="N",
            match_pattern="O",
            multi=True,
        )

        narrowed = _narrow_to_track_ids(args, ["a"])

        assert narrowed.track_ids == ["a"]
        assert narrowed.artist == []
        # Edit-specific fields preserved
        assert narrowed.field == "Title"
        assert narrowed.replace_value == "N"
        assert narrowed.match_pattern == "O"
        assert narrowed.multi is True


class TestPrintResponseIds:
    def test_prints_space_separated_ids(self, capsys):
        track = Track(ID="1", FileNameL="x", FolderPath="/x")
        resp = SearchResponse(
            tracks=[track, Track(ID="2", FileNameL="y", FolderPath="/y")]
        )
        _print_response_ids(resp)
        assert capsys.readouterr().out.strip() == "1 2"


class TestPrintResponseJson:
    def test_emits_envelope_json(self, capsys):
        track = Track(ID="1", FileNameL="x", FolderPath="/x")
        resp = EditResponse(
            tracks=[track],
            result=EditResult(
                field="Title", edits=[EditOp(id="1", new_value="N")], skipped=[]
            ),
        )
        _print_response_json(resp)
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["tracks"][0]["ID"] == "1"
        assert payload["result"]["field"] == "Title"

    def test_convert_response_json(self, capsys):
        track = Track(ID="1", FileNameL="x.aif", FolderPath="/x.aif")
        resp = ConvertResponse(
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
        _print_response_json(resp)
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["result"]["format_out"] == "aiff"
