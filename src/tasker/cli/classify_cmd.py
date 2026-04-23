"""`tasker mail classify` command."""

from __future__ import annotations

from typing import Annotated

import typer

from tasker.cli.classify_flow import run_classification_for_task


def classify_task(
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
    """
    Propose a project via the configured BYOK model; confirm before any DB update.

    Requires a linked message (from `tasker mail ingest` or
    `tasker mail capture`) and at least one project in config.
    """
    run_classification_for_task(task_id, dry_run=dry_run, yes=yes)
