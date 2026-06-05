import os
from unittest.mock import Mock, patch

import ffmpeg
import pytest

from rekordbox_edit.api.convert import (
    cleanup_converted_files,
    convert,
    convert_to_lossless,
    convert_to_mp3,
    get_output_path,
    plan_convert,
    rollback_and_cleanup,
    update_database_record,
    ConvertPlan,
    ConvertResult,
)
from rekordbox_edit.models import ConvertPlanArgs, Track
from rekordbox_edit.utils import OutputFormats


class TestPlanConvert:
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_filters_already_converted_tracks(
        self, mock_get_type, mock_gfc, mock_db, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(FileType=1)  # already AIFF
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff"))

        assert plan.files == []

    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_lossy_formats(
        self, mock_get_type, mock_gfc, mock_db, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        mp3_content = make_djmd_content_item(FileType=5)  # MP3 — skip
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mp3_content]
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff"))

        assert plan.files == []

    @patch("rekordbox_edit.api.convert.os.path.exists")
    @patch("rekordbox_edit.api.convert.get_output_path")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_conflicts_when_no_overwrite(
        self,
        mock_get_type,
        mock_gfc,
        mock_get_output,
        mock_exists,
        mock_db,
        make_djmd_content_item,
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(FileType=11)  # WAV → convert to AIFF
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result
        mock_get_output.return_value = ("/path/output.aif", "output.aif", "/path")
        mock_exists.return_value = True  # output already exists

        plan = plan_convert(
            mock_db, ConvertPlanArgs(format_out="aiff", overwrite=False)
        )

        assert plan.files == []
        assert len(plan.skipped) == 1

    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_should_delete_defaults_true_for_lossless(
        self, mock_get_type, mock_gfc, mock_db
    ):
        mock_get_type.return_value = 99
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff"))
        assert plan.should_delete is True

    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_should_delete_defaults_false_for_mp3(
        self, mock_get_type, mock_gfc, mock_db
    ):
        mock_get_type.return_value = 99
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="mp3"))
        assert plan.should_delete is False


class TestConvertToLossless:
    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_convert_to_aiff_16bit(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is True
        mock_get_audio_info.assert_called_once_with("input.flac")
        mock_ffmpeg.input.assert_called_once_with("input.flac")
        mock_input.output.assert_called_once_with(
            "output.aiff", acodec="pcm_s16be", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_convert_to_wav_24bit(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 24}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = convert_to_lossless("input.flac", "output.wav", OutputFormats.WAV)

        assert result is True
        mock_input.output.assert_called_once_with(
            "output.wav", acodec="pcm_s24le", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_convert_to_flac(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 24}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = convert_to_lossless("input.wav", "output.flac", OutputFormats.FLAC)

        assert result is True
        mock_input.output.assert_called_once_with(
            "output.flac", acodec="flac", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_convert_unsupported_format_raises(
        self, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}

        fake_format = Mock()
        fake_format.value = "xyz"

        with pytest.raises(Exception, match="Unsupported lossless format"):
            convert_to_lossless("input.flac", "output.xyz", fake_format)

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_convert_ffmpeg_error_returns_false(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", "stdout", "stderr")

        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_ffmpeg_not_found_raises(self, mock_ffmpeg_in_path):
        mock_ffmpeg_in_path.return_value = False

        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unknown_bit_depth_falls_back_to_first_codec(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 8}  # not in {16, 24, 32}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is True
        mock_input.output.assert_called_once_with(
            "output.aiff", acodec="pcm_s16be", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_no_stderr_returns_false(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", "stdout", None)

        result = convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is False

    @patch("rekordbox_edit.api.convert.get_audio_info")
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unexpected_exception_reraises(
        self, mock_ffmpeg, mock_ffmpeg_in_path, mock_get_audio_info
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("disk full")

        with pytest.raises(RuntimeError, match="disk full"):
            convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)


class TestConvertToMp3:
    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_success(self, mock_ffmpeg, mock_ffmpeg_in_path):
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = convert_to_mp3("input.flac", "output.mp3")

        assert result is True
        mock_ffmpeg.input.assert_called_once_with("input.flac")
        mock_input.output.assert_called_once_with(
            "output.mp3",
            acodec="libmp3lame",
            audio_bitrate="320k",
            map_metadata=0,
            write_id3v2=1,
        )

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_returns_false(self, mock_ffmpeg, mock_ffmpeg_in_path):
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", "stdout", "stderr")

        result = convert_to_mp3("input.flac", "output.mp3")

        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    def test_ffmpeg_not_found_raises(self, mock_ffmpeg_in_path):
        mock_ffmpeg_in_path.return_value = False

        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            convert_to_mp3("input.flac", "output.mp3")

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_no_stderr_returns_false(
        self, mock_ffmpeg, mock_ffmpeg_in_path
    ):
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", "stdout", None)

        result = convert_to_mp3("input.flac", "output.mp3")

        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path")
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unexpected_exception_reraises(self, mock_ffmpeg, mock_ffmpeg_in_path):
        mock_ffmpeg_in_path.return_value = True
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("permission denied")

        with pytest.raises(RuntimeError, match="permission denied"):
            convert_to_mp3("input.flac", "output.mp3")


class TestUpdateDatabaseRecord:
    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_flac_sets_bitrate_zero(self, mock_get_audio_info, make_djmd_content_item):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123, BitDepth=24)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 24}

        update_database_record(mock_db, 123, "output.flac", "/path/to", "FLAC")

        assert mock_content.FileNameL == "output.flac"
        assert mock_content.FolderPath == "/path/to/output.flac"
        assert mock_content.FileType == 5  # FLAC
        assert mock_content.BitRate == 0

    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_mp3_sets_bitrate_from_probe(
        self, mock_get_audio_info, make_djmd_content_item
    ):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": 320, "bit_depth": 16}

        update_database_record(mock_db, 123, "output.mp3", "/path/to", "MP3")

        assert mock_content.FileNameL == "output.mp3"
        assert mock_content.FolderPath == "/path/to/output.mp3"
        assert mock_content.FileType == 1  # MP3
        assert mock_content.BitRate == 320

    def test_content_not_found_raises(self):
        mock_db = Mock()
        mock_db.get_content().filter_by(ID=123).first.return_value = None

        with pytest.raises(Exception, match="Content record with ID 123 not found"):
            update_database_record(mock_db, 123, "output.flac", "/path/to", "FLAC")

    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_bit_depth_mismatch_raises(
        self, mock_get_audio_info, make_djmd_content_item
    ):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123, BitDepth=16)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 24}

        with pytest.raises(Exception, match="Bit depth mismatch"):
            update_database_record(mock_db, 123, "output.aiff", "/path/to", "AIFF")

    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_mp3_none_bitrate_defaults_to_320(
        self, mock_get_audio_info, make_djmd_content_item
    ):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": None, "bit_depth": 16}

        update_database_record(mock_db, 123, "output.mp3", "/path/to", "MP3")

        assert mock_content.BitRate == 320

    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_unsupported_format_raises(
        self, mock_get_audio_info, mock_get_file_type, make_djmd_content_item
    ):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 16}
        mock_get_file_type.return_value = None

        with pytest.raises(Exception, match="Unsupported output format"):
            update_database_record(mock_db, 123, "output.xyz", "/path/to", "XYZ")


class TestCleanupConvertedFiles:
    @patch("os.remove")
    def test_removes_all_output_files(self, mock_remove):
        converted_files = [
            {"output_path": "/path/file1.aiff"},
            {"output_path": "/path/file2.aiff"},
        ]

        cleanup_converted_files(converted_files)

        assert mock_remove.call_count == 2
        mock_remove.assert_any_call("/path/file1.aiff")
        mock_remove.assert_any_call("/path/file2.aiff")

    @patch("os.remove")
    def test_oserror_is_swallowed(self, mock_remove):
        converted_files = [{"output_path": "/path/file1.aiff"}]
        mock_remove.side_effect = OSError("Permission denied")

        cleanup_converted_files(converted_files)  # must not raise

        mock_remove.assert_called_once_with("/path/file1.aiff")


class TestRollbackAndCleanup:
    def test_rolls_back_session(self, mock_db):
        rollback_and_cleanup(mock_db, [])
        mock_db.session.rollback.assert_called_once()

    def test_no_db_is_noop(self):
        rollback_and_cleanup(None, [])  # must not raise

    def test_no_session_is_noop(self):
        db = Mock()
        db.session = None
        rollback_and_cleanup(db, [])  # must not raise

    @patch("rekordbox_edit.api.convert.cleanup_converted_files")
    def test_cleans_up_converted_files(self, mock_cleanup, mock_db):
        converted_files = [{"output_path": "/path/file.aiff"}]
        rollback_and_cleanup(mock_db, converted_files)
        mock_cleanup.assert_called_once_with(converted_files)

    @patch("rekordbox_edit.api.convert.cleanup_converted_files")
    def test_skips_cleanup_when_no_converted_files(self, mock_cleanup, mock_db):
        rollback_and_cleanup(mock_db, [])
        mock_cleanup.assert_not_called()

    @patch("rekordbox_edit.api.convert.logger")
    def test_rollback_exception_logs_critical_and_reraises(self, mock_logger, mock_db):
        mock_db.session.rollback.side_effect = Exception("DB connection lost")

        with pytest.raises(Exception, match="DB connection lost"):
            rollback_and_cleanup(mock_db, [])

        assert mock_logger.critical.call_count == 2


class TestConvert:
    def _make_plan(self, files=None, format_out="aiff", should_delete=True):
        return ConvertPlan(
            files=files or [Track(ID="1", FileNameL="track.wav")],
            skipped=[],
            should_delete=should_delete,
            format_out=format_out,
        )

    def _seed_db(self, mock_db, *contents):
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = (
            list(contents)
        )

    def test_empty_plan_returns_early_without_commit(self, mock_db):
        plan = ConvertPlan(files=[], skipped=[], should_delete=True, format_out="aiff")
        result = convert(mock_db, plan)
        assert result == ConvertResult(converted=[], deleted=0)
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_no_ffmpeg_raises_immediately(self, _, mock_db):
        with pytest.raises(RuntimeError, match="FFmpeg"):
            convert(mock_db, self._make_plan())
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.convert.rollback_and_cleanup")
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_missing_source_triggers_rollback_and_raises(
        self,
        _,
        mock_get_output,
        mock_exists,
        mock_rollback,
        mock_db,
        make_djmd_content_item,
    ):
        self._seed_db(mock_db, make_djmd_content_item(ID="1"))
        with pytest.raises(RuntimeError, match="Source not found"):
            convert(mock_db, self._make_plan())
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert.rollback_and_cleanup")
    @patch("rekordbox_edit.api.convert.convert_to_lossless", return_value=False)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_conversion_failure_triggers_rollback_and_raises(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_lossless,
        mock_rollback,
        mock_db,
        make_djmd_content_item,
    ):
        self._seed_db(mock_db, make_djmd_content_item(ID="1"))
        with pytest.raises(RuntimeError, match="Conversion failed"):
            convert(mock_db, self._make_plan())
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert.rollback_and_cleanup")
    @patch(
        "rekordbox_edit.api.convert.update_database_record",
        side_effect=RuntimeError("DB error"),
    )
    @patch("rekordbox_edit.api.convert.convert_to_lossless", return_value=True)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_exception_triggers_rollback_and_reraises(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_lossless,
        mock_update,
        mock_rollback,
        mock_db,
        make_djmd_content_item,
    ):
        self._seed_db(mock_db, make_djmd_content_item(ID="1"))
        with pytest.raises(RuntimeError, match="DB error"):
            convert(mock_db, self._make_plan())
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert.rollback_and_cleanup")
    @patch(
        "rekordbox_edit.api.convert.convert_to_lossless", side_effect=KeyboardInterrupt
    )
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_keyboard_interrupt_triggers_rollback_and_reraises(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_lossless,
        mock_rollback,
        mock_db,
        make_djmd_content_item,
    ):
        self._seed_db(mock_db, make_djmd_content_item(ID="1"))
        with pytest.raises(KeyboardInterrupt):
            convert(mock_db, self._make_plan())
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert.update_database_record")
    @patch("rekordbox_edit.api.convert.convert_to_lossless", return_value=True)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_successful_lossless_commits_and_returns_result(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_lossless,
        mock_update,
        mock_db,
        make_djmd_content_item,
    ):
        content = make_djmd_content_item(ID="1", FolderPath="/music/track.wav")
        self._seed_db(mock_db, content)

        result = convert(mock_db, self._make_plan(should_delete=False))

        mock_lossless.assert_called_once()
        mock_update.assert_called_once()
        mock_db.session.commit.assert_called_once()
        assert len(result.converted) == 1
        assert result.deleted == 0

    @patch("rekordbox_edit.api.convert.update_database_record")
    @patch("rekordbox_edit.api.convert.convert_to_mp3", return_value=True)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.mp3", "out.mp3", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_mp3_format_uses_convert_to_mp3(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_mp3,
        mock_update,
        mock_db,
        make_djmd_content_item,
    ):
        content = make_djmd_content_item(ID="1", FolderPath="/music/track.wav")
        self._seed_db(mock_db, content)

        convert(mock_db, self._make_plan(format_out="mp3", should_delete=False))

        mock_mp3.assert_called_once_with(content.FolderPath, "/out.mp3")

    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert.update_database_record")
    @patch("rekordbox_edit.api.convert.convert_to_lossless", return_value=True)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_deletes_originals_when_should_delete_true(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_lossless,
        mock_update,
        mock_remove,
        mock_db,
        make_djmd_content_item,
    ):
        content = make_djmd_content_item(ID="1", FolderPath="/music/track.wav")
        self._seed_db(mock_db, content)

        result = convert(mock_db, self._make_plan(should_delete=True))

        mock_remove.assert_called_once_with(content.FolderPath)
        assert result.deleted == 1

    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert.update_database_record")
    @patch("rekordbox_edit.api.convert.convert_to_lossless", return_value=True)
    @patch(
        "rekordbox_edit.api.convert.get_output_path",
        return_value=("/out.aiff", "out.aiff", "/"),
    )
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_skips_deletion_when_should_delete_false(
        self,
        _,
        mock_exists,
        mock_get_output,
        mock_lossless,
        mock_update,
        mock_remove,
        mock_db,
        make_djmd_content_item,
    ):
        content = make_djmd_content_item(ID="1", FolderPath="/music/track.wav")
        self._seed_db(mock_db, content)

        result = convert(mock_db, self._make_plan(should_delete=False))

        mock_remove.assert_not_called()
        assert result.deleted == 0


class TestGetOutputPath:
    def test_basic_path(self, make_djmd_content_item):
        content = make_djmd_content_item(
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        output_path, output_filename, src_dirname = get_output_path(content, "aiff")

        assert output_path == os.path.normpath("/music/folder/song.aiff")
        assert output_filename == "song.aiff"
        assert src_dirname == os.path.normpath("/music/folder")

    def test_mp3_extension(self, make_djmd_content_item):
        content = make_djmd_content_item(
            FileNameL="song.flac",
            FolderPath="/music/folder/song.flac",
        )

        output_path, output_filename, src_dirname = get_output_path(content, "mp3")

        assert output_path == os.path.normpath("/music/folder/song.mp3")
        assert output_filename == "song.mp3"
        assert src_dirname == os.path.normpath("/music/folder")
