"""Persistence helpers for `MessageRef` rows."""

from __future__ import annotations

from sqlmodel import Session, select

from tasker.infrastructure.db.models import MessageRef


class MessageRefRepository:
    """CRUD-style access to message references."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        task_id: int,
        msg_path: str,
        outlook_entry_id: str | None = None,
        outlook_store_id: str | None = None,
        subject: str | None = None,
        sender: str | None = None,
        recipients_to: str | None = None,
        recipients_cc: str | None = None,
        recipients_bcc: str | None = None,
        body_text: str | None = None,
        attachment_names_json: str | None = None,
    ) -> MessageRef:
        row = MessageRef(
            task_id=task_id,
            msg_path=msg_path,
            outlook_entry_id=outlook_entry_id,
            outlook_store_id=outlook_store_id,
            subject=subject,
            sender=sender,
            recipients_to=recipients_to,
            recipients_cc=recipients_cc,
            recipients_bcc=recipients_bcc,
            body_text=body_text,
            attachment_names_json=attachment_names_json,
        )
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_for_task(self, task_id: int) -> list[MessageRef]:
        stmt = (
            select(MessageRef)
            .where(MessageRef.task_id == task_id)
            .order_by(MessageRef.created_at.asc())
        )
        return list(self._session.exec(stmt).all())

    def delete(self, ref_id: int) -> bool:
        row = self._session.get(MessageRef, ref_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True
