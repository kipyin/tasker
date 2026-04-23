"""Mutate Outlook Inbox messages via COM (Windows + optional pywin32)."""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Callable

from tasker.domain.exceptions import OutlookNotAvailableError

_OUTLOOK_EXTRA_HINT = (
    "On Windows, install: pip install tasker[outlook] "
    "(adds pywin32 for local Outlook automation)."
)


def _win32_mod() -> types.ModuleType:
    try:
        return importlib.import_module(
            "tasker.infrastructure.outlook._inbox_actions_win32",
        )
    except ImportError as exc:
        raise OutlookNotAvailableError(
            f"pywin32 is required for Outlook COM. {_OUTLOOK_EXTRA_HINT}",
        ) from exc


def _require_entry_id(entry_id: str) -> str:
    e = (entry_id or "").strip()
    if not e:
        msg = "entry_id must be non-empty"
        raise ValueError(msg)
    return e


def apply_message_read(
    entry_id: str,
    store_id: str | None = None,
    *,
    unread: bool = False,
    _apply: Callable[..., None] | None = None,
) -> None:
    """
    Mark the message read (default) or unread (``unread=True``).

    ``_apply`` is for tests; production leaves it ``None``.
    """
    eid = _require_entry_id(entry_id)
    if _apply is not None:
        _apply(eid, store_id, unread=unread)
        return
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    _win32_mod().apply_message_read_win32(eid, store_id, unread=unread)


def apply_message_flag(
    entry_id: str,
    store_id: str | None = None,
    *,
    clear: bool = False,
    _apply: Callable[..., None] | None = None,
) -> None:
    """Set or clear the follow-up flag on the message."""
    eid = _require_entry_id(entry_id)
    if _apply is not None:
        _apply(eid, store_id, clear=clear)
        return
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    _win32_mod().apply_message_flag_win32(eid, store_id, clear=clear)


def apply_message_categories(
    entry_id: str,
    store_id: str | None = None,
    categories: str = "",
    *,
    append: bool = False,
    _apply: Callable[..., None] | None = None,
) -> None:
    """Set or append semicolon-separated categories (Outlook format)."""
    eid = _require_entry_id(entry_id)
    if _apply is not None:
        _apply(eid, store_id, categories, append=append)
        return
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    _win32_mod().apply_message_categories_win32(
        eid, store_id, categories, append=append
    )


def apply_message_archive(
    entry_id: str,
    store_id: str | None = None,
    *,
    _apply: Callable[..., None] | None = None,
) -> None:
    """Move the message to the mailbox Archive folder."""
    eid = _require_entry_id(entry_id)
    if _apply is not None:
        _apply(eid, store_id)
        return
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    _win32_mod().apply_message_archive_win32(eid, store_id)


def apply_message_delete(
    entry_id: str,
    store_id: str | None = None,
    *,
    _apply: Callable[..., None] | None = None,
) -> None:
    """Delete the message (moves to Deleted Items)."""
    eid = _require_entry_id(entry_id)
    if _apply is not None:
        _apply(eid, store_id)
        return
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    _win32_mod().apply_message_delete_win32(eid, store_id)
