"""Textual TUI."""

from __future__ import annotations

__all__ = ["TaskerApp", "run_tui"]


def __getattr__(name: str):
    if name == "TaskerApp":
        from tasker.ui.app import TaskerApp

        return TaskerApp
    if name == "run_tui":
        from tasker.ui.app import run_tui

        return run_tui
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
