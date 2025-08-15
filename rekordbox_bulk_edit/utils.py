"""Shared utility functions for rekordbox-bulk-edit."""

import platform
import shutil

import ffmpeg
from pyrekordbox import Rekordbox6Database

from rekordbox_bulk_edit.logger import Logger

logger = Logger()


# File type mappings for Rekordbox database
def get_file_type_name(file_type_code: int):
    """Get human-readable name for file type code."""
    _get_file_type_name = {
        0: "MP3",
        1: "MP3",
        4: "M4A",
        5: "FLAC",
        11: "WAV",
        12: "AIFF",
    }
    name = _get_file_type_name.get(file_type_code)
    if name is None:
        raise ValueError(f"Unknown file_type: {file_type_code}")
    return name


def get_file_type_for_format(format_name: str):
    """Get file type code for format name (case-insensitive)."""
    if not format_name:
        raise ValueError("Format name cannot be empty or None")
    _get_file_type_for_format = {"MP3": 1, "M4A": 4, "FLAC": 5, "WAV": 11, "AIFF": 12}
    file_type = _get_file_type_for_format.get(format_name.upper())
    if file_type is None:
        raise ValueError(f"Unknown format: {format_name}")
    return file_type


def get_extension_for_format(format_name: str):
    """Get file extension for format name (case-insensitive)."""
    if not format_name:
        raise ValueError("Format name cannot be empty or None")
    _get_extension_for_format = {
        "MP3": ".mp3",
        "AIFF": ".aiff",
        "FLAC": ".flac",
        "WAV": ".wav",
        "ALAC": ".m4a",
    }
    extension = _get_extension_for_format.get(format_name.upper())
    if extension is None:
        raise ValueError(f"Unknown format: {format_name}")
    return extension


def print_track_info(content_list):
    """Print formatted track information"""
    if not content_list:
        return

    # Column widths (total ≈ 240 chars with spacing)
    widths = {
        "id": 10,
        "filename": 40,
        "type": 8,
        "sample_rate": 14,
        "bitrate": 8,
        "bit_depth": 8,
        "location": 70,
    }

    # Print header
    header = (
        f"{'ID':<{widths['id']}}   "
        f"{'FileNameL':<{widths['filename']}}   "
        f"{'Type':<{widths['type']}}   "
        f"{'SampleRate':<{widths['sample_rate']}}   "
        f"{'BitRate':<{widths['bitrate']}}   "
        f"{'BitDepth':<{widths['bit_depth']}}   "
        f"{'FolderPath':<{widths['location']}}"
    )

    logger.info(header)
    logger.info("-" * len(header))

    # Print each track
    for content in content_list:
        # Get values with fallbacks
        track_id = str(content.ID or "")
        filename = content.FileNameL or "N/A"
        file_format = get_file_type_name(content.FileType)

        # Get sample rate
        value = content.SampleRate
        if value and value != 0:
            sample_rate = str(value)
        else:
            sample_rate = "--"

        # Get bitrate
        value = content.BitRate
        if value or value == 0:
            bitrate = str(value)
        else:
            bitrate = "--"

        # Get bit depth
        value = content.BitDepth
        if value or value == 0:
            bit_depth = str(value)
        else:
            bit_depth = "--"

        location = content.FolderPath or "N/A"

        # Truncate long values in the middle
        if len(filename) > widths["filename"]:
            available = widths["filename"] - 3  # Reserve 3 chars for "..."
            start_chars = available // 2
            end_chars = available - start_chars
            filename = filename[:start_chars] + "..." + filename[-end_chars:]
        if len(location) > widths["location"]:
            available = widths["location"] - 3  # Reserve 3 chars for "..."
            start_chars = available // 2
            end_chars = available - start_chars
            location = location[:start_chars] + "..." + location[-end_chars:]

        # Print row
        row = (
            f"{track_id:<{widths['id']}}   "
            f"{filename:<{widths['filename']}}   "
            f"{file_format:<{widths['type']}}   "
            f"{sample_rate:<{widths['sample_rate']}}   "
            f"{bitrate:<{widths['bitrate']}}   "
            f"{bit_depth:<{widths['bit_depth']}}   "
            f"{location:<{widths['location']}}"
        )

        logger.info(row)


def get_track_info(track_id=None, format_filter=None):
    """Get track information from database. Returns list of matching tracks."""
    try:
        db = Rekordbox6Database()
        all_content = db.get_content()

        if track_id:
            # Find specific track
            content_list = [
                content for content in all_content if content.ID == int(track_id)
            ]
        else:
            if format_filter:
                # Filter by specific format
                try:
                    target_file_type = get_file_type_for_format(format_filter)
                    content_list = [
                        content
                        for content in all_content
                        if content.FileType == target_file_type
                    ]
                except ValueError:
                    content_list = []
            else:
                # Get all audio files (exclude unknown types)
                known_file_types = {0, 1, 4, 5, 11, 12}  # Known file type codes
                content_list = [
                    content
                    for content in all_content
                    if content.FileType in known_file_types
                ]

        return content_list

    except Exception as e:
        logger.error(f"{get_track_info.__name__}: Failed to access RekordBox database.")
        logger.error(e, exc_info=True)
        return []


def check_ffmpeg_available():
    """Check if ffmpeg is available in PATH"""
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_directions():
    """Get helpful error message for missing ffmpeg"""
    if platform.system() == "Windows":  # Windows
        return """
FFmpeg is required for rekordbox-bulk-edit.
Please install FFmpeg:
https://ffmpeg.org/download.html
"""
    else:  # macOS
        return """
FFmpeg is required for rekordbox-bulk-edit.
Please install FFmpeg:
brew install ffmpeg
or https://ffmpeg.org/download.html
"""


def get_audio_info(file_path) -> dict[str, int]:
    """Get audio information from file using ffmpeg probe"""
    try:
        # Check if ffmpeg is available first
        if not check_ffmpeg_available():
            raise Exception(get_ffmpeg_directions())

        probe = ffmpeg.probe(file_path)
        audio_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "audio"),
            None,
        )
        if not audio_stream:
            raise Exception("No audio stream")

        # Try multiple ways to get bit depth
        bit_depth = -1  # default

        # Method 1: bits_per_sample
        if "bits_per_sample" in audio_stream and audio_stream["bits_per_sample"] != 0:
            bit_depth = int(audio_stream["bits_per_sample"])
        # Method 2: bits_per_raw_sample
        elif (
            "bits_per_raw_sample" in audio_stream
            and audio_stream["bits_per_raw_sample"] != 0
        ):
            bit_depth = int(audio_stream["bits_per_raw_sample"])
        # Method 3: parse from sample_fmt (e.g., "s16", "s24", "s32")
        elif "sample_fmt" in audio_stream:
            sample_fmt = audio_stream["sample_fmt"]
            if "16" in sample_fmt:
                bit_depth = 16
            elif "24" in sample_fmt:
                bit_depth = 24
            elif "32" in sample_fmt:
                bit_depth = 32

        # Get bitrate (try from stream first, then calculate)
        bitrate = -1
        if "bit_rate" in audio_stream and audio_stream["bit_rate"]:
            bitrate = int(audio_stream["bit_rate"]) // 1000  # Convert to kbps
        else:
            logger.verbose("Calculating bit rate...")
            # Calculate bitrate: sample_rate * bit_depth * channels, then convert to kbps
            sample_rate = int(audio_stream.get("sample_rate", -1))
            channels = int(audio_stream.get("channels", 1))
            bitrate = (sample_rate * bit_depth * channels) // 1000  # Convert to kbps

        if bit_depth < 0:
            raise Exception("No valid bit depth")
        if bitrate < 0:
            raise Exception("No valid bitrate")

        return {
            "bit_depth": bit_depth,
            "sample_rate": int(audio_stream.get("sample_rate", 44100)),
            "channels": int(audio_stream.get("channels", 2)),
            "bitrate": bitrate,
        }
    except Exception as e:
        logger.error(f"Failed to get info for {file_path}")
        logger.error(e, exc_info=True)
        raise e
