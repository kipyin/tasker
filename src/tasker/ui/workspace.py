"""Resolve filesystem locations for TUI actions (project root vs. email folder)."""

from __future__ import annotations

from pathlib import Path

from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.db.models import MessageRef, Task


def resolve_working_folder(
    config: AppConfig,
    task: Task,
    ref: MessageRef | None,
) -> Path | None:
    """
    Prefer the configured project working root when the task has a matching `project_id`
    and that root exists; otherwise use the parent directory of the linked `.msg`.
    """
    if task.project_id:
        for p in config.projects:
            if p.id == task.project_id:
                root = Path(p.root).expanduser()
                if root.is_dir():
                    return root.resolve()
                break
    if ref is not None:
        parent = Path(ref.msg_path).expanduser().parent
        if parent.is_dir():
            return parent.resolve()
    return None
