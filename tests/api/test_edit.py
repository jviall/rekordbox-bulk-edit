import pytest
from unittest.mock import Mock, patch

from rekordbox_edit.api.edit import EditPlan, EditResult, edit, plan_edit
from rekordbox_edit.models import EditPlanArgs, Track


class TestPlanEdit:
    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_returns_edit_plan(self, mock_gfc, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result

        plan = plan_edit(mock_db, EditPlanArgs(field="Title", replace_value="New"))

        assert isinstance(plan, EditPlan)
        assert len(plan.edits) == 1
        track, new_val = plan.edits[0]
        assert isinstance(track, Track)
        assert track.ID == "1"
        assert new_val == "New"

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_skips_tracks_with_no_change(self, mock_gfc, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(Title="Same")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result

        plan = plan_edit(mock_db, EditPlanArgs(field="Title", replace_value="Same"))

        assert plan.edits == []

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_raises_value_error_for_multi_without_flag(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        content1 = make_djmd_content_item(ID="1", Title="Old")
        content2 = make_djmd_content_item(ID="2", Title="Old")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content1, content2]
        mock_gfc.return_value = mock_result

        with pytest.raises(ValueError, match="multi"):
            plan_edit(mock_db, EditPlanArgs(field="Title", replace_value="New", multi=False))

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_multi_flag_allows_multiple_edits(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        content1 = make_djmd_content_item(ID="1", Title="Old")
        content2 = make_djmd_content_item(ID="2", Title="Old")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content1, content2]
        mock_gfc.return_value = mock_result

        plan = plan_edit(mock_db, EditPlanArgs(field="Title", replace_value="New", multi=True))

        assert len(plan.edits) == 2

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_match_pattern_applied(self, mock_gfc, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(Title="Hello World")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result

        plan = plan_edit(
            mock_db,
            EditPlanArgs(field="Title", replace_value="Earth", match_pattern="World"),
        )

        _, new_val = plan.edits[0]
        assert new_val == "Hello Earth"


class TestEdit:
    def test_applies_changes_and_commits(self, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = [content]

        track = Track(ID="1", Title="Old")
        plan = EditPlan(field="Title", edits=[(track, "New Title")])

        result = edit(mock_db, plan)

        assert content.Title == "New Title"
        mock_db.session.commit.assert_called_once()
        assert isinstance(result, EditResult)
        assert result.applied == 1

    def test_empty_plan_returns_zero(self, mock_db):
        plan = EditPlan(field="Title", edits=[])
        result = edit(mock_db, plan)
        assert result.applied == 0
        mock_db.session.commit.assert_not_called()
