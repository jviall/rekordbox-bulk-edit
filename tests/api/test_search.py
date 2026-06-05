from unittest.mock import Mock, patch

from rekordbox_edit.api.search import search
from rekordbox_edit.args import FilterArgs, Track


class TestSearch:
    @patch("rekordbox_edit.api.search.get_filtered_content")
    def test_returns_list_of_tracks(self, mock_gfc, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(ID="ABC")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result

        result = search(mock_db, FilterArgs())

        assert len(result) == 1
        assert isinstance(result[0], Track)
        assert result[0].ID == "ABC"

    @patch("rekordbox_edit.api.search.get_filtered_content")
    def test_empty_result(self, mock_gfc, mock_db):
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        result = search(mock_db, FilterArgs())

        assert result == []

    @patch("rekordbox_edit.api.search.get_filtered_content")
    def test_passes_args_to_get_filtered_content(self, mock_gfc, mock_db):
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        args = FilterArgs(artist=["Daft Punk"], match_all=True)
        search(mock_db, args)

        mock_gfc.assert_called_once_with(mock_db, args)
