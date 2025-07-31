"""Unit tests for convert command functionality."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
import ffmpeg

from rekordbox_bulk_edit.commands.convert import (
    convert_to_lossless,
    convert_to_mp3,
    update_database_record,
    check_file_exists_and_confirm,
    confirm,
    _verify_bit_depth,
    UserQuit,
    cleanup_converted_files,
    handle_original_file_deletion,
)


class TestConvertToLossless:
    """Test convert_to_lossless function."""

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_to_aiff_16bit(self, mock_click, mock_ffmpeg, mock_get_audio_info):
        """Test converting to AIFF with 16-bit depth."""
        # Setup
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_lossless("input.flac", "output.aiff", "aiff")

        # Assert
        assert result is True
        mock_get_audio_info.assert_called_once_with("input.flac")
        mock_ffmpeg.input.assert_called_once_with("input.flac")
        mock_input.output.assert_called_once_with(
            "output.aiff",
            acodec="pcm_s16be",
            map_metadata=0,
            write_id3v2=1
        )
        mock_click.echo.assert_called()

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_to_wav_24bit(self, mock_click, mock_ffmpeg, mock_get_audio_info):
        """Test converting to WAV with 24-bit depth."""
        # Setup
        mock_get_audio_info.return_value = {"bit_depth": 24}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_lossless("input.flac", "output.wav", "wav")

        # Assert
        assert result is True
        mock_input.output.assert_called_once_with(
            "output.wav",
            acodec="pcm_s24le",
            map_metadata=0,
            write_id3v2=1
        )

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_to_flac(self, mock_click, mock_ffmpeg, mock_get_audio_info):
        """Test converting to FLAC."""
        # Setup
        mock_get_audio_info.return_value = {"bit_depth": 24}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_lossless("input.wav", "output.flac", "flac")

        # Assert
        assert result is True
        mock_input.output.assert_called_once_with(
            "output.flac",
            acodec="flac",
            map_metadata=0,
            write_id3v2=1
        )

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_unsupported_format(self, mock_click, mock_ffmpeg, mock_get_audio_info):
        """Test conversion with unsupported format raises exception."""
        # Setup
        mock_get_audio_info.return_value = {"bit_depth": 16}

        # Execute & Assert
        result = convert_to_lossless("input.flac", "output.xyz", "xyz")
        assert result is False
        mock_click.echo.assert_called()

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_ffmpeg_error(self, mock_click, mock_ffmpeg, mock_get_audio_info):
        """Test handling of ffmpeg errors."""
        # Setup
        mock_get_audio_info.return_value = {"bit_depth": 16}
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        
        # Create an ffmpeg.Error with stderr
        error = ffmpeg.Error("cmd", "stdout", "stderr")
        mock_output.run.side_effect = error

        # Execute
        result = convert_to_lossless("input.flac", "output.aiff", "aiff")

        # Assert
        assert result is False
        mock_click.echo.assert_called()


class TestConvertToMp3:
    """Test convert_to_mp3 function."""

    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_to_mp3_success(self, mock_click, mock_ffmpeg):
        """Test successful MP3 conversion."""
        # Setup
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        mock_output.run.return_value = None

        # Execute
        result = convert_to_mp3("input.flac", "output.mp3")

        # Assert
        assert result is True
        mock_ffmpeg.input.assert_called_once_with("input.flac")
        mock_input.output.assert_called_once_with(
            "output.mp3",
            acodec="libmp3lame",
            audio_bitrate="320k",
            map_metadata=0,
            write_id3v2=1
        )
        mock_click.echo.assert_called_with("Converting to MP3 320kbps CBR")

    @patch('rekordbox_bulk_edit.commands.convert.ffmpeg')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_convert_to_mp3_ffmpeg_error(self, mock_click, mock_ffmpeg):
        """Test MP3 conversion with ffmpeg error."""
        # Setup
        mock_input = Mock()
        mock_output = Mock()
        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.overwrite_output.return_value = mock_output
        
        error = ffmpeg.Error("cmd", "stdout", "stderr")
        mock_output.run.side_effect = error

        # Execute
        result = convert_to_mp3("input.flac", "output.mp3")

        # Assert
        assert result is False
        mock_click.echo.assert_called()


class TestVerifyBitDepth:
    """Test _verify_bit_depth function."""

    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_verify_bit_depth_match(self, mock_click):
        """Test bit depth verification when depths match."""
        # Setup
        mock_content = Mock()
        mock_content.BitDepth = 24
        converted_audio_info = {"bit_depth": 24}

        # Execute - should not raise exception
        _verify_bit_depth(mock_content, converted_audio_info)

        # Assert
        mock_click.echo.assert_called_with(
            "  ✓ Bit depth verification passed: 24-bit matches database"
        )

    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_verify_bit_depth_mismatch(self, mock_click):
        """Test bit depth verification when depths don't match."""
        # Setup
        mock_content = Mock()
        mock_content.BitDepth = 16
        converted_audio_info = {"bit_depth": 24}

        # Execute & Assert
        with pytest.raises(Exception, match="Bit depth mismatch"):
            _verify_bit_depth(mock_content, converted_audio_info)

    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_verify_bit_depth_no_database_field(self, mock_click):
        """Test bit depth verification when database has no BitDepth field."""
        # Setup
        mock_content = Mock()
        mock_content.configure_mock(**{})  # Ensure no BitDepth attribute
        # Remove BitDepth attribute if it exists
        if hasattr(mock_content, 'BitDepth'):
            delattr(mock_content, 'BitDepth')
        converted_audio_info = {"bit_depth": 24}

        # Execute - should not raise exception
        _verify_bit_depth(mock_content, converted_audio_info)

        # Assert
        mock_click.echo.assert_called_with(
            "  ⚠ Warning: Could not verify bit depth - no bit depth field found in database"
        )


class TestUpdateDatabaseRecord:
    """Test update_database_record function."""

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert._verify_bit_depth')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    @patch('os.path.join')
    def test_update_database_record_flac(self, mock_join, mock_click, mock_verify, mock_get_audio_info):
        """Test updating database record for FLAC conversion."""
        # Setup
        mock_db = Mock()
        mock_content = Mock()
        mock_content.ID = 123
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        
        mock_join.return_value = "/path/to/output.flac"
        mock_get_audio_info.return_value = {"bitrate": 1000}
        
        # Execute
        result = update_database_record(mock_db, 123, "output.flac", "/path/to", "flac")

        # Assert
        assert result is True
        assert mock_content.FileNameL == "output.flac"
        assert mock_content.FolderPath == "/path/to/output.flac"
        assert mock_content.FileType == 5  # FLAC file type
        assert mock_content.BitRate == 0  # FLAC bitrate set to 0
        mock_verify.assert_called_once()

    @patch('rekordbox_bulk_edit.commands.convert.get_audio_info')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    @patch('os.path.join')
    def test_update_database_record_mp3(self, mock_join, mock_click, mock_get_audio_info):
        """Test updating database record for MP3 conversion."""
        # Setup
        mock_db = Mock()
        mock_content = Mock()
        mock_content.ID = 123
        mock_db.get_content().filter_by(ID=123).first.return_value = mock_content
        
        mock_join.return_value = "/path/to/output.mp3"
        mock_get_audio_info.return_value = {"bitrate": 320}
        
        # Execute
        result = update_database_record(mock_db, 123, "output.mp3", "/path/to", "mp3")

        # Assert
        assert result is True
        assert mock_content.FileNameL == "output.mp3"
        assert mock_content.FolderPath == "/path/to/output.mp3"
        assert mock_content.FileType == 1  # MP3 file type
        assert mock_content.BitRate == 320

    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_update_database_record_content_not_found(self, mock_click):
        """Test updating database record when content not found."""
        # Setup
        mock_db = Mock()
        mock_db.get_content().filter_by(ID=123).first.return_value = None
        
        # Execute & Assert
        with pytest.raises(Exception, match="Content record with ID 123 not found"):
            update_database_record(mock_db, 123, "output.flac", "/path/to", "flac")


class TestConfirm:
    """Test confirm function."""

    @patch('rekordbox_bulk_edit.commands.convert.click.prompt')
    def test_confirm_yes_default_empty_response(self, mock_prompt):
        """Test confirm with default yes and empty response."""
        mock_prompt.return_value = ""
        result = confirm("Continue?", default_yes=True)
        assert result is True

    @patch('rekordbox_bulk_edit.commands.convert.click.prompt')
    def test_confirm_no_default_empty_response(self, mock_prompt):
        """Test confirm with default no and empty response."""
        mock_prompt.return_value = ""
        result = confirm("Continue?", default_yes=False)
        assert result is False

    @patch('rekordbox_bulk_edit.commands.convert.click.prompt')
    def test_confirm_yes_response(self, mock_prompt):
        """Test confirm with yes response."""
        mock_prompt.return_value = "y"
        result = confirm("Continue?", default_yes=False)
        assert result is True

    @patch('rekordbox_bulk_edit.commands.convert.click.prompt')
    def test_confirm_no_response(self, mock_prompt):
        """Test confirm with no response."""
        mock_prompt.return_value = "n"
        result = confirm("Continue?", default_yes=True)
        assert result is False

    @patch('rekordbox_bulk_edit.commands.convert.click.prompt')
    def test_confirm_quit_response(self, mock_prompt):
        """Test confirm with quit response."""
        mock_prompt.return_value = "q"
        with pytest.raises(UserQuit, match="User chose to quit"):
            confirm("Continue?", default_yes=True)


class TestCheckFileExistsAndConfirm:
    """Test check_file_exists_and_confirm function."""

    @patch('os.path.exists')
    def test_file_does_not_exist(self, mock_exists):
        """Test when output file doesn't exist."""
        mock_exists.return_value = False
        result = check_file_exists_and_confirm("/path/output.aiff", "aiff", False)
        assert result is False

    @patch('os.path.exists')
    @patch('rekordbox_bulk_edit.commands.convert.confirm')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_file_exists_user_confirms_skip(self, mock_click, mock_confirm, mock_exists):
        """Test when file exists and user confirms to skip conversion."""
        mock_exists.return_value = True
        mock_confirm.return_value = True
        
        result = check_file_exists_and_confirm("/path/output.aiff", "aiff", False)
        
        assert result is True
        mock_click.echo.assert_called()
        mock_confirm.assert_called_once()

    @patch('os.path.exists')
    @patch('rekordbox_bulk_edit.commands.convert.confirm')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_file_exists_user_declines_skip(self, mock_click, mock_confirm, mock_exists):
        """Test when file exists and user declines to skip conversion."""
        mock_exists.return_value = True
        mock_confirm.return_value = False
        
        result = check_file_exists_and_confirm("/path/output.aiff", "aiff", False)
        
        assert result is None
        mock_click.echo.assert_called()

    @patch('os.path.exists')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_file_exists_auto_confirm(self, mock_click, mock_exists):
        """Test when file exists with auto-confirm enabled."""
        mock_exists.return_value = True
        
        result = check_file_exists_and_confirm("/path/output.aiff", "aiff", True)
        
        assert result is True
        mock_click.echo.assert_called()


class TestCleanupConvertedFiles:
    """Test cleanup_converted_files function."""

    @patch('os.remove')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_cleanup_converted_files_success(self, mock_click, mock_remove):
        """Test successful cleanup of converted files."""
        converted_files = [
            {"output_path": "/path/file1.aiff"},
            {"output_path": "/path/file2.aiff"}
        ]
        
        cleanup_converted_files(converted_files)
        
        assert mock_remove.call_count == 2
        mock_remove.assert_any_call("/path/file1.aiff")
        mock_remove.assert_any_call("/path/file2.aiff")

    @patch('os.remove')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_cleanup_converted_files_with_error(self, mock_click, mock_remove):
        """Test cleanup when file removal fails."""
        converted_files = [{"output_path": "/path/file1.aiff"}]
        mock_remove.side_effect = OSError("Permission denied")
        
        # Should not raise exception
        cleanup_converted_files(converted_files)
        
        mock_remove.assert_called_once_with("/path/file1.aiff")
        # Verify the function continues despite the error
        assert mock_remove.call_count == 1


class TestHandleOriginalFileDeletion:
    """Test handle_original_file_deletion function."""

    @patch('os.remove')
    @patch('rekordbox_bulk_edit.commands.convert.confirm')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_handle_deletion_user_confirms(self, mock_click, mock_confirm, mock_remove):
        """Test handling deletion when user confirms."""
        mock_confirm.return_value = True
        converted_files = [
            {"flac_path": "/path/file1.flac"},
            {"flac_path": "/path/file2.flac"}
        ]
        
        handle_original_file_deletion(converted_files, False)
        
        assert mock_remove.call_count == 2
        mock_remove.assert_any_call("/path/file1.flac")
        mock_remove.assert_any_call("/path/file2.flac")

    @patch('rekordbox_bulk_edit.commands.convert.confirm')
    @patch('rekordbox_bulk_edit.commands.convert.click')
    def test_handle_deletion_user_declines(self, mock_click, mock_confirm):
        """Test handling deletion when user declines."""
        mock_confirm.return_value = False
        converted_files = [{"flac_path": "/path/file1.flac"}]
        
        handle_original_file_deletion(converted_files, False)
        
        mock_click.echo.assert_called_with("Original files preserved")

    @patch('rekordbox_bulk_edit.commands.convert.confirm')
    def test_handle_deletion_user_quits(self, mock_confirm):
        """Test handling deletion when user quits."""
        mock_confirm.side_effect = UserQuit("User chose to quit")
        converted_files = [{"flac_path": "/path/file1.flac"}]
        
        with pytest.raises(UserQuit):
            handle_original_file_deletion(converted_files, False)
