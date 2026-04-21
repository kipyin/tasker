"""Windows-only: resolve MailItem by EntryID and map to ParsedMsg."""

from __future__ import annotations

from typing import Any

import pywintypes
import win32com.client

from tasker.domain.exceptions import OutlookCOMError
from tasker.domain.parsed_msg import ParsedMsg
from tasker.infrastructure.outlook._inbox_win32 import _OL_MAIL, _str_prop


def get_mail_item(entry_id: str, store_id: str | None) -> Any:
    """Return Outlook ``MailItem`` for ``entry_id`` (and optional ``store_id``)."""
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        session = outlook.GetNamespace("MAPI")
        if store_id:
            item = session.GetItemFromID(entry_id, store_id)
        else:
            item = session.GetItemFromID(entry_id)
    except pywintypes.com_error as exc:
        raise OutlookCOMError(
            "Could not open the Outlook message (invalid or stale EntryID, "
            "or Outlook not available).",
        ) from exc
    try:
        if item.Class != _OL_MAIL:
            raise OutlookCOMError("The item is not a mail message.")
    except pywintypes.com_error as exc:
        raise OutlookCOMError("Could not read the Outlook message type.") from exc
    return item


def mail_item_to_parsed_msg(item: Any) -> ParsedMsg:
    """Map a COM ``MailItem`` to :class:`ParsedMsg` (plain body, attachment names)."""
    sender = _str_prop(item, "SenderEmailAddress") or _str_prop(item, "SenderName")
    to_ = _str_prop(item, "To")
    cc = _str_prop(item, "CC")
    bcc = _str_prop(item, "BCC")
    subject = _str_prop(item, "Subject")
    body = _str_prop(item, "Body")

    names: list[str] = []
    try:
        attachments = item.Attachments
        n = int(attachments.Count)
    except pywintypes.com_error:
        n = 0
    for i in range(1, n + 1):
        try:
            att = attachments.Item(i)
        except pywintypes.com_error:
            continue
        name = _str_prop(att, "FileName")
        names.append(name if name else "(unnamed attachment)")

    return ParsedMsg(
        sender=sender,
        recipients_to=to_,
        recipients_cc=cc,
        recipients_bcc=bcc,
        subject=subject,
        body_text=body,
        attachment_names=tuple(names),
    )


def fetch_parsed_msg_from_outlook_win32(
    entry_id: str,
    store_id: str | None,
) -> ParsedMsg:
    item = get_mail_item(entry_id, store_id)
    return mail_item_to_parsed_msg(item)
