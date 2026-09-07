"""Parity checks between the tag registry and everything reading it.

The registry only earns its keep if drift fails loudly, so these assert that
`tags.TrackTags`, `DjmdContent`, and the relation kinds all still agree
with it.
"""

from typing import get_type_hints

from pyrekordbox.db6 import tables as tb

from rekordbox_edit._tag_fields import TAG_FIELDS
from rekordbox_edit.api._relations import RELATIONS
from rekordbox_edit.tags import TrackTags

#: TrackTags keys read off the audio stream rather than a tag, so they have no
#: registry row: `import` derives both and neither is editable.
_STREAM_KEYS = {"length", "file_type"}


def test_every_registry_tag_is_a_track_tags_key():
    keys = set(get_type_hints(TrackTags))
    assert {f.tag for f in TAG_FIELDS} <= keys


def test_every_track_tags_key_has_a_registry_row():
    keys = set(get_type_hints(TrackTags)) - _STREAM_KEYS
    assert keys == {f.tag for f in TAG_FIELDS}


def test_every_registry_column_exists_on_content():
    columns = {c.key for c in tb.DjmdContent.__table__.columns}
    for field in TAG_FIELDS:
        assert field.column in columns, field.tag


def test_relational_rows_name_a_known_kind_and_proxy():
    for field in TAG_FIELDS:
        if field.relation is None:
            assert field.proxy is None, field.tag
            continue
        assert field.relation in RELATIONS, field.tag
        assert field.proxy is not None, field.tag
        assert hasattr(tb.DjmdContent, field.proxy), field.tag
