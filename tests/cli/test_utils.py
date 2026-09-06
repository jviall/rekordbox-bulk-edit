from unittest.mock import Mock, patch

import click
import pytest

from click.testing import CliRunner

from rekordbox_edit.logger import PrintChoice
from rekordbox_edit.cli.convert import convert_command
from rekordbox_edit.cli.edit import edit_command
from rekordbox_edit.cli.remove import remove_command
from rekordbox_edit.errors import (
    DatabaseBusyError,
    DependencyMissingError,
    InputError,
    RekordboxRunningError,
)
from rekordbox_edit.cli._utils import (
    UserQuit,
    _handle_stdin,
    _print_response_ids,
    _print_response_json,
    _validate_scripting_preconditions,
    confirm,
)
from rekordbox_edit.models import (
    ConvertOp,
    ConvertResponse,
    ConvertResult,
    EditOp,
    EditResponse,
    EditResult,
    RemoveResponse,
    RemoveResult,
    Track,
)


class TestHandleStdin:
    def test_returns_false_when_tty(self):
        kwargs = {"track_ids": ()}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert _handle_stdin(kwargs) is False

    def test_appends_ids_from_piped_stdin(self):
        kwargs = {"track_ids": ("existing",)}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = b"AAA BBB"
            result = _handle_stdin(kwargs)
        assert result is True
        assert kwargs["track_ids"] == ["existing", "AAA", "BBB"]

    def test_strips_bom_from_piped_stdin(self):
        kwargs = {"track_ids": ()}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = bytes([0xEF, 0xBB, 0xBF]) + b"AAA BBB"
            result = _handle_stdin(kwargs)
        assert result is True
        assert kwargs["track_ids"] == ["AAA", "BBB"]

    def test_empty_piped_stdin_returns_false(self):
        kwargs = {"track_ids": ()}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = b"  "
            result = _handle_stdin(kwargs)
        assert result is False
        assert kwargs["track_ids"] == ()

    def test_bom_only_piped_stdin_returns_false(self):
        kwargs = {"track_ids": ()}
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.buffer.read.return_value = bytes([0xEF, 0xBB, 0xBF])
            result = _handle_stdin(kwargs)
        assert result is False
        assert kwargs["track_ids"] == ()


class TestValidateScriptingPreconditions:
    def test_scripting_mode_without_confirmation_raises(self):
        with pytest.raises(click.UsageError):
            _validate_scripting_preconditions(
                PrintChoice.IDS, piped_stdin=False, dry_run=False, yes=False
            )

    def test_scripting_mode_with_yes_ok(self):
        _validate_scripting_preconditions(
            PrintChoice.IDS, piped_stdin=False, dry_run=False, yes=True
        )

    def test_scripting_mode_with_dry_run_ok(self):
        _validate_scripting_preconditions(
            PrintChoice.IDS, piped_stdin=False, dry_run=True, yes=False
        )

    def test_piped_stdin_without_confirmation_raises(self):
        with pytest.raises(click.UsageError, match="Piping"):
            _validate_scripting_preconditions(
                None, piped_stdin=True, dry_run=False, yes=False
            )

    def test_piped_stdin_with_confirmation_ok(self):
        _validate_scripting_preconditions(
            None, piped_stdin=True, dry_run=False, yes=True
        )


class TestPrintResponseIds:
    def test_prints_space_separated_ids(self, capsys):
        _print_response_ids(["1", "2"])
        assert capsys.readouterr().out.strip() == "1 2"


class TestPrintResponseJson:
    def test_emits_envelope_json(self, capsys):
        track = Track(ID="1", FileNameL="x", FolderPath="/x")
        resp = EditResponse(
            result=EditResult(
                field="Title",
                dry_run=False,
                edits=[EditOp(id="1", new_value="N", track=track)],
                skipped=[],
            ),
        )
        _print_response_json(resp)
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["tracks"][0]["ID"] == "1"
        assert payload["result"]["field"] == "Title"

    def test_convert_response_json(self, capsys):
        track = Track(ID="1", FileNameL="x.aif", FolderPath="/x.aif")
        resp = ConvertResponse(
            result=ConvertResult(
                format_out="aiff",
                dry_run=False,
                converted=[
                    ConvertOp(
                        id="1",
                        source_path="/x.wav",
                        output_path="/x.aif",
                        track=track,
                    )
                ],
                deleted=0,
                skipped=[],
            ),
        )
        _print_response_json(resp)
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["result"]["format_out"] == "aiff"


class TestConfirm:
    """Test confirm function."""

    @pytest.fixture
    def mock_dependencies(self, mocker):
        """Mock all dependencies for confirm function."""
        mock_click_prompt = mocker.patch("rekordbox_edit.cli._utils.click.prompt")
        mock_logger = mocker.patch("rekordbox_edit.cli._utils.logger")
        return {
            "click_prompt": mock_click_prompt,
            "logger": mock_logger,
        }

    def test_confirm_yes(self, mock_dependencies):
        """Test confirm returns True when user enters 'y'."""
        mock_dependencies["click_prompt"].return_value = "y"

        result = confirm("Continue?", default=False, abort=False)

        assert result is True
        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_no(self, mock_dependencies):
        """Test confirm returns False when user enters 'n' with abort=False."""
        mock_dependencies["click_prompt"].return_value = "n"

        result = confirm("Continue?", default=True, abort=False)

        assert result is False
        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_quit(self, mock_dependencies):
        """Test confirm raises UserQuit when user enters 'q' with abort=False."""
        mock_dependencies["click_prompt"].return_value = "q"

        with pytest.raises(UserQuit, match="User quit"):
            confirm("Continue?", default=True, abort=False)

    def test_confirm_no_abort_true(self, mock_dependencies):
        """Test confirm raises UserQuit when user enters 'n' with abort=True."""
        mock_dependencies["click_prompt"].return_value = "n"

        with pytest.raises(UserQuit, match="User declined"):
            confirm("Continue?", default=True, abort=True)

        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_no_binary_true(self, mock_dependencies):
        """Test confirm raises UserQuit when user enters 'n' with abort=True."""
        mock_dependencies["click_prompt"].return_value = "n"

        confirm("Continue?", default=True, binary=True)

        mock_dependencies["click_prompt"].assert_called_once()

    def test_confirm_case_insensitive_yes(self, mock_dependencies):
        """Test confirm handles case-insensitive 'YES' input."""
        mock_dependencies["click_prompt"].return_value = "Y"

        result = confirm("Continue?", default=False, abort=False)

        assert result is True

    def test_confirm_case_insensitive_no(self, mock_dependencies):
        """Test confirm handles case-insensitive 'NO' input."""
        mock_dependencies["click_prompt"].return_value = "N"

        result = confirm("Continue?", default=True, abort=False)

        assert result is False

    def test_confirm_case_insensitive_quit(self, mock_dependencies):
        """Test confirm handles case-insensitive 'QUIT' input."""
        mock_dependencies["click_prompt"].return_value = "Q"

        with pytest.raises(UserQuit, match="User quit"):
            confirm("Continue?", default=True, abort=False)


class TestWithDatabaseErrorTranslation:
    """with_database is the single place API errors become CLI ones."""

    @pytest.fixture(autouse=True)
    def _rekordbox_not_running(self):
        with patch("rekordbox_edit.api._utils.get_rekordbox_pid", return_value=None):
            yield

    def _invoke(self, mock_db_class, mock_edit, error):
        mock_db_class.return_value = Mock(session=Mock())
        mock_edit.side_effect = error
        return CliRunner().invoke(
            edit_command, ["Title", "--replace", "New", "--yes", "--title", "x"]
        )

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_input_error_becomes_a_usage_error(self, mock_db_class, mock_edit):
        result = self._invoke(mock_db_class, mock_edit, InputError("bad filter"))

        assert result.exit_code == 2
        assert "bad filter" in result.output

    @pytest.mark.parametrize(
        "error",
        [
            DependencyMissingError("FFmpeg is required"),
            RekordboxRunningError("Rekordbox is running"),
            DatabaseBusyError("another process holds the lock"),
        ],
    )
    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_environment_errors_log_and_exit_one(
        self, mock_db_class, mock_edit, error, caplog
    ):
        result = self._invoke(mock_db_class, mock_edit, error)

        assert result.exit_code == 1
        assert str(error) in caplog.text

    @patch("rekordbox_edit.cli.edit.edit")
    @patch("rekordbox_edit.cli._utils.Rekordbox6Database")
    def test_unexpected_errors_are_not_swallowed(self, mock_db_class, mock_edit):
        # A stray RuntimeError is a bug, not user error, so it must reach
        # main()'s crash handler rather than being reported as usage.
        result = self._invoke(mock_db_class, mock_edit, RuntimeError("boom"))

        assert isinstance(result.exception, RuntimeError)


#: Each write command, the arguments it needs beyond a filter, the api
#: function its module calls, and an empty response for that function.
WRITE_COMMANDS = [
    pytest.param(
        edit_command,
        ["Title", "--replace", "New"],
        "rekordbox_edit.cli.edit.edit",
        EditResponse(
            result=EditResult(field="Title", dry_run=False, edits=[], skipped=[])
        ),
        id="edit",
    ),
    pytest.param(
        convert_command,
        ["--format-out", "mp3"],
        "rekordbox_edit.cli.convert.convert",
        ConvertResponse(
            result=ConvertResult(
                format_out="mp3", dry_run=False, converted=[], deleted=0, skipped=[]
            )
        ),
        id="convert",
    ),
    pytest.param(
        remove_command,
        [],
        "rekordbox_edit.cli.remove.remove",
        RemoveResponse(
            result=RemoveResult(
                dry_run=False, removed=[], skipped=[], deleted_relatives=0
            )
        ),
        id="remove",
    ),
]


class TestWriteCommandsRequireAFilter:
    """`rbe remove --yes` used to match the whole library without a prompt."""

    @pytest.fixture(autouse=True)
    def _stub_db(self):
        with patch("rekordbox_edit.cli._utils.Rekordbox6Database") as db_class:
            db_class.return_value = Mock(session=Mock())
            yield

    @pytest.mark.parametrize("command,args,api_target,response", WRITE_COMMANDS)
    def test_no_filter_is_a_usage_error(self, command, args, api_target, response):
        with patch(api_target) as api:
            result = CliRunner().invoke(command, [*args, "--yes"])

        assert result.exit_code == 2
        assert "at least one filter" in result.output
        api.assert_not_called()

    @pytest.mark.parametrize("command,args,api_target,response", WRITE_COMMANDS)
    def test_piped_track_ids_satisfy_it(self, command, args, api_target, response):
        """Piped IDs arrive after the flags are parsed, so they have to be
        merged in before the request is built."""
        with patch(api_target, return_value=response) as api:
            result = CliRunner().invoke(
                command, [*args, "--yes", "--print", "ids"], input="AAA"
            )

        assert result.exit_code == 0, result.output
        assert api.call_args.args[1].track_ids == ["AAA"]


class TestInteractiveExclusivity:
    """--interactive used to be discarded in silence whenever --yes or
    --dry-run was present."""

    @pytest.mark.parametrize(
        "other,expected",
        [
            ("--yes", "asks about none"),
            ("--dry-run", "nothing to confirm"),
        ],
    )
    def test_interactive_conflicts_are_rejected(self, other, expected):
        with pytest.raises(click.UsageError, match=expected):
            _validate_scripting_preconditions(
                PrintChoice.INFO,
                piped_stdin=False,
                dry_run=other == "--dry-run",
                yes=other == "--yes",
                interactive=True,
            )

    def test_interactive_alone_is_fine(self):
        _validate_scripting_preconditions(
            PrintChoice.INFO,
            piped_stdin=False,
            dry_run=False,
            yes=False,
            interactive=True,
        )

    def test_interactive_cannot_reach_a_scripting_print_mode(self):
        # Prompts and the machine payload share stdout, so an interactive
        # scripted run would interleave them. Exclusivity above rules the
        # combination out before it can be reached.
        with pytest.raises(click.UsageError, match="requires --dry-run or --yes"):
            _validate_scripting_preconditions(
                PrintChoice.IDS,
                piped_stdin=False,
                dry_run=False,
                yes=False,
                interactive=True,
            )
