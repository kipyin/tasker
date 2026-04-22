"""Shared classification flow for CLI commands (ingest + classify reuse)."""

from __future__ import annotations

import questionary
import typer
from rich.panel import Panel
from sqlmodel import Session

from tasker.cli.common import console
from tasker.domain.exceptions import AIClientError, ClassificationError
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository
from tasker.services.classification import (
    apply_confirmed_proposal,
    load_task_primary_ref,
    request_classification_proposal,
    resolve_api_key,
)


def run_classification_for_task(
    task_id: int,
    *,
    dry_run: bool,
    yes: bool,
) -> None:
    """
    Load task + ref, request AI proposal, optionally apply after confirm.

    When ``dry_run`` is True, no prompts and no DB writes after the proposal.
    When ``yes`` is True, applies without a confirmation prompt.
    """
    try:
        _, config, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        try:
            api_key = resolve_api_key(config)
        except ClassificationError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            refs = MessageRefRepository(session)
            try:
                task, ref = load_task_primary_ref(
                    tasks=tasks, refs=refs, task_id=task_id
                )
            except ClassificationError as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc

            try:
                proposal = request_classification_proposal(
                    config=config,
                    task=task,
                    ref=ref,
                    api_key=api_key,
                )
            except (ClassificationError, AIClientError) as exc:
                console.print(f"[red]{exc}[/red]")
                raise typer.Exit(code=1) from exc
        finally:
            session.close()
    finally:
        engine.dispose()

    lines = [
        f"[bold]project_id[/bold]: {proposal.project_id}",
        f"[bold]rationale[/bold]: {proposal.rationale}",
    ]
    if proposal.suggested_title:
        lines.append(f"[bold]suggested_title[/bold]: {proposal.suggested_title}")
    console.print(
        Panel(
            "\n".join(lines),
            title="AI classification proposal",
            expand=False,
        )
    )

    if dry_run:
        console.print("[dim]Dry run: no changes were written.[/dim]")
        return

    if yes:
        confirmed = True
    else:
        confirmed = questionary.confirm(
            "Apply this classification "
            "(set project, activate task, append rationale to notes)?",
            default=False,
        ).ask()

    if confirmed is not True:
        console.print("[yellow]Aborted; database unchanged.[/yellow]")
        raise typer.Exit(0)

    try:
        _, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        session = Session(engine)
        try:
            tasks = TaskRepository(session)
            updated = apply_confirmed_proposal(
                tasks=tasks,
                task_id=task_id,
                proposal=proposal,
            )
        finally:
            session.close()
    finally:
        engine.dispose()

    console.print(
        f"Updated task [bold]{updated.id}[/bold] → "
        f"[cyan]{updated.status.value}[/cyan] "
        f"project [bold]{updated.project_id!r}[/bold]: {updated.title}"
    )
