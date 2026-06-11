import logging
from pathlib import Path
from typing import List, Tuple, Union

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import (
    DjmdAlbum,
    DjmdArtist,
    DjmdContent,
    DjmdPlaylist,
    DjmdSongPlaylist,
)
from sqlalchemy import ColumnElement, Result, and_, func, or_, select
from sqlalchemy.orm import aliased

from rekordbox_edit.models import FilterArgs

logger = logging.getLogger(__name__)


class CollectionQuery:
    def __init__(self, match_all=False):
        self._stmt = select(DjmdContent)
        self._conditions: list[ColumnElement[bool]] = []
        self._limit_count = None
        self._last_count = None
        self._match_all = match_all

    def _copy(self) -> "CollectionQuery":
        """Create a copy of this query in its current state."""
        new_inst = CollectionQuery.__new__(CollectionQuery)
        new_inst._stmt = self._stmt._clone()
        new_inst._conditions = self._conditions.copy()
        new_inst._limit_count = self._limit_count
        new_inst._last_count = self._last_count
        new_inst._match_all = self._match_all
        return new_inst

    def match_any(self) -> "CollectionQuery":
        """Set the filter combination logic to use the OR operator (the default)."""
        new_inst = self._copy()
        new_inst._match_all = False
        return new_inst

    def match_all(self) -> "CollectionQuery":
        """Set the filter combination logic to use the AND operator."""
        new_inst = self._copy()
        new_inst._match_all = True
        return new_inst

    def by_track_ids(self, track_ids: Union[str, List[str]]) -> "CollectionQuery":
        """Filter by specific track ID(s)."""
        new_inst = self._copy()
        if isinstance(track_ids, str):
            track_ids = [track_ids]
        new_inst._conditions.append(DjmdContent.ID.in_(track_ids))
        return new_inst

    def by_artist(self, artist_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by artist name."""

        new_inst = self._copy()
        ArtistAlias = aliased(DjmdArtist)
        new_inst._stmt = new_inst._stmt.outerjoin(
            ArtistAlias, DjmdContent.ArtistID == ArtistAlias.ID
        )

        if not artist_name:
            condition = ArtistAlias.Name.is_(None)
        elif exact:
            condition = ArtistAlias.Name == artist_name
        else:
            condition = ArtistAlias.Name.ilike(f"%{artist_name}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_title(self, title: str, exact: bool = False) -> "CollectionQuery":
        """Filter by track name."""

        new_inst = self._copy()

        if not title:
            condition = DjmdContent.Title.is_(None)
        elif exact:
            condition = DjmdContent.Title == title
        else:
            condition = DjmdContent.Title.ilike(f"%{title}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_album(self, album_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by album name."""

        new_inst = self._copy()
        AlbumAlias = aliased(DjmdAlbum)
        new_inst._stmt = new_inst._stmt.outerjoin(
            AlbumAlias, DjmdContent.AlbumID == AlbumAlias.ID
        )

        if not album_name:
            condition = DjmdContent.AlbumID.is_(None)
        elif exact:
            condition = AlbumAlias.Name == album_name
        else:
            condition = AlbumAlias.Name.ilike(f"%{album_name}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_playlist(self, playlist_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by playlist name."""

        new_inst = self._copy()
        PlaylistAlias = aliased(DjmdPlaylist)
        SongPlaylistAlias = aliased(DjmdSongPlaylist)

        new_inst._stmt = new_inst._stmt.outerjoin(
            SongPlaylistAlias, DjmdContent.ID == SongPlaylistAlias.ContentID
        ).outerjoin(PlaylistAlias, SongPlaylistAlias.PlaylistID == PlaylistAlias.ID)

        if not playlist_name:
            condition = SongPlaylistAlias.ContentID.is_(None)
        elif exact:
            condition = PlaylistAlias.Name == playlist_name
        else:
            condition = PlaylistAlias.Name.ilike(f"%{playlist_name}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_format(self, format_name: str) -> "CollectionQuery":
        """Filter by file format."""
        from rekordbox_edit.utils import get_file_type_for_format

        if not format_name:
            logger.warning("Empty format filter has no effect")
            return self

        new_inst = self._copy()

        try:
            file_type_code = get_file_type_for_format(format_name)
            condition = DjmdContent.FileType == file_type_code
            new_inst._conditions.append(condition)
        except ValueError:
            logger.warning(f"Invalid format: {format_name}")
        return new_inst

    def by_path(self, path_str: str, exact: bool = False) -> "CollectionQuery":
        """Filter by file path, matching against FolderPath and/or FileNameL.

        Paths get normalized to posix format.
        --path args arg matched as substrings.
        --exact-path argsl are resolved to absolute paths and must match exact.

        Args with a trailing '/' only query against FolderPath.
        Args with no parent folders in the path only query against FileNameL.
        """
        new_inst = self._copy()

        is_dir_only = path_str.endswith("/") or path_str.endswith("\\")

        if exact:
            resolved = Path(path_str).resolve()
            if is_dir_only:
                folder_part = resolved.as_posix() + "/"
                name_part = ""
            elif "/" not in path_str and "\\" not in path_str:
                folder_part = ""
                name_part = resolved.name
            else:
                folder_part = resolved.parent.as_posix() + "/"
                name_part = resolved.name
        else:
            normalized = Path(path_str)
            if is_dir_only:
                folder_part = normalized.as_posix()
                name_part = ""
            else:
                parent_str = normalized.parent.as_posix()
                folder_part = "" if parent_str == "." else parent_str
                name_part = normalized.name

        conditions: list[ColumnElement[bool]] = []
        if folder_part:
            if exact:
                conditions.append(DjmdContent.FolderPath == folder_part)
            else:
                conditions.append(DjmdContent.FolderPath.ilike(f"%{folder_part}%"))
        if name_part:
            if exact:
                conditions.append(DjmdContent.FileNameL == name_part)
            else:
                conditions.append(DjmdContent.FileNameL.ilike(f"%{name_part}%"))

        if conditions:
            combined = and_(*conditions) if len(conditions) > 1 else conditions[0]
            new_inst._conditions.append(combined)

        return new_inst

    def limit(self, count: int) -> "CollectionQuery":
        """Limit query results to the first {count} items."""
        new_inst = self._copy()
        new_inst._limit_count = count
        return new_inst

    def last(self, count: int) -> "CollectionQuery":
        """Limit query results to the last {count} items, kept in canonical order."""
        new_inst = self._copy()
        new_inst._last_count = count
        return new_inst

    def count(self, db: Rekordbox6Database) -> int:
        """Get a count of the query's results on the given database instance."""
        if not db.session:
            raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")
        stmt = self._get_full_statement()
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = db.session.execute(count_stmt)
        return result.scalar_one()

    def execute(
        self,
        db: Rekordbox6Database,
    ) -> Result[Tuple[DjmdContent]]:
        """Execute the query on the given database instance and return results."""
        if not db.session:
            raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")
        stmt = self._get_full_statement()
        logger.debug(f"Executing Query:\n{str(stmt)}")
        return db.session.execute(stmt)

    def _get_full_statement(self):
        """Return the final statement with all expressions applied."""
        stmt = self._stmt

        if self._conditions:
            logic = "AND" if self._match_all else "OR"
            logger.debug(
                f"Building query with {len(self._conditions)} condition(s) using {logic} logic"
            )
            if self._match_all:
                combined_condition = and_(*self._conditions)
            else:
                combined_condition = or_(*self._conditions)
            stmt = stmt.where(combined_condition)

        if self._last_count is not None:
            logger.debug(f"Query last: {self._last_count}")
            tail = (
                stmt.order_by(DjmdContent.FolderPath.desc(), DjmdContent.ID.desc())
                .limit(self._last_count)
                .subquery()
            )
            tail_content = aliased(DjmdContent, tail)
            return select(tail_content).order_by(
                tail_content.FolderPath.asc(), tail_content.ID.asc()
            )

        stmt = stmt.order_by(DjmdContent.FolderPath.asc(), DjmdContent.ID.asc())

        if self._limit_count is not None:
            logger.debug(f"Query limit: {self._limit_count}")
            stmt = stmt.limit(self._limit_count)

        return stmt


def get_filtered_content(
    db: Rekordbox6Database,
    filters: FilterArgs,
) -> Result[Tuple[DjmdContent]]:
    """Query the Rekordbox database with the provided filters."""
    db = db if db is not None else Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    query = CollectionQuery()

    if filters.track_ids:
        logger.debug(f"Filtering by {len(filters.track_ids)} track ID argument(s)")
        query = query.by_track_ids(track_ids=filters.track_ids)

    for tid in filters.track_id:
        query = query.by_track_ids(tid)

    for fmt in filters.format:
        query = query.by_format(fmt)

    for playlist in filters.playlist:
        query = query.by_playlist(playlist)

    for exact_playlist in filters.exact_playlist:
        query = query.by_playlist(exact_playlist, exact=True)

    for artist in filters.artist:
        query = query.by_artist(artist)

    for exact_artist in filters.exact_artist:
        query = query.by_artist(exact_artist, exact=True)

    for album in filters.album:
        query = query.by_album(album)

    for exact_album in filters.exact_album:
        query = query.by_album(exact_album, exact=True)

    for title in filters.title:
        query = query.by_title(title)

    for title in filters.exact_title:
        query = query.by_title(title, exact=True)

    for path in filters.path:
        query = query.by_path(path)

    for exact_path in filters.exact_path:
        query = query.by_path(exact_path, exact=True)

    if filters.match_all:
        query = query.match_all()

    if filters.first is not None:
        query = query.limit(filters.first)

    if filters.last is not None:
        query = query.last(filters.last)

    return query.execute(db)
