"""Outlook Inbox listing (mocked COM path via ``_fetch_recent``)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import pytest

from tasker.domain.exceptions import OutlookNotAvailableError
from tasker.infrastructure.outlook import InboxMessageSummary, list_recent_inbox


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
