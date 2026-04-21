"""`tasker project` subcommands: list/add/edit/remove projects in config."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table
from sqlalchemy.engine import Engine

from tasker.cli.common import console
from tasker.infrastructure.config.schema import ProjectConfig
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.paths import CONFIG_FILENAME
from tasker.services.config_file import (
    ConfigMutationError,
    add_project,
    mutate_config_file,
    read_config_or_default,
    remove_project,
    update_project,
)

project_app = typer.Typer(help="Manage projects in Tasker configuration.")


def _config_file_path() -> tuple[Path, Engine]:
    """Return (cfg_path, engine) after ensuring layout; caller must dispose engine."""
    home, _, engine = prepare_local_storage()
    return home / CONFIG_FILENAME, engine


def project_list() -> None:
    """List configured projects (id, name, root)."""
    try:
        cfg_path, engine = _config_file_path()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        cfg = read_config_or_default(cfg_path)
        if not cfg.projects:
            console.print("[dim]No projects configured.[/dim]")
            return
        table = Table(title="Projects")
        table.add_column("id", style="cyan")
        table.add_column("name")
        table.add_column("root")
        for p in cfg.projects:
            table.add_row(p.id, p.name, p.root)
        console.print(table)
    finally:
        engine.dispose()


def project_add(
    project_id: Annotated[str, typer.Option("--id", "-i", help="Stable project id.")],
    name: Annotated[str, typer.Option("--name", "-n", help="Display name.")],
    root: Annotated[str, typer.Option("--root", "-r", help="Working directory path.")],
) -> None:
    """Add a project to the configuration file."""
    try:
        cfg_path, engine = _config_file_path()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        def _add(c):
            return add_project(
                c,
                ProjectConfig(id=project_id, name=name, root=root),
            )

        mutate_config_file(cfg_path, _add)
    except ConfigMutationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()

    console.print(f"Added project [bold]{project_id}[/bold].")


def project_edit(
    project_id: Annotated[str, typer.Argument(help="Existing project id.")],
    name: Annotated[str | None, typer.Option("--name", "-n")] = None,
    root: Annotated[str | None, typer.Option("--root", "-r")] = None,
    new_id: Annotated[
        str | None,
        typer.Option("--new-id", help="Rename project id."),
    ] = None,
    clear_default_bucket: Annotated[
        bool,
        typer.Option(
            "--clear-default-bucket",
            help="Clear default_bucket for this project.",
        ),
    ] = False,
    default_bucket: Annotated[
        str | None,
        typer.Option("--default-bucket", help="Set default attachment bucket name."),
    ] = None,
) -> None:
    """Update fields on an existing project."""
    no_field_changes = all(
        v is None for v in (name, root, new_id, default_bucket)
    )
    if no_field_changes and not clear_default_bucket:
        console.print(
            "[red]Provide at least one of --name, --root, --new-id, "
            "--default-bucket, or --clear-default-bucket.[/red]",
        )
        raise typer.Exit(code=1)

    try:
        cfg_path, engine = _config_file_path()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        mutate_config_file(
            cfg_path,
            lambda c: update_project(
                c,
                project_id,
                name=name,
                root=root,
                new_id=new_id,
                default_bucket=default_bucket,
                unset_default_bucket=clear_default_bucket,
            ),
        )
    except ConfigMutationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()

    console.print(f"Updated project [bold]{project_id}[/bold].")


def project_remove(
    project_id: Annotated[str, typer.Argument(help="Project id to remove.")],
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm removal (required for non-interactive use).",
        ),
    ] = False,
) -> None:
    """Remove a project from the configuration file."""
    if not yes:
        console.print(
            "[red]Refusing to remove without --yes. "
            "Re-run with --yes to confirm.[/red]",
        )
        raise typer.Exit(code=1)

    try:
        cfg_path, engine = _config_file_path()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        mutate_config_file(cfg_path, lambda c: remove_project(c, project_id))
    except ConfigMutationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()

    console.print(f"Removed project [bold]{project_id}[/bold].")


project_app.command("list")(project_list)
project_app.command("add")(project_add)
project_app.command("edit")(project_edit)
project_app.command("remove")(project_remove)
