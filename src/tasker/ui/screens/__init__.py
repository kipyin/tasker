"""TUI screens mounted under the main app shell."""

from __future__ import annotations

from tasker.ui.screens.configuration import ConfigurationScreen
from tasker.ui.screens.ingest import IngestScreen
from tasker.ui.screens.outlook_inbox import OutlookInboxScreen
from tasker.ui.screens.projects import ProjectsScreen
from tasker.ui.screens.tasks import TasksScreen

__all__ = [
    "ConfigurationScreen",
    "IngestScreen",
    "OutlookInboxScreen",
    "ProjectsScreen",
    "TasksScreen",
]
