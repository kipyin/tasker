"""`tasker mail outlook-recent` — list recent Inbox messages via Outlook COM."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.table import Table

from tasker.cli.common import console, format_dt
from tasker.domain.exceptions import OutlookCOMError, OutlookNotAvailableError
from tasker.infrastructure.outlook import InboxMessageSummary, list_recent_inbox


def _row_dict(m: InboxMessageSummary) -> dict[str, object]:
    return {
        "entry_id": m.entry_id,
        "subject": m.subject,
        "received": m.received.isoformat(),
        "sender_display": m.sender_display,
        "unread": m.unread,
    }


def outlook_recent(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum number of messages (most recent first, 1–200).",
        ),
    ] = 20,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print JSON instead of a table."),
    ] = False,
) -> None:
    """List recent Inbox messages (metadata only, read-only)."""
    try:
        messages = list_recent_inbox(limit)
    except OutlookNotAvailableError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc
    except OutlookCOMError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    if as_json:
        payload = [_row_dict(m) for m in messages]
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Received", style="cyan", no_wrap=True)
    table.add_column("U", width=3)
    table.add_column("From")
    table.add_column("Subject")
    for m in messages:
        u = "●" if m.unread else " "
        table.add_row(
            format_dt(m.received),
            u,
            m.sender_display,
            m.subject,
        )
    console.print(table)
