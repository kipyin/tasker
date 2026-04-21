"""Domain-level errors for Tasker workflows."""

from __future__ import annotations


class MsgIngestError(Exception):
    """Raised when a `.msg` file cannot be read or parsed."""


class ClassificationError(Exception):
    """Classification failed: config, task state, or invalid model output."""


class AIClientError(Exception):
    """OpenAI-compatible HTTP API failed or returned an unexpected payload."""


class RoutingError(Exception):
    """Attachment routing failed (config, project, or filesystem)."""


class OutlookNotAvailableError(Exception):
    """Outlook COM is unavailable (wrong OS, missing optional dependency, etc.)."""


class OutlookCOMError(Exception):
    """Outlook COM automation failed."""
