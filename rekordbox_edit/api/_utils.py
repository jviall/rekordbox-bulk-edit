from pyrekordbox.db6 import DjmdContent

from rekordbox_edit.models import Track

_COLUMN_KEYS = tuple(c.key for c in DjmdContent.__table__.columns)


def _track_from_content(content: DjmdContent) -> Track:
    data = {k: getattr(content, k) for k in _COLUMN_KEYS}
    data["ID"] = str(data["ID"])
    # association_proxy attributes; not present in __table__.columns
    data["ArtistName"] = content.ArtistName
    data["AlbumName"] = content.AlbumName
    return Track(**data)
