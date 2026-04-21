"""Tests for Tasker Textual app behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.db import make_sqlite_engine
from tasker.ui.app import TaskerApp


def test_reload_tasks_updates_empty_state_without_markup_kwarg() -> None:
    """Empty-state rendering should pass plain content to `Static.update`."""
    engine = make_sqlite_engine(":memory:")
    app = TaskerApp(config=AppConfig(), engine=engine)
    table = MagicMock()
    detail = MagicMock()
    app._tasks_repo = MagicMock()
    app._refs_repo = MagicMock()
    app._tasks_repo.list_all.return_value = []

    def fake_query_one(selector: str, _widget_cls: object) -> object:
        if selector == "#task-table":
            return table
        if selector == "#detail-body":
            return detail
        msg = f"Unexpected selector: {selector}"
        raise AssertionError(msg)

    app.query_one = fake_query_one  # type: ignore[method-assign]

    app._reload_tasks(focus_table=True)

    detail.update.assert_called_once_with("No tasks yet. Use `tasker ingest` to add one.")
