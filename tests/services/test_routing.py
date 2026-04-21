"""Attachment bucket routing and related DB migrations."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session

from tasker.domain.exceptions import OutlookCOMError, RoutingError
from tasker.infrastructure.config.schema import (
    AppConfig,
    BucketConfig,
    ProjectConfig,
    RoutingRuleConfig,
)
from tasker.infrastructure.db import init_db, make_sqlite_engine
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.routing import (
    bucket_directory,
    match_bucket,
    route_task_attachments,
)


def _attachment_mock(name: str, data: bytes) -> MagicMock:
    att = MagicMock()
    att.name = name

    def save(**kwargs: object) -> None:
        custom_path = Path(str(kwargs["customPath"]))
        logical = str(kwargs.get("customFilename") or name)
        out = custom_path / logical
        out.write_bytes(data)

    att.save = save
    return att


def _msg_opener_factory(attachments: list[MagicMock]):
    @contextmanager
    def _open(_path: str):
        msg = MagicMock()
        msg.attachments = attachments
        yield msg

    return _open


def test_match_bucket_first_rule_wins() -> None:
    project = ProjectConfig(
        id="p",
        name="P",
        root="/tmp",
        buckets=[
            BucketConfig(name="a", relative_path="a"),
            BucketConfig(name="b", relative_path="b"),
        ],
        rules=[
            RoutingRuleConfig(bucket="a", pattern="*.pdf"),
            RoutingRuleConfig(bucket="b", pattern="*.*"),
        ],
    )
    assert match_bucket("x.pdf", project) == "a"


def test_match_bucket_default() -> None:
    project = ProjectConfig(
        id="p",
        name="P",
        root="/tmp",
        buckets=[BucketConfig(name="inbox", relative_path="in")],
        rules=[],
        default_bucket="inbox",
    )
    assert match_bucket("anything.bin", project) == "inbox"


def test_bucket_directory_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    project = ProjectConfig(
        id="p",
        name="P",
        root=str(root),
        buckets=[BucketConfig(name="evil", relative_path="..\\outside")],
        rules=[],
    )
    with pytest.raises(RoutingError, match="escapes"):
        bucket_directory(project, "evil")


def test_route_task_attachments_moves_files(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "db.sqlite"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        root = tmp_path / "proj"
        (root / "docs").mkdir(parents=True)
        (root / "text").mkdir(parents=True)
        project = ProjectConfig(
            id="alpha",
            name="Alpha",
            root=str(root),
            buckets=[
                BucketConfig(name="docs", relative_path="docs"),
                BucketConfig(name="text", relative_path="text"),
            ],
            rules=[
                RoutingRuleConfig(bucket="docs", pattern="*.pdf"),
                RoutingRuleConfig(bucket="text", pattern="*.txt"),
            ],
        )
        config = AppConfig(projects=[project])

        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        msg_path = tmp_path / "mail.msg"
        msg_path.write_bytes(b"ole-placeholder")
        task = tasks.create(title="t", project_id="alpha")
        assert task.id is not None
        refs.create(
            task_id=task.id,
            msg_path=str(msg_path),
            attachment_names_json=json.dumps(["report.pdf", "notes.txt"]),
        )

        attachments = [
            _attachment_mock("report.pdf", b"%PDF-1"),
            _attachment_mock("notes.txt", b"hello"),
        ]
        records = route_task_attachments(
            home=tmp_path / "TaskerHome",
            config=config,
            tasks=tasks,
            refs=refs,
            task_id=task.id,
            dry_run=False,
            msg_opener=_msg_opener_factory(attachments),
        )

        assert (root / "docs" / "report.pdf").read_bytes() == b"%PDF-1"
        assert (root / "text" / "notes.txt").read_bytes() == b"hello"
        actions = {r.filename: r.action for r in records}
        assert actions["report.pdf"] == "moved"
        assert actions["notes.txt"] == "moved"

        refreshed = tasks.get(task.id)
        assert refreshed is not None
        assert refreshed.attachment_routes_json is not None
        stored = json.loads(refreshed.attachment_routes_json)
        assert len(stored) == 2
    finally:
        session.close()
        engine.dispose()


def test_route_task_attachments_idempotent_second_run(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "db.sqlite"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        root = tmp_path / "proj"
        (root / "docs").mkdir(parents=True)
        project = ProjectConfig(
            id="alpha",
            name="Alpha",
            root=str(root),
            buckets=[BucketConfig(name="docs", relative_path="docs")],
            rules=[RoutingRuleConfig(bucket="docs", pattern="*.pdf")],
        )
        config = AppConfig(projects=[project])
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        msg_path = tmp_path / "mail.msg"
        msg_path.write_bytes(b"x")
        task = tasks.create(title="t", project_id="alpha")
        assert task.id is not None
        refs.create(
            task_id=task.id,
            msg_path=str(msg_path),
            attachment_names_json=json.dumps(["report.pdf"]),
        )
        data = b"same"
        att = _attachment_mock("report.pdf", data)
        opener = _msg_opener_factory([att])

        route_task_attachments(
            home=tmp_path / "h",
            config=config,
            tasks=tasks,
            refs=refs,
            task_id=task.id,
            msg_opener=opener,
        )
        records2 = route_task_attachments(
            home=tmp_path / "h",
            config=config,
            tasks=tasks,
            refs=refs,
            task_id=task.id,
            msg_opener=opener,
        )
        assert records2[0].action == "skipped_identical"
    finally:
        session.close()
        engine.dispose()


class _FakeAttachments:
    def __init__(self, items: list[MagicMock]) -> None:
        self._items = items

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, index: int) -> MagicMock:
        return self._items[index - 1]


def _outlook_attachment_mock(name: str, data: bytes) -> MagicMock:
    att = MagicMock()
    att.FileName = name

    def save_as(path: str) -> None:
        Path(path).write_bytes(data)

    att.SaveAsFile = save_as
    return att


def test_route_task_attachments_outlook_com_backend(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "db.sqlite"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        root = tmp_path / "proj"
        (root / "docs").mkdir(parents=True)
        project = ProjectConfig(
            id="alpha",
            name="Alpha",
            root=str(root),
            buckets=[BucketConfig(name="docs", relative_path="docs")],
            rules=[RoutingRuleConfig(bucket="docs", pattern="*.pdf")],
        )
        config = AppConfig(projects=[project])
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task = tasks.create(title="t", project_id="alpha")
        assert task.id is not None
        refs.create(
            task_id=task.id,
            msg_path="outlook-com:fake-entry",
            outlook_entry_id="fake-entry",
            attachment_names_json=json.dumps(["report.pdf"]),
        )

        att = _outlook_attachment_mock("report.pdf", b"%PDF-1")
        mail_item = MagicMock()
        mail_item.Attachments = _FakeAttachments([att])

        def getter(entry_id: str, store_id: str | None) -> MagicMock:
            assert entry_id == "fake-entry"
            assert store_id is None
            return mail_item

        records = route_task_attachments(
            home=tmp_path / "TaskerHome",
            config=config,
            tasks=tasks,
            refs=refs,
            task_id=task.id,
            dry_run=False,
            outlook_mail_item_getter=getter,
        )
        assert (root / "docs" / "report.pdf").read_bytes() == b"%PDF-1"
        assert records[0].action == "moved"
    finally:
        session.close()
        engine.dispose()


def test_route_task_attachments_outlook_getter_com_error(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "db.sqlite"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        root = tmp_path / "proj"
        (root / "docs").mkdir(parents=True)
        project = ProjectConfig(
            id="alpha",
            name="Alpha",
            root=str(root),
            buckets=[BucketConfig(name="docs", relative_path="docs")],
            rules=[RoutingRuleConfig(bucket="docs", pattern="*.pdf")],
        )
        config = AppConfig(projects=[project])
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        task = tasks.create(title="t", project_id="alpha")
        assert task.id is not None
        refs.create(
            task_id=task.id,
            msg_path="outlook-com:x",
            outlook_entry_id="x",
        )

        def getter(_eid: str, _sid: str | None) -> MagicMock:
            raise OutlookCOMError("gone")

        with pytest.raises(RoutingError, match="Outlook"):
            route_task_attachments(
                home=tmp_path / "h",
                config=config,
                tasks=tasks,
                refs=refs,
                task_id=task.id,
                outlook_mail_item_getter=getter,
            )
    finally:
        session.close()
        engine.dispose()


def test_route_task_attachments_dry_run_no_files(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "db.sqlite"
    engine = make_sqlite_engine(str(db_file))
    init_db(engine)
    session = Session(engine)
    try:
        root = tmp_path / "proj"
        (root / "docs").mkdir(parents=True)
        project = ProjectConfig(
            id="alpha",
            name="Alpha",
            root=str(root),
            buckets=[BucketConfig(name="docs", relative_path="docs")],
            rules=[RoutingRuleConfig(bucket="docs", pattern="*.pdf")],
        )
        config = AppConfig(projects=[project])
        tasks = TaskRepository(session)
        refs = MessageRefRepository(session)
        msg_path = tmp_path / "mail.msg"
        msg_path.write_bytes(b"x")
        task = tasks.create(title="t", project_id="alpha")
        assert task.id is not None
        refs.create(
            task_id=task.id,
            msg_path=str(msg_path),
            attachment_names_json=json.dumps(["report.pdf"]),
        )
        route_task_attachments(
            home=tmp_path / "h",
            config=config,
            tasks=tasks,
            refs=refs,
            task_id=task.id,
            dry_run=True,
            msg_opener=_msg_opener_factory([_attachment_mock("report.pdf", b"a")]),
        )
        assert not (root / "docs" / "report.pdf").is_file()
    finally:
        session.close()
        engine.dispose()


def test_init_db_adds_attachment_routes_column(tmp_path: Path) -> None:
    from sqlalchemy import inspect, text

    db_file = tmp_path / "legacy.db"
    engine = make_sqlite_engine(str(db_file))
    with engine.begin() as conn:
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

    init_db(engine)
    insp = inspect(engine)
    col_names = {c["name"] for c in insp.get_columns("tasks")}
    assert "attachment_routes_json" in col_names
    engine.dispose()
