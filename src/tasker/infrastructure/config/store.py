"""Load and save `AppConfig` as TOML."""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from tasker.infrastructure.config.schema import AppConfig


def load_config(path: Path) -> AppConfig:
    """Read and validate config from a TOML file."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: Path) -> None:
    """Write config to TOML, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="python", exclude_none=True)
    with path.open("wb") as f:
        tomli_w.dump(payload, f)


def default_config() -> AppConfig:
    """Default configuration for a fresh install."""
    return AppConfig()
