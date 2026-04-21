"""Local Outlook COM adapters (Windows, optional dependency)."""

from __future__ import annotations

from tasker.domain.exceptions import OutlookCOMError, OutlookNotAvailableError
from tasker.infrastructure.outlook.inbox import list_recent_inbox
from tasker.infrastructure.outlook.models import InboxMessageSummary

__all__ = [
    "InboxMessageSummary",
    "list_recent_inbox",
    "OutlookCOMError",
    "OutlookNotAvailableError",
]
