"""`tasker doctor` command."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from tasker.cli.common import console, package_version, print_python_runtime
from tasker.cli.doctor_checks import (
    Check,
    CheckSeverity,
    run_doctor_checks,
    worst_severity,
)
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage


def _render_checks(checks: list[Check]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Status", width=6)
    table.add_column("Check")
    table.add_column("Detail")
    for c in checks:
        if c.severity == CheckSeverity.OK:
            status = "[green]ok[/green]"
        elif c.severity == CheckSeverity.WARN:
            status = "[yellow]warn[/yellow]"
        else:
            status = "[red]fail[/red]"
        detail = c.detail.replace("\n", "\n") if c.detail else "—"
        table.add_row(status, c.title, detail)
    console.print(table)


def doctor(
    check_ai: Annotated[
        bool,
        typer.Option(
            "--check-ai",
            help=(
                "Send a minimal chat-completions request "
                "(needs network and API key)."
            ),
        ),
    ] = False,
    strict_projects: Annotated[
        bool,
        typer.Option(
            "--strict-projects",
            help="Treat missing project roots as failures, not warnings.",
        ),
    ] = False,
) -> None:
    """
    Run health checks: environment, config, projects, database, and optional
    AI reachability.
    """
    console.print(f"Tasker version: [bold]{package_version()}[/bold]")
    print_python_runtime()

    try:
        home, config, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        checks = run_doctor_checks(
            home=home,
            config=config,
            engine=engine,
            strict_projects=strict_projects,
            check_ai_live_request=check_ai,
        )
        _render_checks(checks)
        worst = worst_severity(checks)
        if worst == CheckSeverity.FAIL:
            raise typer.Exit(code=1)
    finally:
        engine.dispose()
