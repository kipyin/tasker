"""Structured result of parsing a `.msg` file (no persistence)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedMsg:
    """Email fields extracted from an Outlook `.msg` file."""

    sender: str
    recipients_to: str
    recipients_cc: str
    recipients_bcc: str
    subject: str
    body_text: str
    attachment_names: tuple[str, ...]
