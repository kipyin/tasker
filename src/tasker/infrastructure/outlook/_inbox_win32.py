"""Windows-only Outlook COM: recent Inbox messages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pywintypes
import win32com.client

from tasker.domain.exceptions import OutlookCOMError
from tasker.infrastructure.outlook.models import InboxMessageSummary

# OlDefaultFolders / olFolderInbox — use numeric value; win32com.client.constants
# often lacks Outlook enums until makepy has run.
_OL_FOLDER_INBOX = 6
_OL_MAIL = 43


def _received_to_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if hasattr(value, "year") and hasattr(value, "month"):
        return datetime(
            int(value.year),  # type: ignore[arg-type]
            int(value.month),  # type: ignore[arg-type]
            int(value.day),  # type: ignore[arg-type]
            int(value.hour),  # type: ignore[arg-type]
            int(value.minute),  # type: ignore[arg-type]
            int(value.second),  # type: ignore[arg-type]
        )
    return datetime.fromtimestamp(float(value))  # type: ignore[arg-type]


def _str_prop(item: Any, name: str, default: str = "") -> str:
    try:
        raw = getattr(item, name)
    except pywintypes.com_error:
        return default
    if raw is None:
        return default
    return str(raw)


def _bool_prop(item: Any, name: str, default: bool = False) -> bool:
    try:
        raw = getattr(item, name)
    except pywintypes.com_error:
        return default
    return bool(raw)


def fetch_recent_inbox(limit: int) -> list[InboxMessageSummary]:
    """Load up to ``limit`` most recent mail items from the default Inbox."""
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        session = outlook.GetNamespace("MAPI")
        inbox = session.GetDefaultFolder(_OL_FOLDER_INBOX)
        items = inbox.Items
        items.Sort("[ReceivedTime]", True)
    except pywintypes.com_error as exc:
        raise OutlookCOMError(
            "Could not open Outlook Inbox via COM. Is Outlook installed and usable?",
        ) from exc

    result: list[InboxMessageSummary] = []
    for item in items:
        if len(result) >= limit:
            break
        try:
            if item.Class != _OL_MAIL:
                continue
        except pywintypes.com_error:
            continue
        try:
            entry_id = _str_prop(item, "EntryID")
            subject = _str_prop(item, "Subject")
            received_raw = item.ReceivedTime
            received = _received_to_datetime(received_raw)
            sender_display = _str_prop(item, "SenderName")
            unread = _bool_prop(item, "UnRead")
        except pywintypes.com_error:
            continue
        result.append(
            InboxMessageSummary(
                entry_id=entry_id,
                subject=subject,
                received=received,
                sender_display=sender_display,
                unread=unread,
            ),
        )
    return result
