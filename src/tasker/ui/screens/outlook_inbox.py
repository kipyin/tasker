"""Recent Outlook Inbox listing (Windows COM, optional pywin32)."""

from __future__ import annotations

import sys
import threading
from datetime import datetime

from textual._context import NoActiveAppError
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Static

if sys.platform == "win32":
    try:
        import pythoncom
    except ImportError:
        pythoncom = None  # type: ignore[assignment, misc]
else:
    pythoncom = None  # type: ignore[assignment, misc]

from tasker.domain.exceptions import OutlookCOMError, OutlookNotAvailableError
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.outlook import InboxMessageSummary, list_recent_inbox
from tasker.infrastructure.outlook.mail_item import fetch_parsed_msg_from_outlook
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_outlook_snapshot
from tasker.ui.screens.tasks import TasksScreen


def _fmt_received(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


class OutlookInboxScreen(Container):
    """Show recent Inbox messages via Outlook COM (background thread)."""

    BINDINGS = [
        Binding("i", "ingest_selected", "Ingest"),
    ]

    DEFAULT_CSS = """
    #outlook-scroll {
        height: 1fr;
        padding: 1 2;
    }
    .outlook-heading {
        text-style: bold;
        padding: 0 0 1 0;
    }
    .outlook-help {
        color: $text-muted;
        padding: 0 0 1 0;
    }
    #outlook-status {
        padding: 1 0 0 0;
    }
    #outlook-refresh {
        width: auto;
        margin: 0 0 1 0;
    }
    #outlook-ingest {
        width: auto;
        margin: 0 0 1 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="outlook-inbox")
        self._limit = 20
        self._load_token = 0
        self._ingest_token = 0
        self._last_messages: list[InboxMessageSummary] = []
        self._tasks_repo: TaskRepository | None = None
        self._refs_repo: MessageRefRepository | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="outlook-scroll"):
            yield Static("Outlook Inbox", classes="outlook-heading")
            yield Static(
                "Recent messages from your default Inbox. Press Refresh to load. "
                "Select a row and press Ingest or [b]i[/b] to create a pending task "
                "(no .msg file). Requires Windows with Outlook and "
                "pip install tasker[outlook].",
                classes="outlook-help",
            )
            with Horizontal():
                yield Button("Refresh", variant="primary", id="outlook-refresh")
                yield Button("Ingest selected", variant="success", id="outlook-ingest")
            yield DataTable(
                id="outlook-table",
                cursor_type="row",
                zebra_stripes=True,
            )
            yield Static("", id="outlook-status", markup=False)

    def on_mount(self) -> None:
        table = self.query_one("#outlook-table", DataTable)
        table.add_columns("Received", " ", "From", "Subject")
        app = self.app
        tasks_repo = getattr(app, "_tasks_repo", None)
        refs_repo = getattr(app, "_refs_repo", None)
        assert isinstance(tasks_repo, TaskRepository)
        assert isinstance(refs_repo, MessageRefRepository)
        self._tasks_repo = tasks_repo
        self._refs_repo = refs_repo

    def action_refresh(self) -> None:
        """Reload Inbox from Outlook (used when this section is active)."""
        self._begin_refresh()

    def action_ingest_selected(self) -> None:
        self._begin_ingest_selected()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "outlook-refresh":
            self._begin_refresh()
        elif event.button.id == "outlook-ingest":
            self._begin_ingest_selected()

    def _set_status(self, text: str) -> None:
        self.query_one("#outlook-status", Static).update(text)

    def _begin_refresh(self) -> None:
        self._load_token += 1
        token = self._load_token
        self._set_status("Loading…")
        app = self.app
        if sys.platform != "win32":
            self._fill_blocked(
                token,
                "Outlook COM is only available on Windows.",
            )
            return
        if pythoncom is None:
            self._fill_blocked(
                token,
                "pywin32 is not installed. On Windows: pip install tasker[outlook]",
            )
            return

        def work() -> None:
            assert pythoncom is not None
            pythoncom.CoInitialize()
            try:
                messages = list_recent_inbox(self._limit)
            except (OutlookCOMError, OutlookNotAvailableError, ValueError) as exc:
                try:
                    app.call_from_thread(self._apply_result, token, [], str(exc))
                except (NoActiveAppError, RuntimeError):
                    pass
            except Exception as exc:
                try:
                    app.call_from_thread(self._apply_result, token, [], str(exc))
                except (NoActiveAppError, RuntimeError):
                    pass
            else:
                try:
                    app.call_from_thread(self._apply_result, token, messages, "")
                except (NoActiveAppError, RuntimeError):
                    pass
            finally:
                pythoncom.CoUninitialize()

        threading.Thread(target=work, daemon=True).start()

    def _fill_blocked(self, token: int, message: str) -> None:
        self._apply_result(token, [], message)

    def _apply_result(
        self,
        token: int,
        messages: list[InboxMessageSummary],
        error: str,
    ) -> None:
        if token != self._load_token:
            return
        table = self.query_one("#outlook-table", DataTable)
        table.clear()
        if error:
            self._set_status(error)
            self._last_messages = []
            return
        self._last_messages = list(messages)
        self._set_status(f"{len(messages)} message(s).")
        for m in messages:
            u = "●" if m.unread else " "
            table.add_row(
                _fmt_received(m.received),
                u,
                m.sender_display,
                m.subject,
            )

    def _begin_ingest_selected(self) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        if not self._last_messages:
            self.app.notify("Load messages first (Refresh).", severity="warning")
            return
        table = self.query_one("#outlook-table", DataTable)
        row_i = table.cursor_coordinate.row
        if row_i < 0 or row_i >= len(self._last_messages):
            self.app.notify("Select a message row.", severity="warning")
            return
        message = self._last_messages[row_i]
        if sys.platform != "win32":
            self.app.notify(
                "Outlook COM is only available on Windows.",
                severity="error",
            )
            return
        if pythoncom is None:
            self.app.notify(
                "pywin32 is not installed. On Windows: pip install tasker[outlook]",
                severity="error",
            )
            return

        self._ingest_token += 1
        token = self._ingest_token
        self._set_status("Ingesting…")
        selected_entry_id = message.entry_id
        app = self.app

        def work() -> None:
            assert pythoncom is not None
            pythoncom.CoInitialize()
            try:
                parsed = fetch_parsed_msg_from_outlook(selected_entry_id, None)
            except (OutlookCOMError, OutlookNotAvailableError, ValueError) as exc:
                try:
                    app.call_from_thread(
                        self._apply_ingest_result,
                        token,
                        selected_entry_id,
                        None,
                        str(exc),
                    )
                except (NoActiveAppError, RuntimeError):
                    pass
            except Exception as exc:
                try:
                    app.call_from_thread(
                        self._apply_ingest_result,
                        token,
                        selected_entry_id,
                        None,
                        str(exc),
                    )
                except (NoActiveAppError, RuntimeError):
                    pass
            else:
                try:
                    app.call_from_thread(
                        self._apply_ingest_result,
                        token,
                        selected_entry_id,
                        parsed,
                        "",
                    )
                except (NoActiveAppError, RuntimeError):
                    pass
            finally:
                pythoncom.CoUninitialize()

        threading.Thread(target=work, daemon=True).start()

    def _apply_ingest_result(
        self,
        token: int,
        entry_id: str,
        parsed: ParsedMsg | None,
        error: str,
    ) -> None:
        if token != self._ingest_token:
            return
        assert self._tasks_repo is not None
        assert self._refs_repo is not None

        if error or parsed is None:
            self.app.notify(error or "Ingest failed.", severity="error")
            self._set_status(f"{len(self._last_messages)} message(s).")
            return

        try:
            task, ref = ingest_outlook_snapshot(
                parsed=parsed,
                entry_id=entry_id,
                store_id=None,
                tasks=self._tasks_repo,
                refs=self._refs_repo,
            )
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            self._set_status(f"{len(self._last_messages)} message(s).")
            return

        session = getattr(self.app, "_session", None)
        if session is not None:
            session.refresh(task)
            session.refresh(ref)

        self.app.notify(
            f"Created pending task #{task.id}: {task.title}",
            severity="information",
        )
        self._set_status(
            f"{len(self._last_messages)} message(s). Task #{task.id} created.",
        )
        tasks_screen = self.app.query_one("#tasks", TasksScreen)
        tasks_screen.refresh_tasks_list(focus_task_id=task.id)
