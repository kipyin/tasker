"""Ensure Tasker data directory, config file, and database exist on disk."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine

from tasker.infrastructure.config import default_config, load_config, save_config
from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.db.engine import init_db, make_sqlite_engine
from tasker.paths import config_path, database_path, tasker_home


class TaskerLayoutError(RuntimeError):
    """Raised when the Tasker data directory cannot be resolved or created."""


def ensure_tasker_home() -> Path:
    """Create `%APPDATA%\\Tasker` if needed. Raises if APPDATA is unset."""
    home = tasker_home()
    if home is None:
        msg = "APPDATA is not set; cannot create Tasker data directory."
        raise TaskerLayoutError(msg)
    home.mkdir(parents=True, exist_ok=True)
    return home


def ensure_config_file(path: Path | None) -> AppConfig:
    """Load config from `path`, or write and return defaults if missing."""
    if path is None:
        return default_config()
    if not path.is_file():
        cfg = default_config()
        save_config(cfg, path)
        return cfg
    return load_config(path)


def ensure_database(engine: Engine) -> None:
    """Create SQLite tables if they do not exist."""
    init_db(engine)


def prepare_local_storage() -> tuple[Path, AppConfig, Engine]:
    """
    Ensure home directory, config file, and SQLite schema exist.

    Returns the resolved home path, loaded config, and database engine.
    """
    home = ensure_tasker_home()
    cfg_path = config_path()
    config = ensure_config_file(cfg_path)
    db_path = database_path()
    if db_path is None:
        msg = "Database path could not be resolved."
        raise TaskerLayoutError(msg)
    engine = make_sqlite_engine(str(db_path))
    ensure_database(engine)
    return home, config, engine
