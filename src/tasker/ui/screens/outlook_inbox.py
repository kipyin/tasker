"""Recent Outlook Inbox listing (Windows COM, optional pywin32)."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from datetime import datetime

from textual._context import NoActiveAppError
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Static

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
from tasker.infrastructure.outlook.inbox_actions import (
    apply_message_archive,
    apply_message_categories,
    apply_message_delete,
    apply_message_flag,
    apply_message_read,
)
from tasker.infrastructure.outlook.mail_item import fetch_parsed_msg_from_outlook
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_outlook_snapshot
from tasker.ui.screens.tasks import TasksScreen


def _fmt_received(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


class ConfirmDeleteMessageModal(ModalScreen[bool]):
    """Confirm move of an Outlook message to Deleted Items."""

    def __init__(self, subject: str) -> None:
        super().__init__()
        self._subject = subject

    def compose(self) -> ComposeResult:
        subj = (self._subject or "(no subject)").replace("\n", " ")[:100]
        yield Static(
            f"Move to Deleted Items?\n\n{subj}\n",
            id="confirm-delete-mail-msg",
        )
        with Horizontal(id="confirm-delete-mail-actions"):
            yield Button("Delete", variant="error", id="confirm-mail-yes")
            yield Button("Cancel", id="confirm-mail-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-mail-yes":
            self.dismiss(True)
        elif event.button.id == "confirm-mail-no":
            self.dismiss(False)


class OutlookInboxScreen(Container):
    """Show recent Inbox messages via Outlook COM (background thread)."""

    BINDINGS = [
        Binding("i", "ingest_selected", "Ingest"),
        Binding("r", "read_selected", "Read"),
        Binding("f", "flag_selected", "Flag"),
        Binding("a", "archive_selected", "Archive"),
        Binding("d", "delete_selected", "Delete"),
        Binding("c", "focus_categories", "Categories"),
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
    #outlook-refresh, #outlook-ingest, .outlook-action-btn {
        width: auto;
        margin: 0 0 1 0;
    }
    #outlook-cat-input.hidden {
        display: none;
    }
    #outlook-cat-input {
        margin: 0 0 1 0;
    }
    #outlook-actions-row-2, #outlook-actions-row-3 {
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="outlook-inbox")
        self._limit = 20
        self._load_token = 0
        self._ingest_token = 0
        self._op_token = 0
        self._delete_target: InboxMessageSummary | None = None
        self._last_messages: list[InboxMessageSummary] = []
        self._tasks_repo: TaskRepository | None = None
        self._refs_repo: MessageRefRepository | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="outlook-scroll"):
            yield Static("Outlook Inbox", classes="outlook-heading")
            yield Static(
                "Recent Inbox. Refresh, select a row. Shortcuts: [b]i[/b] Ingest, "
                "[b]r[/b] read, [b]f[/b] flag, [b]c[/b] categories, [b]a[/b] archive, "
                "[b]d[/b] delete. Windows + Outlook + pip install tasker[outlook].",
                classes="outlook-help",
            )
            with Horizontal(id="outlook-actions-row-1"):
                yield Button("Refresh", variant="primary", id="outlook-refresh")
                yield Button("Ingest", variant="success", id="outlook-ingest")
            with Horizontal(id="outlook-actions-row-2"):
                yield Button("Read", id="outlook-read", classes="outlook-action-btn")
                yield Button("Flag", id="outlook-flag", classes="outlook-action-btn")
                yield Button(
                    "Unflag",
                    id="outlook-unflag",
                    classes="outlook-action-btn",
                )
                yield Button(
                    "Categories",
                    id="outlook-categories-btn",
                    classes="outlook-action-btn",
                )
            with Horizontal(id="outlook-actions-row-3"):
                yield Button(
                    "Archive",
                    id="outlook-archive",
                    classes="outlook-action-btn",
                )
                yield Button(
                    "Delete",
                    variant="error",
                    id="outlook-delete",
                    classes="outlook-action-btn",
                )
            yield Input(
                placeholder="Categories (e.g. Red; Client) — Enter to apply",
                id="outlook-cat-input",
                classes="hidden",
            )
            yield DataTable(
                id="outlook-table",
                cursor_type="row",
                zebra_stripes=True,
            )
            yield Static("", id="outlook-status", markup=False)

    def on_mount(self) -> None:
        table = self.query_one("#outlook-table", DataTable)
        table.add_columns("#", "Received", " ", "From", "Subject")
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

    def action_read_selected(self) -> None:
        self._begin_read_selected()

    def action_flag_selected(self) -> None:
        self._begin_flag_selected(clear=False)

    def action_archive_selected(self) -> None:
        self._begin_archive_selected()

    def action_delete_selected(self) -> None:
        self._begin_delete_selected()

    def action_focus_categories(self) -> None:
        inp = self.query_one("#outlook-cat-input", Input)
        inp.remove_class("hidden")
        inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "outlook-cat-input":
            return
        text = (event.value or "").strip()
        event.input.value = ""
        event.input.add_class("hidden")
        if not text:
            self.app.notify(
                "Enter categories (semicolons allowed).",
                severity="warning",
            )
            return
        m = self._require_selected_message()
        if m is None or not self._outlook_env_ok():
            return
        self._run_outlook_mutation(
            "Updating categories…",
            lambda: apply_message_categories(
                m.entry_id,
                m.store_id,
                text,
                append=False,
            ),
            "Categories updated.",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "outlook-refresh":
            self._begin_refresh()
        elif bid == "outlook-ingest":
            self._begin_ingest_selected()
        elif bid == "outlook-read":
            self._begin_read_selected()
        elif bid == "outlook-flag":
            self._begin_flag_selected(clear=False)
        elif bid == "outlook-unflag":
            self._begin_flag_selected(clear=True)
        elif bid == "outlook-categories-btn":
            self.action_focus_categories()
        elif bid == "outlook-archive":
            self._begin_archive_selected()
        elif bid == "outlook-delete":
            self._begin_delete_selected()

    def _require_selected_message(self) -> InboxMessageSummary | None:
        if not self._last_messages:
            self.app.notify("Load messages first (Refresh).", severity="warning")
            return None
        table = self.query_one("#outlook-table", DataTable)
        row_i = table.cursor_coordinate.row
        if row_i < 0 or row_i >= len(self._last_messages):
            self.app.notify("Select a message row.", severity="warning")
            return None
        return self._last_messages[row_i]

    def _outlook_env_ok(self) -> bool:
        if sys.platform != "win32":
            self.app.notify(
                "Outlook COM is only available on Windows.",
                severity="error",
            )
            return False
        if pythoncom is None:
            self.app.notify(
                "pywin32 is not installed. On Windows: pip install tasker[outlook]",
                severity="error",
            )
            return False
        return True

    def _run_outlook_mutation(
        self,
        working: str,
        op: Callable[[], None],
        success: str,
    ) -> None:
        if not self._outlook_env_ok():
            return
        self._op_token += 1
        token = self._op_token
        self._set_status(working)
        app = self.app

        def work() -> None:
            assert pythoncom is not None
            err = ""
            pythoncom.CoInitialize()
            try:
                op()
            except (OutlookCOMError, OutlookNotAvailableError, ValueError) as exc:
                err = str(exc)
            except Exception as exc:  # pragma: no cover
                err = str(exc)
            finally:
                pythoncom.CoUninitialize()
            try:
                app.call_from_thread(self._apply_mutation_result, token, err, success)
            except (NoActiveAppError, RuntimeError):
                pass

        threading.Thread(target=work, daemon=True).start()

    def _apply_mutation_result(
        self,
        token: int,
        error: str,
        success: str,
    ) -> None:
        if token != self._op_token:
            return
        if error:
            self.app.notify(error, severity="error")
        else:
            self.app.notify(success, severity="information")
        self._set_status(
            f"{len(self._last_messages)} message(s).",
        )
        self._begin_refresh()

    def _begin_read_selected(self) -> None:
        m = self._require_selected_message()
        if m is None or not self._outlook_env_ok():
            return
        self._run_outlook_mutation(
            "Marking read…",
            lambda: apply_message_read(m.entry_id, m.store_id, unread=False),
            "Marked as read.",
        )

    def _begin_flag_selected(self, *, clear: bool) -> None:
        m = self._require_selected_message()
        if m is None or not self._outlook_env_ok():
            return
        self._run_outlook_mutation(
            "Updating flag…",
            lambda: apply_message_flag(m.entry_id, m.store_id, clear=clear),
            "Flag cleared." if clear else "Flag set.",
        )

    def _begin_archive_selected(self) -> None:
        m = self._require_selected_message()
        if m is None or not self._outlook_env_ok():
            return
        self._run_outlook_mutation(
            "Archiving…",
            lambda: apply_message_archive(m.entry_id, m.store_id),
            "Message archived.",
        )

    def _begin_delete_selected(self) -> None:
        m = self._require_selected_message()
        if m is None or not self._outlook_env_ok():
            return
        self._delete_target = m
        self.app.push_screen(
            ConfirmDeleteMessageModal(m.subject or ""),
            self._on_delete_mail_confirmed,
        )

    def _on_delete_mail_confirmed(self, confirmed: bool | None) -> None:
        m = self._delete_target
        self._delete_target = None
        if not confirmed or m is None:
            return
        if not self._outlook_env_ok():
            return
        self._run_outlook_mutation(
            "Deleting…",
            lambda: apply_message_delete(m.entry_id, m.store_id),
            "Message moved to Deleted Items.",
        )

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
            except Exception as exc:  # pragma: no cover
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
        for i, m in enumerate(messages, start=1):
            u = "●" if m.unread else " "
            table.add_row(
                str(i),
                _fmt_received(m.received),
                u,
                m.sender_display,
                m.subject,
            )

    def _begin_ingest_selected(self) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        if not self._outlook_env_ok():
            return
        if not self._last_messages:
            self.app.notify("Load messages first (Refresh).", severity="warning")
            return
        table = self.query_one("#outlook-table", DataTable)
        row_i = table.cursor_coordinate.row
        if row_i < 0 or row_i >= len(self._last_messages):
            self.app.notify("Select a message row.", severity="warning")
            return
        message = self._last_messages[row_i]

        self._ingest_token += 1
        token = self._ingest_token
        self._set_status("Ingesting…")
        selected_entry_id = message.entry_id
        store_id = message.store_id
        app = self.app

        def work() -> None:
            assert pythoncom is not None
            pythoncom.CoInitialize()
            try:
                parsed = fetch_parsed_msg_from_outlook(selected_entry_id, store_id)
            except (OutlookCOMError, OutlookNotAvailableError, ValueError) as exc:
                try:
                    app.call_from_thread(
                        self._apply_ingest_result,
                        token,
                        selected_entry_id,
                        store_id,
                        None,
                        str(exc),
                    )
                except (NoActiveAppError, RuntimeError):
                    pass
            except Exception as exc:  # pragma: no cover
                try:
                    app.call_from_thread(
                        self._apply_ingest_result,
                        token,
                        selected_entry_id,
                        store_id,
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
                        store_id,
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
        store_id: str | None,
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
                store_id=store_id,
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