"""Synthetic `MessageRef.msg_path` values for live Outlook (no `.msg` file)."""

from __future__ import annotations


def outlook_com_msg_path(entry_id: str) -> str:
    """Stable, non-filesystem label for refs ingested via Outlook COM."""
    return f"outlook-com:{entry_id}"
