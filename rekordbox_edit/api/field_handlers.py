"""Per-field edit handlers.

Each field the `edit` command can change is one handler: it reads the field's
current value, computes the new value from the request, validates input, and
writes it. Simple columns use `StringField`; other fields subclass to add their
own encoding or relational lookup.
"""

import logging

from pyrekordbox import Rekordbox6Database

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


FIELD_HANDLERS: dict[str, FieldHandler] = {
    handler.name: handler for handler in (StringField("Title", "Title"),)
}
