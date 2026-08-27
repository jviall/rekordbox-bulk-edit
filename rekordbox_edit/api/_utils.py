import logging
from collections.abc import Sequence

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.models import ConvertOp, EditOp, Track
from rekordbox_edit.utils import AudioInfo, get_file_type_for_format

logger = logging.getLogger(__name__)

_COLUMN_KEYS = tuple(c.key for c in DjmdContent.__table__.columns)


def _track_from_content(content: DjmdContent) -> Track:
    data = {k: getattr(content, k) for k in _COLUMN_KEYS}
    data["ID"] = str(data["ID"])
    # association_proxy attributes; not present in __table__.columns
    data["ArtistName"] = content.ArtistName
    data["AlbumName"] = content.AlbumName
    return Track(**data)


def _order_tracks_by_op(
    contents: Sequence[DjmdContent], ops: Sequence[EditOp | ConvertOp]
) -> list[Track]:
    """Build Track list in op order from raw DjmdContent rows.

    Builds the id -> content lookup internally so callers don't have to. Ops
    whose id is not in `contents` are silently skipped (the caller already
    knows about the divergence from upstream logic).
    """
    content_map = {str(c.ID): c for c in contents}
    return [
        _track_from_content(content_map[op.id]) for op in ops if op.id in content_map
    ]


_MP3_FILE_TYPE = get_file_type_for_format("mp3")
_FLAC_FILE_TYPE = get_file_type_for_format("flac")


def _sync_audio_columns(
    content: DjmdContent, audio_info: AudioInfo, file_type: int, file_size: int
) -> None:
    """Write the technical columns describing an audio file onto its content
    row: FileType, SampleRate, BitDepth, BitRate, and FileSize. Follows
    rekordbox's conventions: FLAC bitrate is stored as 0 (VBR) and MP3 bit
    depth as 16 (probes report none for MP3)."""
    content.FileType = file_type
    if audio_info["sample_rate"]:
        content.SampleRate = audio_info["sample_rate"]
    if file_type == _MP3_FILE_TYPE:
        content.BitDepth = 16
    elif audio_info["bit_depth"]:
        content.BitDepth = audio_info["bit_depth"]
    if file_type == _FLAC_FILE_TYPE:
        content.BitRate = 0
    elif audio_info["bitrate"] is not None:
        content.BitRate = audio_info["bitrate"]
    content.FileSize = file_size


def _update_anlz_paths(
    db: Rekordbox6Database, content: DjmdContent, new_filename: str
) -> None:
    """Rewrite the PPTH path tag in a track's ANLZ files to the given file
    name, in rekordbox's device-relative ``?/<name>`` form.

    No-op for tracks without an analysis.
    """
    if not content.AnalysisDataPath:
        return
    new_ppth = f"?/{new_filename}"
    anlz_files = db.read_anlz_files(content.ID)
    for anlz_path, anlz in anlz_files.items():
        anlz.set_path(new_ppth)
        anlz.save(anlz_path)
        logger.debug(f"Updated PPTH of {anlz_path} to {new_ppth}")
