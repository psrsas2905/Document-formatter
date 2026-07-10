"""File logging for crash diagnostics — friendly messages go to the user,
full tracebacks and subprocess stderr go here.

Log location (per-user, created on demand):
  Windows:  %LOCALAPPDATA%/docformat/logs/docformat.log
  macOS:    ~/Library/Logs/docformat/docformat.log
  Linux:    $XDG_STATE_HOME/docformat/docformat.log (default ~/.local/state)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_LOGGER_NAME = "docformat"


def log_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "docformat" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "docformat"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "docformat"


def setup_logging(verbose: bool = False) -> Path:
    """Attach a rotating file handler to the docformat logger (idempotent).

    Returns the log file path so error messages can point users at it.
    """
    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "docformat.log"

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, "_docformat", False)
        for h in logger.handlers
    ):
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler._docformat = True
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return log_file
