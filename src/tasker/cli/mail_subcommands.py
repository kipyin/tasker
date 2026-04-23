"""`tasker mail` inbox listing and row-indexed message actions (Outlook COM)."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.table import Table
from sqlmodel import Session

from tasker.cli.common import console, format_dt
from tasker.domain.exceptions import OutlookCOMError, OutlookNotAvailableError
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.outlook import InboxMessageSummary, list_recent_inbox
from tasker.infrastructure.outlook.inbox import get_inbox_message_at_index
from tasker.infrastructure.outlook.inbox_actions import (
    apply_message_archive,
    apply_message_categories,
    apply_message_delete,
    apply_message_flag,
    apply_message_read,
)
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_outlook_entry

_DEFAULT_LIMIT = 20


def _outlook_com_error(exc: Exception) -> None:
    if isinstance(exc, OutlookCOMError):
        console.print(f"[red]{exc}[/red]")
    else:
        console.print(f"[yellow]{exc}[/yellow]")


def _row_dict(m: InboxMessageSummary, one_based_index: int) -> dict[str, object]:
    return {
        "index": one_based_index,
        "subject": m.subject,
        "received": m.received.isoformat(),
        "sender_display": m.sender_display,
        "unread": m.unread,
    }


def mail_inbox(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum number of messages (most recent first, 1–200).",
        ),
    ] = _DEFAULT_LIMIT,
    as_json: Annotated[
        bool,
        typer.Option(
            "--json",
            help="JSON output (includes row index).",
        ),
    ] = False,
) -> None:
    """List recent Inbox; use the # column with other mail subcommands."""
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
        payload = [
            _row_dict(m, i + 1) for i, m in enumerate(messages)
        ]
        console.print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="magenta", justify="right", no_wrap=True)
    table.add_column("Received", style="cyan", no_wrap=True)
    table.add_column("U", width=3)
    table.add_column("From")
    table.add_column("Subject")
    for i, m in enumerate(messages, start=1):
        u = "●" if m.unread else " "
        table.add_row(
            str(i),
            format_dt(m.received),
            u,
            m.sender_display,
            m.subject,
        )
    console.print(table)


def _message_for_action(
    index: int,
    limit: int,
) -> InboxMessageSummary:
    try:
        return get_inbox_message_at_index(index, limit=limit)
    except OutlookNotAvailableError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc
    except OutlookCOMError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc


def mail_read(
    index: Annotated[
        int,
        typer.Argument(
            min=1,
            help="1-based row from `tasker mail inbox` (same --limit).",
        ),
    ],
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Must match the window used when you picked the index (1–200).",
        ),
    ] = _DEFAULT_LIMIT,
    unread: Annotated[
        bool,
        typer.Option("--unread", help="Mark as unread instead of read."),
    ] = False,
) -> None:
    """Mark a recent Inbox message as read, or with --unread as unread."""
    m = _message_for_action(index, limit)
    try:
        apply_message_read(m.entry_id, m.store_id, unread=unread)
    except (OutlookNotAvailableError, OutlookCOMError) as exc:
        _outlook_com_error(exc)
        raise typer.Exit(code=1) from exc
    state = "unread" if unread else "read"
    subj = (m.subject or "(no subject)").replace("\n", " ")[:60]
    console.print(f"Marked {state}: [bold]{subj}[/bold]")


def mail_flag(
    index: Annotated[
        int,
        typer.Argument(
            min=1,
            help="1-based row from `tasker mail inbox` (same --limit).",
        ),
    ],
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Must match the window used when you picked the index (1–200).",
        ),
    ] = _DEFAULT_LIMIT,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            help="Remove the follow-up flag instead of setting it.",
        ),
    ] = False,
) -> None:
    """Set or clear the follow-up flag on a recent Inbox message."""
    m = _message_for_action(index, limit)
    try:
        apply_message_flag(m.entry_id, m.store_id, clear=clear)
    except (OutlookNotAvailableError, OutlookCOMError) as exc:
        _outlook_com_error(exc)
        raise typer.Exit(code=1) from exc
    action = "Cleared flag for" if clear else "Flagged"
    subj = (m.subject or "(no subject)").replace("\n", " ")[:60]
    console.print(f"{action}: [bold]{subj}[/bold]")


def mail_categories(
    index: Annotated[
        int,
        typer.Argument(
            min=1,
            help="1-based row from `tasker mail inbox` (same --limit).",
        ),
    ],
    set_value: Annotated[
        str,
        typer.Option(
            "--set",
            help='Categories (semicolon-separated), e.g. "Red; Client".',
        ),
    ] = "",
    append: Annotated[
        bool,
        typer.Option(
            "--append",
            help="Add these categories to existing ones (de-duplicated).",
        ),
    ] = False,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Must match the window used when you picked the index (1–200).",
        ),
    ] = _DEFAULT_LIMIT,
) -> None:
    """Set or append semicolon-separated Outlook categories on a message."""
    m = _message_for_action(index, limit)
    if not (set_value or "").strip() and not append:
        console.print(
            "[yellow]Use --set with categories, or use --append with --set.[/yellow]",
        )
        raise typer.Exit(code=1)
    if not (set_value or "").strip() and append:
        console.print(
            "[yellow]--append requires --set with at least one category.[/yellow]",
        )
        raise typer.Exit(code=1)
    try:
        apply_message_categories(
            m.entry_id,
            m.store_id,
            set_value,
            append=append,
        )
    except (OutlookNotAvailableError, OutlookCOMError) as exc:
        _outlook_com_error(exc)
        raise typer.Exit(code=1) from exc
    subj = (m.subject or "(no subject)").replace("\n", " ")[:60]
    console.print(f"Updated categories for: [bold]{subj}[/bold]")


def mail_archive(
    index: Annotated[
        int,
        typer.Argument(
            min=1,
            help="1-based row from `tasker mail inbox` (same --limit).",
        ),
    ],
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Must match the window used when you picked the index (1–200).",
        ),
    ] = _DEFAULT_LIMIT,
) -> None:
    """Move a recent Inbox message to the mailbox Archive folder."""
    m = _message_for_action(index, limit)
    try:
        apply_message_archive(m.entry_id, m.store_id)
    except (OutlookNotAvailableError, OutlookCOMError) as exc:
        _outlook_com_error(exc)
        raise typer.Exit(code=1) from exc
    subj = (m.subject or "(no subject)").replace("\n", " ")[:60]
    console.print(f"Archived: [bold]{subj}[/bold]")


def mail_delete(
    index: Annotated[
        int,
        typer.Argument(
            min=1,
            help="1-based row from `tasker mail inbox` (same --limit).",
        ),
    ],
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Must match the window used when you picked the index (1–200).",
        ),
    ] = _DEFAULT_LIMIT,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Do not confirm; move the message to Deleted Items.",
        ),
    ] = False,
) -> None:
    """Delete a recent Inbox message (moves to Deleted Items)."""
    m = _message_for_action(index, limit)
    subj = (m.subject or "(no subject)").replace("\n", " ")[:80]
    if not yes and not typer.confirm(
        f"Move to Deleted Items?  {subj}",
    ):
        raise typer.Abort
    try:
        apply_message_delete(m.entry_id, m.store_id)
    except (OutlookNotAvailableError, OutlookCOMError) as exc:
        _outlook_com_error(exc)
        raise typer.Exit(code=1) from exc
    console.print(f"Deleted (Deleted Items): [bold]{subj}[/bold]")


def mail_capture(
    index: Annotated[
        int,
        typer.Argument(
            min=1,
            help="1-based row from `tasker mail inbox` (same --limit).",
        ),
    ],
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Must match the window used when you picked the index (1–200).",
        ),
    ] = _DEFAULT_LIMIT,
) -> None:
    """Create a pending task from a message in your local Outlook (no `.msg` file)."""
    m = _message_for_action(index, limit)

    try:
        _, config, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            refs = MessageRefRepository(session)
            try:
                task, ref = ingest_outlook_entry(
                    entry_id=m.entry_id,
                    store_id=m.store_id,
                    tasks=tasks,
                    refs=refs,
                )
            except (OutlookNotAvailableError, OutlookCOMError, ValueError) as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc
            session.refresh(task)
            session.refresh(ref)
        finally:
            session.close()
    finally:
        engine.dispose()

    console.print(
        f"Created pending task [bold]{task.id}[/bold] "
        f"([cyan]{task.status.value}[/cyan]): {task.title}",
    )
    console.print(
        f"Linked Outlook message ref [bold]{ref.id}[/bold] "
        f"(entry_id set; msg_path label: {ref.msg_path})",
    )
    console.print(f"Projects configured: {len(config.projects)}")
