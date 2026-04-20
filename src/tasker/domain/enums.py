"""Domain enumerations shared across persistence and services."""

from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    """Lifecycle state for a task."""

    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    ARCHIVED = "archived"
