"""Canonical filesystem locations for Tasker data (Windows: %APPDATA%\\Tasker)."""

from __future__ import annotations

import os
from pathlib import Path

_TASKER_DIR_NAME = "Tasker"
CONFIG_FILENAME = "config.toml"
DATABASE_FILENAME = "tasker.db"


def tasker_home() -> Path | None:
    """Return the Tasker application data directory, or None if APPDATA is unset."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / _TASKER_DIR_NAME


def config_path() -> Path | None:
    """Expected path to the user config file, if the home directory can be resolved."""
    home = tasker_home()
    if home is None:
        return None
    return home / CONFIG_FILENAME


def database_path() -> Path | None:
    """SQLite database path when the home directory can be resolved."""
    home = tasker_home()
    if home is None:
        return None
    return home / DATABASE_FILENAME
