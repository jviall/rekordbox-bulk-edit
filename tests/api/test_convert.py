import logging
import os
import threading
import time
from dataclasses import replace
from unittest.mock import Mock, patch

import ffmpeg
import pytest

from rekordbox_edit.errors import ConvertAborted, DependencyMissingError
from rekordbox_edit.api._convert import (
    TEMP_PREFIX,
    ConvertedFileProbe,
    _EncodeJob,
    _apply_converted_record,
    _encode_one,
    _encode_job_for,
    _classify_convert,
    _classify_fidelity,
    _get_output_path,
    _hi_res_output_kwargs,
    _mp3_output_kwargs,
    _probe_converted_file,
    _recheck_convert,
    _rollback_session,
    _run_ffmpeg,
    _sweep_orphan_temp_files,
    _temp_output_path,
    convert,
)
from sqlalchemy import text

from rekordbox_edit.query import require_session
from rekordbox_edit.models import (
    ConvertOp,
    ConvertRequest,
    ConvertResponse,
    SkippedTrack,
    Track,
)
from rekordbox_edit.utils import AudioInfo, OutputFormats, get_file_type_for_format

_PROBE_WAV_16_44 = {
    "bit_depth": 16,
    "sample_rate": 44100,
    "channels": 2,
    "bitrate": 1411,
    "codec": "pcm_s16le",
    "container": "wav",
}
_PROBE_WAV_24_96 = {
    "bit_depth": 24,
    "sample_rate": 96000,
    "channels": 2,
    "bitrate": 4608,
    "codec": "pcm_s24le",
    "container": "wav",
}
_PROBE_WAV_16_22 = {
    "bit_depth": 16,
    "sample_rate": 22050,
    "channels": 2,
    "bitrate": 705,
    "codec": "pcm_s16le",
    "container": "wav",
}
_PROBE_AAC_M4A = {
    "bit_depth": 16,
    "sample_rate": 44100,
    "channels": 2,
    "bitrate": 256,
    "codec": "aac",
    "container": "mov,mp4,m4a,3gp,3g2,mj2",
}


class TestClassifyConvert:
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_skips_already_target_format(self, mock_get_type, make_djmd_content_item):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="1", FileType=1)  # already AIFF

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, SkippedTrack)
        assert result.reason == "already_target_format"

    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_skips_lossy_source_as_unsupported(
        self, mock_get_type, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="2", FileType=4)  # M4A: lossy source

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, SkippedTrack)
        assert result.reason == "unsupported_source_format"

    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_skips_unmapped_source_as_unsupported(
        self, mock_get_type, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="9", FileType=20)  # e.g. a video file

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, SkippedTrack)
        assert result.reason == "unsupported_source_format"

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_below_target_sample_rate_clamps_to_source(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="6", FileType=11, SampleRate=22050)

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, ConvertOp)
        assert result.output_sample_rate == 22050

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_mp3_output_ignores_source_sample_rate(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.mp3", "out.mp3", "/")
        content = make_djmd_content_item(ID="7", FileType=11, SampleRate=22050)

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="mp3")
        )

        assert isinstance(result, ConvertOp)
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_missing_db_fields_default_to_target(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(
            ID="8", FileType=11, BitDepth=None, SampleRate=None
        )

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, ConvertOp)
        assert result.output_bit_depth == 16
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_skips_output_conflict_when_no_overwrite(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="3", FileType=11)  # WAV

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff", overwrite=False)
        )

        assert isinstance(result, SkippedTrack)
        assert result.reason == "output_file_exists"

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_overwrite_allows_conflict(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="3", FileType=11, FolderPath="/in.wav")

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
        )

        assert isinstance(result, ConvertOp)
        assert result.source_path == "/in.wav"
        assert result.output_path == "/out.aif"

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_returns_convert_op_with_paths(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/music/song.aif", "song.aif", "/music")
        content = make_djmd_content_item(
            ID="4", FileType=11, FolderPath="/music/song.wav"
        )

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, ConvertOp)
        assert result.id == "4"
        assert result.source_path == "/music/song.wav"
        assert result.output_path == "/music/song.aif"

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_populates_audio_fields(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/music/song.aif", "song.aif", "/music")
        content = make_djmd_content_item(
            ID="4", FileType=11, BitDepth=24, SampleRate=96000
        )

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, ConvertOp)
        assert result.source_file_type == "WAV"
        assert result.source_bit_depth == 24
        assert result.source_sample_rate == 96000
        assert result.output_file_type == "AIFF"
        assert result.output_bit_depth == 16
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    def test_mp3_output_targets_conversion_default(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/music/song.mp3", "song.mp3", "/music")
        content = make_djmd_content_item(ID="7", FileType=11)

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="mp3")
        )

        assert isinstance(result, ConvertOp)
        assert result.output_file_type == "MP3"
        assert result.output_bit_depth == 16
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    def test_alac_source_is_convertible(
        self, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="10", FileType=6, FolderPath="/in.m4a")

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, ConvertOp)
        assert result.source_file_type == "ALAC"

    def test_aac_source_skipped_as_unsupported(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="11", FileType=4)

        result = _classify_convert(
            content, ConvertRequest(title=["x"], format_out="aiff")
        )

        assert isinstance(result, SkippedTrack)
        assert result.reason == "unsupported_source_format"


def _seed_db(mock_db, *contents):
    """Make mock_db.session.execute(select).scalars().all() return contents."""
    mock_db.session.execute.return_value.scalars.return_value.all.return_value = list(
        contents
    )


def _seed_filter(mock_gfc, *contents):
    mock_gfc.return_value.scalars.return_value.all.return_value = list(contents)


class TestConvertDryRun:
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_returns_response_without_commit(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        mock_exists,
        _ffmpeg,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff"), dry_run=True
        )

        assert isinstance(response, ConvertResponse)
        assert response.result.format_out == "aiff"
        assert len(response.result.converted) == 1
        assert response.result.deleted == 0
        assert response.result.dry_run is True
        assert response.tracks == []
        assert response.result.converted[0].track.ID == "1"
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_dry_run_surfaces_skipped(
        self,
        mock_gfc,
        mock_get_type,
        _ffmpeg,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="1", FileType=1)  # already AIFF
        _seed_filter(mock_gfc, content)

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff"), dry_run=True
        )

        assert response.result.converted == []
        assert response.tracks == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "already_target_format"


class TestConvertResponseTracksDryRunRule:
    """`tracks` is empty for a dry run, since a dry run changes nothing; the
    ops still carry their tracks, and a real run populates both."""

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_dry_run_has_empty_tracks_but_ops_carry_theirs(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        mock_exists,
        _ffmpeg,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1}.get(fmt.upper(), 99)
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff"), dry_run=True
        )

        assert response.tracks == []
        assert response.result.converted[0].track.ID == "1"

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.find_content_by_ids")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_real_run_has_both_tracks_and_ops(
        self,
        _ffmpeg,
        mock_gfc,
        mock_by_ids,
        mock_run,
        mock_apply,
        _get_audio_info,
        mock_db,
        make_djmd_content_item,
    ):
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/A.wav")
        mock_by_ids.return_value = {"1": content}
        _seed_db(mock_db, content)
        op = _op(id="1", source="/A.wav", output="/A.aif")

        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
            patch(
                "rekordbox_edit.api._convert.os.path.exists",
                side_effect=lambda path: path != op.output_path,
            ),
        ):
            response = convert(
                mock_db,
                ConvertRequest(title=["x"], format_out="aiff", delete_originals="none"),
                ops=[op],
            )

        assert response.result.dry_run is False
        assert response.tracks[0].ID == "1"
        assert response.result.converted[0].track.ID == "1"


class TestTempOutputPath:
    def test_keeps_the_extension_so_ffmpeg_still_infers_the_format(self):
        temp = _temp_output_path("/music/song.aiff")

        assert temp.endswith(".aiff")
        assert os.path.dirname(temp) == "/music"
        assert os.path.basename(temp).startswith(TEMP_PREFIX)


class TestSweepOrphanTempFiles:
    def test_removes_orphans_and_leaves_everything_else(self, tmp_path):
        orphan = tmp_path / f"{TEMP_PREFIX}999-song.aiff"
        orphan.write_text("half an encode")
        bystander = tmp_path / "song.wav"
        bystander.write_text("a real track")

        _sweep_orphan_temp_files([str(tmp_path / "song.aiff")])

        assert not orphan.exists()
        assert bystander.exists()

    def test_an_unreadable_directory_does_not_raise(self, tmp_path):
        _sweep_orphan_temp_files([str(tmp_path / "absent" / "song.aiff")])


def _op(id="A", source="/A.wav", output="/A.aif"):
    return ConvertOp(
        id=id,
        source_path=source,
        output_path=output,
        source_file_type="WAV",
        output_file_type="AIFF",
        track=Track(ID=id, FileNameL=os.path.basename(source), FolderPath=source),
    )


class TestRecheckConvert:
    """Every op here passed classification during the preview, so a path that
    reads differently now changed while the user was deciding."""

    @patch("rekordbox_edit.api._convert.os.path.exists")
    def test_unchanged_paths_keep_the_op(self, mock_exists):
        op = _op()
        mock_exists.side_effect = lambda path: path == op.source_path

        assert (
            _recheck_convert(op, ConvertRequest(title=["x"], format_out="aiff")) is op
        )

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    def test_a_vanished_source_is_db_or_fs_changed(self, _exists):
        op = _op()
        result = _recheck_convert(op, ConvertRequest(title=["x"], format_out="aiff"))

        assert result == SkippedTrack(reason="db_or_fs_changed", track=op.track)

    @patch("rekordbox_edit.api._convert.os.path.exists")
    def test_an_output_that_appeared_is_db_or_fs_changed(self, mock_exists):
        mock_exists.side_effect = lambda path: True  # source and output both there

        op = _op()
        result = _recheck_convert(op, ConvertRequest(title=["x"], format_out="aiff"))

        assert result == SkippedTrack(reason="db_or_fs_changed", track=op.track)

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    def test_overwrite_tolerates_an_output_that_appeared(self, _exists):
        op = _op()
        assert (
            _recheck_convert(
                op, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
            )
            is op
        )


class TestConvertFromApprovedOps:
    @patch("rekordbox_edit.api._convert.find_content_by_ids")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_a_vanished_source_never_reaches_ffmpeg(
        self, _ffmpeg, _exists, mock_gfc, mock_by_ids, mock_db, make_djmd_content_item
    ):
        mock_by_ids.return_value = {"A": make_djmd_content_item(ID="A")}
        op = _op()

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff"), ops=[op]
        )

        mock_gfc.assert_not_called()
        assert response.result.converted == []
        assert response.result.skipped == [
            SkippedTrack(reason="db_or_fs_changed", track=op.track)
        ]
        mock_db.session.commit.assert_not_called()

    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.find_content_by_ids")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_an_op_that_still_holds_is_converted_and_committed(
        self,
        _ffmpeg,
        mock_gfc,
        mock_by_ids,
        mock_run,
        mock_apply,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        content = make_djmd_content_item(ID="A", FileType=11, FolderPath="/A.wav")
        mock_by_ids.return_value = {"A": content}
        _seed_db(mock_db, content)
        op = _op(source="/A.wav", output="/A.aif")

        with patch(
            "rekordbox_edit.api._convert.os.path.exists",
            side_effect=lambda path: path != op.output_path,
        ):
            response = convert(
                mock_db,
                ConvertRequest(title=["x"], format_out="aiff", delete_originals="none"),
                ops=[op],
            )

        mock_gfc.assert_not_called()
        assert [o.id for o in response.result.converted] == ["A"]
        assert [t.ID for t in response.tracks] == ["A"]
        assert response.result.skipped == []
        mock_run.assert_called_once()
        mock_apply.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.api._convert.find_content_by_ids", return_value={})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_a_row_deleted_since_the_preview_is_db_or_fs_changed(
        self, _ffmpeg, _by_ids, mock_db
    ):
        op = _op()
        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff"), ops=[op]
        )

        assert response.result.skipped == [
            SkippedTrack(reason="db_or_fs_changed", track=op.track)
        ]


class TestConvertRealRun:
    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        # These tests mock ffmpeg away, so no output file ever exists to move
        # into place, to sweep, or to probe. TestApplyConvertedRecord and
        # TestProbeConvertedFile cover those halves directly.
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_no_ffmpeg_raises_immediately(self, _, mock_db):
        with pytest.raises(DependencyMissingError, match="FFmpeg"):
            convert(mock_db, ConvertRequest(title=["x"], format_out="aiff"))

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_no_matching_tracks_returns_empty_response(
        self, mock_gfc, _ffmpeg, mock_db
    ):
        _seed_filter(mock_gfc)

        response = convert(mock_db, ConvertRequest(title=["x"], format_out="aiff"))

        assert response.result.converted == []
        assert response.tracks == []
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api._convert.get_audio_info")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_codec_mismatch_skips_track_and_continues(
        self,
        mock_gfc,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        mock_update,
        mock_probe,
        mock_db,
        make_djmd_content_item,
    ):
        # Row A claims ALAC but holds AAC; row B is a genuine WAV. A is
        # skipped with codec_mismatch, B converts, and the run commits.
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        mismatched = make_djmd_content_item(ID="A", FileType=6, FolderPath="/A.m4a")
        good = make_djmd_content_item(ID="B", FileType=11, FolderPath="/B.wav")
        _seed_filter(mock_gfc, mismatched, good)
        _seed_db(mock_db, good)
        mock_probe.side_effect = lambda path: (
            _PROBE_AAC_M4A if path == "/A.m4a" else _PROBE_WAV_16_44
        )

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        assert [op.id for op in response.result.converted] == ["B"]
        assert [t.ID for t in response.tracks] == ["B"]
        assert {(s.track.ID, s.reason) for s in response.result.skipped if s.track} == {
            ("A", "codec_mismatch")
        }
        mock_run.assert_called_once()
        mock_update.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_the_committed_track_reflects_the_post_conversion_row(
        self,
        mock_gfc,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        _get_audio_info,
        mock_db,
        make_djmd_content_item,
    ):
        # A stale pre-write snapshot would still report the source WAV's
        # FileType and FolderPath: op.track is captured during
        # classification, before _apply_converted_record() ever touches the
        # row. Unlike the other TestConvertRealRun cases, this one lets
        # _apply_converted_record run for real so the row is actually
        # mutated, instead of mocking it away.
        mock_get_output.return_value = ("/A.aif", "A.aif", "/")
        content = make_djmd_content_item(ID="A", FileType=11, FolderPath="/A.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        with patch(
            "rekordbox_edit.api._convert._probe_converted_file",
            return_value=ConvertedFileProbe(
                audio_info=AudioInfo(
                    bit_depth=16,
                    sample_rate=44100,
                    channels=2,
                    bitrate=1411,
                    codec="pcm_s16le",
                    container="wav",
                    duration=180.0,
                ),
                file_size=123,
            ),
        ):
            response = convert(
                mock_db,
                ConvertRequest(
                    title=["x"],
                    format_out="aiff",
                    delete_originals="none",
                    overwrite=True,
                ),
            )

        aiff_file_type = get_file_type_for_format("aiff")
        assert response.result.converted[0].track.FileType == aiff_file_type
        assert response.result.converted[0].track.FolderPath == "/A.aif"
        assert response.tracks[0].FileType == aiff_file_type
        assert response.tracks[0].FolderPath == "/A.aif"

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_AAC_M4A)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_codec_mismatch_never_touches_files(
        self,
        mock_gfc,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # Every op mismatches: no ffmpeg run, no deletion, empty response.
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="A", FileType=6, FolderPath="/A.m4a")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="all", overwrite=True
            ),
        )

        mock_run.assert_not_called()
        mock_remove.assert_not_called()
        assert response.result.converted == []
        assert response.result.skipped[0].reason == "codec_mismatch"

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_successful_hi_res_commits(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_run,
        mock_update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)  # post-commit re-query returns the same row

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        mock_run.assert_called_once_with(
            "/in.wav",
            _temp_output_path("/out.aif"),
            _hi_res_output_kwargs(OutputFormats.AIFF, 44100),
            "aiff",
        )
        mock_update.assert_called_once()
        mock_db.session.commit.assert_called_once()
        op = response.result.converted[0]
        assert op.id == "1"
        assert op.source_file_type == "WAV"
        assert op.source_bit_depth == 16
        assert op.source_sample_rate == 44100
        assert op.output_file_type == "AIFF"
        assert op.output_bit_depth == 16
        assert op.output_sample_rate == 44100
        assert response.result.deleted == 0
        assert response.tracks[0].ID == "1"

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_deletes_originals_when_mode_all(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="all", overwrite=True
            ),
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_24_96)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_lossless_mode_keeps_originals_from_lossy_conversion(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"],
                format_out="aiff",
                delete_originals="lossless",
                overwrite=True,
            ),
        )

        mock_hi_res.assert_called_once()
        mock_remove.assert_not_called()
        assert response.result.deleted == 0
        assert len(response.result.converted) == 1

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_24_96)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_all_mode_deletes_originals_from_lossy_conversion(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="all", overwrite=True
            ),
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_lossless_mode_deletes_originals_from_lossless_conversion(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"],
                format_out="aiff",
                delete_originals="lossless",
                overwrite=True,
            ),
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_22)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_probed_below_target_source_converts_at_source_rate(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_run,
        mock_update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # DB fields say 16/44.1 but the probe reveals a 22.05 kHz source: the
        # conversion keeps the source rate instead of up-sampling, and the op
        # reports the rate that was actually encoded.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
        )

        mock_run.assert_called_once_with(
            "/in.wav",
            _temp_output_path("/out.aif"),
            _hi_res_output_kwargs(OutputFormats.AIFF, 22050),
            "aiff",
        )
        op = response.result.converted[0]
        assert op.output_sample_rate == 22050
        assert response.result.skipped == []

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_lossless_mode_keeps_originals_for_mp3_output(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _mp3,
        _update,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.mp3", "out.mp3", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"],
                format_out="mp3",
                delete_originals="lossless",
                overwrite=True,
            ),
        )

        mock_remove.assert_not_called()
        assert response.result.deleted == 0

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._rollback_session")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=False)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_conversion_failure_triggers_rollback_and_raises(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_rollback,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)

        with pytest.raises(ConvertAborted, match="Conversion failed"):
            convert(
                mock_db, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
            )

        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._rollback_session")
    @patch("rekordbox_edit.api._convert.os.remove", side_effect=KeyboardInterrupt)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_post_commit_interrupt_does_not_trigger_cleanup(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        _remove,
        mock_rollback,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # commit succeeds; KeyboardInterrupt in the delete-originals loop must
        # NOT cause _cleanup_converted_files to run (output already committed).
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        with pytest.raises(KeyboardInterrupt):
            convert(
                mock_db,
                ConvertRequest(
                    title=["x"],
                    format_out="aiff",
                    delete_originals="all",
                    overwrite=True,
                ),
            )

        mock_db.session.commit.assert_called_once()
        mock_rollback.assert_not_called()

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_preserves_op_order_in_response_tracks(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        # _get_output_path is called twice per content; just return matching paths
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        contents = [
            make_djmd_content_item(ID="A", FileType=11, FolderPath="/A.wav"),
            make_djmd_content_item(ID="B", FileType=11, FolderPath="/B.wav"),
            make_djmd_content_item(ID="C", FileType=11, FolderPath="/C.wav"),
        ]
        _seed_filter(mock_gfc, *contents)
        # Post-commit re-query returns in scrambled order
        _seed_db(mock_db, contents[2], contents[0], contents[1])

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        assert [op.id for op in response.result.converted] == ["A", "B", "C"]
        assert [t.ID for t in response.tracks] == ["A", "B", "C"]

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_post_commit_requery_failure_falls_back_to_pre_mutation(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_hi_res,
        mock_update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        # Only the post-commit select fails; the USN reservation shares this
        # execute() and would otherwise abort the batch first.
        reserved = []

        def _execute(statement, *args, **kwargs):
            if not reserved:
                reserved.append(statement)
                return Mock(scalar=Mock(return_value=1))
            raise RuntimeError("post-commit query failed")

        mock_db.session.execute.side_effect = _execute

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        # Commit happened
        mock_db.session.commit.assert_called_once()
        # Response built successfully (no ValidationError raised)
        assert len(response.result.converted) == 1
        assert response.result.converted[0].id == "1"
        # tracks came from the pre-commit fallback
        assert len(response.tracks) == 1
        assert response.tracks[0].ID == "1"

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_real_run_skips_when_output_exists_without_overwrite(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        mock_exists,
        _ffmpeg,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)

        # Default overwrite=False with output path existing -> classifier should skip.
        response = convert(mock_db, ConvertRequest(title=["x"], format_out="aiff"))

        assert response.result.converted == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "output_file_exists"
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api._convert._rollback_session")
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_missing_source_is_skipped_rather_than_aborting(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_rollback,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
        )

        assert response.result.converted == []
        assert [s.reason for s in response.result.skipped] == ["file_not_found"]
        mock_rollback.assert_not_called()
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._rollback_session")
    @patch(
        "rekordbox_edit.api._convert._apply_converted_record",
        side_effect=RuntimeError("DB error"),
    )
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_db_update_exception_triggers_rollback_and_reraises(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _hi_res,
        _update,
        mock_rollback,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)

        with pytest.raises(ConvertAborted, match="DB error"):
            convert(
                mock_db, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
            )
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_mp3_format_runs_mp3_kwargs(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        _update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.mp3", "out.mp3", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        convert(mock_db, ConvertRequest(title=["x"], format_out="mp3", overwrite=True))

        mock_run.assert_called_once_with(
            "/in.wav", _temp_output_path("/out.mp3"), _mp3_output_kwargs(44100), "mp3"
        )

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_skips_deletion_when_mode_none(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _hi_res,
        _update,
        mock_remove,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="1", FileType=11, FolderPath="/in.wav")
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        mock_remove.assert_not_called()
        assert response.result.deleted == 0

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._update_anlz_paths")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_updates_anlz_paths_after_commit(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _run,
        _update,
        mock_anlz,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/music/out.aif", "out.aif", "/music")
        content = make_djmd_content_item(
            ID="1", FileType=11, FolderPath="/music/in.wav"
        )
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        mock_db.session.commit.assert_called_once()
        mock_anlz.assert_called_once_with(mock_db, content, "out.aif")

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch(
        "rekordbox_edit.api._convert._update_anlz_paths",
        side_effect=RuntimeError("ANLZ write failed"),
    )
    @patch("rekordbox_edit.api._convert._rollback_session")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_anlz_update_failure_is_non_fatal(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _run,
        _update,
        mock_rollback,
        _anlz,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/music/out.aif", "out.aif", "/music")
        content = make_djmd_content_item(
            ID="1", FileType=11, FolderPath="/music/in.wav"
        )
        _seed_filter(mock_gfc, content)
        _seed_db(mock_db, content)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"], format_out="aiff", delete_originals="none", overwrite=True
            ),
        )

        # The committed conversion stands; a failed PPTH refresh does not roll back.
        mock_db.session.commit.assert_called_once()
        mock_rollback.assert_not_called()
        assert len(response.result.converted) == 1


# ── Helper-function tests (preserved from existing file) ──────────────────


class TestEncodeJob:
    def test_carries_plain_values_off_the_row(self, make_djmd_content_item):
        # Workers run off the main thread, so the job may hold no ORM object.
        content = make_djmd_content_item(
            ID="7", FileType=11, FolderPath="/in.wav", FileNameL="in.wav"
        )
        op = ConvertOp(
            id="7",
            source_path="/in.wav",
            output_path="/out.aif",
            track=Track(ID="7", FileNameL="in.wav", FolderPath="/in.wav"),
        )

        job = _encode_job_for(content, op, "AIFF")

        assert (job.source_path, job.file_type) == ("/in.wav", 11)
        assert job.temp_path == _temp_output_path("/out.aif")
        assert not any(isinstance(v, type(content)) for v in job.__dict__.values())


class TestEncodeOne:
    """The worker half. Every case here must reach its answer without a session."""

    _BASE = _EncodeJob(
        source_path="/in.wav",
        file_name="in.wav",
        file_type=11,
        output_path="/out.aif",
        temp_path="/.rbe-convert-1-out.aif",
        output_format="AIFF",
    )

    def _job(self, **overrides) -> _EncodeJob:
        return replace(self._BASE, **overrides)

    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=False)
    def test_a_missing_source_is_reported_as_a_skip(self, _exists):
        result = _encode_one(self._job())

        assert result.skipped is not None
        assert result.skipped.reason == "file_not_found"
        assert result.probe is None

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_AAC_M4A)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    def test_a_codec_mismatch_is_reported_as_a_skip(self, _exists, _probe):
        result = _encode_one(self._job(file_type=11))  # 11 is WAV, probe says aac

        assert result.skipped is not None
        assert result.skipped.reason == "codec_mismatch"

    @patch("rekordbox_edit.api._convert._remove_temp_file")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=False)
    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    def test_a_failed_encode_cleans_up_its_own_temp(
        self, _exists, _probe, _run, mock_remove
    ):
        with pytest.raises(RuntimeError, match="Conversion failed"):
            _encode_one(self._job())

        mock_remove.assert_called_once_with("/.rbe-convert-1-out.aif")

    @patch("rekordbox_edit.api._convert._probe_converted_file")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_24_96)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    def test_a_hi_res_source_reports_a_lossy_conversion(
        self, _exists, _probe, mock_run, mock_converted
    ):
        result = _encode_one(self._job())

        assert result.skipped is None
        assert result.is_lossless is False
        assert result.output_sample_rate == 44100
        # The encode targets the temp path, never the final one.
        assert mock_run.call_args.args[1] == "/.rbe-convert-1-out.aif"

    @patch("rekordbox_edit.api._convert._probe_converted_file")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    def test_an_at_target_source_reports_a_lossless_conversion(
        self, _exists, _probe, _run, _converted
    ):
        assert _encode_one(self._job()).is_lossless is True

    @patch("rekordbox_edit.api._convert._probe_converted_file")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    def test_mp3_output_is_never_lossless(self, _exists, _probe, _run, _converted):
        result = _encode_one(self._job(output_format="MP3", output_path="/out.mp3"))

        assert result.is_lossless is False


class TestConvertPerFileCommits:
    """A failure partway through keeps the files that already converted."""

    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg")
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_a_mid_batch_failure_keeps_the_earlier_commits(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        _update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        # The first file encodes, the second fails, the third is never reached.
        mock_run.side_effect = [True, False]
        contents = [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in (1, 2, 3)
        ]
        _seed_filter(mock_gfc, *contents)

        with pytest.raises(ConvertAborted) as raised:
            convert(
                mock_db,
                ConvertRequest(
                    title=["x"], format_out="aiff", overwrite=True, threads=1
                ),
            )

        assert raised.value.converted == 1
        assert raised.value.not_attempted == 1
        assert raised.value.failed_path == "/in2.wav"
        assert mock_db.session.commit.call_count == 1
        # Nothing beyond the failure was encoded: at one worker the pool never
        # runs ahead of the drain point.
        assert mock_run.call_count == 2

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists")
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_a_source_that_vanished_does_not_stop_the_batch(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        _run,
        _update,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # The user can take minutes at the confirm prompt, so a source moved in
        # that window is routine. Skip it and keep converting the rest.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        mock_exists.side_effect = lambda path: path != "/in2.wav"
        contents = [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in (1, 2, 3)
        ]
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        response = convert(
            mock_db, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
        )

        assert [op.id for op in response.result.converted] == ["1", "3"]
        assert [(s.track.ID, s.reason) for s in response.result.skipped if s.track] == [
            ("2", "file_not_found")
        ]
        assert mock_db.session.commit.call_count == 2

    @patch("rekordbox_edit.api._convert.os.remove")
    @patch("rekordbox_edit.api._convert.get_audio_info")
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_the_delete_policy_is_decided_per_file(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _run,
        _update,
        mock_probe,
        mock_remove,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        # First source is already at the target, second is hi-res: only the
        # first conversion is lossless, so only its original may be deleted.
        mock_probe.side_effect = [_PROBE_WAV_16_44, _PROBE_WAV_24_96]
        contents = [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in (1, 2)
        ]
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        response = convert(
            mock_db,
            ConvertRequest(
                title=["x"],
                format_out="aiff",
                overwrite=True,
                delete_originals="lossless",
            ),
        )

        assert mock_db.session.commit.call_count == 2
        assert response.result.deleted == 1
        mock_remove.assert_called_once_with("/in1.wav")


class TestConvertParallelEncoding:
    """Properties that only appear once more than one encode is in flight."""

    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @staticmethod
    def _contents(make_djmd_content_item, count):
        return [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in range(1, count + 1)
        ]

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg")
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_results_follow_submission_order_not_completion_order(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        _apply,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # rbe convert --print ids feeds pipelines, so the order of the ids it
        # emits is part of the contract. Finish the encodes backwards.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        delays = {"/in1.wav": 0.06, "/in2.wav": 0.03, "/in3.wav": 0.0}

        def _slow(src, *_args, **_kwargs):
            time.sleep(delays[src])
            return True

        mock_run.side_effect = _slow
        contents = self._contents(make_djmd_content_item, 3)
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        response = convert(
            mock_db,
            ConvertRequest(title=["x"], format_out="aiff", overwrite=True, threads=3),
        )

        assert [op.id for op in response.result.converted] == ["1", "2", "3"]

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_no_worker_touches_the_session(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _run,
        _apply,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # The session is not thread-safe, and USN maintenance will depend on
        # every database touch staying on the main thread. Record who calls.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        main_thread = threading.current_thread().ident
        callers = []
        mock_db.session.commit.side_effect = lambda: callers.append(
            threading.current_thread().ident
        )
        contents = self._contents(make_djmd_content_item, 4)
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        convert(
            mock_db,
            ConvertRequest(title=["x"], format_out="aiff", overwrite=True, threads=4),
        )

        assert callers == [main_thread] * 4

    @patch("rekordbox_edit.api._convert._remove_temp_file")
    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg")
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_an_abort_wastes_at_most_the_pool_width(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        _apply,
        _probe,
        mock_remove,
        mock_db,
        make_djmd_content_item,
    ):
        # Ten files, two workers, the second fails: at most two encodes run
        # ahead of the drain, so the remaining eight are never started.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        mock_run.side_effect = lambda src, *a, **k: src != "/in2.wav"
        contents = self._contents(make_djmd_content_item, 10)
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        with pytest.raises(ConvertAborted) as raised:
            convert(
                mock_db,
                ConvertRequest(
                    title=["x"], format_out="aiff", overwrite=True, threads=2
                ),
            )

        assert raised.value.converted == 1
        assert mock_run.call_count <= 3
        # Whatever ran ahead and succeeded had its temp file cleaned up.
        assert mock_remove.called


class TestConvertProgressReporting:
    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_every_file_is_reported_started_then_finished(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _run,
        _apply,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        events = []

        class _Recorder:
            def batch_size(self, total):
                events.append(("batch_size", total))

            def started(self, index, file_name):
                events.append(("started", index))

            def finished(self, index, converted):
                events.append(("finished", index, converted))

        contents = [
            make_djmd_content_item(
                ID=str(i), FileType=11, FolderPath=f"/in{i}.wav", FileNameL=f"in{i}.wav"
            )
            for i in (1, 2, 3)
        ]
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        convert(
            mock_db,
            ConvertRequest(title=["x"], format_out="aiff", overwrite=True, threads=1),
            progress=_Recorder(),
        )

        assert events[0] == ("batch_size", 3)
        assert [e for e in events if e[0] == "started"] == [
            ("started", 0),
            ("started", 1),
            ("started", 2),
        ]
        assert [e for e in events if e[0] == "finished"] == [
            ("finished", 0, True),
            ("finished", 1, True),
            ("finished", 2, True),
        ]

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists")
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_a_skipped_file_is_reported_as_not_converted(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        _run,
        _apply,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # The overall bar still advances for a skip, so the caller has to be
        # told the difference rather than inferring it from a missing call.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        mock_exists.side_effect = lambda path: path != "/in2.wav"
        finished = []

        class _Recorder:
            def batch_size(self, total):
                pass

            def started(self, index, file_name):
                pass

            def finished(self, index, converted):
                finished.append((index, converted))

        contents = [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in (1, 2, 3)
        ]
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        convert(
            mock_db,
            ConvertRequest(title=["x"], format_out="aiff", overwrite=True, threads=1),
            progress=_Recorder(),
        )

        assert finished == [(0, True), (1, False), (2, True)]


class TestConvertLogging:
    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_the_api_leaves_the_batch_summary_to_the_caller(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _run,
        _apply,
        _probe,
        mock_db,
        make_djmd_content_item,
        caplog,
    ):
        # The CLI prints "Converted N files to X". The API printing it too put
        # the line on screen twice.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )
        contents = [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in (1, 2)
        ]
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        with caplog.at_level(logging.INFO, logger="rekordbox_edit.api._convert"):
            convert(
                mock_db, ConvertRequest(title=["x"], format_out="aiff", overwrite=True)
            )

        assert "Converted 2 files" not in caplog.text


class TestConvertInterrupt:
    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api._convert.os.replace"),
            patch("rekordbox_edit.api._convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api._convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.api._convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api._convert._apply_converted_record")
    @patch("rekordbox_edit.api._convert._run_ffmpeg")
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api._convert._get_output_path")
    @patch("rekordbox_edit.api._convert.get_file_type_for_format")
    @patch("rekordbox_edit.api._convert.get_filtered_content")
    def test_ctrl_c_keeps_the_files_already_converted(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_run,
        _apply,
        _probe,
        mock_db,
        make_djmd_content_item,
    ):
        # Per-file commits make an interrupt cheap: what finished is committed.
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.side_effect = lambda content, fmt: (
            f"/{content.ID}.aif",
            f"{content.ID}.aif",
            "/",
        )

        def _interrupt_on_second(src, *_a, **_k):
            if src == "/in2.wav":
                raise KeyboardInterrupt
            return True

        mock_run.side_effect = _interrupt_on_second
        contents = [
            make_djmd_content_item(ID=str(i), FileType=11, FolderPath=f"/in{i}.wav")
            for i in (1, 2, 3)
        ]
        _seed_filter(mock_gfc, *contents)
        _seed_db(mock_db, *contents)

        with pytest.raises(ConvertAborted) as raised:
            convert(
                mock_db,
                ConvertRequest(
                    title=["x"], format_out="aiff", overwrite=True, threads=1
                ),
            )

        assert raised.value.converted == 1
        assert raised.value.not_attempted == 1
        assert mock_db.session.commit.call_count == 1


class TestClassifyFidelity:
    @pytest.mark.parametrize(
        "bit_depth,sample_rate,expected",
        [
            (16, 44100, ("lossless", 44100)),
            (24, 44100, ("lossy", 44100)),
            (16, 96000, ("lossy", 44100)),
            (24, 96000, ("lossy", 44100)),
            (None, 44100, ("lossy", 44100)),  # unknown bit depth: keep originals
            (8, 44100, ("lossy", 44100)),
            (16, 22050, ("lossless", 22050)),  # rate clamps to the source
            (24, 22050, ("lossy", 22050)),
        ],
    )
    def test_fidelity_classification(self, bit_depth, sample_rate, expected):
        audio_info: AudioInfo = {
            "bit_depth": bit_depth,
            "sample_rate": sample_rate,
            "channels": 2,
            "bitrate": None,
            "codec": "flac",
            "container": "flac",
            "duration": None,
        }

        assert _classify_fidelity(audio_info) == expected


class TestRunFfmpeg:
    @pytest.fixture
    def chain(self):
        """The mocked ffmpeg builder chain, ending at the object .run() lands on."""
        with (
            patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True),
            patch("rekordbox_edit.api._convert.ffmpeg") as mock_ffmpeg,
        ):
            output = Mock()
            mock_ffmpeg.input.return_value.output.return_value = output
            output.overwrite_output.return_value = output
            output.global_args.return_value = output
            yield mock_ffmpeg, output

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_ffmpeg_not_found_raises(self, _):
        with pytest.raises(DependencyMissingError, match="not found in PATH"):
            _run_ffmpeg("in.flac", "out.aiff", {"acodec": "pcm_s16be"}, "aiff")

    def test_success_passes_kwargs_through(self, chain):
        mock_ffmpeg, output = chain
        output.run.return_value = None

        result = _run_ffmpeg(
            "in.flac", "out.wav", {"acodec": "pcm_s16le", "ar": 44100}, "wav"
        )

        assert result is True
        mock_ffmpeg.input.assert_called_once_with("in.flac")
        mock_ffmpeg.input.return_value.output.assert_called_once_with(
            "out.wav", acodec="pcm_s16le", ar=44100
        )

    def test_the_child_is_kept_off_the_terminal(self, chain):
        # Without -nostdin, ffmpeg puts the tty in non-canonical mode to watch
        # for keys like "q". Concurrent encodes race on restoring it and the
        # loser leaves the shell echoing ^M instead of accepting Enter.
        _, output = chain
        output.run.return_value = None

        _run_ffmpeg("in.flac", "out.aiff", {}, "aiff")

        output.global_args.assert_called_once_with("-nostdin")

    def test_ffmpeg_error_returns_false(self, chain):
        _, output = chain
        output.run.side_effect = ffmpeg.Error("cmd", b"stdout", b"stderr")

        assert _run_ffmpeg("in.flac", "out.aiff", {}, "aiff") is False

    def test_ffmpeg_error_no_stderr_returns_false(self, chain):
        _, output = chain
        output.run.side_effect = ffmpeg.Error("cmd", b"stdout", None)

        assert _run_ffmpeg("in.flac", "out.aiff", {}, "aiff") is False

    def test_unexpected_exception_reraises(self, chain):
        _, output = chain
        output.run.side_effect = RuntimeError("disk full")

        with pytest.raises(RuntimeError, match="disk full"):
            _run_ffmpeg("in.flac", "out.aiff", {}, "aiff")


class TestHiResOutputKwargs:
    def test_aiff(self):
        assert _hi_res_output_kwargs(OutputFormats.AIFF, 44100) == {
            "acodec": "pcm_s16be",
            "ar": 44100,
            "map_metadata": 0,
            "write_id3v2": 1,
        }

    def test_wav(self):
        assert _hi_res_output_kwargs(OutputFormats.WAV, 44100) == {
            "acodec": "pcm_s16le",
            "ar": 44100,
            "map_metadata": 0,
            "write_id3v2": 1,
        }

    def test_flac_pins_bit_depth_via_sample_fmt(self):
        kwargs = _hi_res_output_kwargs(OutputFormats.FLAC, 44100)
        assert kwargs["acodec"] == "flac"
        assert kwargs["sample_fmt"] == "s16"

    def test_uses_given_sample_rate(self):
        assert _hi_res_output_kwargs(OutputFormats.WAV, 22050)["ar"] == 22050

    def test_unsupported_format_raises(self):
        fake_format = Mock()
        fake_format.value = "xyz"
        with pytest.raises(Exception, match="Unsupported hi-res format"):
            _hi_res_output_kwargs(fake_format, 44100)


class TestMp3OutputKwargs:
    def test_fixed_lame_settings(self):
        assert _mp3_output_kwargs(44100) == {
            "acodec": "libmp3lame",
            "audio_bitrate": "320k",
            "ar": 44100,
            "sample_fmt": "s16p",
            "map_metadata": 0,
            "write_id3v2": 1,
        }

    def test_uses_given_sample_rate(self):
        assert _mp3_output_kwargs(22050)["ar"] == 22050


class TestProbeConvertedFile:
    """The probe half runs off the main thread once encoding is parallel, so it
    must reach its answer from the filesystem alone."""

    @patch("rekordbox_edit.api._convert.os.path.getsize", return_value=987654)
    @patch("rekordbox_edit.api._convert.get_audio_info")
    def test_reads_size_and_audio_without_a_session(
        self, mock_get_audio_info, _mock_getsize
    ):
        mock_get_audio_info.return_value = {"bitrate": 1411, "bit_depth": 16}

        probe = _probe_converted_file("/path/to/output.aiff", "AIFF")

        assert probe.file_size == 987654
        assert probe.audio_info["bitrate"] == 1411
        assert probe.audio_info["bit_depth"] == 16

    @patch("rekordbox_edit.api._convert.os.path.getsize", return_value=1)
    @patch("rekordbox_edit.api._convert.get_audio_info")
    def test_mp3_without_a_probed_bitrate_assumes_320(
        self, mock_get_audio_info, _mock_getsize
    ):
        mock_get_audio_info.return_value = {"bitrate": None}

        assert (
            _probe_converted_file("/path/to/output.mp3", "MP3").audio_info["bitrate"]
            == 320
        )


def _converted(bitrate=1000, bit_depth=16, sample_rate=44100, file_size=987654):
    """A ConvertedFileProbe with a complete AudioInfo, for the apply half.

    The apply half takes the probe as a value, so these tests need no file on
    disk and no ffmpeg.
    """
    return ConvertedFileProbe(
        audio_info=AudioInfo(
            bit_depth=bit_depth,
            sample_rate=sample_rate,
            channels=2,
            bitrate=bitrate,
            codec="pcm_s16be",
            container="aiff",
            duration=180.0,
        ),
        file_size=file_size,
    )


class TestApplyConvertedRecord:
    def test_sets_file_size_from_the_probe(self, make_djmd_content_item):
        content = make_djmd_content_item(ID=123, BitDepth=24)

        _apply_converted_record(
            content, _converted(), "output.aiff", "/path/to", "AIFF"
        )

        assert content.FileSize == 987654

    def test_normalizes_folder_path_separators(self, make_djmd_content_item):
        content = make_djmd_content_item(ID=123, BitDepth=24)

        # new_folder arrives with Windows separators, as os.path.dirname yields.
        _apply_converted_record(
            content, _converted(), "song.aiff", r"A:\Music\dir", "AIFF"
        )

        assert content.FolderPath == "A:/Music/dir/song.aiff"

    def test_org_folder_path_follows_when_it_matched_old_path(
        self, make_djmd_content_item
    ):
        content = make_djmd_content_item(
            ID=123, BitDepth=24, FolderPath="A:/Music/song.wav"
        )
        content.OrgFolderPath = "A:/Music/song.wav"  # matches the old path

        _apply_converted_record(content, _converted(), "song.aiff", "A:/Music", "AIFF")

        assert content.OrgFolderPath == "A:/Music/song.aiff"

    def test_org_folder_path_left_alone_when_it_differed(self, make_djmd_content_item):
        content = make_djmd_content_item(
            ID=123, BitDepth=24, FolderPath="A:/Music/song.wav"
        )
        content.OrgFolderPath = "A:/OriginalImport/song.wav"  # a real original

        _apply_converted_record(content, _converted(), "song.aiff", "A:/Music", "AIFF")

        assert content.OrgFolderPath == "A:/OriginalImport/song.wav"

    def test_flac_sets_bitrate_zero(self, make_djmd_content_item):
        content = make_djmd_content_item(ID=123, BitDepth=24)

        _apply_converted_record(
            content, _converted(bit_depth=24), "output.flac", "/path/to", "FLAC"
        )

        assert content.FileNameL == "output.flac"
        assert content.FolderPath == "/path/to/output.flac"
        assert content.BitRate == 0

    def test_hi_res_output_updates_bit_depth_and_sample_rate(
        self, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID=123, BitDepth=24, SampleRate=96000)

        _apply_converted_record(
            content, _converted(bitrate=1411), "output.aiff", "/path/to", "AIFF"
        )

        assert content.BitDepth == 16
        assert content.SampleRate == 44100

    def test_unknown_probe_values_leave_db_fields_unchanged(
        self, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID=123, BitDepth=24, SampleRate=96000)

        _apply_converted_record(
            content,
            _converted(bitrate=1411, bit_depth=None, sample_rate=None),
            "output.aiff",
            "/path/to",
            "AIFF",
        )

        assert content.BitDepth == 24
        assert content.SampleRate == 96000

    def test_mp3_sets_bitrate_from_the_probe(self, make_djmd_content_item):
        content = make_djmd_content_item(ID=123)

        _apply_converted_record(
            content,
            _converted(bitrate=320, bit_depth=None),
            "output.mp3",
            "/path/to",
            "MP3",
        )

        assert content.BitRate == 320

    def test_mp3_output_updates_bit_depth_and_sample_rate(self, make_djmd_content_item):
        content = make_djmd_content_item(ID=123, BitDepth=24, SampleRate=96000)

        _apply_converted_record(
            content,
            _converted(bitrate=320, bit_depth=None, sample_rate=48000),
            "output.mp3",
            "/path/to",
            "MP3",
        )

        assert content.BitDepth == 16
        assert content.SampleRate == 48000


class TestRollbackSession:
    def test_rolls_back_session(self, mock_db):
        _rollback_session(mock_db)
        mock_db.session.rollback.assert_called_once()

    def test_no_db_is_noop(self):
        _rollback_session(None)

    def test_no_session_is_noop(self):
        db = Mock()
        db.session = None
        _rollback_session(db)

    @patch("rekordbox_edit.api._convert._logger")
    def test_rollback_exception_logs_critical_and_reraises(self, mock_logger, mock_db):
        mock_db.session.rollback.side_effect = Exception("DB connection lost")

        with pytest.raises(Exception, match="DB connection lost"):
            _rollback_session(mock_db)

        assert mock_logger.critical.call_count == 2


class TestGetOutputPath:
    def test_basic_path(self, make_djmd_content_item):
        content = make_djmd_content_item(
            FileNameL="song.flac", FolderPath="/music/folder/song.flac"
        )

        output_path, output_filename, src_dirname = _get_output_path(content, "aiff")

        assert output_path == os.path.normpath("/music/folder/song.aiff")
        assert output_filename == "song.aiff"
        assert src_dirname == os.path.normpath("/music/folder")

    def test_mp3_extension(self, make_djmd_content_item):
        content = make_djmd_content_item(
            FileNameL="song.flac", FolderPath="/music/folder/song.flac"
        )

        output_path, output_filename, _ = _get_output_path(content, "mp3")

        assert output_path == os.path.normpath("/music/folder/song.mp3")
        assert output_filename == "song.mp3"


class TestConvertStampsUsns:
    """Against the real library, since stamping is a database behavior."""

    _COUNTER = text(
        "SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'"
    )

    @patch(
        "rekordbox_edit.api._convert._probe_converted_file",
        # A real probe, not a Mock: these values are written to actual columns.
        return_value=ConvertedFileProbe(
            audio_info=AudioInfo(
                bit_depth=16,
                sample_rate=44100,
                channels=2,
                bitrate=1411,
                codec="pcm_s16be",
                container="aiff",
                duration=180.0,
            ),
            file_size=123456,
        ),
    )
    @patch("rekordbox_edit.api._convert.os.replace")
    @patch("rekordbox_edit.api._convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api._convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api._convert.os.listdir", return_value=[])
    @patch(
        "rekordbox_edit.api._convert.get_audio_info",
        return_value={**_PROBE_WAV_16_44, "codec": "flac", "container": "flac"},
    )
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_each_converted_row_takes_one_usn(
        self, _ffmpeg, _probe, _listdir, _exists, _run, _replace, _converted, db
    ):
        session = require_session(db)
        start = session.execute(self._COUNTER).scalar()
        # FLAC sources: convertable, and the fixture has three of them.
        tracks = db.get_content().filter_by(FileType=5).limit(2).all()
        assert len(tracks) == 2, "fixture should carry at least two FLAC tracks"

        response = convert(
            db,
            ConvertRequest(
                format_out="aiff",
                overwrite=True,
                delete_originals="none",
                track_ids=[str(t.ID) for t in tracks],
                threads=1,
            ),
        )

        converted = len(response.result.converted)
        assert converted == 2
        assert session.execute(self._COUNTER).scalar() == start + converted
        # Per-file commits mean per-file stamps, in the order they converted.
        assert sorted(t.rb_local_usn for t in tracks) == [start + 1, start + 2]
