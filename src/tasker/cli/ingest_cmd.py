"""`tasker mail ingest` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from sqlmodel import Session

from tasker.cli.common import console
from tasker.domain.exceptions import MsgIngestError
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.ingest import ingest_msg_path


def ingest(
    path: Annotated[
        Path,
        typer.Argument(
            ...,
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
) -> None:
    """Parse a `.msg` file and create a pending task with stored email context."""
    if path.suffix.lower() != ".msg":
        console.print("[red]Expected a .msg file.[/red]")
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
            task, ref = ingest_msg_path(path=path, tasks=tasks, refs=refs)
            # Second commit in `refs.create` expires ORM instances; refresh before
            # session closes.
            session.refresh(task)
            session.refresh(ref)
        except MsgIngestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        finally:
            session.close()
    finally:
        engine.dispose()

    console.print(
        f"Created pending task [bold]{task.id}[/bold] "
        f"([cyan]{task.status.value}[/cyan]): {task.title}"
    )
    console.print(f"Linked message ref [bold]{ref.id}[/bold] → {ref.msg_path}")
    console.print(f"Projects configured: {len(config.projects)}")
