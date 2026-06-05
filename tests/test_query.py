#!/usr/bin/env python3
"""Tests for the CollectionQuery class."""

import os
import platform
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import ColumnElement

from rekordbox_edit.models import FilterArgs
from rekordbox_edit.query import CollectionQuery, get_filtered_content


def _compile(condition: ColumnElement[bool]) -> str:
    return str(condition.compile(compile_kwargs={"literal_binds": True}))


class TestCollectionQuery:
    """Test the CollectionQuery class."""

    def test_init(self):
        """Test that new instances select the DjmdContent table and initialize fields."""
        query = CollectionQuery()

        # Check that the statement selects from DjmdContent
        assert str(query._stmt).lower().find("djmdcontent") != -1

        # Check initial state
        assert query._conditions == []
        assert query._limit_count is None
        assert query._match_all is False

        # Test with match_all=True
        query_all = CollectionQuery(match_all=True)
        assert query_all._match_all is True

    def test_match_any(self):
        """Test that the match_any method correctly sets the _match_all field to False."""
        query = CollectionQuery(match_all=True)

        new_query = query.match_any()

        # Should return a new instance
        assert new_query is not query
        assert new_query._match_all is False
        # Original should be unchanged
        assert query._match_all is True

    def test_match_all(self):
        """Test that the match_all method correctly sets the _match_all field to True."""
        query = CollectionQuery(match_all=False)

        new_query = query.match_all()

        # Should return a new instance
        assert new_query is not query
        assert new_query._match_all is True
        # Original should be unchanged
        assert query._match_all is False

    def test_by_artist(self):
        """Test that the by_artist method outer-joins with the DjmdArtist table and
        adds an ilike condition on the DjmdArtist.Name field."""
        query = CollectionQuery()
        artist_name = "Test Artist"

        new_query = query.by_artist(artist_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Check that the statement includes a join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdartist" in stmt_str

        # Check that the condition is an ilike operation
        condition_str = str(new_query._conditions[0]).lower()
        print(condition_str)
        assert "like lower" in condition_str
        assert '."name"' in condition_str.lower()

    def test_by_exact_artist(self):
        """Test that the by_artist method outer-joins with the DjmdArtist table and
        adds an == condition on the DjmdArtist.Name field when exact is True."""
        query = CollectionQuery()
        artist_name = "Exact Artist"

        new_query = query.by_artist(artist_name, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Check that the statement includes a join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdartist" in stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str

    def test_by_title(self):
        """Test that the by_title method does not modify the statement and
        adds an ilike condition on the Title field."""
        query = CollectionQuery()
        title = "Test Title"

        original_stmt_str = str(query._stmt)
        new_query = query.by_title(title)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Statement should not have additional joins (only the original select)
        new_stmt_str = str(new_query._stmt)
        assert new_stmt_str == original_stmt_str

        # Check that the condition is an ilike operation on Title
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" in condition_str
        assert "title" in condition_str

    def test_by_exact_title(self):
        """Test that the by_title method does not modify the statement and
        adds an == condition on the Title field when exact is True."""
        query = CollectionQuery()
        title = "Exact Title"

        original_stmt_str = str(query._stmt)
        new_query = query.by_title(title, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Statement should not have additional joins
        new_stmt_str = str(new_query._stmt)
        assert new_stmt_str == original_stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str
        assert "title" in condition_str

    def test_by_album(self):
        """Test that the by_album method outer-joins with the DjmdAlbum table and
        adds an ilike condition on the DjmdAlbum.Name field."""
        query = CollectionQuery()
        album_name = "Test Album"

        new_query = query.by_album(album_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Check that the statement includes an outer join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdalbum" in stmt_str

        # Check that the condition is an ilike operation
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" in condition_str

    def test_by_exact_album(self):
        """Test that the by_album method outer-joins with the DjmdAlbum table and
        adds an == condition on the DjmdAlbum.Name field when exact is True."""
        query = CollectionQuery()
        album_name = "Exact Album"

        new_query = query.by_album(album_name, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Check that the statement includes an outer join
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdalbum" in stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str

    def test_by_playlist(self):
        """Test that the by_playlist method outer-joins with the DjmdPlaylist and DjmdSongPlaylist
        tables and adds an ilike condition on the DjmdPlaylist.Name field."""
        query = CollectionQuery()
        playlist_name = "Test Playlist"

        new_query = query.by_playlist(playlist_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Check that the statement includes outer joins with both tables
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdsongplaylist" in stmt_str
        assert "djmdplaylist" in stmt_str

        # Check that the condition is an ilike operation
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" in condition_str

    def test_by_exact_playlist(self):
        """Test that the by_playlist method outer-joins with the DjmdPlaylist table and
        adds an == condition on the DjmdPlaylist.Name field when exact is True."""
        query = CollectionQuery()
        playlist_name = "Exact Playlist"

        new_query = query.by_playlist(playlist_name, exact=True)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Check that the statement includes outer joins with both tables
        stmt_str = str(new_query._stmt).lower()
        assert "left outer join" in stmt_str or "outer join" in stmt_str
        assert "djmdsongplaylist" in stmt_str
        assert "djmdplaylist" in stmt_str

        # Check that the condition is an equality operation (not ilike)
        condition_str = str(new_query._conditions[0]).lower()
        assert "like lower" not in condition_str
        assert "=" in condition_str

    def test_by_format(self, mocker):
        """Test that the by_format method does not modify the statement and
        adds a condition on the DjmdContent.FileType field."""
        # Mock the get_file_type_for_format function
        mock_get_file_type = mocker.patch(
            "rekordbox_edit.utils.get_file_type_for_format"
        )
        mock_get_file_type.return_value = 5  # Example file type code

        query = CollectionQuery()
        format_name = "FLAC"

        original_stmt_str = str(query._stmt)
        new_query = query.by_format(format_name)

        # Should return a new instance
        assert new_query is not query

        # Check that a condition was added
        assert len(new_query._conditions) == 1

        # Statement should not have additional joins
        new_stmt_str = str(new_query._stmt)
        assert new_stmt_str == original_stmt_str

        # Check that the condition involves FileType
        condition_str = str(new_query._conditions[0]).lower()
        assert "filetype" in condition_str

        # Verify the helper function was called
        mock_get_file_type.assert_called_once_with(format_name)

    def test_copy(self):
        """ """
        query = CollectionQuery()
        query_copy = query._copy()

        assert query_copy._match_all == query._match_all
        assert query_copy._conditions == query._conditions
        assert query_copy._limit_count == query._limit_count
        assert str(query_copy._stmt) == str(query._stmt)
        assert str(query_copy._get_full_statement()) == str(query._get_full_statement())

    def test_copy_with_filters(self):
        """ """
        query = CollectionQuery()
        query.by_album("Discovery").by_format("flac").by_format("aiff").by_title("")
        query_copy = query._copy()

        assert query_copy._match_all == query._match_all
        assert query_copy._conditions == query._conditions
        assert query_copy._limit_count == query._limit_count
        assert str(query_copy._stmt) == str(query._stmt)
        assert str(query_copy._get_full_statement()) == str(query._get_full_statement())

    def test_by_track_ids_single_string(self):
        """A single string ID is accepted and results in an IN condition."""
        query = CollectionQuery()
        new_query = query.by_track_ids("123")

        assert new_query is not query
        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0]).lower()
        assert "in" in condition_str

    def test_by_track_ids_list(self):
        """A list of IDs results in a single IN condition."""
        query = CollectionQuery()
        new_query = query.by_track_ids(["123", "456", "789"])

        assert new_query is not query
        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0]).lower()
        assert "in" in condition_str

    def test_by_artist_empty_string(self):
        """Empty artist name adds an IS NULL condition."""
        query = CollectionQuery()
        new_query = query.by_artist("")

        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0]).lower()
        assert "null" in condition_str

    def test_by_title_empty_string(self):
        """Empty title adds an IS NULL condition."""
        query = CollectionQuery()
        new_query = query.by_title("")

        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0]).lower()
        assert "null" in condition_str

    def test_by_album_empty_string(self):
        """Empty album name adds an IS NULL condition."""
        query = CollectionQuery()
        new_query = query.by_album("")

        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0]).lower()
        assert "null" in condition_str

    def test_by_playlist_empty_string(self):
        """Empty playlist name adds an IS NULL condition for tracks not in any playlist."""
        query = CollectionQuery()
        new_query = query.by_playlist("")

        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0]).lower()
        assert "null" in condition_str

    def test_by_format_empty_string(self, mocker):
        """Empty format string logs a warning and returns self unchanged."""
        mock_warn = mocker.patch("rekordbox_edit.query.logger")
        query = CollectionQuery()
        result = query.by_format("")

        assert result is query
        assert len(result._conditions) == 0
        mock_warn.warning.assert_called_once()

    def test_by_format_invalid(self, mocker):
        """Invalid format logs a warning and returns a copy without adding a condition."""
        mocker.patch(
            "rekordbox_edit.utils.get_file_type_for_format",
            side_effect=ValueError("unknown format"),
        )
        mock_warn = mocker.patch("rekordbox_edit.query.logger")
        query = CollectionQuery()
        new_query = query.by_format("xyz")

        assert new_query is not query
        assert len(new_query._conditions) == 0
        mock_warn.warning.assert_called_once()

    def test_limit(self):
        """limit() sets _limit_count and returns a new instance."""
        query = CollectionQuery()
        new_query = query.limit(10)

        assert new_query is not query
        assert new_query._limit_count == 10
        assert query._limit_count is None

    def test_limit_in_sql(self):
        """limit() results in a LIMIT clause in the final statement."""
        query = CollectionQuery().limit(5)
        stmt_str = str(query._get_full_statement()).lower()
        assert "limit" in stmt_str

    def test_get_full_statement_no_conditions(self):
        """No conditions produces a statement with no WHERE clause."""
        query = CollectionQuery()
        stmt_str = str(query._get_full_statement()).lower()
        assert "where" not in stmt_str

    def test_get_full_statement_or_logic(self):
        """Multiple conditions with default OR logic produces OR in the WHERE clause."""
        query = CollectionQuery().by_title("A").by_title("B")
        stmt_str = str(query._get_full_statement()).lower()
        assert " or " in stmt_str
        assert " and " not in stmt_str

    def test_get_full_statement_and_logic(self):
        """Multiple conditions with match_all=True produces AND in the WHERE clause."""
        query = CollectionQuery().by_title("A").by_title("B").match_all()
        stmt_str = str(query._get_full_statement()).lower()
        assert " and " in stmt_str
        assert " or " not in stmt_str

    def test_by_path_filename_only(self):
        """A bare filename (no directory) adds a FileNameL ilike condition only.
        The FolderPath condition is skipped — the filter still runs with just FileNameL.
        """
        query = CollectionQuery()
        new_query = query.by_path("track.mp3")

        assert new_query is not query
        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0])
        assert "FileNameL" in condition_str
        assert "LIKE lower" in condition_str
        assert "FolderPath" not in condition_str

    def test_by_path_folder_only_forward_slash(self):
        """A trailing-forward-slash string adds a FolderPath ilike condition only.
        The FileNameL condition is skipped — the filter still runs with just FolderPath.
        """
        query = CollectionQuery()
        new_query = query.by_path("./Test/Folder/")

        assert new_query is not query
        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0])
        assert "FileNameL" not in condition_str
        assert "LIKE lower" in condition_str
        assert "FolderPath" in condition_str

    def test_by_path_folder_and_filename(self):
        """A path with both parts adds a compound AND condition covering both columns."""
        query = CollectionQuery()
        new_query = query.by_path("Music/Artist/track.mp3")

        assert new_query is not query
        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0])
        assert "FolderPath" in condition_str
        assert "FileNameL" in condition_str
        assert " AND " in condition_str
        assert condition_str.count("LIKE lower") == 2

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="backslash path parsing is Windows-only"
    )
    def test_by_path_backslash_normalised_to_forward_slash(self):
        """Backslash separators in --path input are normalised to forward slashes."""
        query = CollectionQuery()
        new_query = query.by_path("Music\\Artist\\track.mp3")

        query_str = _compile(new_query._conditions[0])
        assert "\\" not in query_str
        assert "Music/Artist" in query_str

    def test_by_path_no_resolve(self):
        """by_path does NOT resolve the path."""
        query = CollectionQuery()
        new_query = query.by_path("../some/relative/track.mp3")

        condition_str = _compile(new_query._conditions[0])
        # The raw string (or parts of it) must appear, not a resolved absolute path
        assert ".." in condition_str and "relative" in condition_str

    def test_by_path_ilike_wraps_with_wildcards(self):
        """The ilike condition includes % wildcards for substring matching."""
        query = CollectionQuery()
        new_query = query.by_path("track.mp3")

        condition_str = _compile(new_query._conditions[0])
        assert "%" in condition_str

    # --- by_path exact mode ---

    def test_by_exact_path_filename_only(self):
        """Exact match on a bare filename produces an equality condition on FileNameL only."""
        query = CollectionQuery()
        new_query = query.by_path("track.mp3", exact=True)

        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0])
        assert "FolderPath" not in condition_str
        assert "FileNameL" in condition_str
        assert "=" in condition_str
        assert "LIKE lower" not in condition_str

    def test_by_exact_path_folder_only(self):
        """Exact match on a only folder path produces equality check on FolderPath only."""
        query = CollectionQuery()
        # Build a cross-platform absolute path using pathlib
        path = "/Test/Artist/"
        new_query = query.by_path(path, exact=True)

        assert len(new_query._conditions) == 1
        condition_str = _compile(new_query._conditions[0])
        assert "FolderPath" in condition_str
        assert "FileNameL" not in condition_str
        assert "=" in condition_str
        assert path in condition_str
        assert "like lower" not in condition_str

    def test_by_exact_path_folder_and_filename(self):
        """Exact match on a full path produces a compound AND with equality on both columns."""
        query = CollectionQuery()
        # Build a cross-platform absolute path using pathlib
        abs_path = "/Artist/track.mp3"
        new_query = query.by_path(abs_path, exact=True)

        assert len(new_query._conditions) == 1
        condition_str = str(new_query._conditions[0])
        assert "FolderPath" in condition_str
        assert "FileNameL" in condition_str
        assert " AND " in condition_str
        assert "LIKE lower" not in condition_str

    def test_by_exact_path_resolves_relative_path(self):
        """Exact match resolves relative paths to absolute before querying."""
        cwd = Path(os.getcwd()).as_posix()
        query = CollectionQuery()
        new_query = query.by_path("Album/track.mp3", exact=True)

        condition_str = _compile(new_query._conditions[0])
        # cwd should appear as the resolved folder part
        assert cwd in condition_str

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="backslash path parsing is Windows-only"
    )
    def test_by_exact_path_backslash_normalised_to_forward_slash(self):
        """Backslash separators in --exact-path input are normalised via as_posix()."""
        query = CollectionQuery()
        # Pass a Windows-style absolute path; as_posix() must produce forward slashes
        new_query = query.by_path(
            "C:\\Users\\foo\\music\\Artist\\track.mp3", exact=True
        )

        condition_str = _compile(new_query._conditions[0])
        assert "\\" not in condition_str
        assert "/" in condition_str

    def test_by_path_returns_new_instance(self):
        """by_path always returns a new CollectionQuery instance."""
        query = CollectionQuery()
        assert query.by_path("track.mp3") is not query
        assert query.by_path("track.mp3", exact=True) is not query


@pytest.fixture
def mock_query(mocker):
    instance = MagicMock(spec=CollectionQuery)
    for method in [
        "by_track_ids",
        "by_artist",
        "by_title",
        "by_album",
        "by_playlist",
        "by_format",
        "match_all",
        "match_any",
    ]:
        getattr(instance, method).return_value = instance
    mocker.patch("rekordbox_edit.query.CollectionQuery", return_value=instance)
    return instance


class TestGetFilteredContent:
    """Tests for the get_filtered_content function."""

    def test_no_filters(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs())
        mock_query.by_track_ids.assert_not_called()
        mock_query.by_artist.assert_not_called()
        mock_query.by_title.assert_not_called()
        mock_query.by_album.assert_not_called()
        mock_query.by_playlist.assert_not_called()
        mock_query.by_format.assert_not_called()
        mock_query.match_all.assert_not_called()
        mock_query.execute.assert_called_once_with(mock_db)

    def test_track_id_args(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(track_ids=["123", "456"]))
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123", "456"])

    def test_track_ids(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(track_id=["123", "456"]))
        assert mock_query.by_track_ids.call_count == 2
        mock_query.by_track_ids.assert_any_call("123")
        mock_query.by_track_ids.assert_any_call("456")

    def test_artist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"]))
        mock_query.by_artist.assert_called_once_with("Daft Punk")

    def test_multiple_artists(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk", "Justice"]))
        assert mock_query.by_artist.call_count == 2
        mock_query.by_artist.assert_any_call("Daft Punk")
        mock_query.by_artist.assert_any_call("Justice")

    def test_exact_artist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_artist=["Daft Punk"]))
        mock_query.by_artist.assert_called_once_with("Daft Punk", exact=True)

    def test_title(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(title=["One More Time"]))
        mock_query.by_title.assert_called_once_with("One More Time")

    def test_exact_title(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_title=["One More Time"]))
        mock_query.by_title.assert_called_once_with("One More Time", exact=True)

    def test_album(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(album=["Discovery"]))
        mock_query.by_album.assert_called_once_with("Discovery")

    def test_exact_album(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_album=["Discovery"]))
        mock_query.by_album.assert_called_once_with("Discovery", exact=True)

    def test_playlist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(playlist=["My Playlist"]))
        mock_query.by_playlist.assert_called_once_with("My Playlist")

    def test_exact_playlist(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_playlist=["My Playlist"]))
        mock_query.by_playlist.assert_called_once_with("My Playlist", exact=True)

    def test_path(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(path=["Music/track.mp3"]))
        mock_query.by_path.assert_called_once_with("Music/track.mp3")

    def test_exact_path(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(exact_path=["/Music/track.wav"]))
        mock_query.by_path.assert_called_once_with("/Music/track.wav", exact=True)

    def test_format(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(format=["flac"]))
        mock_query.by_format.assert_called_once_with("flac")

    def test_multiple_formats(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(format=["flac", "aiff"]))
        assert mock_query.by_format.call_count == 2
        mock_query.by_format.assert_any_call("flac")
        mock_query.by_format.assert_any_call("aiff")

    def test_match_all(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"], match_all=True))
        mock_query.match_all.assert_called_once()

    def test_default_no_match_all(self, mock_db, mock_query):
        get_filtered_content(mock_db, FilterArgs(artist=["Daft Punk"]))
        mock_query.match_all.assert_not_called()

    def test_track_id_args_combined_with_format(self, mock_db, mock_query):
        """Positional track IDs should combine with other filters, not override them."""
        get_filtered_content(
            mock_db,
            FilterArgs(track_ids=["123"], format=["flac"], match_all=True),
        )
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123"])
        mock_query.by_format.assert_called_once_with("flac")
        mock_query.match_all.assert_called_once()

    def test_track_id_args_combined_with_artist(self, mock_db, mock_query):
        """Piped IDs + artist filter with match_all narrows to artist within that ID set."""
        get_filtered_content(
            mock_db,
            FilterArgs(track_ids=["123", "456"], artist=["Justice"], match_all=True),
        )
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123", "456"])
        mock_query.by_artist.assert_called_once_with("Justice")
        mock_query.match_all.assert_called_once()

    def test_track_id_args_or_with_artist(self, mock_db, mock_query):
        """Piped IDs OR'd with artist expands the result set."""
        get_filtered_content(mock_db, FilterArgs(track_ids=["123"], artist=["Justice"]))
        mock_query.by_track_ids.assert_called_once_with(track_ids=["123"])
        mock_query.by_artist.assert_called_once_with("Justice")
        mock_query.match_all.assert_not_called()

    def test_no_session_raises(self, mock_db):
        """get_filtered_content raises RuntimeError when db has no session."""
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            get_filtered_content(mock_db, FilterArgs())


class TestCollectionQueryExecution:
    """Tests for the count() and execute() methods on CollectionQuery."""

    def test_count_returns_scalar(self):
        """count() executes a COUNT query and returns the scalar result."""
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_db.session.execute.return_value = mock_result

        count = CollectionQuery().count(mock_db)

        assert count == 42
        mock_db.session.execute.assert_called_once()

    def test_count_with_conditions(self):
        """count() works correctly when the query has filter conditions."""
        mock_db = MagicMock()
        mock_db.session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 7
        mock_db.session.execute.return_value = mock_result

        count = CollectionQuery().by_title("One More Time").count(mock_db)

        assert count == 7

    def test_count_no_session_raises(self):
        """count() raises RuntimeError when db has no session."""
        mock_db = MagicMock()
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            CollectionQuery().count(mock_db)

    def test_execute_no_session_raises(self):
        """execute() raises RuntimeError when db has no session."""
        mock_db = MagicMock()
        mock_db.session = None

        with pytest.raises(RuntimeError, match="No Session"):
            CollectionQuery().execute(mock_db)
