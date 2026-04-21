"""Textual shell: tasks, projects, config, ingest, and Outlook Inbox."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Footer

from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.lifecycle import prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.ui.screens.configuration import ConfigurationScreen
from tasker.ui.screens.ingest import IngestScreen
from tasker.ui.screens.outlook_inbox import OutlookInboxScreen
from tasker.ui.screens.projects import ProjectsScreen
from tasker.ui.screens.tasks import TasksScreen


class TaskerApp(App[None]):
    """Root app: nav bar, section switcher, shared DB session for screens."""

    TITLE = "Tasker"
    CSS = """
    #nav-bar {
        height: auto;
        dock: top;
    }
    #content-switcher {
        height: 1fr;
    }
    .section-placeholder {
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("1", "show_tasks", "Tasks"),
        Binding("2", "show_projects", "Projects"),
        Binding("3", "show_configuration", "Config"),
        Binding("4", "show_ingest", "Ingest"),
        Binding("5", "show_outlook_inbox", "Outlook"),
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("o", "open_msg", "Open .msg"),
        Binding("f", "open_folder", "Open folder"),
    ]

    def __init__(self, *, config: AppConfig, engine: Engine) -> None:
        super().__init__()
        self._config = config
        self._engine = engine
        # Session/repos before child widgets mount (TasksScreen.on_mount runs before
        # TaskerApp.on_mount in Textual's dispatch order).
        self._session = Session(self._engine)
        self._tasks_repo = TaskRepository(self._session)
        self._refs_repo = MessageRefRepository(self._session)

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="nav-bar"):
                yield Button("Tasks", id="nav-tasks")
                yield Button("Projects", id="nav-projects")
                yield Button("Configuration", id="nav-config")
                yield Button("Ingest", id="nav-ingest")
                yield Button("Outlook", id="nav-outlook")
                yield Button("Quit", id="nav-quit")
            with ContentSwitcher(id="content-switcher"):
                yield TasksScreen(config=self._config)
                yield ProjectsScreen(config=self._config)
                yield ConfigurationScreen()
                yield IngestScreen()
                yield OutlookInboxScreen()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#content-switcher", ContentSwitcher).current = "tasks"

    def on_unmount(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def _content_switcher(self) -> ContentSwitcher:
        return self.query_one("#content-switcher", ContentSwitcher)

    def _is_tasks_section_active(self) -> bool:
        return self._content_switcher().current == "tasks"

    def _tasks_screen(self) -> TasksScreen:
        return self.query_one("#tasks", TasksScreen)

    def apply_config(self, config: AppConfig) -> None:
        """Replace in-memory config and sync screens that depend on it."""
        self._config = config
        self._tasks_screen().set_config(config)
        self._projects_screen().set_config(config)

    def _projects_screen(self) -> ProjectsScreen:
        return self.query_one("#projects", ProjectsScreen)

    def action_show_tasks(self) -> None:
        self._content_switcher().current = "tasks"

    def action_show_projects(self) -> None:
        self._content_switcher().current = "projects"

    def action_show_configuration(self) -> None:
        self._content_switcher().current = "config"

    def action_show_ingest(self) -> None:
        self._content_switcher().current = "ingest"

    def action_show_outlook_inbox(self) -> None:
        self._content_switcher().current = "outlook-inbox"

    def action_refresh(self) -> None:
        cs = self._content_switcher().current
        if cs == "tasks":
            self._tasks_screen().action_refresh()
        elif cs == "outlook-inbox":
            self._outlook_screen().action_refresh()

    def _outlook_screen(self) -> OutlookInboxScreen:
        return self.query_one("#outlook-inbox", OutlookInboxScreen)

    def action_open_msg(self) -> None:
        if not self._is_tasks_section_active():
            return
        self._tasks_screen().action_open_msg()

    def action_open_folder(self) -> None:
        if not self._is_tasks_section_active():
            return
        self._tasks_screen().action_open_folder()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid is None or not bid.startswith("nav-"):
            return
        if bid == "nav-tasks":
            self.action_show_tasks()
        elif bid == "nav-projects":
            self.action_show_projects()
        elif bid == "nav-config":
            self.action_show_configuration()
        elif bid == "nav-ingest":
            self.action_show_ingest()
        elif bid == "nav-outlook":
            self.action_show_outlook_inbox()
        elif bid == "nav-quit":
            self.exit()


def run_tui() -> None:
    """Prepare storage, run the Textual app, then dispose the DB engine."""
    _, config, engine = prepare_local_storage()
    try:
        TaskerApp(config=config, engine=engine).run()
    finally:
        engine.dispose()
