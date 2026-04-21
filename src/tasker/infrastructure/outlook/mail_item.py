"""Load full email snapshot from Outlook COM (Windows + optional pywin32)."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

from tasker.domain.exceptions import OutlookNotAvailableError
from tasker.domain.parsed_msg import ParsedMsg

_OUTLOOK_EXTRA_HINT = (
    "On Windows, install: pip install tasker[outlook] "
    "(adds pywin32 for local Outlook automation)."
)


def fetch_parsed_msg_from_outlook(
    entry_id: str,
    store_id: str | None = None,
    *,
    _fetch: Callable[[str, str | None], ParsedMsg] | None = None,
) -> ParsedMsg:
    """
    Resolve ``MailItem`` by EntryID and return the same shape as :func:`parse_msg_file`.

    ``_fetch`` is for tests; production leaves it ``None``.
    """
    if not (entry_id or "").strip():
        msg = "entry_id must be non-empty"
        raise ValueError(msg)
    if _fetch is not None:
        return _fetch(entry_id.strip(), store_id)
    if sys.platform != "win32":
        raise OutlookNotAvailableError(
            "Outlook COM is only supported on Windows. "
            f"{_OUTLOOK_EXTRA_HINT}",
        )
    try:
        mod = importlib.import_module(
            "tasker.infrastructure.outlook._mail_item_win32",
        )
    except ImportError as exc:
        raise OutlookNotAvailableError(
            f"pywin32 is required for Outlook COM. {_OUTLOOK_EXTRA_HINT}",
        ) from exc
    return mod.fetch_parsed_msg_from_outlook_win32(entry_id.strip(), store_id)
