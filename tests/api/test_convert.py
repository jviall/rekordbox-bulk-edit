import os
from unittest.mock import Mock, patch

import ffmpeg
import pytest

from rekordbox_edit.api.convert import (
    _classify_convert,
    _cleanup_converted_files,
    _convert_to_lossless,
    _convert_to_mp3,
    _get_output_path,
    _rollback_and_cleanup,
    _update_database_record,
    convert,
)
from rekordbox_edit.models import (
    ConvertArgs,
    ConvertOp,
    ConvertResponse,
    SkippedTrack,
)
from rekordbox_edit.utils import OutputFormats


class TestClassifyConvert:
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_already_target_format(self, mock_get_type, make_djmd_content_item):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="1", FileType=1)  # already AIFF

        result = _classify_convert(content, ConvertArgs(format_out="aiff"))

        assert isinstance(result, SkippedTrack)
        assert result.reason == "already_target_format"

    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_lossy_formats(self, mock_get_type, make_djmd_content_item):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(
            fmt.upper(), 99
        )
        content = make_djmd_content_item(ID="2", FileType=5)  # MP3

        result = _classify_convert(content, ConvertArgs(format_out="aiff"))

        assert isinstance(result, SkippedTrack)
        assert result.reason == "already_target_format"

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
            content, ConvertArgs(format_out="aiff", overwrite=False)
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
            content, ConvertArgs(format_out="aiff", overwrite=True)
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

        result = _classify_convert(content, ConvertArgs(format_out="aiff"))

        assert isinstance(result, ConvertOp)
        assert result.id == "4"
        assert result.source_path == "/music/song.wav"
        assert result.output_path == "/music/song.aif"


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

        response = convert(mock_db, ConvertArgs(format_out="aiff"), dry_run=True)

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

        response = convert(mock_db, ConvertArgs(format_out="aiff"), dry_run=True)

        assert response.result.converted == []
        assert response.tracks == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "already_target_format"


class TestConvertRealRun:
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_no_ffmpeg_raises_immediately(self, _, mock_db):
        with pytest.raises(RuntimeError, match="FFmpeg"):
            convert(mock_db, ConvertArgs(format_out="aiff"))

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_no_matching_tracks_returns_empty_response(
        self, mock_gfc, _ffmpeg, mock_db
    ):
        _seed_filter(mock_gfc)

        response = convert(mock_db, ConvertArgs(format_out="aiff"))

        assert response.result.converted == []
        assert response.tracks == []
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_successful_lossless_commits(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_lossless,
        mock_update,
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
            mock_db, ConvertArgs(format_out="aiff", delete=False, overwrite=True)
        )

        mock_lossless.assert_called_once_with("/in.wav", "/out.aif", OutputFormats.AIFF)
        mock_update.assert_called_once()
        mock_db.session.commit.assert_called_once()
        assert response.result.converted[0].id == "1"
        assert response.result.deleted == 0
        assert response.tracks[0].ID == "1"

    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_deletes_originals_when_should_delete_true(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        mock_exists,
        mock_lossless,
        mock_update,
        mock_remove,
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
            mock_db, ConvertArgs(format_out="aiff", delete=True, overwrite=True)
        )

        mock_remove.assert_called_once_with("/in.wav")
        assert response.result.deleted == 1

    @patch("rekordbox_edit.api.convert._rollback_and_cleanup")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=False)
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
        mock_lossless,
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

        with pytest.raises(RuntimeError, match="Conversion failed"):
            convert(mock_db, ConvertArgs(format_out="aiff", overwrite=True))

        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert._rollback_and_cleanup")
    @patch("rekordbox_edit.api.convert.os.remove", side_effect=KeyboardInterrupt)
    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
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
        mock_lossless,
        mock_update,
        _remove,
        mock_rollback,
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
                mock_db, ConvertArgs(format_out="aiff", delete=True, overwrite=True)
            )

        mock_db.session.commit.assert_called_once()
        mock_rollback.assert_not_called()

    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
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
        mock_lossless,
        mock_update,
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
            mock_db, ConvertArgs(format_out="aiff", delete=False, overwrite=True)
        )

        assert [op.id for op in response.result.converted] == ["A", "B", "C"]
        assert [t.ID for t in response.tracks] == ["A", "B", "C"]

    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
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
        mock_lossless,
        mock_update,
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
            mock_db, ConvertArgs(format_out="aiff", delete=False, overwrite=True)
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
        response = convert(mock_db, ConvertArgs(format_out="aiff"))

        assert response.result.converted == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "output_file_exists"
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.convert._rollback_and_cleanup")
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=False)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_missing_source_triggers_rollback_and_raises(
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

        with pytest.raises(RuntimeError, match="Source not found"):
            convert(mock_db, ConvertArgs(format_out="aiff", overwrite=True))
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert._rollback_and_cleanup")
    @patch(
        "rekordbox_edit.api.convert._update_database_record",
        side_effect=RuntimeError("DB error"),
    )
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
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
        _lossless,
        _update,
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

        with pytest.raises(RuntimeError, match="DB error"):
            convert(mock_db, ConvertArgs(format_out="aiff", overwrite=True))
        mock_rollback.assert_called_once()

    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_mp3", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_mp3_format_uses_convert_to_mp3(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        mock_mp3,
        _update,
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

        convert(mock_db, ConvertArgs(format_out="mp3", overwrite=True))

        mock_mp3.assert_called_once_with("/in.wav", "/out.mp3")

    @patch("rekordbox_edit.api.convert.os.remove")
    @patch("rekordbox_edit.api.convert._update_database_record")
    @patch("rekordbox_edit.api.convert._convert_to_lossless", return_value=True)
    @patch("rekordbox_edit.api.convert.os.path.exists", return_value=True)
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert._get_output_path")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    def test_skips_deletion_when_should_delete_false(
        self,
        mock_gfc,
        mock_get_type,
        mock_get_output,
        _ffmpeg,
        _exists,
        _lossless,
        _update,
        mock_remove,
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
            mock_db, ConvertArgs(format_out="aiff", delete=False, overwrite=True)
        )

        mock_remove.assert_not_called()
        assert response.result.deleted == 0


# ── Helper-function tests (preserved from existing file) ──────────────────


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

        result = _convert_to_lossless("input.flac", "output.aiff", OutputFormats.AIFF)

        assert result is True
        mock_input.output.assert_called_once_with(
            "output.aiff", acodec="pcm_s16be", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_ffmpeg_not_found_raises(self, _):
        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            _convert_to_lossless("in.flac", "out.aiff", OutputFormats.AIFF)

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 24})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_convert_to_wav_24bit(self, mock_ffmpeg, _ffmpeg_in_path, _audio):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = _convert_to_lossless("in.flac", "out.wav", OutputFormats.WAV)

        assert result is True
        mock_ffmpeg.input.return_value.output.assert_called_once_with(
            "out.wav", acodec="pcm_s24le", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 24})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_convert_to_flac(self, mock_ffmpeg, _ffmpeg_in_path, _audio):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = _convert_to_lossless("in.wav", "out.flac", OutputFormats.FLAC)

        assert result is True
        mock_ffmpeg.input.return_value.output.assert_called_once_with(
            "out.flac", acodec="flac", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 16})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    def test_unsupported_format_raises(self, _ffmpeg_in_path, _audio):
        fake_format = Mock()
        fake_format.value = "xyz"
        with pytest.raises(Exception, match="Unsupported lossless format"):
            _convert_to_lossless("in.flac", "out.xyz", fake_format)

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 8})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unknown_bit_depth_falls_back_to_first_codec(
        self, mock_ffmpeg, _ffmpeg_in_path, _audio
    ):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = _convert_to_lossless("in.flac", "out.aiff", OutputFormats.AIFF)

        assert result is True
        # First codec in {16: pcm_s16be, ...} for AIFF.
        mock_ffmpeg.input.return_value.output.assert_called_once_with(
            "out.aiff", acodec="pcm_s16be", map_metadata=0, write_id3v2=1
        )

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 16})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_returns_false(self, mock_ffmpeg, _ffmpeg_in_path, _audio):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", b"stdout", b"stderr")

        result = _convert_to_lossless("in.flac", "out.aiff", OutputFormats.AIFF)

        assert result is False

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 16})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_no_stderr_returns_false(
        self, mock_ffmpeg, _ffmpeg_in_path, _audio
    ):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", b"stdout", None)

        result = _convert_to_lossless("in.flac", "out.aiff", OutputFormats.AIFF)

        assert result is False

    @patch("rekordbox_edit.api.convert.get_audio_info", return_value={"bit_depth": 16})
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unexpected_exception_reraises(self, mock_ffmpeg, _ffmpeg_in_path, _audio):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("disk full")

        with pytest.raises(RuntimeError, match="disk full"):
            _convert_to_lossless("in.flac", "out.aiff", OutputFormats.AIFF)


class TestConvertToMp3:
    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_success(self, mock_ffmpeg, _):
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        result = _convert_to_mp3("in.flac", "out.mp3")

        assert result is True

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=False)
    def test_ffmpeg_not_found_raises(self, _):
        with pytest.raises(Exception, match="FFmpeg not found in PATH"):
            _convert_to_mp3("in.flac", "out.mp3")

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_returns_false(self, mock_ffmpeg, _):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", b"stdout", b"stderr")

        result = _convert_to_mp3("in.flac", "out.mp3")

        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_ffmpeg_error_no_stderr_returns_false(self, mock_ffmpeg, _):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = ffmpeg.Error("cmd", b"stdout", None)

        result = _convert_to_mp3("in.flac", "out.mp3")

        assert result is False

    @patch("rekordbox_edit.utils.ffmpeg_in_path", return_value=True)
    @patch("rekordbox_edit.api.convert.ffmpeg")
    def test_unexpected_exception_reraises(self, mock_ffmpeg, _):
        mock_output = Mock()
        mock_ffmpeg.input.return_value.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.side_effect = RuntimeError("permission denied")

        with pytest.raises(RuntimeError, match="permission denied"):
            _convert_to_mp3("in.flac", "out.mp3")


class TestUpdateDatabaseRecord:
    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_flac_sets_bitrate_zero(self, mock_get_audio_info, make_djmd_content_item):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123, BitDepth=24)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": 1000, "bit_depth": 24}

        _update_database_record(mock_db, 123, "output.flac", "/path/to", "FLAC")

        assert mock_content.FileNameL == "output.flac"
        assert mock_content.FolderPath == "/path/to/output.flac"
        assert mock_content.BitRate == 0

    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_mp3_sets_bitrate_from_probe(
        self, mock_get_audio_info, make_djmd_content_item
    ):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": 320, "bit_depth": 16}

        _update_database_record(mock_db, 123, "output.mp3", "/path/to", "MP3")

        assert mock_content.BitRate == 320

    @patch("rekordbox_edit.api.convert.get_audio_info")
    def test_mp3_none_bitrate_defaults_to_320(
        self, mock_get_audio_info, make_djmd_content_item
    ):
        mock_db = Mock()
        mock_content = make_djmd_content_item(ID=123)
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        mock_get_audio_info.return_value = {"bitrate": None, "bit_depth": 16}

        _update_database_record(mock_db, 123, "output.mp3", "/path/to", "MP3")

        assert mock_content.BitRate == 320

    def test_content_not_found_raises(self):
        mock_db = Mock()
        mock_db.get_content().filter_by(ID=123).first.return_value = None

        with pytest.raises(Exception, match="Content record with ID 123 not found"):
            _update_database_record(mock_db, 123, "output.flac", "/path/to", "FLAC")


class TestCleanupConvertedFiles:
    @patch("os.remove")
    def test_removes_all_output_files(self, mock_remove):
        ops = [
            ConvertOp(id="1", source_path="/s1", output_path="/p/f1.aiff"),
            ConvertOp(id="2", source_path="/s2", output_path="/p/f2.aiff"),
        ]
        _cleanup_converted_files(ops)
        assert mock_remove.call_count == 2

    @patch("os.remove", side_effect=OSError)
    def test_oserror_is_swallowed(self, _):
        _cleanup_converted_files(
            [ConvertOp(id="1", source_path="/s", output_path="/p/f.aiff")]
        )


class TestRollbackAndCleanup:
    def test_rolls_back_session(self, mock_db):
        _rollback_and_cleanup(mock_db, [])
        mock_db.session.rollback.assert_called_once()

    def test_no_db_is_noop(self):
        _rollback_and_cleanup(None, [])

    def test_no_session_is_noop(self):
        db = Mock()
        db.session = None
        _rollback_and_cleanup(db, [])

    @patch("rekordbox_edit.api.convert._cleanup_converted_files")
    def test_cleans_up_converted_files(self, mock_cleanup, mock_db):
        ops = [ConvertOp(id="1", source_path="/s", output_path="/p/f.aiff")]
        _rollback_and_cleanup(mock_db, ops)
        mock_cleanup.assert_called_once_with(ops)

    @patch("rekordbox_edit.api.convert._cleanup_converted_files")
    def test_skips_cleanup_when_no_converted_files(self, mock_cleanup, mock_db):
        _rollback_and_cleanup(mock_db, [])
        mock_cleanup.assert_not_called()

    @patch("rekordbox_edit.api.convert.logger")
    def test_rollback_exception_logs_critical_and_reraises(self, mock_logger, mock_db):
        mock_db.session.rollback.side_effect = Exception("DB connection lost")

        with pytest.raises(Exception, match="DB connection lost"):
            _rollback_and_cleanup(mock_db, [])

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
