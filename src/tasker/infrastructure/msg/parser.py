"""Parse Outlook `.msg` files via extract-msg."""

from __future__ import annotations

import json
from pathlib import Path

from extract_msg import openMsg
from extract_msg.exceptions import InvalidFileFormatError

from tasker.domain.exceptions import MsgIngestError
from tasker.domain.parsed_msg import ParsedMsg

_OUTLOOK_MESSAGE_ATTRS = ("sender", "to", "cc", "bcc", "subject", "body", "attachments")


def _safe_str(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _looks_like_outlook_message(msg: object) -> bool:
    return all(hasattr(msg, name) for name in _OUTLOOK_MESSAGE_ATTRS)


def _attachment_names(msg: object) -> tuple[str, ...]:
    names: list[str] = []
    try:
        for att in msg.attachments:
            name = getattr(att, "name", None)
            names.append(_safe_str(name) or "(unnamed attachment)")
    except Exception:
        return ()
    return tuple(names)


def parse_msg_file(path: Path) -> ParsedMsg:
    """
    Extract sender, recipients, subject, plain body, and attachment names.

    Raises MsgIngestError if the file is missing, not a valid MSG, or parsing fails.
    """
    resolved = path.expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise MsgIngestError(f"File not found: {resolved}")

    try:
        with openMsg(str(resolved)) as msg:
            if _looks_like_outlook_message(msg):
                sender = _safe_str(msg.sender)
                to_ = _safe_str(msg.to)
                cc = _safe_str(msg.cc)
                bcc = _safe_str(msg.bcc)
                subject = _safe_str(msg.subject)
                body = _safe_str(msg.body)
                attachments = _attachment_names(msg)
            else:
                sender = to_ = cc = bcc = subject = body = ""
                attachments = ()
    except MsgIngestError:
        raise
    except InvalidFileFormatError as exc:
        raise MsgIngestError(f"Not a valid Outlook .msg file: {resolved}") from exc
    except OSError as exc:
        raise MsgIngestError(f"Cannot read file: {resolved}") from exc
    except Exception as exc:
        raise MsgIngestError(f"Failed to parse .msg: {resolved}") from exc

    return ParsedMsg(
        sender=sender,
        recipients_to=to_,
        recipients_cc=cc,
        recipients_bcc=bcc,
        subject=subject,
        body_text=body,
        attachment_names=attachments,
    )


def attachment_names_to_json(names: tuple[str, ...]) -> str | None:
    if not names:
        return None
    return json.dumps(list(names))
