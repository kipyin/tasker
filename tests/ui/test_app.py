"""Tests for Tasker Textual app behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import ContentSwitcher, Input, Select, TextArea

from tasker.domain.enums import TaskStatus
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.config.store import load_config
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.paths import config_path
from tasker.ui.app import TaskerApp
from tasker.ui.screens.projects import ProjectEditorModal
from tasker.ui.screens.tasks import (
    ConfirmDeleteTaskModal,
    TaskEditorModal,
    TasksScreen,
    TaskViewModal,
)


def test_reload_tasks_updates_empty_state_without_markup_kwarg() -> None:
    """Empty-state rendering should pass plain content to `Static.update`."""
    table = MagicMock()
    detail = MagicMock()
    screen = TasksScreen(config=AppConfig())
    screen._tasks_repo = MagicMock()
    screen._refs_repo = MagicMock()
    screen._tasks_repo.list_all.return_value = []

    def fake_query_one(selector: str, _widget_cls: object) -> object:
        if selector == "#task-table":
            return table
        if selector == "#detail-body":
            return detail
        msg = f"Unexpected selector: {selector}"
        raise AssertionError(msg)

    screen.query_one = fake_query_one  # type: ignore[method-assign]

    screen._reload_tasks(focus_table=True)

    empty = "No tasks yet. Add one with New or use `tasker mail ingest`."
    detail.update.assert_called_once_with(empty)


def test_navigation_switches_sections_via_nav_bar_and_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Nav bar and keys 1–5 move the content switcher between sections."""

    monkeypatch.setenv("APPDATA", str(tmp_path))

    async def _run() -> None:
        _, config, engine = prepare_local_storage()
        try:
            tui = TaskerApp(config=config, engine=engine)
            async with tui.run_test() as pilot:
                # Avoid `pilot.pause()` — the app may never become fully idle; a short
                # sleep is enough for mount + first paint.
                await asyncio.sleep(0.05)
                switcher = pilot.app.query_one("#content-switcher", ContentSwitcher)
                assert switcher.current == "tasks"

                await pilot.click("#nav-projects")
                assert switcher.current == "projects"

                await pilot.click("#nav-config")
                assert switcher.current == "config"

                await pilot.click("#nav-ingest")
                assert switcher.current == "ingest"

                await pilot.click("#nav-outlook")
                assert switcher.current == "outlook-inbox"

                await pilot.click("#nav-tasks")
                assert switcher.current == "tasks"

                await pilot.press("2")
                assert switcher.current == "projects"

                await pilot.press("5")
                assert switcher.current == "outlook-inbox"

                await pilot.press("1")
                assert switcher.current == "tasks"
        finally:
            engine.dispose()

    asyncio.run(_run())


def test_configuration_save_persists_and_updates_app_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Config screen save writes TOML and refreshes the app's in-memory config."""

    monkeypatch.setenv("APPDATA", str(tmp_path))

    async def _run() -> None:
        _, _config, engine = prepare_local_storage()
        try:
            tui = TaskerApp(config=_config, engine=engine)
            async with tui.run_test(size=(100, 50)) as pilot:
                await asyncio.sleep(0.05)
                await pilot.click("#nav-config")
                await asyncio.sleep(0.05)
                pilot.app.query_one("#cfg-base-url", Input).value = (
                    "https://example.invalid/v1"
                )
                pilot.app.query_one("#cfg-model", Input).value = "custom-model"
                pilot.app.query_one("#cfg-api-key", Input).value = "MY_LLM_KEY"
                await pilot.click("#cfg-save")
                await asyncio.sleep(0.1)
                assert pilot.app._config.ai.base_url == "https://example.invalid/v1"
                assert pilot.app._config.ai.model == "custom-model"
                assert pilot.app._config.ai.api_key == "MY_LLM_KEY"
                tasks = pilot.app.query_one("#tasks", TasksScreen)
                assert tasks._config.ai.api_key == "MY_LLM_KEY"
        finally:
            engine.dispose()

    asyncio.run(_run())

    path = config_path()
    assert path is not None
    disk = load_config(path)
    assert disk.ai.base_url == "https://example.invalid/v1"
    assert disk.ai.model == "custom-model"
    assert disk.ai.api_key == "MY_LLM_KEY"


def test_projects_add_persists_and_updates_app_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Projects screen add opens the editor, saves TOML, and refreshes app config."""

    monkeypatch.setenv("APPDATA", str(tmp_path))

    async def _run() -> None:
        _, _config, engine = prepare_local_storage()
        try:
            tui = TaskerApp(config=_config, engine=engine)
            async with tui.run_test(size=(100, 50)) as pilot:
                await asyncio.sleep(0.05)
                await pilot.click("#nav-projects")
                await asyncio.sleep(0.05)
                await pilot.click("#proj-add")
                await pilot.pause()
                editor = pilot.app.screen
                assert isinstance(editor, ProjectEditorModal)
                editor.query_one("#pe-id", Input).value = "p-ui"
                editor.query_one("#pe-name", Input).value = "UI Project"
                editor.query_one("#pe-root", Input).value = str(tmp_path / "work")
                editor.query_one("#pe-buckets", TextArea).text = ""
                editor.query_one("#pe-rules", TextArea).text = ""
                await pilot.click("#pe-save")
                await asyncio.sleep(0.15)
                assert any(p.id == "p-ui" for p in pilot.app._config.projects)
                tasks = pilot.app.query_one("#tasks", TasksScreen)
                assert any(p.id == "p-ui" for p in tasks._config.projects)
        finally:
            engine.dispose()

    asyncio.run(_run())

    path = config_path()
    assert path is not None
    disk = load_config(path)
    assert any(p.id == "p-ui" for p in disk.projects)


def test_ingest_screen_run_creates_pending_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ingest screen runs ingest_msg_path and refreshes the tasks list."""

    monkeypatch.setenv("APPDATA", str(tmp_path))
    msg_file = tmp_path / "mail.msg"
    msg_file.write_bytes(b"placeholder")

    parsed = ParsedMsg(
        sender="s@x.com",
        recipients_to="t@y.com",
        recipients_cc="",
        recipients_bcc="",
        subject="Ingested subject",
        body_text="Hi",
        attachment_names=("x.txt",),
    )

    async def _run() -> None:
        _, _config, engine = prepare_local_storage()
        try:
            tui = TaskerApp(config=_config, engine=engine)
            async with tui.run_test(size=(100, 50)) as pilot:
                await asyncio.sleep(0.05)
                await pilot.click("#nav-ingest")
                await asyncio.sleep(0.05)
                with patch(
                    "tasker.services.ingest.parse_msg_file",
                    return_value=parsed,
                ):
                    pilot.app.query_one("#ingest-path", Input).value = str(msg_file)
                    await pilot.click("#ingest-run")
                    await asyncio.sleep(0.15)
                rows = tui._tasks_repo.list_all()
                assert len(rows) == 1
                assert rows[0].status == TaskStatus.PENDING
                assert "Ingested subject" in rows[0].title
        finally:
            engine.dispose()

    asyncio.run(_run())


def test_tasks_screen_new_edit_delete_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Tasks screen can create, update, and delete rows via modals."""

    monkeypatch.setenv("APPDATA", str(tmp_path))

    async def _run() -> None:
        _, _config, engine = prepare_local_storage()
        try:
            tui = TaskerApp(config=_config, engine=engine)
            async with tui.run_test(size=(100, 50)) as pilot:
                await asyncio.sleep(0.05)
                await pilot.click("#btn-task-new")
                await pilot.pause()
                editor = pilot.app.screen
                assert isinstance(editor, TaskEditorModal)
                editor.query_one("#te-title", Input).value = "TUI Task"
                editor.query_one("#te-status", Select).value = TaskStatus.ACTIVE.value
                editor.query_one("#te-notes", TextArea).text = "hello"
                await pilot.click("#te-save")
                await asyncio.sleep(0.15)
                rows = tui._tasks_repo.list_all()
                assert len(rows) == 1
                assert rows[0].title == "TUI Task"
                assert rows[0].status == TaskStatus.ACTIVE
                assert rows[0].notes == "hello"

                await pilot.click("#btn-task-view")
                await pilot.pause()
                view = pilot.app.screen
                assert isinstance(view, TaskViewModal)
                await pilot.click("#task-view-close")
                await asyncio.sleep(0.05)

                await pilot.click("#btn-task-edit")
                await pilot.pause()
                editor2 = pilot.app.screen
                assert isinstance(editor2, TaskEditorModal)
                editor2.query_one("#te-title", Input).value = "Updated"
                await pilot.click("#te-save")
                await asyncio.sleep(0.15)
                rows2 = tui._tasks_repo.list_all()
                assert len(rows2) == 1
                assert rows2[0].title == "Updated"

                await pilot.click("#btn-task-delete")
                await pilot.pause()
                confirm = pilot.app.screen
                assert isinstance(confirm, ConfirmDeleteTaskModal)
                await pilot.click("#confirm-task-yes")
                await asyncio.sleep(0.15)
                assert tui._tasks_repo.list_all() == []
        finally:
            engine.dispose()

    asyncio.run(_run())
