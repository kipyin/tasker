"""`tasker mail ingest-outlook` — pending task from live Outlook via COM."""

from __future__ import annotations

from typing import Annotated

import typer
from sqlmodel import Session

from tasker.cli.common import console
from tasker.domain.exceptions import OutlookCOMError, OutlookNotAvailableError
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_outlook_entry


def ingest_outlook(
    entry_id: Annotated[
        str,
        typer.Option(
            "--entry-id",
            help=(
                "Outlook MailItem EntryID "
                "(e.g. from `tasker mail outlook-recent --json`)."
            ),
        ),
    ],
    store_id: Annotated[
        str | None,
        typer.Option(
            "--store-id",
            help="Optional store ID for GetItemFromID (multi-mailbox / Exchange).",
        ),
    ] = None,
) -> None:
    """Create a pending task from a message in your local Outlook (no `.msg` file)."""
    eid = (entry_id or "").strip()
    if not eid:
        console.print("[red]--entry-id is required.[/red]")
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
            try:
                task, ref = ingest_outlook_entry(
                    entry_id=eid,
                    store_id=store_id,
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
