"""Adapters for Microsoft Outlook `.msg` files."""

from tasker.infrastructure.msg.parser import attachment_names_to_json, parse_msg_file

__all__ = [
    "attachment_names_to_json",
    "parse_msg_file",
]
