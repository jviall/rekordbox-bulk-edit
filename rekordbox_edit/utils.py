"""Shared utility functions for rekordbox-edit."""

import logging
import platform
import shutil
from enum import Enum

import click
import ffmpeg

logger = logging.getLogger(__name__)


class UserQuit(Exception):
    """Exception raised when user chooses to quit"""

    pass


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


class OutputFormats(Enum):
    MP3 = "mp3"
    FLAC = "flac"
    AIFF = "aiff"
    WAV = "wav"


class InputFormats(Enum):
    FLAC = "flac"
    AIFF = "aiff"
    WAV = "wav"


def ffmpeg_in_path():
    """Check availability of ffmpeg program via which command"""
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_directions():
    """Get helpful error message for missing ffmpeg"""
    if platform.system() == "Windows":  # Windows
        return """
FFmpeg is required for rekordbox-edit.
Please install FFmpeg:
https://ffmpeg.org/download.html
"""
    else:  # macOS
        return """
FFmpeg is required for rekordbox-edit.
Please install FFmpeg:
brew install ffmpeg
or https://ffmpeg.org/download.html
"""


def get_audio_info(file_path) -> dict[str, int | None]:
    """Get audio information from file using ffmpeg probe.

    Returns None for any field that cannot be determined from the probe data.
    Callers are responsible for handling None values and applying format-specific
    assumptions (e.g. MP3 has no true bit depth).
    """
    try:
        # Check if ffmpeg is available first
        if not ffmpeg_in_path():
            raise Exception(get_ffmpeg_directions())

        probe = ffmpeg.probe(file_path)
        audio_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "audio"),
            None,
        )
        if not audio_stream:
            raise Exception(f"No audio stream found in {file_path}")

        # Try multiple ways to get bit depth
        bit_depth = None

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

        if bit_depth is None:
            logger.debug(f"Could not determine bit depth for {file_path}")

        # Get bitrate from stream, or calculate from audio properties if available
        bitrate = None
        if "bit_rate" in audio_stream and audio_stream["bit_rate"]:
            bitrate = int(audio_stream["bit_rate"]) // 1000  # Convert to kbps
        elif bit_depth is not None:
            logger.debug("Calculating bit rate from sample_rate * bit_depth * channels")
            sample_rate = int(audio_stream.get("sample_rate", 0))
            channels = int(audio_stream.get("channels", 1))
            if sample_rate > 0:
                bitrate = (sample_rate * bit_depth * channels) // 1000

        if bitrate is None:
            logger.debug(f"Could not determine bitrate for {file_path}")

        return {
            "bit_depth": bit_depth,
            "sample_rate": int(audio_stream.get("sample_rate", 44100)),
            "channels": int(audio_stream.get("channels", 2)),
            "bitrate": bitrate,
        }
    except Exception as e:
        logger.error(f"Failed to get audio info for {file_path}: {e}")
        logger.debug("Full traceback:", exc_info=True)
        raise e


def confirm(
    prompt: str,
    default: bool = False,
    binary: bool = False,
    abort: bool = False,
):
    """Prompts the user to prompt [y]es/[n]o/[q]uit

    Args:
        prompt: The question to ask the user
        default: Default response (True for y, False for n)
        binary: If True, prompt a simple y/n
        abort: If True, prompt a simple y/n where 'n' raises a UserQuit Exception
    """
    from enum import Enum

    class ConfirmChoice(Enum):
        YES = "y"
        NO = "n"
        QUIT = "q"

    if abort or binary:
        choices = [ConfirmChoice.YES.value, ConfirmChoice.NO.value]
        default_choice = ConfirmChoice.YES.value if default else ConfirmChoice.NO.value
    else:
        choices = [
            ConfirmChoice.YES.value,
            ConfirmChoice.NO.value,
            ConfirmChoice.QUIT.value,
        ]
        default_choice = ConfirmChoice.YES.value if default else ConfirmChoice.NO.value

    response: str = click.prompt(
        prompt,
        type=click.Choice(choices, case_sensitive=False),
        default=default_choice,
    )

    if response.lower() == ConfirmChoice.YES.value:
        logger.debug(f"User confirmed: {prompt}")
        return True
    elif response.lower() == ConfirmChoice.NO.value:
        logger.debug(f"User declined: {prompt}")
        if abort:
            raise UserQuit("User declined to continue")
        else:
            return False
    elif response.lower()[0] == ConfirmChoice.QUIT.value:
        logger.debug("User quit.")
        raise UserQuit("User quit")
