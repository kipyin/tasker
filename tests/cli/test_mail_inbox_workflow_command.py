"""`tasker mail inbox-workflow` interactive command."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlmodel import Session
from typer.testing import CliRunner

from tasker.cli import app
from tasker.domain.classification import ClassificationProposal
from tasker.domain.enums import TaskStatus
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.infrastructure.outlook import InboxMessageSummary
from tasker.infrastructure.repositories import TaskRepository
from tasker.paths import CONFIG_FILENAME, tasker_home


def _fake_messages() -> list[InboxMessageSummary]:
    dt = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    return [
        InboxMessageSummary(
            entry_id="e1",
            subject="Hello",
            received=dt,
            sender_display="Alice",
            unread=True,
        ),
        InboxMessageSummary(
            entry_id="e2",
            subject="Other",
            received=dt,
            sender_display="Bob",
            unread=False,
        ),
    ]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_inbox_workflow_creates_task_and_classifies_with_yes(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    home = tasker_home()
    assert home is not None
    home.mkdir(parents=True, exist_ok=True)
    (home / CONFIG_FILENAME).write_text(
        "\n".join(
            [
                "version = 1",
                (
                    'ai = { base_url = "https://x/v1", model = "m", '
                    'api_key = "k" }'
                ),
                "[[projects]]",
                'id = "p1"',
                'name = "P"',
                'root = "C:/r"',
            ]
        ),
        encoding="utf-8",
    )

    msgs = _fake_messages()

    def fake_list(limit: int) -> list[InboxMessageSummary]:
        return msgs[:limit]

    def fake_ingest(**kwargs: object) -> tuple[object, object]:
        entry_id = kwargs["entry_id"]
        tasks = kwargs["tasks"]
        refs = kwargs["refs"]
        task = tasks.create(
            title=f"T-{entry_id}",
            status=TaskStatus.PENDING,
            project_id="",
        )
        assert task.id is not None
        ref = refs.create(
            task_id=int(task.id),
            msg_path=f"outlook:{entry_id}",
            subject="S",
        )
        return task, ref

    def fake_proposal(**_kwargs: object) -> ClassificationProposal:
        return ClassificationProposal(
            project_id="p1",
            rationale="ok",
            suggested_title=None,
        )

    with (
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.list_recent_inbox",
            side_effect=fake_list,
        ),
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.questionary.select",
            return_value=type(
                "_Sel",
                (),
                {
                    "ask": staticmethod(lambda: msgs[0]),
                },
            )(),
        ),
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.ingest_outlook_entry",
            side_effect=fake_ingest,
        ),
        patch(
            "tasker.cli.classify_flow.request_classification_proposal",
            side_effect=fake_proposal,
        ),
    ):
        r = runner.invoke(
            app,
            ["mail", "inbox-workflow", "--limit", "5", "--yes"],
            env={"APPDATA": str(tmp_path)},
        )

    assert r.exit_code == 0
    assert "Created pending task" in r.stdout
    assert "AI classification proposal" in r.stdout
    assert "Updated task" in r.stdout

    _, _, engine = prepare_local_storage()
    session = Session(engine)
    try:
        tasks = TaskRepository(session)
        rows = tasks.list_all()
        assert len(rows) == 1
        assert rows[0].status == TaskStatus.ACTIVE
        assert rows[0].project_id == "p1"
    finally:
        session.close()
        engine.dispose()


def test_inbox_workflow_cancel_at_select(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    home = tasker_home()
    assert home is not None
    home.mkdir(parents=True, exist_ok=True)
    (home / CONFIG_FILENAME).write_text("version = 1\n", encoding="utf-8")

    msgs = _fake_messages()

    with (
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.list_recent_inbox",
            return_value=msgs,
        ),
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.questionary.select",
            return_value=type(
                "_Sel",
                (),
                {"ask": staticmethod(lambda: None)},
            )(),
        ),
    ):
        r = runner.invoke(
            app,
            ["mail", "inbox-workflow"],
            env={"APPDATA": str(tmp_path)},
        )

    assert r.exit_code == 0
    assert "Cancelled" in r.stdout

    _, _, engine = prepare_local_storage()
    session = Session(engine)
    try:
        assert TaskRepository(session).list_all() == []
    finally:
        session.close()
        engine.dispose()


def test_inbox_workflow_stale_pick_after_relist(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    home = tasker_home()
    assert home is not None
    home.mkdir(parents=True, exist_ok=True)
    (home / CONFIG_FILENAME).write_text("version = 1\n", encoding="utf-8")

    gone = InboxMessageSummary(
        entry_id="gone-id",
        subject="X",
        received=datetime(2026, 1, 1, tzinfo=UTC),
        sender_display="Z",
        unread=False,
    )

    call_count = 0

    def fake_list(_limit: int) -> list[InboxMessageSummary]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [gone]
        return []

    with (
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.list_recent_inbox",
            side_effect=fake_list,
        ),
        patch(
            "tasker.cli.mail_inbox_workflow_cmd.questionary.select",
            return_value=type(
                "_Sel",
                (),
                {"ask": staticmethod(lambda: gone)},
            )(),
        ),
    ):
        r = runner.invoke(
            app,
            ["mail", "inbox-workflow"],
            env={"APPDATA": str(tmp_path)},
        )

    assert r.exit_code == 1
    assert "no longer" in r.stdout.lower()
