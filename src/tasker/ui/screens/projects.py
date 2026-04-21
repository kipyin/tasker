"""Project list and CRUD (Projects section)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Static, TextArea

from tasker.infrastructure.config.schema import (
    AppConfig,
    BucketConfig,
    ProjectConfig,
    RoutingRuleConfig,
)
from tasker.paths import config_path
from tasker.services.config_file import (
    ConfigMutationError,
    add_project,
    mutate_config_file,
    read_config_or_default,
    remove_project,
    update_project,
)


@dataclass(frozen=True)
class ProjectEditorOutcome:
    """Result from the add/edit modal."""

    kind: Literal["add", "edit"]
    project: ProjectConfig
    previous_id: str | None = None


def _format_buckets_text(p: ProjectConfig) -> str:
    return "\n".join(f"{b.name}|{b.relative_path}" for b in p.buckets)


def _format_rules_text(p: ProjectConfig) -> str:
    return "\n".join(f"{r.bucket}|{r.pattern}" for r in p.rules)


def _parse_bucket_lines(text: str, project_id_for_errors: str) -> list[BucketConfig]:
    out: list[BucketConfig] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            msg = (
                f"project {project_id_for_errors!r}: each bucket line must be "
                "name|relative_path (under the project root), e.g. docs|Documents"
            )
            raise ValueError(msg)
        name, rel = line.split("|", 1)
        name, rel = name.strip(), rel.strip()
        if not name or not rel:
            msg = (
                f"project {project_id_for_errors!r}: bucket name and relative_path "
                "must be non-empty on each line"
            )
            raise ValueError(msg)
        out.append(BucketConfig(name=name, relative_path=rel))
    return out


def _parse_rule_lines(text: str, project_id_for_errors: str) -> list[RoutingRuleConfig]:
    out: list[RoutingRuleConfig] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            msg = (
                f"project {project_id_for_errors!r}: each rule line must be "
                "bucket|pattern — pattern is a case-insensitive fnmatch glob "
                "on attachment filenames (e.g. *.pdf, report_*.xlsx)"
            )
            raise ValueError(msg)
        bucket, pattern = line.split("|", 1)
        bucket, pattern = bucket.strip(), pattern.strip()
        if not bucket or not pattern:
            msg = (
                f"project {project_id_for_errors!r}: rule bucket and pattern "
                "must be non-empty on each line"
            )
            raise ValueError(msg)
        out.append(RoutingRuleConfig(bucket=bucket, pattern=pattern))
    return out


def _apply_project_edit(
    cfg: AppConfig,
    previous_id: str,
    p: ProjectConfig,
) -> AppConfig:
    """Map editor fields to `update_project` (default bucket clear vs set)."""
    if p.id != previous_id.strip():
        kwargs: dict = {
            "name": p.name,
            "root": p.root,
            "new_id": p.id,
            "buckets": p.buckets,
            "rules": p.rules,
        }
        if p.default_bucket is None:
            kwargs["unset_default_bucket"] = True
        else:
            kwargs["default_bucket"] = p.default_bucket
        return update_project(cfg, previous_id, **kwargs)

    kwargs2: dict = {
        "name": p.name,
        "root": p.root,
        "buckets": p.buckets,
        "rules": p.rules,
    }
    if p.default_bucket is None:
        kwargs2["unset_default_bucket"] = True
    else:
        kwargs2["default_bucket"] = p.default_bucket
    return update_project(cfg, previous_id, **kwargs2)


def _project_outcome_mutator(
    outcome: ProjectEditorOutcome,
) -> Callable[[AppConfig], AppConfig]:
    """Same mutation used for pre-save validation and `mutate_config_file`."""

    def mut(cfg: AppConfig) -> AppConfig:
        if outcome.kind == "add":
            return add_project(cfg, outcome.project)
        assert outcome.previous_id is not None
        return _apply_project_edit(cfg, outcome.previous_id, outcome.project)

    return mut


class ConfirmDeleteProjectModal(ModalScreen[bool]):
    """Confirm removal of a project."""

    def __init__(self, project_id: str) -> None:
        super().__init__()
        self._project_id = project_id

    def compose(self) -> ComposeResult:
        yield Static(
            f"Delete project {self._project_id!r}? Tasks that reference this "
            "project id are not deleted; they may need a new project assignment.",
            id="confirm-delete-msg",
        )
        with Horizontal(id="confirm-delete-actions"):
            yield Button("Delete", variant="error", id="confirm-yes")
            yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        elif event.button.id == "confirm-no":
            self.dismiss(False)


class ProjectEditorModal(ModalScreen[ProjectEditorOutcome | None]):
    """Add or edit a single project (id, name, root, buckets, rules, default bucket)."""

    DEFAULT_CSS = """
    #project-editor-wrap {
        width: 88;
        max-height: 90%;
        height: auto;
        border: tall $boost;
        background: $surface;
    }
    #project-editor-scroll {
        height: 1fr;
        min-height: 0;
        padding: 1 2 0 2;
    }
    .pe-heading {
        text-style: bold;
        padding: 0 0 1 0;
    }
    .pe-help {
        color: $text-muted;
        padding: 0 0 1 0;
    }
    .pe-label {
        text-style: bold;
        padding: 1 0 0 0;
    }
    .pe-field-hint {
        color: $text-muted;
        padding: 0 0 0 0;
    }
    #pe-id, #pe-name, #pe-root, #pe-default-bucket {
        margin: 0 0 1 0;
    }
    #pe-buckets, #pe-rules {
        min-height: 4;
        height: auto;
        margin: 0 0 1 0;
    }
    #pe-editor-actions {
        height: auto;
        padding: 0 2 1 2;
        margin: 0;
    }
    """

    def __init__(
        self,
        *,
        mode: Literal["add", "edit"],
        initial: ProjectConfig | None = None,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._initial = initial

    def compose(self) -> ComposeResult:
        title = "Add project" if self._mode == "add" else "Edit project"
        with Vertical(id="project-editor-wrap"):
            with VerticalScroll(id="project-editor-scroll"):
                yield Static(title, classes="pe-heading")
                yield Static(
                    "Projects define a working folder (root) and optional attachment "
                    "buckets. On Windows you can paste a full path with backslashes; "
                    "it is stored using normal path rules.",
                    classes="pe-help",
                )
                yield Static("Project id", classes="pe-label")
                yield Static(
                    "Short stable id for tasks and routing (letters, digits, hyphens).",
                    classes="pe-field-hint",
                )
                yield Input(placeholder="my-project", id="pe-id")
                yield Static("Display name", classes="pe-label")
                yield Input(placeholder="My project", id="pe-name")
                yield Static("Root folder", classes="pe-label")
                yield Static(
                    "Absolute or user-relative path to the project working directory.",
                    classes="pe-field-hint",
                )
                yield Input(placeholder=r"C:\Users\you\Work\Alpha", id="pe-root")
                yield Static("Buckets", classes="pe-label")
                yield Static(
                    "One line per bucket: name|relative_path under root (e.g. "
                    "inbox|Inbox\\attachments). Empty section is allowed.",
                    classes="pe-field-hint",
                )
                yield TextArea(id="pe-buckets")
                yield Static("Routing rules", classes="pe-label")
                yield Static(
                    "Ordered rules: bucket|pattern. Pattern matches attachment "
                    "filenames with fnmatch (glob), case-insensitive — e.g. *.pdf, "
                    "scans_*.*. First match wins; if none match, default bucket is "
                    "used.",
                    classes="pe-field-hint",
                )
                yield TextArea(id="pe-rules")
                yield Static("Default bucket", classes="pe-label")
                yield Static(
                    "Optional. Must match a bucket name above. Leave empty if unused.",
                    classes="pe-field-hint",
                )
                yield Input(placeholder="inbox", id="pe-default-bucket")
            with Horizontal(id="pe-editor-actions"):
                yield Button("Save", variant="primary", id="pe-save")
                yield Button("Cancel", id="pe-cancel")

    def on_mount(self) -> None:
        id_input = self.query_one("#pe-id", Input)
        if self._mode == "edit" and self._initial is not None:
            p = self._initial
            id_input.value = p.id
            id_input.disabled = True
            self.query_one("#pe-name", Input).value = p.name
            self.query_one("#pe-root", Input).value = p.root
            self.query_one("#pe-buckets", TextArea).text = _format_buckets_text(p)
            self.query_one("#pe-rules", TextArea).text = _format_rules_text(p)
            self.query_one("#pe-default-bucket", Input).value = (
                p.default_bucket or ""
            )
        else:
            id_input.disabled = False
            self.query_one("#pe-buckets", TextArea).text = (
                "# Example:\n# docs|Documents\n# media|Media"
            )
            self.query_one("#pe-rules", TextArea).text = (
                "# Example:\n# docs|*.pdf\n# media|*.png"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pe-cancel":
            self.dismiss(None)
            return
        if event.button.id != "pe-save":
            return
        self._save()

    def _save(self) -> None:
        pid = self.query_one("#pe-id", Input).value.strip()
        name = self.query_one("#pe-name", Input).value.strip()
        root = self.query_one("#pe-root", Input).value.strip()
        default_raw = self.query_one("#pe-default-bucket", Input).value.strip()
        buckets_text = self.query_one("#pe-buckets", TextArea).text
        rules_text = self.query_one("#pe-rules", TextArea).text

        key_for_err = pid or "(new project)"
        try:
            buckets = _parse_bucket_lines(buckets_text, key_for_err)
            rules = _parse_rule_lines(rules_text, key_for_err)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error")
            return

        default_bucket: str | None = default_raw or None
        project = ProjectConfig(
            id=pid,
            name=name,
            root=root,
            buckets=buckets,
            rules=rules,
            default_bucket=default_bucket,
        )
        if self._mode == "add":
            outcome = ProjectEditorOutcome(kind="add", project=project)
        else:
            assert self._initial is not None
            outcome = ProjectEditorOutcome(
                kind="edit",
                project=project,
                previous_id=self._initial.id,
            )

        cfg_path = config_path()
        if cfg_path is None:
            self.app.notify(
                "APPDATA is not set; cannot save projects.",
                severity="error",
            )
            return
        try:
            _ = _project_outcome_mutator(outcome)(read_config_or_default(cfg_path))
        except ConfigMutationError as exc:
            self.app.notify(str(exc), severity="error")
            return

        self.dismiss(outcome)


class ProjectsScreen(Container):
    """Table of projects; add, edit, delete with validation via config file service."""

    DEFAULT_CSS = """
    #projects-main {
        height: 1fr;
    }
    #projects-help {
        padding: 1 2 0 2;
        color: $text-muted;
    }
    #projects-heading {
        text-style: bold;
        padding: 1 2 0 2;
    }
    #project-table {
        height: 1fr;
        margin: 0 2;
    }
    #projects-actions {
        height: auto;
        padding: 1 2;
    }
    """

    def __init__(self, *, config: AppConfig) -> None:
        super().__init__(id="projects")
        self._config = config

    def set_config(self, config: AppConfig) -> None:
        self._config = config
        self._reload_table(focus_table=True)

    def compose(self) -> ComposeResult:
        with Vertical(id="projects-main"):
            yield Static("Projects", id="projects-heading")
            yield Static(
                "Each project is a working directory plus optional buckets and "
                "filename-based routing rules for email attachments. Ids must be "
                "unique. Changes are written to your Tasker config file.",
                id="projects-help",
            )
            yield DataTable(
                id="project-table",
                cursor_type="row",
                zebra_stripes=True,
            )
            with Horizontal(id="projects-actions"):
                yield Button("Add", variant="primary", id="proj-add")
                yield Button("Edit", id="proj-edit")
                yield Button("Delete", variant="error", id="proj-delete")

    def on_mount(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.add_columns("ID", "Name", "Root")
        self._reload_table(focus_table=True)

    def _reload_table(self, *, focus_table: bool) -> None:
        table = self.query_one("#project-table", DataTable)
        table.clear()
        for p in self._config.projects:
            table.add_row(
                p.id,
                p.name,
                p.root,
                key=p.id,
            )
        if not self._config.projects:
            return
        table.cursor_coordinate = Coordinate(0, 0)
        if focus_table:
            table.focus()

    def _selected_project_id(self) -> str | None:
        table = self.query_one("#project-table", DataTable)
        if not self._config.projects:
            return None
        coord = table.cursor_coordinate
        if coord.row < 0 or coord.row >= len(self._config.projects):
            return None
        return self._config.projects[coord.row].id

    def _project_by_id(self, project_id: str) -> ProjectConfig | None:
        for p in self._config.projects:
            if p.id == project_id:
                return p
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "proj-add":
            self._open_editor(mode="add")
        elif bid == "proj-edit":
            self._open_edit()
        elif bid == "proj-delete":
            self._confirm_delete()

    def _open_editor(
        self,
        *,
        mode: Literal["add", "edit"],
        initial: ProjectConfig | None = None,
    ) -> None:
        self.app.push_screen(
            ProjectEditorModal(mode=mode, initial=initial),
            self._on_editor_closed,
        )

    def _open_edit(self) -> None:
        pid = self._selected_project_id()
        if pid is None:
            self.app.notify("No project selected.", severity="warning")
            return
        proj = self._project_by_id(pid)
        if proj is None:
            self.app.notify("Project not found in config.", severity="error")
            return
        self._open_editor(mode="edit", initial=proj)

    def _on_editor_closed(self, outcome: ProjectEditorOutcome | None) -> None:
        if outcome is None:
            return
        from tasker.ui.app import TaskerApp

        app = self.app
        assert isinstance(app, TaskerApp)
        cfg_file = config_path()
        if cfg_file is None:
            app.notify(
                "APPDATA is not set; cannot save projects.",
                severity="error",
            )
            return

        try:
            updated = mutate_config_file(cfg_file, _project_outcome_mutator(outcome))
        except ConfigMutationError as exc:
            app.notify(str(exc), severity="error")
            return
        app.apply_config(updated)
        app.notify("Projects saved.", severity="information")

    def _confirm_delete(self) -> None:
        pid = self._selected_project_id()
        if pid is None:
            self.app.notify("No project selected.", severity="warning")
            return
        self.app.push_screen(
            ConfirmDeleteProjectModal(pid),
            lambda confirmed: self._on_delete_closed(confirmed, pid),
        )

    def _on_delete_closed(self, confirmed: bool | None, pid: str) -> None:
        if not confirmed:
            return
        from tasker.ui.app import TaskerApp

        app = self.app
        assert isinstance(app, TaskerApp)
        cfg_file = config_path()
        if cfg_file is None:
            app.notify(
                "APPDATA is not set; cannot save projects.",
                severity="error",
            )
            return
        try:
            updated = mutate_config_file(
                cfg_file,
                lambda c: remove_project(c, pid),
            )
        except ConfigMutationError as exc:
            app.notify(str(exc), severity="error")
            return
        app.apply_config(updated)
        app.notify("Project removed.", severity="information")

