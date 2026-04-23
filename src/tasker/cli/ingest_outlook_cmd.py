"""Backward-compatible name for :func:`tasker.cli.mail_subcommands.mail_capture`."""

from __future__ import annotations

from tasker.cli.mail_subcommands import mail_capture as ingest_outlook

__all__ = ["ingest_outlook"]
