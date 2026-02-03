#!/usr/bin/env python3
"""Logging configuration for rekordbox-bulk-edit."""

import atexit
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from platformdirs import PlatformDirs

VERBOSE = 15  # between DEBUG=10 and INFO=20
logging.addLevelName(VERBOSE, "VERBOSE")
LOG_FILE_NAME = f"debug_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"


class ConsoleLogHandler(logging.Handler):
    """Custom logging handler that outputs to Click with styling."""

    def emit(self, record):
        try:
            msg = self.format(record)
            if record.levelno >= logging.CRITICAL:
                click.echo(click.style(msg, fg="red", bold=True))
            elif record.levelno >= logging.ERROR:
                click.echo(click.style(msg, fg="red"))
            elif record.levelno >= logging.WARNING:
                click.echo(click.style(msg, fg="yellow"))
            elif record.levelno >= logging.INFO:
                click.echo(msg)
            elif record.levelno >= VERBOSE:
                click.echo(msg)
            else:
                click.echo(click.style(msg, dim=True, fg="blue"))

        except Exception:
            self.handleError(record)


class Logger:
    """Application logger with file and console output."""

    _app_dir = Path(
        PlatformDirs(appname="rekordbox-bulk-edit", ensure_exists=True).user_data_dir
    )

    def __init__(
        self,
        level: int = logging.INFO,
        log_file: Optional[str] = None,
    ):
        """Initialize logger with file and console handlers.

        Args:
            log_file: Path to log file. If None, uses system temp directory.
            level: Minimum level for log output (default: INFO)
        """
        logging.raiseExceptions = False
        self.logger = logging.getLogger(f"rekordbox_bulk_edit_{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        if log_file:
            self._log_file_path = Path(log_file)
        else:
            self._log_file_path = self._app_dir / LOG_FILE_NAME
        self._log_file_path.parent.mkdir(parents=True, exist_ok=True)

        self.file_handler = logging.FileHandler(
            self._log_file_path, mode="a", encoding="utf-8"
        )
        self.file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(funcName)s:%(lineno)d - %(levelname)s: %(message)s",
        )
        self.file_handler.setFormatter(file_formatter)
        self.logger.addHandler(self.file_handler)

        self.click_echo_handler = ConsoleLogHandler()
        self.click_echo_handler.setLevel(
            level if (level is not None and level >= 0) else logging.INFO
        )
        console_formatter = logging.Formatter("%(message)s")
        self.click_echo_handler.setFormatter(console_formatter)
        self.logger.addHandler(self.click_echo_handler)

        atexit.register(self._flush_handlers)

    def _flush_handlers(self):
        """Flush all log handlers."""
        for handler in self.logger.handlers:
            handler.flush()

    def set_level(self, level: int):
        """Update the console handler log level.

        Args:
            level: New minimum log level for console output
        """
        self.click_echo_handler.setLevel(level)

    def get_debug_file_path(self) -> Path:
        return self._log_file_path

    def debug(self, message="", *args, **kwargs):
        """Log a message with DEBUG level."""
        self.logger.debug(message, *args, **kwargs)

    def verbose(self, message="", *args, **kwargs):
        """Log a message with VERBOSE level."""
        self.logger.log(VERBOSE, message, *args, **kwargs)

    def info(self, message="", *args, **kwargs):
        """Log a message with INFO level."""
        self.logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """Log a message with WARNING level."""
        self.logger.warning(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """Log a message with ERROR level."""
        self.logger.error(message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """Log a message with CRITICAL level."""
        self.logger.critical(message, *args, **kwargs)
