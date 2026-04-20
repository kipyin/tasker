"""Config persistence, data directory layout, SQLite, and repositories."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session

from tasker.domain.enums import TaskStatus
from tasker.infrastructure.config import (
    AppConfig,
    ProjectConfig,
    load_config,
    save_config,
)
from tasker.infrastructure.db import init_db, make_sqlite_engine
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository


def test_config_roundtrip(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(
                id="alpha",
                name="Alpha",
                root=str(tmp_path / "work"),
            ),
        ],
    )
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.projects[0].id == "alpha"
    assert loaded.projects[0].root == str(tmp_path / "work")


def test_prepare_local_storage_creates_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    home, config, engine = prepare_local_storage()
    try:
        assert home == tmp_path / "Tasker"
        assert (home / "config.toml").is_file()
        assert (home / "tasker.db").is_file()
        assert config.version == 1
    finally:
        engine.dispose()


def test_task_repository_crud(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        repo = TaskRepository(session)
        task = repo.create(title="Inbox review", project_id="p1")
        assert task.id is not None
        assert task.status == TaskStatus.DRAFT

        fetched = repo.get(task.id)
        assert fetched is not None
        assert fetched.title == "Inbox review"

        updated = repo.update(task.id, status=TaskStatus.ACTIVE, title="Done")
        assert updated is not None
        assert updated.status == TaskStatus.ACTIVE

        assert len(repo.list_all()) == 1
        assert repo.delete(task.id) is True
        assert repo.get(task.id) is None
    finally:
        session.close()
        engine.dispose()


def test_task_repository_delete_cascade(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task = tasks.create(title="Cascade")
        refs.create(task_id=task.id, msg_path=r"C:\mail\a.msg")
        assert tasks.delete_cascade(task.id) is True
        assert tasks.get(task.id) is None
        assert refs.list_for_task(task.id) == []
    finally:
        session.close()
        engine.dispose()


def test_message_ref_repository(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task = tasks.create(title="Email task")
        r1 = refs.create(task_id=task.id, msg_path=r"C:\mail\a.msg")
        r2 = refs.create(task_id=task.id, msg_path=r"C:\mail\b.msg")
        listed = refs.list_for_task(task.id)
        assert len(listed) == 2
        assert {x.msg_path for x in listed} == {r1.msg_path, r2.msg_path}
        assert refs.delete(r2.id) is True
        assert len(refs.list_for_task(task.id)) == 1
    finally:
        session.close()
        engine.dispose()
