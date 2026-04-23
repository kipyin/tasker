"""Outlook Inbox listing (mocked COM path via ``_fetch_recent``)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

from tasker.domain.exceptions import OutlookNotAvailableError
from tasker.infrastructure.outlook import InboxMessageSummary, list_recent_inbox
from tasker.infrastructure.outlook.inbox import get_inbox_message_at_index


def test_list_recent_inbox_limit_validation() -> None:
    with pytest.raises(ValueError, match="limit"):
        list_recent_inbox(0)
    with pytest.raises(ValueError, match="limit"):
        list_recent_inbox(201)


def test_list_recent_inbox_non_windows() -> None:
    """On non-Windows, COM listing raises ``OutlookNotAvailableError``."""
    if sys.platform == "win32":
        pytest.skip("Windows uses COM path unless _fetch_recent is set")
    with pytest.raises(OutlookNotAvailableError):
        list_recent_inbox(5)


def test_list_recent_inbox_fetcher_override() -> None:
    dt = datetime(2026, 1, 2, 15, 30, tzinfo=UTC)
    sample = InboxMessageSummary(
        entry_id="abc",
        subject="Hello",
        received=dt,
        sender_display="Alice",
        unread=True,
    )

    def fetch(limit: int) -> list[InboxMessageSummary]:
        assert limit == 3
        return [sample]

    rows = list_recent_inbox(3, _fetch_recent=fetch)
    assert len(rows) == 1
    assert rows[0].subject == "Hello"
    assert rows[0].unread is True


def test_get_inbox_message_at_index() -> None:
    dt = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    a = InboxMessageSummary("a", "s1", dt, "x", True)
    b = InboxMessageSummary("b", "s2", dt, "y", False)

    def fetch(limit: int) -> list[InboxMessageSummary]:
        return [a, b][:limit]

    assert get_inbox_message_at_index(1, limit=5, _fetch_recent=fetch) is a
    assert get_inbox_message_at_index(2, limit=5, _fetch_recent=fetch) is b
    with pytest.raises(ValueError, match="index must be between"):
        get_inbox_message_at_index(0, limit=5, _fetch_recent=fetch)
    with pytest.raises(ValueError, match="index must be between"):
        get_inbox_message_at_index(3, limit=2, _fetch_recent=fetch)
