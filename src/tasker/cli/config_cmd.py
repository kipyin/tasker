"""`tasker config` subcommands."""

from __future__ import annotations

import typer
from rich.syntax import Syntax

from tasker.cli.common import console
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.paths import CONFIG_FILENAME

config_app = typer.Typer(help="Inspect Tasker configuration.")


def config_show() -> None:
    """Print the config file path and full TOML contents."""
    try:
        home, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        cfg_file = home / CONFIG_FILENAME
        console.print(f"Config path: [bold]{cfg_file}[/bold]")
        text = cfg_file.read_text(encoding="utf-8")
        console.print(Syntax(text, "toml", theme="monokai", line_numbers=False))
    finally:
        engine.dispose()


def config_path_cmd() -> None:
    """Print the config file path only (for scripts)."""
    try:
        home, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        console.print((home / CONFIG_FILENAME).resolve())
    finally:
        engine.dispose()
