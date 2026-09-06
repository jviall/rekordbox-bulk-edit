"""Remove API for rekordbox-edit."""

import logging
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypedDict

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6 import tables as tb
from sqlalchemy import or_

from rekordbox_edit.api._utils import reserve_usns, track_from_content, writing
from rekordbox_edit.api._field_handlers import _ARTIST_ROLE_COLUMNS
from rekordbox_edit.models import (
    RemoveOp,
    RemoveRequest,
    RemoveResponse,
    RemoveResult,
    SkippedTrack,
)
from rekordbox_edit.query import (
    find_content_by_ids,
    get_filtered_content,
    require_session,
)

_logger = logging.getLogger(__name__)

#: The DjmdContent columns naming a track's relatives, by kind. A removal
#: vacates every one of them. Key and colour are absent by design; see
#: _SWEEPABLE.
_RELATIVE_COLUMNS = {
    "artist": ("ArtistID", "RemixerID", "OrgArtistID", "ComposerID", "Lyricist"),
    "album": ("AlbumID",),
    "genre": ("GenreID",),
    "label": ("LabelID",),
}


def _content_child_tables() -> list[type[tb.Base]]:
    """Every mapped table that references a track by ContentID."""
    tables: list[type[tb.Base]] = []
    for mapper in tb.Base.registry.mappers:
        cls = mapper.class_
        if cls is tb.DjmdContent:
            continue
        if "ContentID" in cls.__table__.columns:
            tables.append(cls)
    return tables


#: The four kinds rekordbox collects at zero references, each mapped to the
#: table holding the record and the DjmdContent column pointing at it.
#:
#: Key and colour are deliberately absent. DjmdKey is a closed enumeration of
#: musical keys shared by hundreds of tracks and ColorID names a fixed
#: palette, so collecting either would be wrong even at zero references. A
#: caller that passes them is ignored rather than obeyed.
_SWEEPABLE: dict[str, tuple[type[tb.Base], Any]] = {
    "artist": (tb.DjmdArtist, tb.DjmdContent.ArtistID),
    "album": (tb.DjmdAlbum, tb.DjmdContent.AlbumID),
    "genre": (tb.DjmdGenre, tb.DjmdContent.GenreID),
    "label": (tb.DjmdLabel, tb.DjmdContent.LabelID),
}


def _is_referenced(db: Rekordbox6Database, kind: str, record_id: str) -> bool:
    """Whether anything still points at this record."""
    session = require_session(db)
    if kind == "artist":
        in_content = (
            session.query(tb.DjmdContent)
            .filter(or_(*(col == record_id for col in _ARTIST_ROLE_COLUMNS)))
            .first()
        )
        in_album = (
            session.query(tb.DjmdAlbum)
            .filter(tb.DjmdAlbum.AlbumArtistID == record_id)
            .first()
        )
        return in_content is not None or in_album is not None
    _, column = _SWEEPABLE[kind]
    return session.query(tb.DjmdContent).filter(column == record_id).first() is not None


def _sweep_orphans(db: Rekordbox6Database, relatives: dict[str, set[str]]) -> int:
    """Delete every given relative nothing references, repeating to a fixpoint.

    Rekordbox sweeps once, which leaks: collecting an orphaned album never
    re-examines the artist that album's AlbumArtistID pointed at, leaving that
    artist at zero references forever. Repeating the sweep until nothing new
    becomes unreferenced closes that gap.

    Kinds outside `_SWEEPABLE` are ignored, so passing a key or a colour id is
    safe rather than a caller error.
    """
    session = require_session(db)
    pending = {
        kind: {i for i in ids if i not in (None, "")}
        for kind, ids in relatives.items()
        if kind in _SWEEPABLE
    }
    collected = 0

    while pending:
        cascaded: dict[str, set[str]] = {}
        for kind, ids in pending.items():
            table, _ = _SWEEPABLE[kind]
            for record_id in ids:
                if _is_referenced(db, kind, record_id):
                    continue
                row = session.query(table).filter_by(ID=record_id).first()
                if row is None:
                    continue
                # An album's own AlbumArtistID may be the last reference
                # holding that artist alive, so deleting the album can orphan
                # it. That cascade is what the loop exists to catch.
                album_artist_id = getattr(row, "AlbumArtistID", None)
                if kind == "album" and album_artist_id:
                    cascaded.setdefault("artist", set()).add(str(album_artist_id))
                session.delete(row)
                collected += 1
                _logger.debug(f"collected orphaned {kind} id={record_id}")
        # Load-bearing: the next pass queries for references, and an
        # uncommitted delete must be visible to that query. This function
        # runs inside a caller's transaction, so flush rather than commit.
        session.flush()
        pending = cascaded

    return collected


#: share/PIONEER/USBANLZ/<xxx>/<uuid> — the analysis directory sits exactly
#: this many path parts below the share directory in every real Rekordbox
#: layout measured. A stored AnalysisDataPath that is shallower than this
#: (corrupt, truncated, or written by a foreign tool) would otherwise resolve
#: to an ancestor tier shared by every other track, so the depth is checked
#: before any delete: see `remove_analysis_files`.
_ANALYSIS_DIR_DEPTH = 4

#: share/PIONEER/Artwork/<xxx>/<uuid> — the artwork directory sits exactly
#: this many path parts below the share directory in every real Rekordbox
#: layout measured. Mirrors `_ANALYSIS_DIR_DEPTH`; see `remove_artwork_files`.
_ARTWORK_DIR_DEPTH = 4


def _resolve_path_of_root(root: Path, path: Path) -> Path | None:
    """Returns the path resolved, or None if it doesn't descend from the given root.

    Bounds the blast radius of every delete in this module to rekordbox's own
    managed storage. Callers still need their own check that the resolved
    path is the *specific* directory they mean to touch, not merely somewhere
    under the root: see `_ANALYSIS_DIR_DEPTH`.
    """
    resolved = path.resolve()
    root = root.resolve()
    if resolved == root or root not in resolved.parents:
        _logger.debug(f"Path ({resolved}) does not descend from root {root}")
        return None
    return resolved


def _rmdir_if_empty_under(root: Path, directory: Path) -> None:
    """Remove a directory only when it is empty and still under the root.

    Every call site passes a computed *parent* of an already-checked path,
    which is not itself guaranteed to still be inside the share tree (a
    shallow stored path can walk it out to the share root or above), so this
    re-checks containment rather than trusting the caller's arithmetic.

    rmdir rather than a recursive delete, so anything unexpected inside stops
    the cleanup instead of being swept away.
    """
    if _resolve_path_of_root(root, directory) is None:
        _logger.warning("Refusing to delete outside the share tree")
        return
    try:
        directory.rmdir()
        _logger.debug(f"removed empty directory {directory}")
    except OSError:
        _logger.debug(f"left non-empty directory {directory}")


def remove_analysis_files(
    db: Rekordbox6Database, analysis_data_path: str | None
) -> None:
    """Delete a track's analysis directory and its prefix directory.
    e.g. share/PIONEER/USBANLZ/<xxx>/<uuid>

    Takes an explicit path value rather than a row, because there may not
    be a row to pass.
    """
    # An empty AnalysisDataPath is refused before any path is resolved. This
    # duplicates the containment check below by design (both must independently
    # hold before anything is deleted; do not remove either as apparently dead
    # code): get_anlz_dir strips the leading separator and joins the remainder
    # onto the share directory, so an empty value resolves to the share root
    # itself, and a recursive delete there would destroy every track's analysis
    # in the library.
    if not analysis_data_path:
        _logger.debug("no analysis to remove")
        return

    share_dir = db.share_directory
    anlz_dir = _resolve_path_of_root(
        share_dir,
        share_dir / Path(analysis_data_path.strip("\\/")).parent,
    )
    if anlz_dir is None:
        _logger.warning("Refusing to delete outside the share tree")
        return

    # A non-empty but malformed AnalysisDataPath is refused too. The real
    # layout is always share/PIONEER/USBANLZ/<xxx>/<uuid>, so a value shallower
    # than that resolves to an ancestor directory shared by every other track
    # (e.g. all of USBANLZ, or all of PIONEER) rather than to this track's own
    # directory. Rekordbox itself never writes a value that shape, but a
    # corrupt or foreign-tool-written column could, and unlike an empty value
    # this is not caught by the share-root check. Skipping the cleanup leaves
    # orphan files behind; deleting an ancestor tier destroys the library, so
    # an unexpected shape is refused rather than acted on.
    depth = len(anlz_dir.relative_to(share_dir.resolve()).parts)
    if depth != _ANALYSIS_DIR_DEPTH:
        _logger.warning(
            "analysis path did not have the expected share/PIONEER/USBANLZ/"
            f"<xxx>/<uuid> shape, skipping cleanup: {anlz_dir}"
        )
        return

    if not anlz_dir.is_dir():
        return

    shutil.rmtree(anlz_dir)
    _logger.debug(f"removed analysis directory {anlz_dir}")
    _rmdir_if_empty_under(share_dir, anlz_dir.parent)


def remove_artwork_files(db: Rekordbox6Database, image_path: str | None) -> None:
    """Delete a track's artwork files, then its directory and prefix if empty.
    e.g. share/PIONEER/Artwork/<xxx>/<uuid>

    Rekordbox deletes the files and leaves both directories in place and empty.
    Removing them is a deliberate divergence: the directory name derives from
    DjmdContent.UUID, minted fresh per inserted row, so nothing can reach an
    abandoned one again.

    A non-empty but malformed ImagePath is refused too. The real layout is
    always share/PIONEER/Artwork/<xxx>/<uuid>, so a value shallower than that
    resolves to an ancestor directory shared by every other track's artwork
    (or, one level shallower still, by a Rekordbox-managed directory that
    holds no artwork at all, such as PIONEER itself). Rekordbox itself never
    writes a value that shape, but a corrupt or foreign-tool-written column
    could, and unlike an empty value this is not caught by the share-root
    check. Skipping the cleanup leaves orphan files behind; deleting an
    ancestor tier destroys other tracks' data, so an unexpected shape is
    refused rather than acted on.
    """

    # An empty ImagePath is refused before any path is resolved. This duplicates
    # the containment check below by design (do not remove either as apparently
    # dead code): an empty value joins onto the share directory unchanged, so
    # `artwork_file` becomes the share directory itself and `art_dir`, its
    # parent, becomes the directory one level ABOVE the share root — the
    # library's own db_directory, which holds the main database files. That is
    # a different, and worse, location than the share root that an empty
    # AnalysisDataPath resolves to; it is not caught by name coincidence the way
    # a share directory literally named "share" happens to survive in tests.
    if not image_path:
        _logger.debug("no artwork to remove")
        return

    share_dir = db.share_directory
    artwork_file = _resolve_path_of_root(share_dir, share_dir / image_path.strip("\\/"))
    if artwork_file is None:
        return

    art_dir = artwork_file.parent
    depth = len(art_dir.relative_to(share_dir.resolve()).parts)
    if depth != _ARTWORK_DIR_DEPTH:
        _logger.warning(
            "artwork path did not have the expected share/PIONEER/Artwork/"
            f"<xxx>/<uuid> shape, skipping cleanup: {art_dir}"
        )
        return

    if not art_dir.is_dir():
        return

    stem, suffix = artwork_file.stem, artwork_file.suffix
    for name in (f"{stem}{suffix}", f"{stem}_m{suffix}", f"{stem}_s{suffix}"):
        target = art_dir / name
        if target.is_file():
            target.unlink()
            _logger.debug(f"removed artwork file {target}")

    _rmdir_if_empty_under(share_dir, art_dir)
    _rmdir_if_empty_under(share_dir, art_dir.parent)


def _relatives_of(contents: Sequence[tb.DjmdContent]) -> dict[str, set[str]]:
    """Collect the shared records the given tracks point at, by kind.

    Read before the rows are deleted, because the foreign keys go with them.
    Each id is a candidate for deletion rather than a record to delete: the
    sweep keeps whichever ones something else still references.
    """
    relatives: dict[str, set[str]] = {kind: set() for kind in _RELATIVE_COLUMNS}
    for content in contents:
        for kind, columns in _RELATIVE_COLUMNS.items():
            for column in columns:
                value = getattr(content, column, None)
                if value not in (None, ""):
                    relatives[kind].add(str(value))
    return relatives


class _OnDiskArtifacts(TypedDict):
    """The paths a removed track leaves behind, read while its row still exists."""

    id: str
    analysis_data_path: str | None
    image_path: str | None
    folder_path: str | None
    other_referents: bool


def _img_has_other_referent(db: Rekordbox6Database, content: tb.DjmdContent) -> bool:
    """Whether another row names the same artwork file."""
    if not content.ImagePath:
        return False
    return (
        require_session(db)
        .query(tb.DjmdContent)
        .filter(
            tb.DjmdContent.ImagePath == content.ImagePath,
            tb.DjmdContent.ID != content.ID,
        )
        .first()
        is not None
    )


def remove(
    db: Rekordbox6Database,
    args: RemoveRequest,
    *,
    dry_run: bool = False,
    ops: list[RemoveOp] | None = None,
) -> RemoveResponse:
    """Delete tracks matching the filter args from the library.

    Removes the DjmdContent row, every child row keyed by ContentID, the
    analysis and artwork files, and any shared artist, album, genre, or label
    the removal leaves unreferenced. The source audio file is kept unless
    `delete_source` is set.

    With `dry_run=True`, returns the planned removals without any writes.

    Pass `ops` to apply an already-approved plan; filters will be ignored.
    """
    _logger.debug(f"remove start dry_run={dry_run} delete_source={args.delete_source}")

    planned: list[RemoveOp] = []
    skipped: list[SkippedTrack] = []
    contents = []

    if ops is None:
        contents = list(get_filtered_content(db, args).scalars().all())
        _logger.debug(f"remove fetched {len(contents)} candidate(s) from filter")
        planned = [
            RemoveOp(id=str(c.ID), track=track_from_content(c)) for c in contents
        ]
    else:
        rows = find_content_by_ids(db, [op.id for op in ops])
        seen_ids: set[str] = set()
        for op in ops:
            if op.id in seen_ids:
                _logger.debug(f"skip remove id={op.id} reason=duplicate_op")
                continue
            seen_ids.add(op.id)
            content = rows.get(op.id)
            if content is None:
                _logger.debug(
                    f"skip remove id={op.id} reason=db_or_fs_changed row_gone"
                )
                skipped.append(SkippedTrack(reason="db_or_fs_changed", track=op.track))
                continue
            contents.append(content)
            planned.append(RemoveOp(id=op.id, track=track_from_content(content)))
        _logger.debug(f"remove re-checked ops={len(planned)} skipped={len(skipped)}")

    if dry_run or not planned:
        return RemoveResponse(
            result=RemoveResult(
                dry_run=dry_run,
                removed=planned if dry_run else [],
                skipped=skipped,
                deleted_relatives=0,
            )
        )

    # Load-bearing ordering: everything the post-commit file work needs
    # (AnalysisDataPath, ImagePath, FolderPath, the other-referent check)
    # must be read here, before the rows are deleted below. This is not
    # defended by a test that can actually fail: a deleted-then-committed
    # SQLAlchemy instance is expunged rather than expired regardless of
    # `expire_on_commit`, so its already-loaded attributes stay readable
    # in Python even if this read were moved to after the delete/commit,
    # and every test in this module would still pass. That safety holds
    # only because every column read above is a plain, non-deferred
    # DjmdContent attribute loaded at query time; moving this block after
    # the delete is safe only until a future deferred column or
    # relationship attribute is added here, at which point it would raise
    # DetachedInstanceError rather than return wrong data.
    on_disk_artifacts: list[_OnDiskArtifacts] = [
        {
            "id": str(c.ID),
            "analysis_data_path": c.AnalysisDataPath,
            "image_path": c.ImagePath,
            "folder_path": c.FolderPath,
            "other_referents": _img_has_other_referent(db, c),
        }
        for c in contents
    ]
    relatives = _relatives_of(contents)

    with writing(db, "remove"):
        session = require_session(db)
        child_tables = _content_child_tables()
        child_rows_deleted = 0
        for content in contents:
            for table in child_tables:
                child_rows_deleted += (
                    session.query(table)
                    .filter(table.__table__.c.ContentID == content.ID)
                    .delete(synchronize_session=False)
                )
            session.delete(content)
        session.flush()

        deleted_relatives = _sweep_orphans(db, relatives)
        # Every deleted row carries an rb_local_usn: the DjmdContent rows, the
        # child rows just deleted above, and the swept orphans. Deleted rows
        # cannot be stamped, but the counter must still move past all of them,
        reserve_usns(db, len(planned) + child_rows_deleted + deleted_relatives)
        session.commit()
        _logger.debug(
            f"remove committed {len(planned)} row(s), "
            f"{deleted_relatives} unreferenced relative(s) deleted"
        )

        deleted_sources = _remove_on_disk_artifacts(
            on_disk_artifacts, db, delete_source=args.delete_source
        )

    for op in planned:
        op.source_deleted = op.id in deleted_sources

    return RemoveResponse(
        result=RemoveResult(
            dry_run=dry_run,
            removed=planned,
            skipped=skipped,
            deleted_relatives=deleted_relatives,
        )
    )


def _remove_on_disk_artifacts(
    artifacts: list[_OnDiskArtifacts],
    db: Rekordbox6Database,
    *,
    delete_source: bool,
) -> set[str]:
    """Delete the on-disk artifacts (analysis, artwork, source audio) after the
    transaction has committed.

    Runs post-commit, matching the convention edit uses for its ANLZ writes,
    and never raises: the database write already succeeded, so a file that
    cannot be deleted is a warning rather than an error implying otherwise.
    """
    deleted_sources: set[str] = set()
    for artifact in artifacts:
        # Each cleanup gets its own try: treating all errors as warnings
        try:
            remove_analysis_files(db, artifact["analysis_data_path"])
        except Exception as e:
            # A malformed stored path (e.g. an embedded NUL in AnalysisDataPath)
            # raises ValueError from Path.resolve(),
            _logger.warning(
                f"could not clean up analysis files for track {artifact['id']}: {e}"
            )
        try:
            if artifact["other_referents"]:
                _logger.debug(
                    f"artwork {artifact['image_path']} still referenced; keeping it"
                )
            else:
                remove_artwork_files(db, artifact["image_path"])

        except Exception as e:
            _logger.warning(
                f"could not clean up artwork files for track {artifact['id']}: {e}"
            )
        folder_path = artifact["folder_path"]
        if not delete_source or not folder_path:
            continue
        try:
            os.remove(folder_path)
            deleted_sources.add(artifact["id"])
            _logger.debug(f"deleted source file {folder_path}")
        except Exception as e:
            _logger.warning(f"could not delete source file {folder_path}: {e}")
    return deleted_sources
