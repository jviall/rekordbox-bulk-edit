"""Unit tests for utils module functionality."""

from unittest.mock import Mock, patch

import pytest

from rekordbox_bulk_edit.utils import (
    get_audio_info,
    get_extension_for_format,
    get_file_type_for_format,
    get_file_type_name,
    get_track_info,
    print_track_info,
)


class TestGetFileTypeName:
    """Test getter functions."""

    def test_get_file_type_name_known_types(self):
        """Test get_file_type_name with known file type codes."""
        assert get_file_type_name(0) == "MP3"
        assert get_file_type_name(1) == "MP3"
        assert get_file_type_name(4) == "M4A"
        assert get_file_type_name(5) == "FLAC"
        assert get_file_type_name(11) == "WAV"
        assert get_file_type_name(12) == "AIFF"

    def test_get_file_type_name_unknown_types(self):
        """Test get_file_type_name with unknown file type codes."""

        with pytest.raises(ValueError, match="Unknown file_type: None"):
            get_file_type_name(None)  # pyright: ignore
        with pytest.raises(ValueError, match="Unknown file_type: -1"):
            get_file_type_name(-1)
        with pytest.raises(ValueError, match="Unknown file_type: 99"):
            get_file_type_name(99)


class TestGetFileTypeForFormat:
    def test_get_file_type_for_format_case_insensitive(self):
        """Test get_file_type_for_format is case-insensitive."""
        assert get_file_type_for_format("MP3") == 1
        assert get_file_type_for_format("mp3") == 1
        assert get_file_type_for_format("Mp3") == 1
        assert get_file_type_for_format("FLAC") == 5
        assert get_file_type_for_format("flac") == 5
        assert get_file_type_for_format("wav") == 11
        assert get_file_type_for_format("AIFF") == 12
        assert get_file_type_for_format("M4A") == 4

    def test_get_file_type_for_format_invalid(self):
        """Test get_file_type_for_format with invalid formats."""
        import pytest

        with pytest.raises(ValueError, match="Unknown format: invalid"):
            get_file_type_for_format("invalid")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_file_type_for_format("")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_file_type_for_format(None)  # pyright: ignore


class TestGetGetExtensionForFormat:
    def test_get_extension_for_format_case_insensitive(self):
        """Test get_extension_for_format is case-insensitive."""
        assert get_extension_for_format("MP3") == ".mp3"
        assert get_extension_for_format("mp3") == ".mp3"
        assert get_extension_for_format("Mp3") == ".mp3"
        assert get_extension_for_format("FLAC") == ".flac"
        assert get_extension_for_format("flac") == ".flac"
        assert get_extension_for_format("WAV") == ".wav"
        assert get_extension_for_format("wav") == ".wav"
        assert get_extension_for_format("AIFF") == ".aiff"
        assert get_extension_for_format("aiff") == ".aiff"
        assert get_extension_for_format("ALAC") == ".m4a"
        assert get_extension_for_format("alac") == ".m4a"

    def test_get_extension_for_format_invalid(self):
        """Test get_extension_for_format with invalid formats."""
        import pytest

        with pytest.raises(ValueError, match="Unknown format: invalid"):
            get_extension_for_format("invalid")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_extension_for_format("")

        with pytest.raises(ValueError, match="Format name cannot be empty or None"):
            get_extension_for_format(None)  # pyright: ignore


class TestPrintTrackInfo:
    """Test print_track_info function."""

    def test_empty_content_list(self, capsys):
        """Test printing with empty content list."""
        print_track_info([])

        captured = capsys.readouterr()
        assert "No tracks found." in captured.out

    def test_single_track_complete_info(self, capsys):
        """Test printing single track with complete information."""
        # Setup mock content
        mock_content = Mock()
        mock_content.ID = 123
        mock_content.FileNameL = "test_track.flac"
        mock_content.FileType = 5  # FLAC
        mock_content.SampleRate = 44100
        mock_content.BitRate = 1411
        mock_content.BitDepth = 16
        mock_content.FolderPath = "/path/to/music/test_track.flac"

        print_track_info([mock_content])

        captured = capsys.readouterr()
        assert "123" in captured.out
        assert "test_track.flac" in captured.out
        assert "FLAC" in captured.out
        assert "44100" in captured.out
        assert "1411" in captured.out
        assert "16" in captured.out
        assert "/path/to/music/test_track.flac" in captured.out

    def test_track_with_missing_fields(self, capsys):
        """Test printing track with missing/None fields."""
        # Setup mock content with missing fields
        mock_content = Mock()
        mock_content.ID = None
        mock_content.FileNameL = None
        mock_content.SampleRate = 0
        mock_content.FileType = 5
        mock_content.BitRate = None
        mock_content.BitDepth = None
        mock_content.FolderPath = None

        print_track_info([mock_content])

        captured = capsys.readouterr()
        assert "N/A" in captured.out
        assert "--" in captured.out

    def test_track_with_zero_values(self, capsys):
        """Test printing track with zero values."""
        # Setup mock content with zero values
        mock_content = Mock()
        mock_content.ID = 123
        mock_content.FileNameL = "test.flac"
        mock_content.FileType = 5
        mock_content.SampleRate = 0
        mock_content.BitRate = 0
        mock_content.BitDepth = 0
        mock_content.FolderPath = "/path/test.flac"

        print_track_info([mock_content])

        captured = capsys.readouterr()
        # BitRate and BitDepth should show "0", SampleRate should show "--"
        lines = captured.out.split("\n")
        data_line = [line for line in lines if "123" in line][0]
        assert "0" in data_line  # Should show 0 for BitRate and BitDepth
        assert "--" in data_line  # Should show -- for SampleRate

    def test_long_filename_truncation(self, capsys):
        """Test truncation of long filenames."""
        # Setup mock content with very long filename
        long_filename = "a" * 60 + ".flac"  # Longer than width limit
        mock_content = Mock()
        mock_content.ID = 123
        mock_content.FileNameL = long_filename
        mock_content.FileType = 5
        mock_content.SampleRate = 44100
        mock_content.BitRate = 1411
        mock_content.BitDepth = 16
        mock_content.FolderPath = "/path/test.flac"

        print_track_info([mock_content])

        captured = capsys.readouterr()
        assert "..." in captured.out  # Should contain truncation indicator

    def test_multiple_tracks(self, capsys):
        """Test printing multiple tracks."""
        # Setup multiple mock content objects
        mock_content1 = Mock()
        mock_content1.ID = 123
        mock_content1.FileNameL = "track1.flac"
        mock_content1.FileType = 5
        mock_content1.SampleRate = 44100
        mock_content1.BitRate = 1411
        mock_content1.BitDepth = 16
        mock_content1.FolderPath = "/path/track1.flac"

        mock_content2 = Mock()
        mock_content2.ID = 456
        mock_content2.FileNameL = "track2.mp3"
        mock_content2.FileType = 1
        mock_content2.SampleRate = 44100
        mock_content2.BitRate = 320
        mock_content2.BitDepth = None
        mock_content2.FolderPath = "/path/track2.mp3"

        print_track_info([mock_content1, mock_content2])

        captured = capsys.readouterr()
        assert "123" in captured.out
        assert "456" in captured.out
        assert "track1.flac" in captured.out
        assert "track2.mp3" in captured.out
        assert "FLAC" in captured.out
        assert "MP3" in captured.out


class TestGetTrackInfo:
    """Test get_track_info function."""

    @patch("rekordbox_bulk_edit.utils.Rekordbox6Database")
    def test_get_specific_track_by_id(self, mock_db_class):
        """Test getting specific track by ID."""
        # Setup mock database
        mock_db = Mock()
        mock_db_class.return_value = mock_db

        mock_track = Mock()
        mock_track.ID = 123
        mock_all_content = [mock_track, Mock(ID=456)]
        mock_db.get_content.return_value = mock_all_content

        # Execute
        result = get_track_info(track_id=123)

        # Assert
        assert len(result) == 1
        assert result[0].ID == 123

    @patch("rekordbox_bulk_edit.utils.Rekordbox6Database")
    def test_get_all_tracks_no_filter(self, mock_db_class):
        """Test getting all tracks without filter."""
        # Setup mock database
        mock_db = Mock()
        mock_db_class.return_value = mock_db

        mock_track1 = Mock(FileType=5)  # FLAC
        mock_track2 = Mock(FileType=1)  # MP3
        mock_track3 = Mock(FileType=999)  # Unknown type
        mock_all_content = [mock_track1, mock_track2, mock_track3]
        mock_db.get_content.return_value = mock_all_content

        # Execute
        result = get_track_info()

        # Assert - should exclude unknown file types
        assert len(result) == 2
        assert mock_track1 in result
        assert mock_track2 in result
        assert mock_track3 not in result

    @patch("rekordbox_bulk_edit.utils.Rekordbox6Database")
    def test_get_tracks_with_format_filter(self, mock_db_class):
        """Test getting tracks with format filter."""
        # Setup mock database
        mock_db = Mock()
        mock_db_class.return_value = mock_db

        mock_flac_track = Mock(FileType=5)  # FLAC
        mock_mp3_track = Mock(FileType=1)  # MP3
        mock_all_content = [mock_flac_track, mock_mp3_track]
        mock_db.get_content.return_value = mock_all_content

        # Execute - filter for FLAC only
        result = get_track_info(format_filter="flac")

        # Assert
        assert len(result) == 1
        assert result[0] == mock_flac_track

    @patch("rekordbox_bulk_edit.utils.Rekordbox6Database")
    def test_get_tracks_invalid_format_filter(self, mock_db_class):
        """Test getting tracks with invalid format filter."""
        # Setup mock database
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.get_content.return_value = [Mock(FileType=5)]

        # Execute - invalid format should return empty list due to exception handling
        result = get_track_info(format_filter="invalid")

        # Assert - should return empty list when format is invalid
        assert len(result) == 0

    @patch("rekordbox_bulk_edit.utils.Rekordbox6Database")
    def test_database_error_handling(self, mock_db_class):
        """Test handling of database errors."""
        # Setup mock to raise exception
        mock_db_class.side_effect = Exception("Database connection failed")

        # Execute
        result = get_track_info()

        # Assert - should return empty list on error
        assert result == []

    @patch("rekordbox_bulk_edit.utils.Rekordbox6Database")
    def test_track_not_found_by_id(self, mock_db_class):
        """Test when specific track ID is not found."""
        # Setup mock database
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.get_content.return_value = [Mock(ID=456)]  # Different ID

        # Execute
        result = get_track_info(track_id=123)

        # Assert
        assert len(result) == 0


class TestGetAudioInfo:
    """Test get_audio_info function."""

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_successful_probe_complete_info(self, mock_probe):
        """Test successful probe with complete audio information."""
        # Setup mock probe response
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 24,
                    "sample_rate": "48000",
                    "channels": 2,
                    "bit_rate": "2304000",  # 2304 kbps
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.flac")

        # Assert
        assert result["bit_depth"] == 24
        assert result["sample_rate"] == 48000
        assert result["channels"] == 2
        assert result["bitrate"] == 2304  # Converted to kbps

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_probe_with_bits_per_raw_sample(self, mock_probe):
        """Test probe using bits_per_raw_sample for bit depth."""
        # Setup mock probe response without bits_per_sample
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_raw_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                    "bit_rate": "1411200",
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.wav")

        # Assert
        assert result["bit_depth"] == 16
        assert result["bitrate"] == 1411

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_probe_with_sample_fmt_parsing(self, mock_probe):
        """Test bit depth parsing from sample_fmt."""
        # Setup mock probe response with sample_fmt
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "sample_fmt": "s32",
                    "sample_rate": "96000",
                    "channels": 2,
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.wav")

        # Assert
        assert result["bit_depth"] == 32
        assert result["sample_rate"] == 96000

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_probe_calculated_bitrate(self, mock_probe):
        """Test bitrate calculation when not provided."""
        # Setup mock probe response without bitrate
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 16,
                    "sample_rate": "44100",
                    "channels": 2,
                    # No bit_rate field
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.wav")

        # Assert - calculated: 44100 * 16 * 2 / 1000 = 1411.2 -> 1411
        assert result["bitrate"] == 1411

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_probe_no_audio_stream(self, mock_probe):
        """Test probe with no audio stream."""
        # Setup mock probe response without audio stream
        mock_probe.return_value = {
            "streams": [{"codec_type": "video", "width": 1920, "height": 1080}]
        }

        # Execute
        result = get_audio_info("/path/to/video.mp4")

        # Assert - should return defaults
        assert result["bit_depth"] == 16
        assert result["sample_rate"] == 44100
        assert result["channels"] == 2
        assert result["bitrate"] == 1411

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_probe_exception_handling(self, mock_probe):
        """Test handling of ffmpeg probe exceptions."""
        # Setup mock to raise exception
        mock_probe.side_effect = Exception("File not found")

        # Execute
        result = get_audio_info("/nonexistent/file.flac")

        # Assert - should return defaults
        assert result["bit_depth"] == 16
        assert result["sample_rate"] == 44100
        assert result["channels"] == 2
        assert result["bitrate"] == 1411

    @patch("rekordbox_bulk_edit.utils.ffmpeg.probe")
    def test_probe_zero_values_handling(self, mock_probe):
        """Test handling of zero values in probe data."""
        # Setup mock probe response with zero bit depth
        mock_probe.return_value = {
            "streams": [
                {
                    "codec_type": "audio",
                    "bits_per_sample": 0,  # Zero value
                    "sample_fmt": "s24",  # Should use this instead
                    "sample_rate": "48000",
                    "channels": 2,
                }
            ]
        }

        # Execute
        result = get_audio_info("/path/to/audio.flac")

        # Assert - should use sample_fmt parsing
        assert result["bit_depth"] == 24
