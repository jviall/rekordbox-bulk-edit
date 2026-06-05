from unittest.mock import Mock, patch

from rekordbox_edit.api.convert import plan_convert
from rekordbox_edit.models import ConvertPlanArgs


class TestPlanConvert:
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_filters_already_converted_tracks(
        self, mock_get_type, mock_gfc, mock_db, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(fmt.upper(), 99)
        content = make_djmd_content_item(FileType=1)  # already AIFF
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff"))

        assert plan.files == []

    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_lossy_formats(
        self, mock_get_type, mock_gfc, mock_db, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(fmt.upper(), 99)
        mp3_content = make_djmd_content_item(FileType=5)  # MP3 — skip
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mp3_content]
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff"))

        assert plan.files == []

    @patch("rekordbox_edit.api.convert.os.path.exists")
    @patch("rekordbox_edit.api.convert.get_output_path")
    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_skips_conflicts_when_no_overwrite(
        self, mock_get_type, mock_gfc, mock_get_output, mock_exists,
        mock_db, make_djmd_content_item
    ):
        mock_get_type.side_effect = lambda fmt: {"AIFF": 1, "MP3": 5, "M4A": 6}.get(fmt.upper(), 99)
        content = make_djmd_content_item(FileType=11)  # WAV → convert to AIFF
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_gfc.return_value = mock_result
        mock_get_output.return_value = ("/path/output.aif", "output.aif", "/path")
        mock_exists.return_value = True  # output already exists

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff", overwrite=False))

        assert plan.files == []
        assert len(plan.skipped) == 1

    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_should_delete_defaults_true_for_lossless(
        self, mock_get_type, mock_gfc, mock_db
    ):
        mock_get_type.return_value = 99
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="aiff"))
        assert plan.should_delete is True

    @patch("rekordbox_edit.api.convert.get_filtered_content")
    @patch("rekordbox_edit.api.convert.get_file_type_for_format")
    def test_should_delete_defaults_false_for_mp3(
        self, mock_get_type, mock_gfc, mock_db
    ):
        mock_get_type.return_value = 99
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        plan = plan_convert(mock_db, ConvertPlanArgs(format_out="mp3"))
        assert plan.should_delete is False
