import os
from unittest.mock import Mock, patch

import ffmpeg
import pytest

from rekordbox_edit.api.convert import (
    TEMP_PREFIX,
    ConvertAborted,
    ConvertedFileProbe,
    _apply_converted_record,
    _classify_convert,
    _classify_fidelity,
    _get_output_path,
    _hi_res_output_kwargs,
    _mp3_output_kwargs,
    _probe_converted_file,
    _rollback_session,
    _run_ffmpeg,
    _sweep_orphan_temp_files,
    _temp_output_path,
    _update_anlz_paths,
    convert,
)
from rekordbox_edit.models import (
    ConvertOp,
    ConvertRequest,
    ConvertResponse,
    SkippedTrack,
)
from rekordbox_edit.utils import AudioInfo, OutputFormats

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
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_already_target_format(self, mock_get_type, make_djmd_content_item):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="1", FileType=1)  # already AIFF

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, SkippedTrack)
        assert result.reason == "already_target_format"

    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_lossy_source_as_unsupported(
        self, mock_get_type, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="2", FileType=4)  # M4A: lossy source

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, SkippedTrack)
        assert result.reason == "unsupported_source_format"

    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_unmapped_source_as_unsupported(
        self, mock_get_type, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="9", FileType=20)  # e.g. a video file

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, SkippedTrack)
        assert result.reason == "unsupported_source_format"

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_below_target_sample_rate_clamps_to_source(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="6", FileType=11, SampleRate=22050)

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, ConvertOp)
        assert result.output_sample_rate == 22050

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_mp3_output_ignores_source_sample_rate(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.mp3", "out.mp3", "/")
        content = make_djmd_content_item(ID="7", FileType=11, SampleRate=22050)

        result = _classify_convert(content, ConvertRequest(format_out="mp3"))

        assert isinstance(result, ConvertOp)
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
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

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, ConvertOp)
        assert result.output_bit_depth == 16
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_output_conflict_when_no_overwrite(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="3", FileType=11)  # WAV

        result = _classify_convert(
            content, ConvertRequest(format_out="aiff", overwrite=False)
        )

        assert isinstance(result, SkippedTrack)
        assert result.reason == "output_file_exists"

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_overwrite_allows_conflict(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="3", FileType=11, FolderPath="/in.wav")

        result = _classify_convert(
            content, ConvertRequest(format_out="aiff", overwrite=True)
        )

        assert isinstance(result, ConvertOp)
        assert result.source_path == "/in.wav"
        assert result.output_path == "/out.aif"

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
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

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, ConvertOp)
        assert result.id == "4"
        assert result.source_path == "/music/song.wav"
        assert result.output_path == "/music/song.aif"

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
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

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, ConvertOp)
        assert result.source_file_type == "WAV"
        assert result.source_bit_depth == 24
        assert result.source_sample_rate == 96000
        assert result.output_file_type == "AIFF"
        assert result.output_bit_depth == 16
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_mp3_output_targets_conversion_default(
        self, mock_get_type, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mock_get_output.return_value = ("/music/song.mp3", "song.mp3", "/music")
        content = make_djmd_content_item(ID="7", FileType=11)

        result = _classify_convert(content, ConvertRequest(format_out="mp3"))

        assert isinstance(result, ConvertOp)
        assert result.output_file_type == "MP3"
        assert result.output_bit_depth == 16
        assert result.output_sample_rate == 44100

    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    def test_alac_source_is_convertible(
        self, mock_get_output, mock_exists, make_djmd_content_item
    ):
        mock_get_output.return_value = ("/out.aif", "out.aif", "/")
        content = make_djmd_content_item(ID="10", FileType=6, FolderPath="/in.m4a")

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

        assert isinstance(result, ConvertOp)
        assert result.source_file_type == "ALAC"

    def test_aac_source_skipped_as_unsupported(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="11", FileType=4)

        result = _classify_convert(content, ConvertRequest(format_out="aiff"))

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
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        response = convert(mock_db, ConvertRequest(format_out="aiff"), dry_run=True)

        assert isinstance(response, ConvertResponse)
        assert response.result.format_out == "aiff"
        assert len(response.result.converted) == 1
        assert response.result.deleted == 0
        assert response.tracks[0].ID == "1"
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        response = convert(mock_db, ConvertRequest(format_out="aiff"), dry_run=True)

        assert response.result.converted == []
        assert response.tracks == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "already_target_format"


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


class TestConvertRealRun:
    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        # These tests mock ffmpeg away, so no output file ever exists to move
        # into place, to sweep, or to probe. TestApplyConvertedRecord and
        # TestProbeConvertedFile cover those halves directly.
        with (
            patch("rekordbox_edit.api.convert.os.replace"),
            patch("rekordbox_edit.api.convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api.convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_no_ffmpeg_raises_immediately(self, _, mock_db):
        with pytest.raises(RuntimeError, match="FFmpeg"):
            convert(mock_db, ConvertRequest(format_out="aiff"))

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_no_matching_tracks_returns_empty_response(
        self, mock_gfc, _ffmpeg, mock_db
    ):
        _seed_filter(mock_gfc)

        response = convert(mock_db, ConvertRequest(format_out="aiff"))

        assert response.result.converted == []
        assert response.tracks == []
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
        )

        assert [op.id for op in response.result.converted] == ["B"]
        assert [t.ID for t in response.tracks] == ["B"]
        assert {(s.id, s.reason) for s in response.result.skipped} == {
            ("A", "codec_mismatch")
        }
        mock_run.assert_called_once()
        mock_update.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_AAC_M4A)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="all", overwrite=True),
        )

        mock_run.assert_not_called()
        mock_remove.assert_not_called()
        assert response.result.converted == []
        assert response.result.skipped[0].reason == "codec_mismatch"

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
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

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="all", overwrite=True),
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_24_96)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
                format_out="aiff", delete_originals="lossless", overwrite=True
            ),
        )

        mock_hi_res.assert_called_once()
        mock_remove.assert_not_called()
        assert response.result.deleted == 0
        assert len(response.result.converted) == 1

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_24_96)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="all", overwrite=True),
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
                format_out="aiff", delete_originals="lossless", overwrite=True
            ),
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_22)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        response = convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))

        mock_run.assert_called_once_with(
            "/in.wav",
            _temp_output_path("/out.aif"),
            _hi_res_output_kwargs(OutputFormats.AIFF, 22050),
            "aiff",
        )
        op = response.result.converted[0]
        assert op.output_sample_rate == 22050
        assert response.result.skipped == []

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
                format_out="mp3", delete_originals="lossless", overwrite=True
            ),
        )

        mock_remove.assert_not_called()
        assert response.result.deleted == 0

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._rollback_session")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=False)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        with pytest.raises(RuntimeError, match="Conversion failed"):
            convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))

        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._rollback_session")
    @patch("rekordbox_edit.api.convert.os.remove", side_effect=KeyboardInterrupt)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
                    format_out="aiff", delete_originals="all", overwrite=True
                ),
            )

        mock_db.session.commit.assert_called_once()
        mock_rollback.assert_not_called()

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
        )

        assert [op.id for op in response.result.converted] == ["A", "B", "C"]
        assert [t.ID for t in response.tracks] == ["A", "B", "C"]

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
        # Mock the post-commit select to raise
        mock_db.session.execute.side_effect = RuntimeError("post-commit query failed")

        response = convert(
            mock_db,
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
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
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
        response = convert(mock_db, ConvertRequest(format_out="aiff"))

        assert response.result.converted == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "output_file_exists"
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.convert._rollback_session")
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        response = convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))

        assert response.result.converted == []
        assert [s.reason for s in response.result.skipped] == ["file_not_found"]
        mock_rollback.assert_not_called()
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._rollback_session")
    @patch(
        "rekordbox_edit.api.convert._apply_converted_record",
        side_effect=RuntimeError("DB error"),
    )
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        with pytest.raises(RuntimeError, match="DB error"):
            convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        convert(mock_db, ConvertRequest(format_out="mp3", overwrite=True))

        mock_run.assert_called_once_with(
            "/in.wav", _temp_output_path("/out.mp3"), _mp3_output_kwargs(44100), "mp3"
        )

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
        )

        mock_remove.assert_not_called()
        assert response.result.deleted == 0

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._update_anlz_paths")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
        )

        mock_db.session.commit.assert_called_once()
        mock_anlz.assert_called_once_with(mock_db, content, "out.aif")

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch(
        "rekordbox_edit.api.convert._update_anlz_paths",
        side_effect=RuntimeError("ANLZ write failed"),
    )
    @patch("rekordbox_edit.api.convert._rollback_session")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            ConvertRequest(format_out="aiff", delete_originals="none", overwrite=True),
        )

        # The committed conversion stands; a failed PPTH refresh does not roll back.
        mock_db.session.commit.assert_called_once()
        mock_rollback.assert_not_called()
        assert len(response.result.converted) == 1


# ── Helper-function tests (preserved from existing file) ──────────────────


class TestConvertPerFileCommits:
    """A failure partway through keeps the files that already converted."""

    @pytest.fixture(autouse=True)
    def _stub_temp_file_moves(self):
        with (
            patch("rekordbox_edit.api.convert.os.replace"),
            patch("rekordbox_edit.api.convert.os.listdir", return_value=[]),
            patch("rekordbox_edit.api.convert._probe_converted_file"),
        ):
            yield

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg")
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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
            convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))

        assert raised.value.converted == 1
        assert raised.value.not_attempted == 1
        assert raised.value.failed_path == "/in2.wav"
        assert mock_db.session.commit.call_count == 1
        assert mock_run.call_count == 2

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value=_PROBE_WAV_16_44)
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists")
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        response = convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))

        assert [op.id for op in response.result.converted] == ["1", "3"]
        assert [(s.id, s.reason) for s in response.result.skipped] == [
            ("2", "file_not_found")
        ]
        assert mock_db.session.commit.call_count == 2

    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.api.convert._apply_converted_record")
    @patch("rekordbox_edit.api.convert._run_ffmpeg", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
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

        response = convert(mock_db, ConvertRequest(format_out="aiff", overwrite=True))

        assert mock_db.session.commit.call_count == 2
        assert response.result.deleted == 1
        mock_remove.assert_called_once_with("/in1.wav")


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
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_ffmpeg_not_found_raises(self, _):
        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            _run_ffmpeg("in.flac", "out.aiff", {"acodec": "pcm_s16be"}, "aiff")

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_success_passes_kwargs_through(self, mock_ffmpeg, _ffmpeg_in_path):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = _run_ffmpeg(
            "in.flac", "out.wav", {"acodec": "pcm_s16le", "ar": 44100}, "wav"
        )

        assert result is True
        mock_ffmpeg.input.assert_called_once_with("in.flac")
        mock_ffmpeg.input.return_value.output.assert_called_once_with(
            "out.wav", acodec="pcm_s16le", ar=44100
        )

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_returns_false(self, mock_ffmpeg, _ffmpeg_in_path):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", b"stdout", b"stderr")

        assert _run_ffmpeg("in.flac", "out.aiff", {}, "aiff") is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_no_stderr_returns_false(self, mock_ffmpeg, _ffmpeg_in_path):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", b"stdout", None)

        assert _run_ffmpeg("in.flac", "out.aiff", {}, "aiff") is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unexpected_exception_reraises(self, mock_ffmpeg, _ffmpeg_in_path):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("disk full")

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

    @patch("rekordbox_edit.api.convert.os.path.getsize", return_value=987654)
    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_reads_size_and_audio_without_a_session(
        self, mock_get_audio_info, _mock_getsize
    ):
        mock_get_audio_info.return_value = {"bitrate": 1411, "bit_depth": 16}

        probe = _probe_converted_file("/path/to/output.aiff", "AIFF")

        assert probe.file_size == 987654
        assert probe.audio_info["bitrate"] == 1411
        assert probe.audio_info["bit_depth"] == 16

    @patch("rekordbox_edit.api.convert.os.path.getsize", return_value=1)
    @patch("rekordbox_edit.api.convert.get_audio_info")
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


class TestUpdateAnlzPaths:
    def test_rewrites_ppth_to_device_relative_form(self, make_djmd_content_item):
        mock_db = Mock()
        content = make_djmd_content_item(ID=7)
        content.AnalysisDataPath = "share/PIONEER/USBANLZ/x/ANLZ0000.DAT"
        dat, ext = Mock(), Mock()
        mock_db.read_anlz_files.return_value = {
            "/a/ANLZ0000.DAT": dat,
            "/a/ANLZ0000.EXT": ext,
        }

        _update_anlz_paths(mock_db, content, "new song.aiff")

        dat.set_path.assert_called_once_with("?/new song.aiff")
        dat.save.assert_called_once_with("/a/ANLZ0000.DAT")
        ext.set_path.assert_called_once_with("?/new song.aiff")
        ext.save.assert_called_once_with("/a/ANLZ0000.EXT")

    def test_skips_track_without_analysis(self, make_djmd_content_item):
        mock_db = Mock()
        content = make_djmd_content_item(ID=7)  # AnalysisDataPath defaults to None

        _update_anlz_paths(mock_db, content, "new.aiff")

        mock_db.read_anlz_files.assert_not_called()


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

    @patch("rekordbox_edit.api.convert.logger")
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
