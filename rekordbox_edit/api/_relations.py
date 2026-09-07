"""The shared records a track points at, and the rules for reusing, creating,
and collecting them.

Artist, album, genre, label, and key each live in their own table and are
reached from `DjmdContent` through a foreign key. `edit`, `import`, and
`remove` all need the same three facts about each kind: which table holds it,
which columns count as a reference to it, and how a new one is made. That
knowledge lives here once rather than in each command.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb
from sqlalchemy import or_

from rekordbox_edit.query import require_session

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Relation:
    """One kind of shared record, and how the library refers to it."""

    kind: str
    table: type[tb.Base]
    name_attr: str
    """The column on `table` holding the record's name."""
    content_columns: tuple[str, ...]
    """Every `DjmdContent` column pointing at a record of this kind."""
    factory_name: str | None = None
    """The `Rekordbox6Database` method creating a record, or None where the
    table is a closed set the tool must not add to."""
    empty_value: str = ""
    """What a cleared foreign key stores."""
    extra_columns: tuple[tuple[type[tb.Base], str], ...] = ()
    """References from outside `DjmdContent`, as (table, column name)."""
    cascade_columns: dict[str, str] = field(default_factory=dict)
    """Columns on this record pointing at another kind, by that kind. Deleting
    the record may leave those targets unreferenced."""

    @property
    def sweepable(self) -> bool:
        """Whether Rekordbox collects this kind once nothing references it.

        A closed table is shared by hundreds of tracks and names a fixed
        vocabulary, so collecting one of its rows would be wrong even at zero
        references.
        """
        return self.factory_name is not None


#: Every kind of shared record, by kind name. `key` is present so callers can
#: resolve a KeyID from a name, but `DjmdKey` is a closed table: it has no
#: factory, so it is never created and never collected.
RELATIONS: dict[str, Relation] = {
    "artist": Relation(
        kind="artist",
        table=tb.DjmdArtist,
        name_attr="Name",
        content_columns=(
            "ArtistID",
            "RemixerID",
            "OrgArtistID",
            "ComposerID",
            "Lyricist",
        ),
        factory_name="add_artist",
        extra_columns=((tb.DjmdAlbum, "AlbumArtistID"),),
    ),
    "album": Relation(
        kind="album",
        table=tb.DjmdAlbum,
        name_attr="Name",
        content_columns=("AlbumID",),
        factory_name="add_album",
        cascade_columns={"AlbumArtistID": "artist"},
    ),
    "genre": Relation(
        kind="genre",
        table=tb.DjmdGenre,
        name_attr="Name",
        content_columns=("GenreID",),
        factory_name="add_genre",
    ),
    "label": Relation(
        kind="label",
        table=tb.DjmdLabel,
        name_attr="Name",
        content_columns=("LabelID",),
        factory_name="add_label",
    ),
    "key": Relation(
        kind="key",
        table=tb.DjmdKey,
        name_attr="ScaleName",
        content_columns=("KeyID",),
        empty_value="0",
    ),
}

#: Every DjmdContent column pointing at a DjmdArtist row, as column objects.
ARTIST_ROLE_COLUMNS = tuple(
    getattr(tb.DjmdContent, name) for name in RELATIONS["artist"].content_columns
)


def find_by_name(db: Rekordbox6Database, kind: str, name: str):
    """The lowest-ID record of this kind carrying `name`, or None."""
    relation = RELATIONS[kind]
    return (
        require_session(db)
        .query(relation.table)
        .filter_by(**{relation.name_attr: name})
        .order_by(getattr(relation.table, "ID"))
        .first()
    )


def get_or_create(
    db: Rekordbox6Database, kind: str, name: str, created: list | None = None
):
    """Reuse a record of this kind matching by name, else create one.

    New rows are appended to `created` when given: `add_content` flushes,
    which moves them out of `session.new` before they can be found again.

    Raises KeyError for a kind with no factory, whose table the tool must not
    add to.
    """
    existing = find_by_name(db, kind, name)
    if existing is not None:
        return existing
    relation = RELATIONS[kind]
    if relation.factory_name is None:
        raise KeyError(f"{kind} records cannot be created")
    row = getattr(db, relation.factory_name)(name)
    if created is not None:
        created.append(row)
    return row


def is_referenced(db: Rekordbox6Database, kind: str, record_id: str) -> bool:
    """Whether anything still points at this record."""
    session = require_session(db)
    relation = RELATIONS[kind]
    columns = [getattr(tb.DjmdContent, name) for name in relation.content_columns]
    if (
        session.query(tb.DjmdContent)
        .filter(or_(*(column == record_id for column in columns)))
        .first()
        is not None
    ):
        return True
    for table, column_name in relation.extra_columns:
        if (
            session.query(table)
            .filter(getattr(table, column_name) == record_id)
            .first()
            is not None
        ):
            return True
    return False


def delete_if_orphaned(db: Rekordbox6Database, kind: str, record_id: Any) -> int:
    """Collect one vacated record, and anything the collection orphans."""
    if record_id in (None, ""):
        return 0
    return sweep_orphans(db, {kind: {str(record_id)}})


def sweep_orphans(db: Rekordbox6Database, relatives: dict[str, set[str]]) -> int:
    """Delete every given relative nothing references, repeating to a fixpoint.

    Rekordbox sweeps once, which leaks: collecting an orphaned album never
    re-examines the artist that album's AlbumArtistID pointed at, leaving that
    artist at zero references forever. Repeating the sweep until nothing new
    becomes unreferenced closes that gap.

    Kinds that are not sweepable are ignored, so passing a key id is safe
    rather than a caller error.
    """
    session = require_session(db)
    pending = {
        kind: {i for i in ids if i not in (None, "")}
        for kind, ids in relatives.items()
        if kind in RELATIONS and RELATIONS[kind].sweepable
    }
    collected = 0

    while pending:
        cascaded: dict[str, set[str]] = {}
        for kind, ids in pending.items():
            relation = RELATIONS[kind]
            for record_id in ids:
                if is_referenced(db, kind, record_id):
                    continue
                row = session.query(relation.table).filter_by(ID=record_id).first()
                if row is None:
                    continue
                # An album's own AlbumArtistID may be the last reference
                # holding that artist alive, so deleting the album can orphan
                # it. That cascade is what the loop exists to catch.
                for column_name, target_kind in relation.cascade_columns.items():
                    target_id = getattr(row, column_name, None)
                    if target_id:
                        cascaded.setdefault(target_kind, set()).add(str(target_id))
                session.delete(row)
                collected += 1
                _logger.debug(f"collected orphaned {kind} id={record_id}")
        # Load-bearing: the next pass queries for references, and an
        # uncommitted delete must be visible to that query. This function
        # runs inside a caller's transaction, so flush rather than commit.
        session.flush()
        pending = cascaded

    return collected


def relatives_of(contents) -> dict[str, set[str]]:
    """Collect the sweepable records the given tracks point at, by kind.

    Read before the rows are deleted, because the foreign keys go with them.
    Each id is a candidate for deletion rather than a record to delete: the
    sweep keeps whichever ones something else still references.
    """
    sweepable = {kind: r for kind, r in RELATIONS.items() if r.sweepable}
    relatives: dict[str, set[str]] = {kind: set() for kind in sweepable}
    for content in contents:
        for kind, relation in sweepable.items():
            for column_name in relation.content_columns:
                value = getattr(content, column_name, None)
                if value not in (None, ""):
                    relatives[kind].add(str(value))
    return relatives
