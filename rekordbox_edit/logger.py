#!/usr/bin/env python3
"""Logging configuration for rekordbox-edit."""

import atexit
import logging
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import Optional

from platformdirs import PlatformDirs
from rich.console import Console

from rekordbox_edit.display import RBE_THEME, RbeHighlighter

LOG_FILE_NAME = f"debug_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

_APP_DIR = Path(
    PlatformDirs(appname="rekordbox-edit", ensure_exists=True).user_data_dir
)


class PrintChoice(Enum):
    """How much console output a command should produce."""

    SILENT = 0
    IDS = 1
    INFO = 2
    DEBUG = 3
    JSON = 4


_console_handler: Optional["ConsoleLogHandler"] = None
_debug_file_path: Path = _APP_DIR / LOG_FILE_NAME


#: Console for log output. Kept apart from `display.console`, which records
#: renderables so tables can be copied into the debug log; log lines already
#: reach that log through the file handler, and recording them again would
#: duplicate every one of them.
#:
#: `soft_wrap` keeps long paths on one line, as the previous click.echo did.
#: Rich would otherwise wrap them at the terminal width.
console = Console(soft_wrap=True, theme=RBE_THEME, highlighter=RbeHighlighter())

_LEVEL_STYLES = {
    logging.CRITICAL: "logging.level.critical",
    logging.ERROR: "logging.level.error",
    logging.WARNING: "logging.level.warning",
}


class ConsoleLogHandler(logging.Handler):
    """Logging handler that writes console output through rich."""

    def emit(self, record):
        try:
            style = next(
                (s for lvl, s in _LEVEL_STYLES.items() if record.levelno >= lvl),
                None,
            )
            # A warning-or-worse line is colored as one block, so the
            # per-token action/path/option accents (meant for INFO lines)
            # don't compete with the severity color for attention.
            #
            # markup=False because rich would read a bracketed run as a style
            # tag and drop it: a track named "Set [b].wav" would otherwise log
            # as "Set .wav".
            console.print(
                self.format(record),
                style=style,
                markup=False,
                highlight=style is None,
            )
        except Exception:
            self.handleError(record)


def get_debug_file_path() -> Path:
    return _debug_file_path


def set_level(level: PrintChoice | None) -> None:
    """Update the console handler log level."""
    global _console_handler

    if _console_handler is None:
        return
    if level in (PrintChoice.SILENT, PrintChoice.IDS, PrintChoice.JSON):
        _console_handler.setLevel(logging.ERROR)
    elif level == PrintChoice.DEBUG:
        _console_handler.setLevel(logging.DEBUG)
    else:
        _console_handler.setLevel(logging.INFO)


def setup_logging(log_file: Optional[str] = None) -> None:
    """Configure the package logger with file and console handlers."""
    global _console_handler, _debug_file_path

    pkg_logger = logging.getLogger("rekordbox_edit")
    pkg_logger.setLevel(logging.DEBUG)
    pkg_logger.propagate = False

    for handler in pkg_logger.handlers[:]:
        handler.close()
        pkg_logger.removeHandler(handler)

    if log_file:
        _debug_file_path = Path(log_file)
    else:
        _debug_file_path = _APP_DIR / LOG_FILE_NAME
    _debug_file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(_debug_file_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s:%(funcName)s:%(lineno)d - %(levelname)s: %(message)s"
        )
    )
    pkg_logger.addHandler(file_handler)

    # Add pyrekordbox loggers to debug log file:
    manager = logging.root.manager
    for name in manager.loggerDict:
        lgr = logging.getLogger(name)
        if name.startswith("pyrekordbox") and isinstance(lgr, logging.Logger):
            lgr.addHandler(file_handler)
    # silence the pyrekordbox logger that warns about RB being open--we do that when necessary ourselves
    pyrekordbox_logger = logging.getLogger("pyrekordbox.db6.database")
    pyrekordbox_logger.propagate = False

    _console_handler = ConsoleLogHandler()
    _console_handler.setLevel(logging.INFO)
    _console_handler.setFormatter(logging.Formatter("%(message)s"))
    pkg_logger.addHandler(_console_handler)


def _flush_handlers() -> None:
    for handler in logging.getLogger("rekordbox_edit").handlers:
        handler.flush()


atexit.register(_flush_handlers)
