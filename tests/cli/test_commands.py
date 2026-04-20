"""Typer commands: task CRUD, config, and ingest."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session
from typer.testing import CliRunner

from tasker.cli import app
from tasker.infrastructure.db import init_db, make_sqlite_engine
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.paths import database_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_add_view_edit_remove(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    r = runner.invoke(app, ["add", "--title", "Alpha", "--status", "pending"])
    assert r.exit_code == 0
    assert "Created task" in r.stdout

    r = runner.invoke(app, ["view"])
    assert r.exit_code == 0
    assert "Alpha" in r.stdout

    r = runner.invoke(app, ["view", "1"])
    assert r.exit_code == 0
    assert "Alpha" in r.stdout

    r = runner.invoke(app, ["edit", "1", "--title", "Beta", "--status", "active"])
    assert r.exit_code == 0
    assert "Beta" in r.stdout

    r = runner.invoke(app, ["remove", "1"])
    assert r.exit_code == 1
    assert "--yes" in r.stdout

    r = runner.invoke(app, ["remove", "1", "--yes"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["view"])
    assert r.exit_code == 0
    assert "No tasks" in r.stdout


def test_cli_config_show_and_path(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["config", "path"])
    assert r.exit_code == 0
    assert "config.toml" in r.stdout
    assert "Tasker" in r.stdout
    expected = (tmp_path / "Tasker" / "config.toml").resolve()
    normalized_out = "".join(r.stdout.split())
    normalized_expected = "".join(str(expected).split())
    assert normalized_expected in normalized_out

    r = runner.invoke(app, ["config", "show"])
    assert r.exit_code == 0
    assert "version" in r.stdout.lower() or "version" in r.stdout


def test_cli_edit_requires_field(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    runner.invoke(app, ["add", "--title", "X"])
    r = runner.invoke(app, ["edit", "1"])
    assert r.exit_code == 1
    assert "at least one" in r.stdout.lower()


def test_cli_add_bad_status(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    r = runner.invoke(app, ["add", "--title", "Y", "--status", "nope"])
    assert r.exit_code != 0


def test_cli_delete_cascade_removes_refs(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    runner.invoke(app, ["add", "--title", "With ref"])

    db = database_path()
    assert db is not None
    engine = make_sqlite_engine(str(db))
    init_db(engine)
    session = Session(engine)
    try:
        refs = MessageRefRepository(session)
        refs.create(task_id=1, msg_path=str(Path("C:/mail/x.msg")))
    finally:
        session.close()
        engine.dispose()

    r = runner.invoke(app, ["remove", "1", "--yes"])
    assert r.exit_code == 0

    engine = make_sqlite_engine(str(db))
    init_db(engine)
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        assert tasks.get(1) is None
        refs = MessageRefRepository(session)
        assert refs.list_for_task(1) == []
    finally:
        session.close()
        engine.dispose()
