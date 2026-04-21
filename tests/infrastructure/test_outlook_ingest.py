"""Outlook COM snapshot ingest (no `.msg` file)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlmodel import Session

from tasker.domain.enums import TaskStatus
from tasker.domain.exceptions import OutlookNotAvailableError
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.db import init_db, make_sqlite_engine
from tasker.infrastructure.outlook.mail_item import fetch_parsed_msg_from_outlook
from tasker.infrastructure.outlook.paths import outlook_com_msg_path
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_outlook_entry, ingest_outlook_snapshot


def test_outlook_com_msg_path() -> None:
    assert outlook_com_msg_path("abc").startswith("outlook-com:")
    assert "abc" in outlook_com_msg_path("abc")


def test_ingest_outlook_snapshot_persists_ref(tmp_path) -> None:
    db_file = tmp_path / "t.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        parsed = ParsedMsg(
            sender="a@x.com",
            recipients_to="b@y.com",
            recipients_cc="",
            recipients_bcc="",
            subject="Hi",
            body_text="Body",
            attachment_names=("f.txt",),
        )
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task, ref = ingest_outlook_snapshot(
            parsed=parsed,
            entry_id="entry-1",
            store_id="store-9",
            tasks=tasks,
            refs=refs,
        )
        assert task.status == TaskStatus.PENDING
        assert ref.msg_path == outlook_com_msg_path("entry-1")
        assert ref.outlook_entry_id == "entry-1"
        assert ref.outlook_store_id == "store-9"
        assert ref.subject == "Hi"
        assert json.loads(ref.attachment_names_json or "[]") == ["f.txt"]
    finally:
        session.close()
        engine.dispose()


def test_ingest_outlook_entry_uses_fetch_inject(tmp_path) -> None:
    db_file = tmp_path / "t.db"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        parsed = ParsedMsg(
            sender="s",
            recipients_to="t",
            recipients_cc="",
            recipients_bcc="",
            subject="S",
            body_text="",
            attachment_names=(),
        )

        def fetch(_eid: str, _sid: str | None) -> ParsedMsg:
            return parsed

        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task, ref = ingest_outlook_entry(
            entry_id="e2",
            store_id=None,
            tasks=tasks,
            refs=refs,
            _fetch_parsed=fetch,
        )
        assert ref.outlook_entry_id == "e2"
        assert ref.outlook_store_id is None
        assert task.title == "S"
    finally:
        session.close()
        engine.dispose()


def test_fetch_parsed_msg_from_outlook_non_windows_raises() -> None:
    with patch(
        "tasker.infrastructure.outlook.mail_item.sys.platform",
        "linux",
    ):
        with pytest.raises(OutlookNotAvailableError):
            fetch_parsed_msg_from_outlook("id", None)
