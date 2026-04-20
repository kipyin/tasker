"""TUI helpers: workspace resolution and opening paths with the OS handler."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import tasker.ui.open_external as open_external_mod
from tasker.infrastructure.config.schema import AppConfig, ProjectConfig
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.ui.open_external import open_path_with_default_handler
from tasker.ui.workspace import resolve_working_folder


def test_resolve_working_folder_uses_project_root(tmp_path: Path) -> None:
    root = tmp_path / "proj_root"
    root.mkdir()
    cfg = AppConfig(
        projects=[
            ProjectConfig(id="p1", name="One", root=str(root)),
        ],
    )
    task = Task(title="t", project_id="p1")
    ref = MessageRef(task_id=1, msg_path=str(tmp_path / "a.msg"))
    assert resolve_working_folder(cfg, task, ref) == root.resolve()


def test_resolve_working_folder_falls_back_to_msg_parent(tmp_path: Path) -> None:
    cfg = AppConfig(projects=[])
    msg = tmp_path / "mail.msg"
    msg.write_text("x", encoding="utf-8")
    task = Task(title="t", project_id="")
    ref = MessageRef(task_id=1, msg_path=str(msg))
    assert resolve_working_folder(cfg, task, ref) == tmp_path.resolve()


def test_resolve_working_folder_unknown_project_uses_msg_parent(tmp_path: Path) -> None:
    msg = tmp_path / "mail.msg"
    msg.write_text("x", encoding="utf-8")
    cfg = AppConfig(projects=[])
    task = Task(title="t", project_id="missing")
    ref = MessageRef(task_id=1, msg_path=str(msg))
    assert resolve_working_folder(cfg, task, ref) == tmp_path.resolve()


def test_open_path_raises_when_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError):
        open_path_with_default_handler(missing)


def test_open_path_calls_startfile_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "f.txt"
    path.write_text("hi", encoding="utf-8")
    mock_start = MagicMock()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(open_external_mod.os, "startfile", mock_start)
    open_path_with_default_handler(path)
    mock_start.assert_called_once()
    called_path = mock_start.call_args[0][0]
    assert Path(called_path) == path.expanduser()
