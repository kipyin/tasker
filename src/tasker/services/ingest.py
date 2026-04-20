"""Ingest `.msg` files into pending tasks (no AI, no attachment moves)."""

from __future__ import annotations

from pathlib import Path

from tasker.domain.enums import TaskStatus
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.msg import attachment_names_to_json, parse_msg_file
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository

_MAX_TITLE_LEN = 512


def _task_title(parsed: ParsedMsg, path: Path) -> str:
    if parsed.subject:
        return parsed.subject[:_MAX_TITLE_LEN]
    return path.name[:_MAX_TITLE_LEN]


def ingest_msg_path(
    *,
    path: Path,
    tasks: TaskRepository,
    refs: MessageRefRepository,
) -> tuple[Task, MessageRef]:
    """
    Parse a `.msg` file, create a **pending** task, and persist a message ref snapshot.

    Attachment files are not moved; only names are recorded.
    """
    parsed = parse_msg_file(path)
    resolved = path.expanduser().resolve(strict=False)
    msg_path = str(resolved)
    task = tasks.create(
        title=_task_title(parsed, resolved),
        status=TaskStatus.PENDING,
        notes="Imported from .msg; awaiting confirmation.",
    )
    assert task.id is not None
    ref = refs.create(
        task_id=task.id,
        msg_path=msg_path,
        subject=parsed.subject or None,
        sender=parsed.sender or None,
        recipients_to=parsed.recipients_to or None,
        recipients_cc=parsed.recipients_cc or None,
        recipients_bcc=parsed.recipients_bcc or None,
        body_text=parsed.body_text or None,
        attachment_names_json=attachment_names_to_json(parsed.attachment_names),
    )
    return task, ref
