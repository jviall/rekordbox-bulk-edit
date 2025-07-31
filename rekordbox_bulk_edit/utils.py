"""Shared utility functions for rekordbox-bulk-edit."""

import os

import ffmpeg
from pyrekordbox import Rekordbox6Database


def format_file_type(file_type_code):
    """Convert file type code to human readable format"""
    file_type_map = {0: "MP3", 1: "MP3", 4: "M4A", 5: "FLAC", 11: "WAV", 12: "AIFF"}
    return file_type_map.get(file_type_code, f"Unk({file_type_code})")


def print_track_info(content_list):
    """Print formatted track information"""
    if not content_list:
        print("No tracks found.")
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

    print(header)
    print("-" * len(header))

    # Print each track
    for content in content_list:
        # Get values with fallbacks
        track_id = str(content.ID or "")
        filename = content.FileNameL or "N/A"
        file_type = format_file_type(content.FileType)

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
            f"{file_type:<{widths['type']}}   "
            f"{sample_rate:<{widths['sample_rate']}}   "
            f"{bitrate:<{widths['bitrate']}}   "
            f"{bit_depth:<{widths['bit_depth']}}   "
            f"{location:<{widths['location']}}"
        )

        print(row)


def get_track_info(track_id=None):
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
            # Get all FLAC files
            content_list = [content for content in all_content if content.FileType == 5]

        return content_list

    except Exception as e:
        print(f"Error accessing RekordBox database: {e}")
        return []


def get_audio_info(file_path):
    """Get audio information from file using ffmpeg probe"""
    try:
        probe = ffmpeg.probe(file_path)
        audio_stream = next(
            (stream for stream in probe["streams"] if stream["codec_type"] == "audio"),
            None,
        )
        if audio_stream:
            # Try multiple ways to get bit depth
            bit_depth = 16  # default

            # Method 1: bits_per_sample
            if (
                "bits_per_sample" in audio_stream
                and audio_stream["bits_per_sample"] != 0
            ):
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
            bitrate = 0
            if "bit_rate" in audio_stream and audio_stream["bit_rate"]:
                bitrate = int(audio_stream["bit_rate"]) // 1000  # Convert to kbps
            else:
                # Calculate bitrate: sample_rate * bit_depth * channels, then convert to kbps
                sample_rate = int(audio_stream.get("sample_rate", 44100))
                channels = int(audio_stream.get("channels", 2))
                bitrate = (
                    sample_rate * bit_depth * channels
                ) // 1000  # Convert to kbps
                print(f"Calculated bit rate: {bitrate} kbps")

            return {
                "bit_depth": bit_depth,
                "sample_rate": int(audio_stream.get("sample_rate", 44100)),
                "channels": int(audio_stream.get("channels", 2)),
                "bitrate": bitrate,
            }
    except Exception as e:
        print(f"Warning: Could not probe {file_path}: {e}")

    # Return defaults if probe fails
    return {
        "bit_depth": 16,
        "sample_rate": 44100,
        "channels": 2,
        "bitrate": 1411,
    }  # 1411 kbps for 16-bit/44.1kHz/stereo
