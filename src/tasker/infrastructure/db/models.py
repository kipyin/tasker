"""SQLModel table definitions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from tasker.domain.enums import TaskStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    status: TaskStatus = Field(default=TaskStatus.DRAFT)
    project_id: str = ""
    notes: str | None = None
    attachment_routes_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class MessageRef(SQLModel, table=True):
    """Pointer to a `.msg` on disk for a task, plus parsed snapshot fields."""

    __tablename__ = "message_refs"

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", nullable=False)
    msg_path: str
    subject: str | None = None
    sender: str | None = None
    recipients_to: str | None = None
    recipients_cc: str | None = None
    recipients_bcc: str | None = None
    body_text: str | None = None
    attachment_names_json: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
