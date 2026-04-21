"""Outlook COM data shapes (read-only metadata)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class InboxMessageSummary:
    """Recent Inbox mail item metadata (no body or attachments in v1)."""

    entry_id: str
    subject: str
    received: datetime
    sender_display: str
    unread: bool
