from collections.abc import Sequence

from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.models import ConvertOp, EditOp, Track

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
