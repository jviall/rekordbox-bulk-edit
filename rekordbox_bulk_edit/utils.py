"""Shared utility functions for rekordbox-bulk-edit."""

import platform
import shutil
from enum import Enum
from typing import Dict, Sequence

import ffmpeg
from pyrekordbox.db6 import DjmdContent

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


class PrintableField(Enum):
    """Columns of DjmdContent that you can print"""

    ID = "ID"
    FileNameL = "FileNameL"
    FolderPath = "FolderPath"
    FileType = "FileType"
    SampleRate = "SampleRate"
    BitDepth = "BitDepth"
    BitRate = "BitRate"
    ArtistName = "ArtistName"
    AlbumName = "AlbumName"
    Title = "Title"


# Column widths (total ≈ 240 chars with spacing)
PRINT_WIDTHS: Dict[PrintableField, int] = {
    PrintableField.ID: 10,
    PrintableField.FileNameL: 25,
    PrintableField.Title: 25,
    PrintableField.ArtistName: 20,
    PrintableField.AlbumName: 20,
    PrintableField.FileType: 4,
    PrintableField.SampleRate: 8,
    PrintableField.BitRate: 5,
    PrintableField.BitDepth: 5,
    PrintableField.FolderPath: 50,
}

# Print header
PRINT_HEADERS: Dict[PrintableField, str] = {
    PrintableField.ID: f"{'ID':<{PRINT_WIDTHS[PrintableField.ID]}}",
    PrintableField.FileNameL: f"{'File':<{PRINT_WIDTHS[PrintableField.FileNameL]}}",
    PrintableField.Title: f"{'Title':<{PRINT_WIDTHS[PrintableField.Title]}}",
    PrintableField.ArtistName: f"{'Artist':<{PRINT_WIDTHS[PrintableField.ArtistName]}}",
    PrintableField.AlbumName: f"{'Album':<{PRINT_WIDTHS[PrintableField.AlbumName]}}",
    PrintableField.FileType: f"{'Type':<{PRINT_WIDTHS[PrintableField.FileType]}}",
    PrintableField.SampleRate: f"{'SampleRt':<{PRINT_WIDTHS[PrintableField.SampleRate]}}",
    PrintableField.BitRate: f"{'BitRt':<{PRINT_WIDTHS[PrintableField.BitRate]}}",
    PrintableField.BitDepth: f"{'BitDp':<{PRINT_WIDTHS[PrintableField.BitDepth]}}",
    PrintableField.FolderPath: f"{'FolderPath':<{PRINT_WIDTHS[PrintableField.FolderPath]}}",
}


def truncate_field(field: PrintableField, value: str | None):
    if value is None:
        return ""
    if len(value) <= PRINT_WIDTHS[field]:
        return value
    available = PRINT_WIDTHS[field] - 3  # Reserve 3 chars for "..."
    start_chars = available // 5 * 2
    end_chars = available - start_chars
    return f"{value[:start_chars]}...{value[-end_chars:]}"


def print_track_info(
    content_list: Sequence[DjmdContent],
    print_columns: Sequence[PrintableField] | None = None,
):
    """Print formatted track information"""
    if not content_list:
        return

    print_columns = print_columns or [
        PrintableField.Title,
        PrintableField.ArtistName,
        PrintableField.AlbumName,
        PrintableField.FileType,
        PrintableField.SampleRate,
        PrintableField.BitDepth,
        PrintableField.FolderPath,
    ]

    header = "  ".join(map(lambda col: PRINT_HEADERS[col], print_columns))
    logger.info(header)
    logger.info("-" * len(header))

    # Print each track
    for content in content_list:
        # Print row
        rows = {
            PrintableField.ID: f"{content.ID:<{PRINT_WIDTHS[PrintableField.ID]}}",
            PrintableField.FileNameL: f"{truncate_field(PrintableField.FileNameL, content.FileNameL):<{PRINT_WIDTHS[PrintableField.FileNameL]}}",
            PrintableField.Title: f"{truncate_field(PrintableField.Title, content.Title):<{PRINT_WIDTHS[PrintableField.Title]}}",
            PrintableField.AlbumName: f"{truncate_field(PrintableField.AlbumName, content.AlbumName):<{PRINT_WIDTHS[PrintableField.AlbumName]}}",
            PrintableField.ArtistName: f"{truncate_field(PrintableField.ArtistName, content.ArtistName):<{PRINT_WIDTHS[PrintableField.ArtistName]}}",
            PrintableField.FileType: f"{get_file_type_name(content.FileType):<{PRINT_WIDTHS[PrintableField.FileType]}}",
            PrintableField.SampleRate: f"{content.SampleRate:<{PRINT_WIDTHS[PrintableField.SampleRate]}}",
            PrintableField.BitRate: f"{content.BitRate:<{PRINT_WIDTHS[PrintableField.BitRate]}}",
            PrintableField.BitDepth: f"{content.BitDepth:<{PRINT_WIDTHS[PrintableField.BitDepth]}}",
            PrintableField.FolderPath: f"{truncate_field(PrintableField.FolderPath, content.FolderPath):<{PRINT_WIDTHS[PrintableField.FolderPath]}}",
        }

        row = "  ".join(map(lambda col: rows[col], print_columns))

        logger.info(row)


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
