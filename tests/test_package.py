"""Smoke tests for package import and path resolution."""

from __future__ import annotations

import tasker
from tasker.paths import CONFIG_FILENAME, DATABASE_FILENAME, tasker_home


def test_import_package() -> None:
    assert tasker.__doc__
    assert "Tasker" in tasker.__doc__


def test_version_calver() -> None:
    """Version follows CalVer YYYY.MM.MICRO (all numeric segments)."""
    v = tasker.__version__
    assert v != "0.0.0-dev"
    parts = v.split(".")
    assert len(parts) == 3
    year, month, micro = (int(p) for p in parts)
    assert year >= 2026
    assert 1 <= month <= 12
    assert micro >= 0


def test_tasker_home_uses_appdata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert tasker_home() == tmp_path / "Tasker"
    assert CONFIG_FILENAME == "config.toml"
    assert DATABASE_FILENAME == "tasker.db"
