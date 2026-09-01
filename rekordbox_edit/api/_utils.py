import logging
from collections.abc import Sequence
from typing import Any

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import DjmdContent
from sqlalchemy import text

from rekordbox_edit.models import ConvertOp, EditOp, Track
from rekordbox_edit.query import require_session
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


#: Claims the next `count` USNs. SQLite evaluates `int_1 + :count` against the
#: row as it stands, under the write lock the statement takes, and RETURNING
#: hands back the new total, so the claimed block ends there and starts
#: `count - 1` below it. Nothing is read into Python first, so no other writer
#: can slip in between.
_RESERVE_USNS = text(
    "UPDATE agentRegistry SET int_1 = int_1 + :count "
    "WHERE registry_id = 'localUpdateCount' RETURNING int_1"
)


def stamp_usns(db: Rekordbox6Database, rows: Sequence[Any]) -> int | None:
    """Give each row a fresh USN and advance the library's counter.

    A USN is rekordbox's change stamp: a syncing peer would ask for rows above the
    last value it saw.

    Call this inside the transaction that writes the rows.

    One USN per row, which is likely more than how Rekordbox applies changes,
    because we're not going to bother stamping a commit per column changed.
    """
    stampable = [row for row in rows if hasattr(row, "rb_local_usn")]
    if not stampable:
        return None

    session = require_session(db)
    high = session.execute(_RESERVE_USNS, {"count": len(stampable)}).scalar()
    if high is None:
        logger.warning("No localUpdateCount in agentRegistry; leaving USNs unstamped. ")
        return None

    for usn, row in enumerate(stampable, start=high - len(stampable) + 1):
        row.rb_local_usn = usn

    logger.debug(f"reserved USNs {high - len(stampable) + 1}..{high}")
    return high
