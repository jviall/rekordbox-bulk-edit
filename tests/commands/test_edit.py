"""Unit tests for edit command."""

from unittest.mock import Mock, patch

import pytest

from rekordbox_edit.commands.edit import edit_command


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.commands.edit.logger") as mock_log:
        yield mock_log


def _make_db_and_result(tracks):
    """Return (mock_db_class, mock_get_filtered_content) with given tracks."""
    mock_db = Mock()
    mock_db.session = Mock()
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = tracks
    return mock_db, mock_result


class TestEditCommandPhase1:
    """Phase 1: Title field, wholesale replace, single-track guard, confirm flow."""

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_sets_title_and_commits(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--replace sets the field on the matched track and commits the session."""
        track = make_djmd_content_item(Title="Old Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(edit_command, ["Title", "--replace", "New Title"])

        assert result.exit_code == 0
        assert track.Title == "New Title"
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_noop_tracks_are_skipped(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """Tracks whose current value already equals --replace are not committed."""
        track = make_djmd_content_item(Title="Same Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "Same Title", "--yes"]
        )

        assert result.exit_code == 0
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_single_track_guard_aborts_on_multiple_matches(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """When >1 track would change and --multi is absent, exit with non-zero code."""
        tracks = [
            make_djmd_content_item(Title="Track A"),
            make_djmd_content_item(Title="Track B"),
        ]
        mock_db, mock_result = _make_db_and_result(tracks)
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code != 0
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_dry_run_does_not_commit(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--dry-run shows preview but does not write to the database."""
        track = make_djmd_content_item(Title="Old Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New Title", "--dry-run"]
        )

        assert result.exit_code == 0
        mock_db.session.commit.assert_not_called()
        mock_confirm.assert_not_called()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_yes_skips_confirm(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--yes applies changes without prompting."""
        track = make_djmd_content_item(Title="Old Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New Title", "--yes"]
        )

        assert result.exit_code == 0
        mock_confirm.assert_not_called()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_interactive_confirms_each_track(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--interactive prompts per track (skipping the batch prompt)."""
        track = make_djmd_content_item(Title="Old Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New Title", "--interactive"]
        )

        assert result.exit_code == 0
        mock_confirm.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_piped_stdin_requires_yes_or_dry_run(self, mock_db_class, mock_gfc):
        """Piping track IDs into edit without --yes or --dry-run is rejected."""
        mock_db = Mock()
        mock_db.session = Mock()
        mock_db_class.return_value = mock_db

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New Title"], input="12345"
        )

        assert result.exit_code != 0

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_scripting_mode_requires_yes_or_dry_run(self, mock_db_class, mock_gfc):
        """--print=ids without --yes or --dry-run is rejected."""
        mock_db = Mock()
        mock_db.session = Mock()
        mock_db_class.return_value = mock_db

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New Title", "--print", "ids"]
        )

        assert result.exit_code != 0

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_filters_forwarded_to_get_filtered_content(
        self, mock_db_class, mock_gfc, mock_confirm
    ):
        """All global filter flags are forwarded to get_filtered_content."""
        mock_db = Mock()
        mock_db.session = Mock()
        mock_db_class.return_value = mock_db
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        CliRunner().invoke(
            edit_command,
            [
                "Title",
                "--replace",
                "New Title",
                "--artist",
                "Bicep",
                "--format",
                "flac",
                "--match-all",
                "--yes",
            ],
        )

        filters = mock_gfc.call_args.args[1]
        assert filters.artist == ["Bicep"]
        assert filters.format == ["flac"]
        assert filters.match_all is True

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_interactive_and_yes_skips_all_confirms(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--interactive + --yes skips both batch and per-track confirms."""
        track = make_djmd_content_item(Title="Old Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "New Title", "--interactive", "--yes"],
        )

        assert result.exit_code == 0
        mock_confirm.assert_not_called()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_print_ids_outputs_edited_track_ids(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--print=ids outputs the IDs of edited tracks after committing."""
        track = make_djmd_content_item(ID="99999", Title="Old Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "New Title", "--print", "ids", "--yes"],
        )

        assert result.exit_code == 0
        assert "99999" in result.output


class TestEditCommandPhase3:
    """Phase 3: --match flag for literal find/replace within field value."""

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_match_replaces_substring(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--match substitutes the pattern within the current value."""
        track = make_djmd_content_item(Title="Dark Matter (feat. Jane)")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--match", "feat.", "--replace", "ft."],
        )

        assert result.exit_code == 0
        assert track.Title == "Dark Matter (ft. Jane)"
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_match_no_match_is_noop(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """When --match pattern is not found in current value, track is a no-op."""
        track = make_djmd_content_item(Title="Dark Matter")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--match", "feat.", "--replace", "ft.", "--yes"],
        )

        assert result.exit_code == 0
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_match_with_none_current_value_is_noop(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """--match on a track where the field is None is silently skipped."""
        track = make_djmd_content_item(Title=None)
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--match", "feat.", "--replace", "ft.", "--yes"],
        )

        assert result.exit_code == 0
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_match_treats_pattern_as_literal(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """--match treats the pattern as a literal string, not a regex."""
        # "1.0" as a regex would also match "1X0"; as a literal it should not
        track = make_djmd_content_item(Title="Version 1X0")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--match", "1.0", "--replace", "2.0", "--yes"],
        )

        assert result.exit_code == 0
        mock_db.session.commit.assert_not_called()


class TestEditCommandUnicode:
    """Unicode and multibyte character handling in edit command fields."""

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_wholesale_replace_with_unicode_value(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--replace accepts and writes multibyte unicode titles correctly."""
        track = make_djmd_content_item(Title="Original Title")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "日本語タイトル"],
        )

        assert result.exit_code == 0
        assert track.Title == "日本語タイトル"
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_wholesale_replace_of_unicode_current_value(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """A track with a unicode title can be replaced wholesale."""
        track = make_djmd_content_item(Title="Ü-Bahn Nights (feat. Ångström)")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "U-Bahn Nights (feat. Angstrom)"],
        )

        assert result.exit_code == 0
        assert track.Title == "U-Bahn Nights (feat. Angstrom)"
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_match_replace_within_unicode_title(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--match correctly finds and replaces a substring within a unicode title."""
        track = make_djmd_content_item(Title="夜 feat. 山田太郎")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--match", "feat.", "--replace", "ft."],
        )

        assert result.exit_code == 0
        assert track.Title == "夜 ft. 山田太郎"
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_noop_when_unicode_values_are_equal(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """No edit is made when the current unicode value already equals --replace."""
        track = make_djmd_content_item(Title="Ø (Disambiguation)")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "Ø (Disambiguation)", "--yes"],
        )

        assert result.exit_code == 0
        mock_db.session.commit.assert_not_called()


class TestEditCommandPhase4:
    """Phase 4: --multi flag to allow batch edits past the single-track guard."""

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_multi_allows_editing_multiple_tracks(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--multi bypasses the single-track guard and edits all matched tracks."""
        tracks = [
            make_djmd_content_item(Title="Track A (feat. X)"),
            make_djmd_content_item(Title="Track B (feat. Y)"),
        ]
        mock_db, mock_result = _make_db_and_result(tracks)
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--match", "feat.", "--replace", "ft.", "--multi"],
        )

        assert result.exit_code == 0
        assert tracks[0].Title == "Track A (ft. X)"
        assert tracks[1].Title == "Track B (ft. Y)"
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_without_multi_still_aborts_on_multiple(
        self, mock_db_class, mock_gfc, make_djmd_content_item
    ):
        """Without --multi, the single-track guard still aborts on multiple matches."""
        tracks = [
            make_djmd_content_item(Title="Track A"),
            make_djmd_content_item(Title="Track B"),
        ]
        mock_db, mock_result = _make_db_and_result(tracks)
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes"]
        )

        assert result.exit_code != 0
        mock_db.session.commit.assert_not_called()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_multi_with_yes_skips_confirm(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--multi --yes edits multiple tracks without prompting."""
        tracks = [
            make_djmd_content_item(Title="Track A"),
            make_djmd_content_item(Title="Track B"),
        ]
        mock_db, mock_result = _make_db_and_result(tracks)
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "New", "--multi", "--yes"],
        )

        assert result.exit_code == 0
        mock_confirm.assert_not_called()
        mock_db.session.commit.assert_called_once()

    @patch("rekordbox_edit.commands.edit.confirm")
    @patch("rekordbox_edit.commands.edit.get_filtered_content")
    @patch("rekordbox_edit.commands.edit.Rekordbox6Database")
    def test_multi_single_track_still_works(
        self, mock_db_class, mock_gfc, mock_confirm, make_djmd_content_item
    ):
        """--multi with only one matching track works fine (guard is not inverted)."""
        track = make_djmd_content_item(Title="Only Track")
        mock_db, mock_result = _make_db_and_result([track])
        mock_db_class.return_value = mock_db
        mock_gfc.return_value = mock_result
        mock_confirm.return_value = True

        from click.testing import CliRunner

        result = CliRunner().invoke(
            edit_command,
            ["Title", "--replace", "New Title", "--multi"],
        )

        assert result.exit_code == 0
        assert track.Title == "New Title"
        mock_db.session.commit.assert_called_once()
