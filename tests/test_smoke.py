"""Fast smoke checks: CLI loads and TUI mounts headlessly without crashing."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tasker.cli import app as typer_app
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.ui.app import TaskerApp


def test_cli_help_smoke() -> None:
    runner = CliRunner()
    r = runner.invoke(typer_app, ["--help"])
    assert r.exit_code == 0
    assert "Tasker" in r.stdout
    assert "task" in r.stdout.lower()
    assert "mail" in r.stdout.lower()


def test_tui_headless_mount_smoke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Exercise on_mount (task list + detail) under Textual's test harness."""

    monkeypatch.setenv("APPDATA", str(tmp_path))

    async def _run() -> None:
        _, config, engine = prepare_local_storage()
        try:
            tui = TaskerApp(config=config, engine=engine)
            async with tui.run_test() as pilot:
                await asyncio.sleep(0.05)
                assert pilot.app.query_one("#detail-body") is not None
        finally:
            engine.dispose()

    asyncio.run(_run())
