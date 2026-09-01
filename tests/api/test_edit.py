import pytest
from unittest.mock import MagicMock, call, patch

from rekordbox_edit.api.edit import _classify_edit, edit
from rekordbox_edit.api.field_handlers import FIELD_HANDLERS
from sqlalchemy import text

from rekordbox_edit.query import require_session
from rekordbox_edit.models import (
    EditRequest,
    EditOp,
    EditResponse,
    SkippedTrack,
)


@pytest.fixture()
def stub_handler(monkeypatch):
    """A MagicMock field handler registered as the 'Stub' field."""
    handler = MagicMock()
    handler.name = "Stub"
    handler.current_value.return_value = "Old"
    handler.compute_new_value.return_value = "New"
    handler.validate_track.return_value = None
    monkeypatch.setitem(FIELD_HANDLERS, "Stub", handler)
    return handler


class TestClassifyEdit:
    def test_returns_edit_op_when_value_would_change(
        self, mock_db, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", Title="Old")
        args = EditRequest(field="Title", replace_value="New")

        result = _classify_edit(mock_db, content, args)

        assert isinstance(result, EditOp)
        assert result.id == "1"
        assert result.new_value == "New"

    def test_returns_skipped_when_value_equals_current(
        self, mock_db, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", Title="Same")
        args = EditRequest(field="Title", replace_value="Same")

        result = _classify_edit(mock_db, content, args)

        assert isinstance(result, SkippedTrack)
        assert result.id == "1"
        assert result.reason == "no_change"

    def test_plain_replace_sets_when_current_is_none(
        self, mock_db, make_djmd_content_item
    ):
        content = make_djmd_content_item(ID="1", Title=None)
        args = EditRequest(field="Title", replace_value="New")

        result = _classify_edit(mock_db, content, args)

        assert isinstance(result, EditOp)
        assert result.new_value == "New"

    def test_match_skips_when_current_is_none(self, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title=None)
        args = EditRequest(field="Title", replace_value="b", match_pattern="a")

        result = _classify_edit(mock_db, content, args)

        assert isinstance(result, SkippedTrack)
        assert result.reason == "no_change"

    def test_match_pattern_applied(self, mock_db, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Hello World")
        args = EditRequest(field="Title", replace_value="Earth", match_pattern="World")

        result = _classify_edit(mock_db, content, args)

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

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_skipped_content_is_not_applied(
        self, mock_gfc, mock_db, make_djmd_content_item
    ):
        # One track matches and is changed; one has no match and is skipped.
        # Only the matching track's content should be mutated.
        changed = make_djmd_content_item(ID="1", Title="Hello World")
        skipped = make_djmd_content_item(ID="2", Title="Nothing Here")
        mock_gfc.return_value.scalars.return_value.all.return_value = [
            changed,
            skipped,
        ]

        edit(
            mock_db,
            EditRequest(
                field="Title", replace_value="Earth", match_pattern="World", multi=True
            ),
        )

        assert changed.Title == "Hello Earth"
        assert skipped.Title == "Nothing Here"

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_unknown_field_raises(self, mock_gfc, mock_db):
        mock_gfc.return_value.scalars.return_value.all.return_value = []
        with pytest.raises(ValueError, match="Unknown field"):
            edit(mock_db, EditRequest(field="Nope", replace_value="x"))


class TestValidateTrackHook:
    def test_skip_reason_from_handler(
        self, mock_db, make_djmd_content_item, stub_handler
    ):
        stub_handler.validate_track.return_value = "file_not_found"
        content = make_djmd_content_item(ID="1")
        args = EditRequest(field="Stub", replace_value="New")

        result = _classify_edit(mock_db, content, args)

        assert isinstance(result, SkippedTrack)
        assert result.reason == "file_not_found"
        stub_handler.validate_track.assert_called_once_with(
            mock_db, content, "New", args
        )

    def test_none_proceeds(self, mock_db, make_djmd_content_item, stub_handler):
        content = make_djmd_content_item(ID="1")

        result = _classify_edit(
            mock_db, content, EditRequest(field="Stub", replace_value="New")
        )

        assert isinstance(result, EditOp)


class TestPostCommitHook:
    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_called_after_commit_with_old_value(
        self, mock_gfc, mock_db, make_djmd_content_item, stub_handler
    ):
        content = make_djmd_content_item(ID="1")
        mock_gfc.return_value.scalars.return_value.all.return_value = [content]
        order = MagicMock()
        order.attach_mock(mock_db.session.commit, "commit")
        order.attach_mock(stub_handler.post_commit, "post_commit")

        edit(mock_db, EditRequest(field="Stub", replace_value="New"))

        stub_handler.post_commit.assert_called_once_with(mock_db, content, "Old")
        assert order.mock_calls.index(call.commit()) < order.mock_calls.index(
            call.post_commit(mock_db, content, "Old")
        )

    @patch("rekordbox_edit.api.edit.get_filtered_content")
    def test_not_called_on_dry_run(
        self, mock_gfc, mock_db, make_djmd_content_item, stub_handler
    ):
        content = make_djmd_content_item(ID="1")
        mock_gfc.return_value.scalars.return_value.all.return_value = [content]

        edit(mock_db, EditRequest(field="Stub", replace_value="New"), dry_run=True)

        stub_handler.post_commit.assert_not_called()


class TestEditStampsUsns:
    """Against the real library, since stamping is a database behavior."""

    _COUNTER = text(
        "SELECT int_1 FROM agentRegistry WHERE registry_id = 'localUpdateCount'"
    )

    def test_an_edited_row_gets_a_fresh_usn_and_moves_the_counter(self, db):
        session = require_session(db)
        start = session.execute(self._COUNTER).scalar()
        track = db.get_content().first()
        before = track.rb_local_usn

        edit(
            db,
            EditRequest(
                field="Title", track_ids=[str(track.ID)], replace_value="Renamed"
            ),
        )

        assert track.Title == "Renamed"
        assert track.rb_local_usn > before
        assert session.execute(self._COUNTER).scalar() == start + 1
        assert track.rb_local_usn == start + 1

    def test_a_dry_run_leaves_the_counter_alone(self, db):
        session = require_session(db)
        start = session.execute(self._COUNTER).scalar()
        track = db.get_content().first()

        edit(
            db,
            EditRequest(field="Title", track_ids=[str(track.ID)], replace_value="Nope"),
            dry_run=True,
        )

        assert session.execute(self._COUNTER).scalar() == start

    def test_a_skipped_track_consumes_no_usn(self, db):
        session = require_session(db)
        track = db.get_content().first()
        start = session.execute(self._COUNTER).scalar()

        # Replacing a title with the value it already has is a no_change skip.
        response = edit(
            db,
            EditRequest(
                field="Title", track_ids=[str(track.ID)], replace_value=track.Title
            ),
        )

        assert response.result.edits == []
        assert session.execute(self._COUNTER).scalar() == start
