"""Textual task list + detail with actions to open `.msg` and the working folder."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Footer, Static

from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.ui.open_external import open_path_with_default_handler
from tasker.ui.workspace import resolve_working_folder


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


class TaskerApp(App[None]):
    """List tasks from SQLite; show linked email summary; open `.msg` / working dir."""

    TITLE = "Tasker"
    CSS = """
    Horizontal#main {
        height: 1fr;
    }
    #left-pane {
        width: 40%;
        min-width: 24;
        height: 1fr;
    }
    #right-pane {
        width: 1fr;
        height: 1fr;
    }
    #task-table {
        height: 1fr;
    }
    .pane-title {
        text-style: bold;
        padding: 0 0 1 0;
    }
    #detail-scroll {
        height: 1fr;
        border: tall $boost;
        padding: 0 1;
    }
    #actions {
        height: auto;
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("o", "open_msg", "Open .msg"),
        Binding("f", "open_folder", "Open folder"),
    ]

    def __init__(self, *, config: AppConfig, engine: Engine) -> None:
        super().__init__()
        self._config = config
        self._engine = engine
        self._session: Session | None = None
        self._tasks_repo: TaskRepository | None = None
        self._refs_repo: MessageRefRepository | None = None
        self._current_task: Task | None = None
        self._primary_ref: MessageRef | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="left-pane"):
                yield Static("Tasks", classes="pane-title")
                yield DataTable(id="task-table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="right-pane"):
                yield Static("Detail", classes="pane-title")
                with Horizontal(id="actions"):
                    yield Button("Open .msg", variant="primary", id="btn-open-msg")
                    yield Button("Open folder", id="btn-open-folder")
                with VerticalScroll(id="detail-scroll"):
                    yield Static(
                        "Select a task.",
                        id="detail-body",
                        markup=False,
                    )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.add_columns("ID", "Title", "Status", "Project")
        self._session = Session(self._engine)
        self._tasks_repo = TaskRepository(self._session)
        self._refs_repo = MessageRefRepository(self._session)
        self._reload_tasks(focus_table=True)

    def on_unmount(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def _reload_tasks(self, *, focus_table: bool) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        table = self.query_one("#task-table", DataTable)
        table.clear()
        tasks = self._tasks_repo.list_all()
        for t in tasks:
            proj = t.project_id if (t.project_id or "").strip() else "—"
            table.add_row(
                str(t.id),
                t.title,
                t.status.value,
                proj,
                key=str(t.id),
            )
        detail = self.query_one("#detail-body", Static)
        if not tasks:
            self._current_task = None
            self._primary_ref = None
            detail.update("No tasks yet. Use `tasker ingest` to add one.", markup=False)
            return
        table.cursor_coordinate = Coordinate(0, 0)
        first = tasks[0]
        self._show_task_detail(first.id)
        if focus_table:
            table.focus()

    def _show_task_detail(self, task_id: int) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        task = self._tasks_repo.get(task_id)
        if task is None:
            self._current_task = None
            self._primary_ref = None
            self.query_one("#detail-body", Static).update(
                f"Task {task_id} was removed.",
                markup=False,
            )
            return
        refs = self._refs_repo.list_for_task(task_id)
        ref = refs[0] if refs else None
        self._current_task = task
        self._primary_ref = ref
        lines: list[str] = []
        lines.append(f"Task #{task.id}: {task.title}")
        lines.append(f"Status: {task.status.value}")
        lines.append(f"Project: {task.project_id if task.project_id else '—'}")
        if task.notes:
            lines.append("")
            lines.append("Notes")
            lines.append(_truncate(task.notes, 4000))
        if ref is not None:
            lines.append("")
            lines.append("Email")
            lines.append(f"Subject: {ref.subject or '—'}")
            lines.append(f"From: {ref.sender or '—'}")
            if ref.recipients_to:
                lines.append(f"To: {ref.recipients_to}")
            if ref.recipients_cc:
                lines.append(f"Cc: {ref.recipients_cc}")
            body = ref.body_text or ""
            if body:
                lines.append("")
                lines.append("Body")
                lines.append(_truncate(body, 8000))
            lines.append("")
            lines.append(".msg path")
            lines.append(ref.msg_path)
        else:
            lines.append("")
            lines.append("No linked message for this task.")
        self.query_one("#detail-body", Static).update("\n".join(lines), markup=False)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key is None:
            return
        self._show_task_detail(int(key))

    def action_refresh(self) -> None:
        self._reload_tasks(focus_table=False)
        self.notify("Refreshed", severity="information")

    def action_open_msg(self) -> None:
        ref = self._primary_ref
        if ref is None:
            self.notify("No .msg linked to this task.", severity="warning")
            return
        path = Path(ref.msg_path)
        try:
            open_path_with_default_handler(path)
        except FileNotFoundError:
            self.notify(f"File not found: {path}", severity="error")
        except OSError as exc:
            self.notify(str(exc), severity="error")

    def action_open_folder(self) -> None:
        task = self._current_task
        if task is None:
            self.notify("No task selected.", severity="warning")
            return
        folder = resolve_working_folder(self._config, task, self._primary_ref)
        if folder is None:
            self.notify(
                "No working folder (set a project root or link a .msg).",
                severity="warning",
            )
            return
        try:
            open_path_with_default_handler(folder)
        except FileNotFoundError:
            self.notify(f"Folder not found: {folder}", severity="error")
        except OSError as exc:
            self.notify(str(exc), severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-open-msg":
            self.action_open_msg()
        elif event.button.id == "btn-open-folder":
            self.action_open_folder()


def run_tui() -> None:
    """Prepare storage, run the Textual app, then dispose the DB engine."""
    _, config, engine = prepare_local_storage()
    try:
        TaskerApp(config=config, engine=engine).run()
    finally:
        engine.dispose()
