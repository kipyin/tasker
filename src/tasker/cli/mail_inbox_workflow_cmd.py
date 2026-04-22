"""Interactive Outlook inbox → task → classify (questionary; no EntryID for users)."""

from __future__ import annotations

from typing import Annotated

import questionary
import typer
from sqlmodel import Session

from tasker.cli.classify_flow import run_classification_for_task
from tasker.cli.common import console, format_dt
from tasker.domain.exceptions import OutlookCOMError, OutlookNotAvailableError
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.outlook import InboxMessageSummary, list_recent_inbox
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_outlook_entry


def _choice_label(m: InboxMessageSummary) -> str:
    u = "● " if m.unread else "  "
    subj = (m.subject or "(no subject)").replace("\n", " ")
    if len(subj) > 72:
        subj = subj[:69] + "..."
    return f"{u}{format_dt(m.received)}  {m.sender_display}  —  {subj}"


def mail_inbox_workflow(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Recent Inbox messages to show (1–200, same order as outlook-recent).",
        ),
    ] = 20,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Stop after the AI proposal; do not write classification to the DB.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Apply AI classification without a confirmation prompt.",
        ),
    ] = False,
) -> None:
    """
    Pick a recent Inbox message, create a pending task, then run AI classification.

    Uses the same recent-Inbox ordering as ``tasker mail outlook-recent``. Entry IDs
    are resolved internally after you choose a row.
    """
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

    if not messages:
        console.print(
            "[yellow]Inbox has no mail items in the requested window.[/yellow]"
        )
        raise typer.Exit(code=1)

    choices = [
        questionary.Choice(title=_choice_label(m), value=m) for m in messages
    ]
    picked = questionary.select(
        "Choose a message to turn into a task",
        choices=choices,
    ).ask()

    if picked is None:
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    try:
        fresh = list_recent_inbox(limit)
    except (OutlookNotAvailableError, OutlookCOMError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    resolved = next((m for m in fresh if m.entry_id == picked.entry_id), None)
    if resolved is None:
        console.print(
            "[yellow]That message is no longer in the recent Inbox window; "
            "re-run and pick again.[/yellow]"
        )
        raise typer.Exit(code=1)

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
            task, ref = ingest_outlook_entry(
                entry_id=resolved.entry_id,
                store_id=None,
                tasks=tasks,
                refs=refs,
            )
            session.refresh(task)
            session.refresh(ref)
        finally:
            session.close()
    finally:
        engine.dispose()

    console.print(
        f"Created pending task [bold]{task.id}[/bold] "
        f"([cyan]{task.status.value}[/cyan]): {task.title}"
    )
    console.print(f"Projects configured: {len(config.projects)}")

    run_classification_for_task(int(task.id), dry_run=dry_run, yes=yes)
