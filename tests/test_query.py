#!/usr/bin/env python3
"""Tests for the CollectionQuery class."""

from rekordbox_bulk_edit.query import CollectionQuery


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
            "rekordbox_bulk_edit.utils.get_file_type_for_format"
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
