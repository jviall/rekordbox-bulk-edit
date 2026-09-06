from unittest.mock import patch

import pytest

from rekordbox_edit.cli.main import main


class TestMain:
    @patch("rekordbox_edit.cli.main.cli")
    @patch("rekordbox_edit.cli.main.setup_logging")
    def test_calls_setup_logging_then_cli(self, mock_setup, mock_cli):
        main()

        mock_setup.assert_called_once()
        mock_cli.assert_called_once()

    @patch("rekordbox_edit.cli.main._logger")
    @patch("rekordbox_edit.cli.main.cli", side_effect=KeyboardInterrupt)
    @patch("rekordbox_edit.cli.main.setup_logging")
    def test_keyboard_interrupt_logs_and_exits_cleanly(
        self, mock_setup, mock_cli, mock_logger
    ):
        main()  # must not raise

        mock_logger.debug.assert_called_with("User killed the process.")

    @patch("rekordbox_edit.cli.main._logger")
    @patch("rekordbox_edit.cli.main.cli", side_effect=RuntimeError("boom"))
    @patch("rekordbox_edit.cli.main.setup_logging")
    def test_unhandled_exception_logs_critical_and_exits_1(
        self, mock_setup, mock_cli, mock_logger
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_logger.critical.assert_called_once()
        mock_logger.info.assert_called()
