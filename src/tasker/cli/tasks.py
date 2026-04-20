"""Task CRUD commands: add, view, edit, remove."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table
from sqlmodel import Session

from tasker.cli.common import console, format_dt, parse_task_status
from tasker.domain.enums import TaskStatus
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository


def add(
    title: Annotated[
        str,
        typer.Option(
            ...,
            "--title",
            "-t",
            help="Task title.",
        ),
    ],
    project_id: Annotated[
        str,
        typer.Option(
            "--project-id",
            "-p",
            help="Project id from config (may be empty).",
        ),
    ] = "",
    status: Annotated[
        str,
        typer.Option(
            "--status",
            "-s",
            help="One of: draft, pending, active, done, archived.",
        ),
    ] = TaskStatus.DRAFT.value,
    notes: Annotated[
        str | None,
        typer.Option("--notes", help="Optional notes."),
    ] = None,
) -> None:
    """Create a task row (no `.msg` link; use `tasker ingest` for email)."""
    st = parse_task_status(status)
    try:
        _, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            task = tasks.create(
                title=title,
                project_id=project_id,
                status=st,
                notes=notes,
            )
        finally:
            session.close()
    finally:
        engine.dispose()

    console.print(
        f"Created task [bold]{task.id}[/bold] "
        f"([cyan]{task.status.value}[/cyan]): {task.title}"
    )


def view(
    task_id: Annotated[
        int | None,
        typer.Argument(help="Task id; omit to list all tasks."),
    ] = None,
) -> None:
    """Show one task or a summary list of all tasks."""
    try:
        _, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            refs = MessageRefRepository(session)
            if task_id is None:
                rows = tasks.list_all()
                if not rows:
                    console.print("[dim]No tasks.[/dim]")
                    return
                table = Table(title="Tasks")
                table.add_column("id", justify="right", style="cyan")
                table.add_column("status")
                table.add_column("project_id")
                table.add_column("title")
                table.add_column("updated", style="dim")
                for t in rows:
                    table.add_row(
                        str(t.id),
                        t.status.value,
                        t.project_id or "—",
                        t.title,
                        format_dt(t.updated_at),
                    )
                console.print(table)
                return

            task = tasks.get(task_id)
            if task is None:
                console.print(f"[red]No task with id {task_id}.[/red]")
                raise typer.Exit(code=1)
            message_refs = refs.list_for_task(task_id)
            lines = [
                f"[bold]id[/bold]: {task.id}",
                f"[bold]title[/bold]: {task.title}",
                f"[bold]status[/bold]: {task.status.value}",
                f"[bold]project_id[/bold]: {task.project_id or '—'}",
                f"[bold]created[/bold]: {format_dt(task.created_at)}",
                f"[bold]updated[/bold]: {format_dt(task.updated_at)}",
            ]
            if task.notes:
                lines.append(f"[bold]notes[/bold]: {task.notes}")
            if task.attachment_routes_json:
                arj = task.attachment_routes_json
                lines.append(f"[bold]attachment_routes_json[/bold]: {arj}")
            console.print(
                Panel("\n".join(lines), title=f"Task {task.id}", expand=False)
            )
            if not message_refs:
                console.print("[dim]No linked .msg references.[/dim]")
            else:
                ref_table = Table(title="Message references")
                ref_table.add_column("ref_id", justify="right", style="cyan")
                ref_table.add_column("msg_path")
                ref_table.add_column("subject", overflow="ellipsis", max_width=40)
                for r in message_refs:
                    ref_table.add_row(
                        str(r.id),
                        r.msg_path,
                        (r.subject or "—"),
                    )
                console.print(ref_table)
        finally:
            session.close()
    finally:
        engine.dispose()


def edit(
    task_id: Annotated[int, typer.Argument(help="Task id.")],
    title: Annotated[str | None, typer.Option("--title", "-t")] = None,
    status: Annotated[str | None, typer.Option("--status", "-s")] = None,
    project_id: Annotated[str | None, typer.Option("--project-id", "-p")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
) -> None:
    """Update fields on an existing task."""
    if all(v is None for v in (title, status, project_id, notes)):
        console.print(
            "[red]Provide at least one of --title, --status, "
            "--project-id, --notes.[/red]"
        )
        raise typer.Exit(code=1)

    st: TaskStatus | None = None
    if status is not None:
        st = parse_task_status(status)

    try:
        _, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            updated = tasks.update(
                task_id,
                title=title,
                status=st,
                project_id=project_id,
                notes=notes,
            )
        finally:
            session.close()
    finally:
        engine.dispose()

    if updated is None:
        console.print(f"[red]No task with id {task_id}.[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"Updated task [bold]{updated.id}[/bold] "
        f"([cyan]{updated.status.value}[/cyan]): {updated.title}"
    )


def remove_task(
    task_id: Annotated[int, typer.Argument(help="Task id.")],
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm deletion (required for non-interactive use).",
        ),
    ] = False,
) -> None:
    """Delete a task and its linked message references."""
    if not yes:
        console.print(
            "[red]Refusing to delete without --yes. Re-run with --yes to confirm.[/red]"
        )
        raise typer.Exit(code=1)

    try:
        _, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            deleted = tasks.delete_cascade(task_id)
        finally:
            session.close()
    finally:
        engine.dispose()

    if not deleted:
        console.print(f"[red]No task with id {task_id}.[/red]")
        raise typer.Exit(code=1)

    console.print(f"Deleted task [bold]{task_id}[/bold] and linked message refs.")
