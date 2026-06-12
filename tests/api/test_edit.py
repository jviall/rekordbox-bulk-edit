import pytest
from unittest.mock import patch

from rekordbox_edit.api.edit import _classify_edit, edit
from rekordbox_edit.models import (
    EditRequest,
    EditOp,
    EditResponse,
    SkippedTrack,
)


class TestClassifyEdit:
    def test_returns_edit_op_when_value_would_change(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        args = EditRequest(field="Title", replace_value="New")

        result = _classify_edit(content, args)

        assert isinstance(result, EditOp)
        assert result.id == "1"
        assert result.new_value == "New"

    def test_returns_skipped_when_value_equals_current(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Same")
        args = EditRequest(field="Title", replace_value="Same")

        result = _classify_edit(content, args)

        assert isinstance(result, SkippedTrack)
        assert result.id == "1"
        assert result.reason == "no_change"

    def test_returns_skipped_when_current_is_none(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title=None)
        args = EditRequest(field="Title", replace_value="New")

        result = _classify_edit(content, args)

        assert isinstance(result, SkippedTrack)
        assert result.reason == "no_change"

    def test_match_pattern_applied(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Hello World")
        args = EditRequest(field="Title", replace_value="Earth", match_pattern="World")

        result = _classify_edit(content, args)

        assert isinstance(result, EditOp)
        assert result.new_value == "Hello Earth"


class TestEditDryRun:
    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_returns_response_without_committing(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", Title="Old")
        mock_gfc.return_value.scalars.return_value.all.return_value = [content]

        response = edit(
            mock_db, EditRequest(field="Title", replace_value="New"), dry_run=True
        )

        assert isinstance(response, EditResponse)
        assert response.result.field == "Title"
        assert response.result.edits == [EditOp(id="1", new_value="New")]
        assert response.tracks[0].ID == "1"
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_dry_run_surfaces_skipped(self, mock_gfc, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Same")
        mock_gfc.return_value.scalars.return_value.all.return_value = [content]

        response = edit(
            mock_db, EditRequest(field="Title", replace_value="Same"), dry_run=True
        )

        assert response.result.edits == []
        assert response.tracks == []
        assert len(response.result.skipped) == 1
        assert response.result.skipped[0].reason == "no_change"

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_dry_run_still_raises_multi_guard(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        # multi guard MUST still raise even in dry-run; it's a usage error,
        # not a side effect. Verify behaviour matches real-run.
        contents = [
            make_djmd_content_item(ID="1", Title="Old"),
            make_djmd_content_item(ID="2", Title="Old"),
        ]
        mock_gfc.return_value.scalars.return_value.all.return_value = contents

        with pytest.raises(ValueError, match="multi"):
            edit(
                mock_db,
                EditRequest(field="Title", replace_value="New", multi=False),
                dry_run=True,
            )


class TestEditRealRun:
    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_applies_changes_and_commits(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", Title="Old")
        mock_gfc.return_value.scalars.return_value.all.return_value = [content]

        response = edit(mock_db, EditRequest(field="Title", replace_value="New"))

        assert content.Title == "New"
        mock_db.session.commit.assert_called_once()
        assert response.result.edits == [EditOp(id="1", new_value="New")]
        assert response.tracks[0].ID == "1"

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_empty_result_returns_empty_response_without_commit(
        self, mock_gfc, mock_db
    ):
        mock_gfc.return_value.scalars.return_value.all.return_value = []

        response = edit(mock_db, EditRequest(field="Title", replace_value="New"))

        assert response.result.edits == []
        assert response.tracks == []
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_multi_flag_allows_multiple_edits(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        contents = [
            make_djmd_content_item(ID="1", Title="Old"),
            make_djmd_content_item(ID="2", Title="Old"),
        ]
        mock_gfc.return_value.scalars.return_value.all.return_value = contents

        response = edit(
            mock_db, EditRequest(field="Title", replace_value="New", multi=True)
        )

        assert len(response.result.edits) == 2

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_preserves_op_order_in_response_tracks(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        # Even if DB returns rows in non-input order, response.tracks aligns
        # with response.result.edits.
        contents = [
            make_djmd_content_item(ID="C", Title="c-old"),
            make_djmd_content_item(ID="A", Title="a-old"),
            make_djmd_content_item(ID="B", Title="b-old"),
        ]
        mock_gfc.return_value.scalars.return_value.all.return_value = contents

        response = edit(
            mock_db, EditRequest(field="Title", replace_value="x", multi=True)
        )

        # The order of result.edits follows the classifier (i.e. the order
        # of contents). tracks aligns to edits.
        ids = [t.ID for t in response.tracks]
        assert ids == [op.id for op in response.result.edits]
