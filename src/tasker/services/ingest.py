"""Ingest `.msg` files or live Outlook items into pending tasks (no AI, no moves)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tasker.domain.enums import TaskStatus
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.msg import attachment_names_to_json, parse_msg_file
from tasker.infrastructure.outlook.mail_item import fetch_parsed_msg_from_outlook
from tasker.infrastructure.outlook.paths import outlook_com_msg_path
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository

_MAX_TITLE_LEN = 512


def _task_title(parsed: ParsedMsg, path: Path) -> str:
    if parsed.subject:
        return parsed.subject[:_MAX_TITLE_LEN]
    return path.name[:_MAX_TITLE_LEN]


def _task_title_outlook(parsed: ParsedMsg, entry_id: str) -> str:
    if parsed.subject:
        return parsed.subject[:_MAX_TITLE_LEN]
    tail = entry_id.strip()[-24:] if entry_id.strip() else ""
    fb = f"Outlook message {tail}" if tail else "Outlook message"
    return fb[:_MAX_TITLE_LEN]


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


def ingest_outlook_snapshot(
    *,
    parsed: ParsedMsg,
    entry_id: str,
    store_id: str | None,
    tasks: TaskRepository,
    refs: MessageRefRepository,
) -> tuple[Task, MessageRef]:
    """
    Persist a pending task + ref from an already-fetched Outlook snapshot.

    Used when COM runs off the UI thread and DB work must stay on the main thread.
    """
    eid = entry_id.strip()
    if not eid:
        msg = "entry_id must be non-empty"
        raise ValueError(msg)
    task = tasks.create(
        title=_task_title_outlook(parsed, eid),
        status=TaskStatus.PENDING,
        notes="Imported from Outlook (COM); awaiting confirmation.",
    )
    assert task.id is not None
    ref = refs.create(
        task_id=task.id,
        msg_path=outlook_com_msg_path(eid),
        outlook_entry_id=eid,
        outlook_store_id=(store_id.strip() if (store_id or "").strip() else None),
        subject=parsed.subject or None,
        sender=parsed.sender or None,
        recipients_to=parsed.recipients_to or None,
        recipients_cc=parsed.recipients_cc or None,
        recipients_bcc=parsed.recipients_bcc or None,
        body_text=parsed.body_text or None,
        attachment_names_json=attachment_names_to_json(parsed.attachment_names),
    )
    return task, ref


def ingest_outlook_entry(
    *,
    entry_id: str,
    store_id: str | None,
    tasks: TaskRepository,
    refs: MessageRefRepository,
    _fetch_parsed: Callable[[str, str | None], ParsedMsg] | None = None,
) -> tuple[Task, MessageRef]:
    """
    Read a mail item via Outlook COM, create a **pending** task, and persist a ref.

    Does not write a ``.msg`` file. ``_fetch_parsed`` is for tests.
    """
    parsed = (
        _fetch_parsed(entry_id, store_id)
        if _fetch_parsed is not None
        else fetch_parsed_msg_from_outlook(entry_id, store_id)
    )
    return ingest_outlook_snapshot(
        parsed=parsed,
        entry_id=entry_id,
        store_id=store_id,
        tasks=tasks,
        refs=refs,
    )
