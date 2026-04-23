"""Windows-only Outlook COM: inbox message mutations."""

from __future__ import annotations

from typing import Any

import pywintypes
import win32com.client

from tasker.domain.exceptions import OutlookCOMError
from tasker.infrastructure.outlook._inbox_win32 import _str_prop
from tasker.infrastructure.outlook._mail_item_win32 import get_mail_item
from tasker.infrastructure.outlook.category_util import merge_category_strings

# OlFlagStatus — numeric; win32com.client.constants may not be populated.
_OL_FLAG_NONE = 0
_OL_FLAG_MARKED = 2


def _archive_folder_for_item(item: Any) -> Any:
    try:
        store = item.Parent.Store
    except pywintypes.com_error as exc:
        raise OutlookCOMError(
            "Could not resolve mailbox store for this message.",
        ) from exc
    try:
        constants = win32com.client.constants
        code = getattr(constants, "olFolderArchive", None)
        if code is not None:
            return store.GetDefaultFolder(code)
    except pywintypes.com_error:
        pass
    try:
        root = store.GetRootFolder()
        folders = root.Folders
        n = int(folders.Count)
    except pywintypes.com_error as exc:
        raise OutlookCOMError("Could not list folders to find Archive.") from exc
    for i in range(1, n + 1):
        try:
            f = folders.Item(i)
        except pywintypes.com_error:
            continue
        name = _str_prop(f, "Name", "")
        if name.strip().lower() == "archive":
            return f
    raise OutlookCOMError(
        "Could not find an Archive folder for this mailbox "
        '(expected a top-level folder named "Archive").',
    )


def apply_message_read_win32(
    entry_id: str,
    store_id: str | None,
    *,
    unread: bool = False,
) -> None:
    item = get_mail_item(entry_id, store_id)
    try:
        item.UnRead = bool(unread)
    except pywintypes.com_error as exc:
        raise OutlookCOMError(
            "Could not change read/unread state for this message.",
        ) from exc


def apply_message_flag_win32(
    entry_id: str,
    store_id: str | None,
    *,
    clear: bool = False,
) -> None:
    item = get_mail_item(entry_id, store_id)
    try:
        item.FlagStatus = _OL_FLAG_NONE if clear else _OL_FLAG_MARKED
    except pywintypes.com_error as exc:
        raise OutlookCOMError("Could not change flag state for this message.") from exc


def apply_message_categories_win32(
    entry_id: str,
    store_id: str | None,
    categories: str,
    *,
    append: bool = False,
) -> None:
    item = get_mail_item(entry_id, store_id)
    new_value = (
        categories.strip()
        if not append
        else merge_category_strings(_str_prop(item, "Categories", ""), categories)
    )
    try:
        item.Categories = new_value
    except pywintypes.com_error as exc:
        raise OutlookCOMError("Could not set categories for this message.") from exc


def apply_message_archive_win32(entry_id: str, store_id: str | None) -> None:
    item = get_mail_item(entry_id, store_id)
    dest = _archive_folder_for_item(item)
    try:
        item.Move(dest)
    except pywintypes.com_error as exc:
        raise OutlookCOMError("Could not move this message to Archive.") from exc


def apply_message_delete_win32(entry_id: str, store_id: str | None) -> None:
    item = get_mail_item(entry_id, store_id)
    try:
        item.Delete()
    except pywintypes.com_error as exc:
        raise OutlookCOMError("Could not delete this message.") from exc
