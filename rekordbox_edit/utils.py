"""Shared utility functions for rekordbox-edit."""

import logging
import platform
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict

import click
import ffmpeg

logger = logging.getLogger(__name__)


class UserQuit(Exception):
    """Exception raised when user chooses to quit"""

    pass


@dataclass(frozen=True)
class FileTypeInfo:
    """One Rekordbox FileType code: how RBE names, filters, probes, and
    converts it. ``codecs`` are ffprobe codec_name prefixes and
    ``containers`` are format_name substrings; a probe must satisfy both
    (WAV and AIFF share PCM codecs, so their containers disambiguate)."""

    code: int
    name: str
    token: str
    extension: str | None = None
    codecs: tuple[str, ...] = ()
    containers: tuple[str, ...] = ()
    convertable: bool = False


FILE_TYPES: dict[int, FileTypeInfo] = {
    # Corrupt or empty content, independent of container.
    0: FileTypeInfo(code=0, name="INVALID", token="invalid"),
    1: FileTypeInfo(code=1, name="MP3", token="mp3", extension=".mp3", codecs=("mp3",)),
    # 3 is the .mp4 container regardless of content: audio-only AAC/ALAC
    # .mp4 files land here alongside video .mp4, so RBE never converts it.
    3: FileTypeInfo(code=3, name="MP4", token="mp4"),
    4: FileTypeInfo(code=4, name="AAC", token="aac", codecs=("aac",)),
    5: FileTypeInfo(
        code=5,
        name="FLAC",
        token="flac",
        extension=".flac",
        codecs=("flac",),
        convertable=True,
    ),
    6: FileTypeInfo(
        code=6,
        name="ALAC",
        token="alac",
        codecs=("alac",),
        convertable=True,
    ),
    11: FileTypeInfo(
        code=11,
        name="WAV",
        token="wav",
        extension=".wav",
        codecs=("pcm_",),
        containers=("wav",),
        convertable=True,
    ),
    12: FileTypeInfo(
        code=12,
        name="AIFF",
        token="aiff",
        extension=".aiff",
        codecs=("pcm_",),
        containers=("aiff",),
        convertable=True,
    ),
    # Catch-all for non-mp4 video containers (avi, m4v, mov, mpg).
    16: FileTypeInfo(code=16, name="VIDEO", token="video"),
}


def get_file_type_name(file_type_code: int | None) -> str | None:
    """Map a Rekordbox FileType code to a display name, or None if unmapped."""
    if file_type_code is None:
        return None
    info = FILE_TYPES.get(file_type_code)
    return info.name if info else None


def get_file_type_codes_for_format(format_name: str) -> set[int]:
    """All FileType codes a format token matches (case-insensitive).

    Tokens mirror FileType values one to one.
    """
    if not format_name:
        raise ValueError("Format name cannot be empty or None")
    token = format_name.lower()
    codes = {code for code, info in FILE_TYPES.items() if token == info.token}
    if not codes:
        raise ValueError(f"Unknown format: {format_name}")
    return codes


def get_file_type_for_format(format_name: str) -> int:
    """The FileType code Rekordbox records for files RBE writes in this
    output format (case-insensitive). Raises for non-output formats."""
    if not format_name:
        raise ValueError("Format name cannot be empty or None")
    token = format_name.lower()
    for code, info in FILE_TYPES.items():
        if info.extension and token == info.token:
            return code
    raise ValueError(f"Unknown format: {format_name}")


def get_extension_for_format(format_name: str) -> str:
    """Get file extension for an output format name (case-insensitive)."""
    code = get_file_type_for_format(format_name)
    extension = FILE_TYPES[code].extension
    assert extension is not None  # get_file_type_for_format only returns such codes
    return extension


def probe_matches_file_type(
    file_type_code: int | None, codec: str | None, container: str | None
) -> bool:
    """Whether a probed codec/container is consistent with a Rekordbox
    FileType code. Unknown codes never match, so callers treat them as
    mismatches instead of converting blind."""
    if file_type_code is None:
        return False
    info = FILE_TYPES.get(file_type_code)
    if info is None:
        return False
    if info.codecs and not (codec or "").startswith(info.codecs):
        return False
    if info.containers:
        if not container or not any(c in container for c in info.containers):
            return False
    return True


class OutputFormats(Enum):
    MP3 = "mp3"
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


class AudioInfo(TypedDict):
    """Fields extracted from an ffmpeg probe of one audio file."""

    bit_depth: int | None
    sample_rate: int
    channels: int
    bitrate: int | None
    codec: str | None
    container: str | None


def get_audio_info(file_path) -> AudioInfo:
    """Get audio information from file using ffmpeg probe.

    Returns None for any field that cannot be determined from the probe data.
    Callers are responsible for handling None values and applying
    format-specific assumptions (e.g. MP3 has no true bit depth). ``codec``
    is the stream's codec_name and ``container`` the probe's format_name.
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
            "codec": audio_stream.get("codec_name"),
            "container": probe.get("format", {}).get("format_name"),
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
