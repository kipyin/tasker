"""Legacy alias: inbox list command (see ``tasker.cli.mail_subcommands``)."""

from __future__ import annotations

from tasker.cli.mail_subcommands import mail_inbox as outlook_recent

__all__ = ["outlook_recent"]
