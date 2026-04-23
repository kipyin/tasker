"""List recent Inbox messages via Outlook COM (Windows + optional pywin32)."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

from tasker.domain.exceptions import OutlookNotAvailableError
from tasker.infrastructure.outlook.models import InboxMessageSummary

_OUTLOOK_EXTRA_HINT = (
    "On Windows, install: pip install tasker[outlook] "
    "(adds pywin32 for local Outlook automation)."
)


def list_recent_inbox(
    limit: int,
    *,
    _fetch_recent: Callable[[int], list[InboxMessageSummary]] | None = None,
) -> list[InboxMessageSummary]:
    """
    Return up to ``limit`` recent messages from the default Outlook Inbox.

    Metadata only. ``_fetch_recent`` is for tests; production leaves it ``None``.
    """
    if limit < 1 or limit > 200:
        msg = "limit must be between 1 and 200"
        raise ValueError(msg)
    if _fetch_recent is not None:
        return _fetch_recent(limit)
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    try:
        mod = importlib.import_module("tasker.infrastructure.outlook._inbox_win32")
    except ImportError as exc:
        raise OutlookNotAvailableError(
            f"pywin32 is required for Outlook COM. {_OUTLOOK_EXTRA_HINT}",
        ) from exc
    return mod.fetch_recent_inbox(limit)


def get_inbox_message_at_index(
    one_based_index: int,
    *,
    limit: int,
    _fetch_recent: Callable[[int], list[InboxMessageSummary]] | None = None,
) -> InboxMessageSummary:
    """
    Return the message at ``one_based_index`` (1 = most recent).

    Uses the same ordering as :func:`list_recent_inbox` with the given ``limit``.
    ``_fetch_recent`` is for tests; production leaves it ``None``.
    """
    messages = list_recent_inbox(limit, _fetch_recent=_fetch_recent)
    if one_based_index < 1 or one_based_index > len(messages):
        hi = len(messages)
        msg = (
            f"index must be between 1 and {hi} "
            f"(there are {hi} message(s) for this --limit)"
        )
        raise ValueError(msg)
    return messages[one_based_index - 1]
