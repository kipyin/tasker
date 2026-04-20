"""`tasker route-attachments` command."""

from __future__ import annotations

from typing import Annotated

import typer
from sqlmodel import Session

from tasker.cli.common import console
from tasker.domain.exceptions import RoutingError
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.routing import route_task_attachments


def route_attachments(
    task_id: Annotated[
        int,
        typer.Argument(help="Task id with a linked .msg and assigned project."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help=(
                "Show planned destinations only; do not move files or update the task."
            ),
        ),
    ] = False,
) -> None:
    """
    Move attachments from the task's `.msg` into project buckets per config rules.

    Requires `project_id` on the task and bucket/routing rules in config. Operations
    are appended to `<data-dir>/logs/routing.jsonl`.
    """
    try:
        home, config, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            refs = MessageRefRepository(session)
            try:
                records = route_task_attachments(
                    home=home,
                    config=config,
                    tasks=tasks,
                    refs=refs,
                    task_id=task_id,
                    dry_run=dry_run,
                )
            except RoutingError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc
        finally:
            session.close()
    finally:
        engine.dispose()

    for rec in records:
        bucket_s = rec.bucket or "—"
        console.print(
            f"[bold]{rec.filename}[/bold] → bucket [cyan]{bucket_s}[/cyan] "
            f"([magenta]{rec.action}[/magenta]) {rec.dest_path or ''}"
        )
        if rec.detail:
            console.print(f"  [dim]{rec.detail}[/dim]")
    if dry_run:
        console.print("[dim]Dry run: no files were moved.[/dim]")
    else:
        console.print(f"[dim]Logged to {home / 'logs' / 'routing.jsonl'}[/dim]")
