"""Task list + detail pane (Tasks section)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Select, Static, TextArea

from tasker.domain.enums import TaskStatus
from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.ui.open_external import open_path_with_default_handler
from tasker.ui.workspace import resolve_working_folder


def _truncate(text: str, max_len: int | None) -> str:
    if max_len is None or len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _task_detail_lines(
    task: Task,
    ref: MessageRef | None,
    *,
    max_notes: int | None = 4000,
    max_body: int | None = 8000,
) -> list[str]:
    lines: list[str] = []
    lines.append(f"Task #{task.id}: {task.title}")
    lines.append(f"Status: {task.status.value}")
    lines.append(f"Project: {task.project_id if task.project_id else '—'}")
    if task.notes:
        lines.append("")
        lines.append("Notes")
        lines.append(_truncate(task.notes, max_notes))
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
            lines.append(_truncate(body, max_body))
        lines.append("")
        if (ref.outlook_entry_id or "").strip():
            lines.append("Source: Outlook (COM)")
            lines.append(f"Label: {ref.msg_path}")
            if ref.outlook_store_id:
                lines.append(f"Store ID: {ref.outlook_store_id}")
        else:
            lines.append(".msg path")
            lines.append(ref.msg_path)
    else:
        lines.append("")
        lines.append("No linked message for this task.")
    return lines


def _parse_task_status_value(raw: str) -> TaskStatus | None:
    try:
        return TaskStatus(raw.strip().lower())
    except ValueError:
        return None


@dataclass(frozen=True)
class TaskEditorOutcome:
    """Result after saving the add/edit task form (task id to focus)."""

    task_id: int


class TaskViewModal(ModalScreen[None]):
    """Read-only full detail for the selected task."""

    DEFAULT_CSS = """
    #task-view-wrap {
        width: 88;
        max-height: 90%;
        height: auto;
        border: tall $boost;
        background: $surface;
    }
    #task-view-scroll {
        height: 1fr;
        min-height: 0;
        padding: 1 2;
    }
    #task-view-actions {
        height: auto;
        padding: 0 2 1 2;
    }
    """

    def __init__(self, *, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines

    def compose(self) -> ComposeResult:
        with Vertical(id="task-view-wrap"):
            with VerticalScroll(id="task-view-scroll"):
                yield Static("\n".join(self._lines), id="task-view-body", markup=False)
            with Horizontal(id="task-view-actions"):
                yield Button("Close", variant="primary", id="task-view-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "task-view-close":
            self.dismiss(None)


class ConfirmDeleteTaskModal(ModalScreen[bool]):
    """Confirm deletion of a task and its linked message references."""

    def __init__(self, task_row: Task) -> None:
        super().__init__()
        # Do not use `_task` — Textual's MessagePump reserves it for asyncio.Task.
        self._task_row = task_row

    def compose(self) -> ComposeResult:
        yield Static(
            f"Delete task #{self._task_row.id} {self._task_row.title!r}? "
            "Linked .msg references are removed from the database; files on disk "
            "are not deleted.",
            id="confirm-delete-task-msg",
        )
        with Horizontal(id="confirm-delete-task-actions"):
            yield Button("Delete", variant="error", id="confirm-task-yes")
            yield Button("Cancel", id="confirm-task-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-task-yes":
            self.dismiss(True)
        elif event.button.id == "confirm-task-no":
            self.dismiss(False)


class TaskEditorModal(ModalScreen[TaskEditorOutcome | None]):
    """Create or edit core task fields (title, status, project, notes)."""

    DEFAULT_CSS = """
    #task-editor-wrap {
        width: 76;
        max-height: 90%;
        height: auto;
        border: tall $boost;
        background: $surface;
    }
    #task-editor-scroll {
        height: 1fr;
        min-height: 0;
        padding: 1 2 0 2;
    }
    .te-heading {
        text-style: bold;
        padding: 0 0 1 0;
    }
    .te-help {
        color: $text-muted;
        padding: 0 0 1 0;
    }
    .te-label {
        text-style: bold;
        padding: 1 0 0 0;
    }
    #te-title, #te-status, #te-project {
        margin: 0 0 1 0;
    }
    #te-notes {
        min-height: 6;
        height: auto;
        margin: 0 0 1 0;
    }
    #te-editor-actions {
        height: auto;
        padding: 0 2 1 2;
        margin: 0;
    }
    """

    def __init__(
        self,
        *,
        mode: Literal["add", "edit"],
        config: AppConfig,
        tasks_repo: TaskRepository,
        task_id: int | None = None,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._config = config
        self._tasks_repo = tasks_repo
        self._task_id = task_id

    def compose(self) -> ComposeResult:
        title = "New task" if self._mode == "add" else "Edit task"
        with Vertical(id="task-editor-wrap"):
            with VerticalScroll(id="task-editor-scroll"):
                yield Static(title, classes="te-heading")
                yield Static(
                    "Project id must match a project in Configuration (or leave "
                    "unset). Status uses the same values as the CLI.",
                    classes="te-help",
                )
                yield Static("Title", classes="te-label")
                yield Input(placeholder="Task title", id="te-title")
                yield Static("Status", classes="te-label")
                yield Select(
                    [(s.value, s.value) for s in TaskStatus],
                    id="te-status",
                    allow_blank=False,
                    value=TaskStatus.DRAFT.value,
                )
                yield Static("Project", classes="te-label")
                yield Select(
                    [("— none —", "")]
                    + [(p.id, p.id) for p in self._config.projects],
                    id="te-project",
                    allow_blank=False,
                    value="",
                )
                yield Static("Notes", classes="te-label")
                yield TextArea(id="te-notes")
            with Horizontal(id="te-editor-actions"):
                yield Button("Save", variant="primary", id="te-save")
                yield Button("Cancel", id="te-cancel")

    def on_mount(self) -> None:
        if self._mode == "edit":
            assert self._task_id is not None
            task = self._tasks_repo.get(self._task_id)
            if task is None:
                self.app.notify("Task no longer exists.", severity="error")
                self.dismiss(None)
                return
            self.query_one("#te-title", Input).value = task.title
            self.query_one("#te-status", Select).value = task.status.value
            proj = task.project_id or ""
            proj_select = self.query_one("#te-project", Select)
            allowed_project = {""} | {p.id for p in self._config.projects}
            if proj not in allowed_project:
                self.app.notify(
                    f"Project id {proj!r} is not in the list; pick a project or "
                    "add it under Configuration.",
                    severity="warning",
                )
            proj_select.value = proj if proj in allowed_project else ""
            self.query_one("#te-notes", TextArea).text = task.notes or ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "te-cancel":
            self.dismiss(None)
            return
        if event.button.id != "te-save":
            return
        self._save()

    def _save(self) -> None:
        title = self.query_one("#te-title", Input).value.strip()
        if not title:
            self.app.notify("Title is required.", severity="error")
            return
        status_raw = self.query_one("#te-status", Select).value
        if not isinstance(status_raw, str):
            self.app.notify("Pick a status.", severity="error")
            return
        st = _parse_task_status_value(status_raw)
        if st is None:
            self.app.notify("Invalid status.", severity="error")
            return
        project_raw = self.query_one("#te-project", Select).value
        project_id = project_raw if isinstance(project_raw, str) else ""
        notes_text = self.query_one("#te-notes", TextArea).text.strip()
        notes = notes_text or None

        if self._mode == "add":
            row = self._tasks_repo.create(
                title=title,
                project_id=project_id,
                status=st,
                notes=notes,
            )
            self.dismiss(TaskEditorOutcome(task_id=row.id))
            return

        assert self._task_id is not None
        updated = self._tasks_repo.update(
            self._task_id,
            title=title,
            status=st,
            project_id=project_id,
            notes=notes,
        )
        if updated is None:
            self.app.notify("Task no longer exists.", severity="error")
            self.dismiss(None)
            return
        self.dismiss(TaskEditorOutcome(task_id=updated.id))


class TasksScreen(Container):
    """List tasks from SQLite; show linked email summary; open `.msg` / working dir."""

    DEFAULT_CSS = """
    Horizontal#tasks-main {
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
    #task-crud-actions, #actions {
        height: auto;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, *, config: AppConfig) -> None:
        super().__init__(id="tasks")
        self._config = config
        self._tasks_repo: TaskRepository | None = None
        self._refs_repo: MessageRefRepository | None = None
        self._current_task: Task | None = None
        self._primary_ref: MessageRef | None = None

    def set_config(self, config: AppConfig) -> None:
        """Update routing/workspace config after the TOML file changes."""
        self._config = config

    def compose(self) -> ComposeResult:
        with Horizontal(id="tasks-main"):
            with Vertical(id="left-pane"):
                yield Static("Tasks", classes="pane-title")
                yield DataTable(id="task-table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="right-pane"):
                yield Static("Detail", classes="pane-title")
                with Horizontal(id="task-crud-actions"):
                    yield Button("New", variant="primary", id="btn-task-new")
                    yield Button("View", id="btn-task-view")
                    yield Button("Edit", id="btn-task-edit")
                    yield Button("Delete", variant="error", id="btn-task-delete")
                with Horizontal(id="actions"):
                    yield Button("Open .msg", variant="primary", id="btn-open-msg")
                    yield Button("Open folder", id="btn-open-folder")
                with VerticalScroll(id="detail-scroll"):
                    yield Static(
                        "Select a task.",
                        id="detail-body",
                        markup=False,
                    )

    def on_mount(self) -> None:
        app = self.app
        tasks_repo = getattr(app, "_tasks_repo", None)
        refs_repo = getattr(app, "_refs_repo", None)
        assert isinstance(tasks_repo, TaskRepository)
        assert isinstance(refs_repo, MessageRefRepository)
        self._tasks_repo = tasks_repo
        self._refs_repo = refs_repo
        table = self.query_one("#task-table", DataTable)
        table.add_columns("ID", "Title", "Status", "Project")
        self._reload_tasks(focus_table=True)

    def refresh_tasks_list(self, *, focus_task_id: int | None = None) -> None:
        """Reload the table after DB changes from another screen (e.g. ingest)."""
        if self._tasks_repo is None or self._refs_repo is None:
            return
        self._reload_tasks(focus_table=False, focus_task_id=focus_task_id)

    def _reload_tasks(
        self,
        *,
        focus_table: bool,
        focus_task_id: int | None = None,
    ) -> None:
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
            detail.update("No tasks yet. Add one with New or use `tasker mail ingest`.")
            return
        if focus_task_id is not None:
            for i, t in enumerate(tasks):
                if t.id == focus_task_id:
                    table.cursor_coordinate = Coordinate(i, 0)
                    self._show_task_detail(focus_task_id)
                    if focus_table:
                        table.focus()
                    return
        table.cursor_coordinate = Coordinate(0, 0)
        first = tasks[0]
        self._show_task_detail(first.id)
        if focus_table:
            table.focus()

    def _selected_task_id(self) -> int | None:
        assert self._tasks_repo is not None
        table = self.query_one("#task-table", DataTable)
        tasks = self._tasks_repo.list_all()
        if not tasks:
            return None
        coord = table.cursor_coordinate
        if coord.row < 0 or coord.row >= len(tasks):
            return None
        return tasks[coord.row].id

    def _show_task_detail(self, task_id: int) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        task = self._tasks_repo.get(task_id)
        if task is None:
            self._current_task = None
            self._primary_ref = None
            self.query_one("#detail-body", Static).update(
                f"Task {task_id} was removed.",
            )
            return
        refs = self._refs_repo.list_for_task(task_id)
        ref = refs[0] if refs else None
        self._current_task = task
        self._primary_ref = ref
        lines = _task_detail_lines(task, ref)
        self.query_one("#detail-body", Static).update("\n".join(lines))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = event.row_key.value
        if key is None:
            return
        self._show_task_detail(int(key))

    def action_refresh(self) -> None:
        tid = self._current_task.id if self._current_task else None
        self._reload_tasks(focus_table=False, focus_task_id=tid)
        self.notify("Refreshed", severity="information")

    def action_open_msg(self) -> None:
        ref = self._primary_ref
        if ref is None:
            self.notify("No message linked to this task.", severity="warning")
            return
        if (ref.outlook_entry_id or "").strip():
            self.notify(
                "This task is linked via Outlook (COM); open the item in Outlook.",
                severity="information",
            )
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
                "No working folder (set a project root or link a message).",
                severity="warning",
            )
            return
        try:
            open_path_with_default_handler(folder)
        except FileNotFoundError:
            self.notify(f"Folder not found: {folder}", severity="error")
        except OSError as exc:
            self.notify(str(exc), severity="error")

    def _open_editor(self, *, mode: Literal["add", "edit"]) -> None:
        assert self._tasks_repo is not None
        task_id: int | None = None
        if mode == "edit":
            task_id = self._selected_task_id()
            if task_id is None:
                self.notify("No task selected.", severity="warning")
                return
        self.app.push_screen(
            TaskEditorModal(
                mode=mode,
                config=self._config,
                tasks_repo=self._tasks_repo,
                task_id=task_id,
            ),
            self._on_editor_closed,
        )

    def _on_editor_closed(self, outcome: TaskEditorOutcome | None) -> None:
        if outcome is None:
            return
        self._reload_tasks(focus_table=True, focus_task_id=outcome.task_id)
        self.notify("Task saved.", severity="information")

    def _open_view(self) -> None:
        assert self._tasks_repo is not None
        assert self._refs_repo is not None
        task_id = self._selected_task_id()
        if task_id is None:
            self.notify("No task selected.", severity="warning")
            return
        task = self._tasks_repo.get(task_id)
        if task is None:
            self.notify("Task no longer exists.", severity="error")
            self._reload_tasks(focus_table=True)
            return
        refs = self._refs_repo.list_for_task(task_id)
        ref = refs[0] if refs else None
        lines = _task_detail_lines(task, ref, max_notes=None, max_body=None)
        self.app.push_screen(TaskViewModal(lines=lines))

    def _confirm_delete(self) -> None:
        assert self._tasks_repo is not None
        task_id = self._selected_task_id()
        if task_id is None:
            self.notify("No task selected.", severity="warning")
            return
        task = self._tasks_repo.get(task_id)
        if task is None:
            self.notify("Task no longer exists.", severity="error")
            self._reload_tasks(focus_table=True)
            return
        tid = task.id
        self.app.push_screen(
            ConfirmDeleteTaskModal(task),
            lambda confirmed: self._on_delete_closed(confirmed, tid),
        )

    def _on_delete_closed(self, confirmed: bool | None, task_id: int) -> None:
        if not confirmed:
            return
        assert self._tasks_repo is not None
        deleted = self._tasks_repo.delete_cascade(task_id)
        if not deleted:
            self.notify("Task no longer exists.", severity="error")
        else:
            self.notify("Task deleted.", severity="information")
        self._reload_tasks(focus_table=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-task-new":
            self._open_editor(mode="add")
        elif bid == "btn-task-view":
            self._open_view()
        elif bid == "btn-task-edit":
            self._open_editor(mode="edit")
        elif bid == "btn-task-delete":
            self._confirm_delete()
        elif bid == "btn-open-msg":
            self.action_open_msg()
        elif bid == "btn-open-folder":
            self.action_open_folder()
