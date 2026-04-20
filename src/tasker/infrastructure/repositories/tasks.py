"""Persistence helpers for `Task` rows."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from tasker.domain.enums import TaskStatus
from tasker.infrastructure.db.models import MessageRef, Task


def _utc_now() -> datetime:
    return datetime.now(UTC)


class TaskRepository:
    """CRUD-style access to tasks stored in SQLite."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        title: str,
        project_id: str = "",
        status: TaskStatus = TaskStatus.DRAFT,
        notes: str | None = None,
    ) -> Task:
        now = _utc_now()
        row = Task(
            title=title,
            status=status,
            project_id=project_id,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def get(self, task_id: int) -> Task | None:
        return self._session.get(Task, task_id)

    def list_all(self) -> list[Task]:
        stmt = select(Task).order_by(Task.created_at.desc())
        return list(self._session.exec(stmt).all())

    def update(
        self,
        task_id: int,
        *,
        title: str | None = None,
        status: TaskStatus | None = None,
        project_id: str | None = None,
        notes: str | None = None,
        attachment_routes_json: str | None = None,
    ) -> Task | None:
        row = self.get(task_id)
        if row is None:
            return None
        if title is not None:
            row.title = title
        if status is not None:
            row.status = status
        if project_id is not None:
            row.project_id = project_id
        if notes is not None:
            row.notes = notes
        if attachment_routes_json is not None:
            row.attachment_routes_json = attachment_routes_json
        row.updated_at = _utc_now()
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete(self, task_id: int) -> bool:
        row = self.get(task_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    def delete_cascade(self, task_id: int) -> bool:
        """Delete a task and any `MessageRef` rows pointing at it."""
        row = self.get(task_id)
        if row is None:
            return False
        stmt = select(MessageRef).where(MessageRef.task_id == task_id)
        for ref in self._session.exec(stmt).all():
            self._session.delete(ref)
        self._session.delete(row)
        self._session.commit()
        return True
