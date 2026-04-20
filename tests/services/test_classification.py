"""BYOK classification: API key resolution, proposal parsing, apply on confirm."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session

from tasker.domain.classification import ClassificationProposal
from tasker.domain.enums import TaskStatus
from tasker.domain.exceptions import ClassificationError
from tasker.infrastructure.config.schema import AIConfig, AppConfig, ProjectConfig
from tasker.infrastructure.db import init_db, make_sqlite_engine
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.classification import (
    apply_confirmed_proposal,
    load_task_primary_ref,
    request_classification_proposal,
    resolve_api_key,
)


def _sample_config() -> AppConfig:
    return AppConfig(
        ai=AIConfig(
            base_url="https://example.invalid/v1",
            model="test-model",
            api_key_env="TASKER_TEST_KEY",
        ),
        projects=[
            ProjectConfig(id="p1", name="Alpha", root="C:/a"),
            ProjectConfig(id="p2", name="Beta", root="C:/b"),
        ],
    )


def test_resolve_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASKER_TEST_KEY", raising=False)
    cfg = _sample_config()
    cfg.ai.api_key_env = "TASKER_TEST_KEY"
    with pytest.raises(ClassificationError, match="not set"):
        resolve_api_key(cfg)


def test_resolve_api_key_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASKER_TEST_KEY", "secret")
    cfg = _sample_config()
    assert resolve_api_key(cfg) == "secret"


def test_request_classification_proposal_no_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TASKER_TEST_KEY", "x")
    cfg = _sample_config()
    cfg.projects = []
    task = Task(id=1, title="t", status=TaskStatus.PENDING, project_id="")
    ref = MessageRef(id=1, task_id=1, msg_path="m.msg")
    with pytest.raises(ClassificationError, match="No projects"):
        request_classification_proposal(config=cfg, task=task, ref=ref, api_key="x")


def test_request_classification_proposal_parses_json() -> None:
    cfg = _sample_config()

    def fake_complete(**_kwargs: object) -> str:
        return json.dumps(
            {
                "project_id": "p2",
                "rationale": "Beta matches the client name.",
                "suggested_title": "Follow up with Beta",
            }
        )

    task = Task(id=1, title="t", status=TaskStatus.PENDING, project_id="")
    ref = MessageRef(id=1, task_id=1, msg_path="m.msg", subject="Hi")

    prop = request_classification_proposal(
        config=cfg,
        task=task,
        ref=ref,
        api_key="k",
        complete=fake_complete,
    )
    assert prop.project_id == "p2"
    assert "Beta" in prop.rationale
    assert prop.suggested_title == "Follow up with Beta"


def test_request_classification_proposal_rejects_bad_project_id() -> None:
    cfg = _sample_config()

    def fake_complete(**_kwargs: object) -> str:
        return json.dumps(
            {
                "project_id": "nope",
                "rationale": "x",
            }
        )

    task = Task(id=1, title="t", status=TaskStatus.PENDING, project_id="")
    ref = MessageRef(id=1, task_id=1, msg_path="m.msg")

    with pytest.raises(ClassificationError, match="unknown project_id"):
        request_classification_proposal(
            config=cfg,
            task=task,
            ref=ref,
            api_key="k",
            complete=fake_complete,
        )


def test_apply_confirmed_proposal_updates_task(tmp_path: Path) -> None:
    db_file = tmp_path / "t.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        row = tasks.create(
            title="Old",
            status=TaskStatus.PENDING,
            notes="Imported.",
            project_id="",
        )
        assert row.id is not None
        proposal = ClassificationProposal(
            project_id="p1",
            rationale="Because.",
            suggested_title="New title",
        )
        updated = apply_confirmed_proposal(
            tasks=tasks,
            task_id=row.id,
            proposal=proposal,
        )
        assert updated.status == TaskStatus.ACTIVE
        assert updated.project_id == "p1"
        assert updated.title == "New title"
        assert "Classifier rationale: Because." in (updated.notes or "")
        assert "Imported." in (updated.notes or "")
    finally:
        session.close()
        engine.dispose()


def test_load_task_primary_ref_requires_message(tmp_path: Path) -> None:
    db_file = tmp_path / "t.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        row = tasks.create(title="t", status=TaskStatus.PENDING)
        assert row.id is not None
        with pytest.raises(ClassificationError, match="no linked"):
            load_task_primary_ref(tasks=tasks, refs=refs, task_id=row.id)
    finally:
        session.close()
        engine.dispose()
