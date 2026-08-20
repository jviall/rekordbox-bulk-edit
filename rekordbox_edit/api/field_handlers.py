"""Per-field edit handlers.

Each field the `edit` command can change is one handler: it reads the field's
current value, computes the new value from the request, validates input, and
writes it. Simple columns use `StringField`; other fields subclass to add their
own encoding or relational lookup.
"""

import logging

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb
from sqlalchemy import or_

from rekordbox_edit.models import EditRequest

logger = logging.getLogger(__name__)


class FieldHandler:
    """Read, compute, validate, and apply one editable field."""

    name: str
    supports_match: bool = True

    def validate_request(self, args: EditRequest) -> None:
        """Validate request-level input. Raise ValueError on bad input."""

    def current_value(self, content) -> str | None:
        raise NotImplementedError  # pragma: no cover

    def compute_new_value(self, current: str | None, args: EditRequest) -> str | None:
        """New value as a string, or None to signal no change / skip."""
        raise NotImplementedError  # pragma: no cover

    def apply(self, db: Rekordbox6Database, content, new_value: str) -> None:
        raise NotImplementedError  # pragma: no cover


def _replace(current: str | None, args: EditRequest) -> str | None:
    """Find/replace within the current value, or overwrite it wholesale.

    Plain replace assigns the value even to an empty field. Match mode needs
    existing text to search, so it skips an empty (None) field."""
    if args.match_pattern is not None:
        if current is None:
            return None
        return str(current).replace(args.match_pattern, args.replace_value)
    return args.replace_value


class StringField(FieldHandler):
    """A plain text column edited in place."""

    supports_match = True

    def __init__(self, name: str, column: str):
        self.name = name
        self.column = column

    def current_value(self, content):
        return getattr(content, self.column)

    def compute_new_value(self, current, args):
        return _replace(current, args)

    def apply(self, db, content, new_value):
        setattr(content, self.column, new_value)


# Every DjmdContent column pointing at a DjmdArtist row; an artist is orphaned
# only when none of these, nor any album's AlbumArtistID, still reference it.
_ARTIST_ROLE_COLUMNS = (
    tb.DjmdContent.ArtistID,
    tb.DjmdContent.RemixerID,
    tb.DjmdContent.OrgArtistID,
    tb.DjmdContent.ComposerID,
    tb.DjmdContent.Lyricist,
)


class RelationalField(FieldHandler):
    """Artist or album: a shared record reached through a foreign key.

    Setting the value reuses an existing record with the same name or creates
    one, then repoints the track. A record left with no references is deleted,
    matching Rekordbox. Reusing an album leaves its album-artist untouched, and
    new albums are created without one.
    """

    supports_match = True

    def __init__(self, name: str, fk_column: str, name_attr: str, kind: str):
        self.name = name
        self.fk_column = fk_column
        self.name_attr = name_attr
        self.kind = kind

    def current_value(self, content):
        return getattr(content, self.name_attr)

    def compute_new_value(self, current, args):
        return _replace(current, args)

    def apply(self, db, content, new_value):
        old_id = getattr(content, self.fk_column)
        if new_value == "":
            setattr(content, self.fk_column, "")
        else:
            record = self._get_or_create(db, new_value)
            setattr(content, self.fk_column, record.ID)
        db.session.flush()
        self._delete_if_orphaned(db, old_id)

    def _get_or_create(self, db, name):
        if self.kind == "artist":
            existing = (
                db.session.query(tb.DjmdArtist)
                .filter_by(Name=name)
                .order_by(tb.DjmdArtist.ID)
                .first()
            )
            return existing or db.add_artist(name)
        existing = (
            db.session.query(tb.DjmdAlbum)
            .filter_by(Name=name)
            .order_by(tb.DjmdAlbum.ID)
            .first()
        )
        return existing or db.add_album(name)

    def _delete_if_orphaned(self, db, old_id):
        if old_id in (None, ""):
            return
        if self.kind == "artist":
            in_content = (
                db.session.query(tb.DjmdContent)
                .filter(or_(*(col == old_id for col in _ARTIST_ROLE_COLUMNS)))
                .first()
            )
            in_album = (
                db.session.query(tb.DjmdAlbum)
                .filter(tb.DjmdAlbum.AlbumArtistID == old_id)
                .first()
            )
            if in_content is None and in_album is None:
                row = db.get_artist(ID=old_id)
                if row is not None:
                    db.delete(row)
        else:
            in_content = (
                db.session.query(tb.DjmdContent)
                .filter(tb.DjmdContent.AlbumID == old_id)
                .first()
            )
            if in_content is None:
                row = db.get_album(ID=old_id)
                if row is not None:
                    db.delete(row)


FIELD_HANDLERS: dict[str, FieldHandler] = {
    handler.name: handler
    for handler in (
        StringField("Title", "Title"),
        RelationalField("ArtistName", "ArtistID", "ArtistName", "artist"),
        RelationalField("AlbumName", "AlbumID", "AlbumName", "album"),
    )
}
