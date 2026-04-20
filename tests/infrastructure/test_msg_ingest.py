""".msg parsing, message ref snapshot columns, and pending-task ingest."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import inspect
from sqlmodel import Session

from tasker.domain.enums import TaskStatus
from tasker.domain.exceptions import MsgIngestError
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.db import init_db, make_sqlite_engine
from tasker.infrastructure.msg.parser import (
    attachment_names_to_json,
    parse_msg_file,
)
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_msg_path


def test_parse_msg_file_missing_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nope.msg"
    with pytest.raises(MsgIngestError, match="File not found"):
        parse_msg_file(missing)


def test_parse_msg_file_rejects_non_msg_content(tmp_path: Path) -> None:
    bad = tmp_path / "fake.msg"
    bad.write_text("not an ole file", encoding="utf-8")
    with pytest.raises(MsgIngestError):
        parse_msg_file(bad)


def test_parse_msg_file_success(tmp_path: Path) -> None:
    msg_file = tmp_path / "sample.msg"
    msg_file.write_bytes(b"x")

    mock_msg = MagicMock()
    mock_msg.sender = "a@x.com"
    mock_msg.to = "b@y.com"
    mock_msg.cc = ""
    mock_msg.bcc = ""
    mock_msg.subject = "Hello"
    mock_msg.body = "Body text"
    att = MagicMock()
    att.name = "file.pdf"
    mock_msg.attachments = [att]

    with patch("tasker.infrastructure.msg.parser.openMsg") as open_msg:
        open_msg.return_value.__enter__.return_value = mock_msg
        open_msg.return_value.__exit__.return_value = None

        parsed = parse_msg_file(msg_file)

    assert parsed.sender == "a@x.com"
    assert parsed.recipients_to == "b@y.com"
    assert parsed.subject == "Hello"
    assert parsed.body_text == "Body text"
    assert parsed.attachment_names == ("file.pdf",)


def test_attachment_names_to_json() -> None:
    assert attachment_names_to_json(()) is None
    assert json.loads(attachment_names_to_json(("a", "b")) or "[]") == ["a", "b"]


def test_ingest_msg_path_persists_task_and_ref(tmp_path: Path) -> None:
    db_file = tmp_path / "t.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        parsed = ParsedMsg(
            sender="s@x.com",
            recipients_to="t@y.com",
            recipients_cc="",
            recipients_bcc="",
            subject="Subj",
            body_text="Hi",
            attachment_names=("x.txt",),
        )
        msg_path = tmp_path / "mail.msg"
        msg_path.write_bytes(b"placeholder")

        with patch("tasker.services.ingest.parse_msg_file", return_value=parsed):
            tasks = TaskRepository(session)
            refs = MessageRefRepository(session)
            task, ref = ingest_msg_path(
                path=msg_path,
                tasks=tasks,
                refs=refs,
            )

        assert task.status == TaskStatus.PENDING
        assert "awaiting confirmation" in (task.notes or "")
        assert ref.msg_path == str(msg_path.resolve())
        assert ref.subject == "Subj"
        assert ref.sender == "s@x.com"
        assert ref.body_text == "Hi"
        assert json.loads(ref.attachment_names_json or "[]") == ["x.txt"]
    finally:
        session.close()
        engine.dispose()


def test_init_db_migrates_message_refs_columns(tmp_path: Path) -> None:
    """Legacy DBs missing message_refs columns get ALTER TABLE via init_db."""
    from sqlalchemy import text

    db_file = tmp_path / "legacy.db"
    engine = make_sqlite_engine(str(db_file))
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE message_refs ("
                "id INTEGER PRIMARY KEY, "
                "task_id INTEGER NOT NULL, "
                "msg_path TEXT NOT NULL, "
                "created_at TEXT NOT NULL"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE tasks ("
                "id INTEGER PRIMARY KEY, "
                "title TEXT NOT NULL, "
                "status TEXT NOT NULL, "
                "project_id TEXT NOT NULL, "
                "notes TEXT, "
                "created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL"
                ")"
            )
        )

    init_db(engine)
    insp = inspect(engine)
    col_names = {c["name"] for c in insp.get_columns("message_refs")}
    assert "subject" in col_names
    assert "attachment_names_json" in col_names
    engine.dispose()
