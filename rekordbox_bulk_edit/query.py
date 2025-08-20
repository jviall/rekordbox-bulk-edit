from typing import List, Tuple, Union

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import (
    DjmdAlbum,
    DjmdArtist,
    DjmdContent,
    DjmdPlaylist,
    DjmdSongPlaylist,
)
from sqlalchemy import Result, and_, func, or_, select
from sqlalchemy.orm import aliased

from rekordbox_bulk_edit.logger import Logger

logger = Logger()


class CollectionQuery:
    def __init__(self, match_all=False):
        self._stmt = select(DjmdContent)
        self._conditions = []
        self._limit_count = None
        self._match_all = match_all

    def _copy(self) -> "CollectionQuery":
        """Create a copy of this query in its current state."""
        new_inst = CollectionQuery.__new__(CollectionQuery)
        new_inst._stmt = self._stmt._clone()
        new_inst._conditions = self._conditions.copy()
        new_inst._limit_count = self._limit_count
        new_inst._match_all = self.match_any
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

    def by_artist(
        self, artist_name: str, exact_match: bool = False
    ) -> "CollectionQuery":
        """Filter by artist name."""
        if artist_name is None:
            logger.warning("Artist cannot be None")
            return self

        new_inst = self._copy()

        ArtistAlias = aliased(DjmdArtist)

        # Join with DjmdArtist table
        new_inst._stmt = new_inst._stmt.join(
            ArtistAlias, DjmdContent.ArtistID == ArtistAlias.ID
        )

        if exact_match:
            condition = ArtistAlias.Name == artist_name
        else:
            condition = ArtistAlias.Name.ilike(f"%{artist_name}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_track(self, track_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by track name."""
        if track_name is None:
            logger.warning(
                "track_name value of None has no effect. Did you mean to pass an empty string?"
            )
            return self

        new_inst = self._copy()

        if exact:
            condition = DjmdContent.Title == track_name
        else:
            condition = DjmdContent.Title.ilike(f"%{track_name}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_album(self, album_name: str, exact: bool = False) -> "CollectionQuery":
        """Filter by album name."""
        if album_name is None:
            logger.warning(
                "album_name value of None has no effect. Did you mean to pass an empty string?"
            )
            return self

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

    def by_playlist(
        self, playlist_name: str, exact_match: bool = False
    ) -> "CollectionQuery":
        """Filter by playlist name."""
        if playlist_name is None:
            logger.warning(
                "playlist_name value of None has no effect. Did you mean to pass an empty string?"
            )
            return self

        new_inst = self._copy()

        PlaylistAlias = aliased(DjmdPlaylist)
        SongPlaylistAlias = aliased(DjmdSongPlaylist)

        # Join through the many-to-many relationship
        new_inst._stmt = new_inst._stmt.join(
            SongPlaylistAlias, DjmdContent.ID == SongPlaylistAlias.ContentID
        ).join(PlaylistAlias, SongPlaylistAlias.PlaylistID == PlaylistAlias.ID)

        if exact_match:
            condition = PlaylistAlias.Name == playlist_name
        else:
            condition = PlaylistAlias.Name.ilike(f"%{playlist_name}%")

        new_inst._conditions.append(condition)
        return new_inst

    def by_format(self, format_name: str) -> "CollectionQuery":
        """Filter by file format."""
        from rekordbox_bulk_edit.utils import get_file_type_for_format

        if not format_name:
            logger.warning("An empty format filter has no effect")
            return self

        new_inst = self._copy()

        try:
            file_type_code = get_file_type_for_format(format_name)
            condition = DjmdContent.FileType == file_type_code
            new_inst._conditions.append(condition)
        except ValueError:
            logger.warning(f"Invalid format: {format_name}")
        return new_inst

    def limit(self, count: int) -> "CollectionQuery":
        """Limits query results to the first {count} items."""
        new_inst = self._copy()
        new_inst._limit_count = count
        return new_inst

    def count(self, db: Rekordbox6Database) -> int:
        """Get a count of the query's results on the given database instance."""
        if not db.session:
            raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")
        stmt = self._get_full_statement()
        # Create count query using the existing statement as subquery
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
        return db.session.execute(stmt)

    def _get_full_statement(self):
        """Return the final statement with all expressions applied."""
        stmt = self._stmt

        if self._conditions:
            if self._match_all:
                combined_condition = and_(*self._conditions)
            else:
                combined_condition = or_(*self._conditions)
            stmt = stmt.where(combined_condition)

        if self._limit_count is not None:
            stmt = stmt.limit(self._limit_count)

        return stmt


def get_filtered_content(
    db: Rekordbox6Database,
    track_ids: List[str] | None = None,
    formats: List[str] | None = None,
    playlists: List[str] | None = None,
    artists: List[str] | None = None,
    albums: List[str] | None = None,
    exact_albums: List[str] | None = None,
    tracks: List[str] | None = None,
    exact_tracks: List[str] | None = None,
    track_id_args: List[str] | None = None,
    match_all: bool = False,
) -> Result[Tuple[DjmdContent]]:
    """Queries the Rekordbox database according to the provided filters and conditions.
    When `track_id_args` is provided, it's the only filter applied and all others are skipped."""
    db = Rekordbox6Database()
    if not db.session:
        raise RuntimeError("Failed to connect to Rekordbox Database: No Session.")

    query = CollectionQuery()

    if track_id_args and len(track_id_args) > 0:
        query = query.by_track_ids(track_ids=track_id_args)
        return query.execute(db)

    for track_id in track_ids if track_ids is not None else []:
        query = query.by_track_ids(track_id)

    for format in formats if formats is not None else []:
        query = query.by_format(format)

    for playlist in playlists if playlists is not None else []:
        query = query.by_playlist(playlist)

    for artist in artists if artists is not None else []:
        query = query.by_artist(artist)

    for album in albums if albums is not None else []:
        query = query.by_album(album)
    for exact_album in exact_albums if exact_albums is not None else []:
        query = query.by_album(exact_album, exact=True)

    for track in tracks if tracks is not None else []:
        query = query.by_track(track)

    if match_all:
        query.match_all()

    return query.execute(db)
