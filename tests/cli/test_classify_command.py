"""Typer `classify` command (preview / dry-run behavior)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session
from typer.testing import CliRunner

from tasker.cli import app
from tasker.domain.classification import ClassificationProposal
from tasker.domain.enums import TaskStatus
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.paths import CONFIG_FILENAME, tasker_home


def test_classify_cli_dry_run_runs_without_questionary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`classify --dry-run` does not prompt or call the network."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("TASKER_TEST_KEY", "k")

    home = tasker_home()
    assert home is not None
    home.mkdir(parents=True, exist_ok=True)
    (home / CONFIG_FILENAME).write_text(
        "\n".join(
            [
                "version = 1",
                (
                    'ai = { base_url = "https://x/v1", model = "m", '
                    'api_key_env = "TASKER_TEST_KEY" }'
                ),
                "[[projects]]",
                'id = "p1"',
                'name = "P"',
                'root = "C:/r"',
            ]
        ),
        encoding="utf-8",
    )

    _, _, engine = prepare_local_storage()
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task = tasks.create(title="Hi", status=TaskStatus.PENDING, project_id="")
        assert task.id is not None
        tid = int(task.id)
        refs.create(task_id=tid, msg_path="C:/m.msg", subject="S")
    finally:
        session.close()
        engine.dispose()

    def fake_proposal(**_kwargs: object) -> ClassificationProposal:
        return ClassificationProposal(
            project_id="p1",
            rationale="ok",
            suggested_title=None,
        )

    runner = CliRunner()
    with patch(
        "tasker.cli.classify_cmd.request_classification_proposal",
        side_effect=fake_proposal,
    ):
        result = runner.invoke(
            app,
            ["classify", str(tid), "--dry-run"],
            env={"APPDATA": str(tmp_path), "TASKER_TEST_KEY": "k"},
        )

    assert result.exit_code == 0
    assert "Dry run" in result.stdout

    _, _, engine2 = prepare_local_storage()
    session2 = Session(engine2)
    try:
        tasks2 = TaskRepository(session2)
        unchanged = tasks2.get(tid)
        assert unchanged is not None
        assert unchanged.status == TaskStatus.PENDING
    finally:
        session2.close()
        engine2.dispose()
