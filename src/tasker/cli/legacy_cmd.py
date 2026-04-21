"""Deprecated top-level command spellings; delegate to current implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from tasker.cli.classify_cmd import classify_task
from tasker.cli.deprecation import warn_renamed
from tasker.cli.ingest_cmd import ingest
from tasker.cli.route_cmd import route_attachments
from tasker.cli.tasks import add, delete_task, edit, list_tasks, show_task
from tasker.domain.enums import TaskStatus


def add_legacy(
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
    warn_renamed("`tasker add`", "`tasker task add`")
    add(title=title, project_id=project_id, status=status, notes=notes)


def view_legacy(
    task_id: Annotated[
        int | None,
        typer.Argument(help="Task id; omit to list all tasks."),
    ] = None,
) -> None:
    warn_renamed("`tasker view`", "`tasker task list` or `tasker task show`")
    if task_id is None:
        list_tasks()
    else:
        show_task(task_id)


def edit_legacy(
    task_id: Annotated[int, typer.Argument(help="Task id.")],
    title: Annotated[str | None, typer.Option("--title", "-t")] = None,
    status: Annotated[str | None, typer.Option("--status", "-s")] = None,
    project_id: Annotated[str | None, typer.Option("--project-id", "-p")] = None,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
) -> None:
    warn_renamed("`tasker edit`", "`tasker task edit`")
    edit(
        task_id=task_id,
        title=title,
        status=status,
        project_id=project_id,
        notes=notes,
    )


def remove_legacy(
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
    warn_renamed("`tasker remove`", "`tasker task delete`")
    delete_task(task_id=task_id, yes=yes)


def ingest_legacy(
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
    warn_renamed("`tasker ingest`", "`tasker mail ingest`")
    ingest(path)


def classify_legacy(
    task_id: Annotated[
        int,
        typer.Argument(help="Pending task id from `tasker mail ingest`."),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Fetch and show the AI proposal only; do not write to the database.",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Apply the proposal without a confirmation prompt.",
        ),
    ] = False,
) -> None:
    warn_renamed("`tasker classify`", "`tasker mail classify`")
    classify_task(task_id=task_id, dry_run=dry_run, yes=yes)


def route_attachments_legacy(
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
    warn_renamed("`tasker route-attachments`", "`tasker mail save-attachments`")
    route_attachments(task_id=task_id, dry_run=dry_run)
