#!/usr/bin/env python3
"""Tests for the Logger class."""

import logging
import tempfile
from pathlib import Path

import pytest
from platformdirs import PlatformDirs

from rekordbox_bulk_edit.logger import LOG_FILE_NAME, VERBOSE, Logger


class TestLogger:
    """Test the Logger class methods and functionality."""

    @pytest.fixture
    def logger_default_file(self):
        """Create a logger using the default file path for testing default path behavior."""
        log_file_path = (
            Path(PlatformDirs("rekordbox-bulk-edit").user_data_dir) / LOG_FILE_NAME
        )
        logger = Logger()

        yield (logger, log_file_path)

        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)
        if log_file_path.exists():
            try:
                log_file_path.unlink()
            except (PermissionError, FileNotFoundError):
                print(
                    f"Failed to clean up test log file ({str(log_file_path)}) ignoring."
                )
                pass  # Ignore cleanup errors for default path test

    @pytest.fixture
    def logger_custom_file(self):
        """Create a logger with a temporary log file using robust cleanup."""
        with tempfile.NamedTemporaryFile(
            delete=True, prefix=LOG_FILE_NAME, suffix=".log"
        ) as tmp:
            log_file_path = Path(tmp.name)

        logger = Logger(log_file=str(log_file_path))

        yield (logger, str(log_file_path))

        for handler in logger.logger.handlers[:]:
            handler.close()
            logger.logger.removeHandler(handler)

        try:
            log_file_path.unlink()
        except (PermissionError, FileNotFoundError):
            print(f"Failed to clean up test log file ({str(log_file_path)}) ignoring.")
            pass  # OS cleans up temp files eventually

    def test_debug_calls_logger_debug(
        self, mocker, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger.debug calls the underlying logging.Logger debug method."""
        logger, _ = logger_custom_file
        debug_spy = mocker.spy(logger.logger, "debug")

        test_message = "Test message"
        logger.debug(test_message, "arg1", dict(extra=True))

        debug_spy.assert_called_once_with(test_message, "arg1", dict(extra=True))

    def test_verbose_calls_log_with_level(
        self, mocker, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger.verbose calls the underlying logging.Logger log method with level 15."""
        logger, _ = logger_custom_file
        log_spy = mocker.spy(logger.logger, "log")

        test_message = "Test verbose message"
        logger.verbose(test_message, "arg1", dict(extra=True))

        log_spy.assert_called_once_with(VERBOSE, test_message, "arg1", dict(extra=True))

    def test_info_calls_logger_info(
        self, mocker, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger.info calls the underlying logging.Logger info method."""
        logger, _ = logger_custom_file
        info_spy = mocker.spy(logger.logger, "info")

        test_message = "Test info message"
        logger.info(test_message, "arg1", dict(extra=True))

        info_spy.assert_called_once_with(test_message, "arg1", dict(extra=True))

    def test_warning_calls_logger_warning(
        self, mocker, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger.warning calls the underlying logging.Logger warning method."""
        logger, _ = logger_custom_file
        warning_spy = mocker.spy(logger.logger, "warning")

        test_message = "Test warning message"
        logger.warning(test_message, "arg1", dict(extra=True))

        warning_spy.assert_called_once_with(test_message, "arg1", dict(extra=True))

    def test_error_calls_logger_error(
        self, mocker, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger.error calls the underlying logging.Logger error method."""
        logger, _ = logger_custom_file
        error_spy = mocker.spy(logger.logger, "error")

        test_message = "Test error message"
        logger.error(test_message, "arg1", dict(extra=True))

        error_spy.assert_called_once_with(test_message, "arg1", dict(extra=True))

    def test_critical_calls_logger_critical(
        self, mocker, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger.critical calls the underlying logging.Logger critical method."""
        logger, _ = logger_custom_file
        critical_spy = mocker.spy(logger.logger, "critical")

        test_message = "Test critical message"
        logger.critical(test_message, "arg1", dict(extra=True))

        critical_spy.assert_called_once_with(test_message, "arg1", dict(extra=True))

    def test_logger_creates_log_file_in_default_path(
        self, logger_default_file: tuple[Logger, Path]
    ):
        """Test that Logger creates a log file in the default path."""
        logger, log_default_path = logger_default_file

        test_msg = "Log message"

        logger.debug(test_msg)
        logger.verbose(test_msg)
        logger.info(test_msg)
        logger.warning(test_msg)
        logger.error(test_msg)
        logger.critical(test_msg)

        # Flush handlers to ensure messages are written
        logger._flush_handlers()

        # Check that the log file was created
        log_file_path = logger.get_debug_file_path()
        assert str(log_file_path) == str(log_default_path)
        assert log_file_path.exists()

        # Assert that the log file contains the messages
        log_content = log_file_path.read_text(encoding="utf-8")
        assert f"DEBUG: {test_msg}" in log_content
        assert f"VERBOSE: {test_msg}" in log_content
        assert f"INFO: {test_msg}" in log_content
        assert f"WARNING: {test_msg}" in log_content
        assert f"ERROR: {test_msg}" in log_content
        assert f"CRITICAL: {test_msg}" in log_content

    def test_logger_creates_log_file_in_given_location(
        self, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger creates a log file in a given location."""
        logger, custom_path = logger_custom_file

        # Check that the log file was created at the specified location
        log_file_path = logger.get_debug_file_path()
        assert log_file_path.exists()
        assert str(log_file_path) == str(custom_path)

    def test_logger_writes_sequentially_across_instances(
        self, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that Logger successfully writes to a single log file across multiple logger instances."""
        first_logger, log_file_path = logger_custom_file

        # Create second logger instance using the same file path
        second_logger = Logger(log_file=str(log_file_path))

        # Write messages with first logger instance
        messages = (
            "First message",
            "Second message",
            "Third message",
            "Fourth message",
            "Fifth message",
        )

        first_logger.debug(messages[0])
        second_logger.info(messages[1])
        first_logger.warning(messages[2])
        second_logger.error(messages[3])
        first_logger.critical(messages[4])

        second_logger._flush_handlers()
        first_logger._flush_handlers()

        # Read log file and verify all messages are present
        log_content = Path(log_file_path).read_text(encoding="utf-8")

        # Verify messages appear in correct order
        message_lines = [
            line
            for line in log_content.strip().split("\n")
            if any(msg in line for msg in messages)
        ]

        for index, msg in enumerate(messages):
            assert msg in message_lines[index]

        # Clean up second logger
        for handler in second_logger.logger.handlers[:]:
            handler.close()
            second_logger.logger.removeHandler(handler)

    def test_set_level_updates_console_handler(
        self, logger_custom_file: tuple[Logger, Path]
    ):
        """Test that set_level updates the console handler log level."""
        logger, _ = logger_custom_file

        # Verify initial level
        assert logger.click_echo_handler.level == logging.INFO

        # Change level and verify it was updated
        logger.set_level(logging.ERROR)
        assert logger.click_echo_handler.level == logging.ERROR

    def test_verbose_level_constant(self):
        """Test that VERBOSE level is set to 15."""
        assert VERBOSE == 15
        assert logging.getLevelName(VERBOSE) == "VERBOSE"
