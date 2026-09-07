"""The audio tags Rekordbox reads, and the columns they land in.

`import` writes these columns from a file's tags and `edit` changes them
afterward, so both commands read the mapping from here. Adding a tag to
`tags.TrackTags` without adding it here (or the reverse) fails the parity
test in tests/test_tag_fields.py.

Which mutagen key holds a tag is a separate, format-specific concern and
stays in `tags.py`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TagField:
    """One audio tag, the DjmdContent column it lands in, and how each
    command reaches it."""

    tag: str
    """The `tags.TrackTags` key holding the value read off the file."""
    column: str
    """The DjmdContent column storing it: the value itself for a scalar tag,
    or the foreign key for a relational one."""
    relation: str | None = None
    """The `api._relations.RELATIONS` kind `column` points at, or None where
    the column holds the value directly."""
    proxy: str | None = None
    """The DjmdContent attribute reading the related record's name. Set for a
    relational tag only."""
    edit_field: str | None = None
    """The `edit` command's name for this field, or None where the column is
    not editable."""
    default: str | int = ""
    """What `import` writes when the file carries no such tag."""


#: Every tag both commands know about, in the order `import` reads them.
#:
#: `key` is deliberately not editable: Rekordbox derives KeyID from its own
#: analysis, so a user-supplied key would be overwritten the next time the
#: track is analyzed.
TAG_FIELDS: tuple[TagField, ...] = (
    TagField(tag="title", column="Title", edit_field="Title"),
    TagField(
        tag="artist",
        column="ArtistID",
        relation="artist",
        proxy="ArtistName",
        edit_field="ArtistName",
    ),
    TagField(
        tag="album",
        column="AlbumID",
        relation="album",
        proxy="AlbumName",
        edit_field="AlbumName",
    ),
    TagField(
        tag="genre",
        column="GenreID",
        relation="genre",
        proxy="GenreName",
        edit_field="Genre",
    ),
    TagField(
        tag="label",
        column="LabelID",
        relation="label",
        proxy="LabelName",
        edit_field="Label",
    ),
    TagField(
        tag="composer",
        column="ComposerID",
        relation="artist",
        proxy="ComposerName",
        edit_field="ComposerName",
    ),
    TagField(tag="key", column="KeyID", relation="key", proxy="KeyName"),
    TagField(tag="comment", column="Commnt", edit_field="Comment"),
    TagField(tag="isrc", column="ISRC", edit_field="ISRC"),
    TagField(tag="track_no", column="TrackNo", edit_field="TrackNo", default=0),
    TagField(tag="disc_no", column="DiscNo", edit_field="DiscNo", default=0),
    TagField(
        tag="release_year", column="ReleaseYear", edit_field="ReleaseYear", default=0
    ),
)
