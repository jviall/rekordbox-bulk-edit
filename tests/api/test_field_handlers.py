from rekordbox_edit.api.field_handlers import (
    FIELD_HANDLERS,
    StringField,
)
from rekordbox_edit.models import EditRequest


class TestStringField:
    def test_current_value_reads_named_column(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        handler = StringField("Title", "Title")
        assert handler.current_value(content) == "Old"

    def test_compute_plain_replace(self):
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="New")
        assert handler.compute_new_value("Old", args) == "New"

    def test_compute_match_replace(self):
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="Earth", match_pattern="World")
        assert handler.compute_new_value("Hello World", args) == "Hello Earth"

    def test_compute_plain_replace_sets_from_none(self):
        # Plain --replace assigns a value even to an empty field.
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="New")
        assert handler.compute_new_value(None, args) == "New"

    def test_compute_match_skips_none(self):
        # --match has no text to search when the field is empty.
        handler = StringField("Title", "Title")
        args = EditRequest(field="Title", replace_value="b", match_pattern="a")
        assert handler.compute_new_value(None, args) is None

    def test_apply_sets_column(self, make_djmd_content_item):
        content = make_djmd_content_item(ID="1", Title="Old")
        StringField("Title", "Title").apply(db=None, content=content, new_value="New")
        assert content.Title == "New"


class TestRegistry:
    def test_title_registered(self):
        assert FIELD_HANDLERS["Title"].name == "Title"
        assert FIELD_HANDLERS["Title"].supports_match is True
