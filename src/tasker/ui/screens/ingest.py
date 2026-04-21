"""Email `.msg` ingest (Ingest section)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Button, Input, Static

from tasker.domain.exceptions import MsgIngestError
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_msg_path
from tasker.ui.screens.tasks import TasksScreen


class IngestScreen(Container):
    """Parse a `.msg` path and create a pending task (+ message ref)."""

    DEFAULT_CSS = """
    #ingest-scroll {
        height: 1fr;
        padding: 1 2;
    }
    .ingest-heading {
        text-style: bold;
        padding: 0 0 1 0;
    }
    .ingest-help {
        color: $text-muted;
        padding: 0 0 1 0;
    }
    .ingest-label {
        text-style: bold;
        padding: 1 0 0 0;
    }
    #ingest-path {
        margin: 0 0 1 0;
    }
    #ingest-run {
        width: auto;
        margin: 0 0 1 0;
    }
    #ingest-status {
        padding: 1 0 0 0;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="ingest")
        self._tasks_repo: TaskRepository | None = None
        self._refs_repo: MessageRefRepository | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="ingest-scroll"):
            yield Static("Ingest", classes="ingest-heading")
            yield Static(
                "Full path to an Outlook .msg file. "
                "Creates a pending task with email metadata "
                "(attachments are listed, not moved).",
                classes="ingest-help",
            )
            yield Static("Path to .msg", classes="ingest-label")
            yield Input(placeholder=r"C:\path\to\email.msg", id="ingest-path")
            yield Button("Run ingest", variant="primary", id="ingest-run")
            yield Static("", id="ingest-status", markup=False)

    def on_mount(self) -> None:
        app = self.app
        tasks_repo = getattr(app, "_tasks_repo", None)
        refs_repo = getattr(app, "_refs_repo", None)
        assert isinstance(tasks_repo, TaskRepository)
        assert isinstance(refs_repo, MessageRefRepository)
        self._tasks_repo = tasks_repo
        self._refs_repo = refs_repo

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ingest-run":
            self._run_ingest()

    def _run_ingest(self) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        raw = self.query_one("#ingest-path", Input).value.strip()
        status = self.query_one("#ingest-status", Static)
        if not raw:
            self.app.notify("Enter a path to a .msg file.", severity="error")
            status.update("")
            return
        path = Path(raw).expanduser()
        if path.suffix.lower() != ".msg":
            self.app.notify("Path must end with .msg", severity="error")
            status.update("")
            return
        try:
            task, ref = ingest_msg_path(
                path=path,
                tasks=self._tasks_repo,
                refs=self._refs_repo,
            )
        except MsgIngestError as exc:
            self.app.notify(str(exc), severity="error")
            status.update("")
            return

        session = getattr(self.app, "_session", None)
        if session is not None:
            session.refresh(task)
            session.refresh(ref)

        self.app.notify(
            f"Created pending task #{task.id}: {task.title}",
            severity="information",
        )
        status.update(
            f"Task #{task.id} — {task.title}\nMessage ref #{ref.id} → {ref.msg_path}",
        )
        tasks_screen = self.app.query_one("#tasks", TasksScreen)
        tasks_screen.refresh_tasks_list(focus_task_id=task.id)
