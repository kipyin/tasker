"""`tasker doctor` command."""

from __future__ import annotations

import typer

from tasker.cli.common import console, package_version, print_python_runtime
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.paths import CONFIG_FILENAME, DATABASE_FILENAME


def doctor() -> None:
    """Print version, Python, Tasker data directory, and database status."""
    console.print(f"Tasker version: [bold]{package_version()}[/bold]")
    print_python_runtime()

    try:
        home, config, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        db = home / DATABASE_FILENAME
        cfg_path = home / CONFIG_FILENAME
        console.print(f"Tasker data directory: {home}")
        console.print(f"Config file: {cfg_path}")
        console.print(f"Projects configured: {len(config.projects)}")
        console.print(f"Database path: {db}")
        console.print(f"Database exists: {'yes' if db.is_file() else 'no'}")
    finally:
        engine.dispose()
