"""`tasker config` subcommands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.syntax import Syntax

from tasker.cli.common import console
from tasker.cli.deprecation import warn_renamed
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.paths import CONFIG_FILENAME

config_app = typer.Typer(help="Inspect Tasker configuration.")


def _print_config(*, path_only: bool) -> None:
    try:
        home, _, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    try:
        cfg_file = home / CONFIG_FILENAME
        resolved = cfg_file.resolve()
        if path_only:
            console.print(str(resolved))
            return
        console.print(f"Config path: [bold]{cfg_file}[/bold]")
        text = cfg_file.read_text(encoding="utf-8")
        console.print(Syntax(text, "toml", theme="monokai", line_numbers=False))
    finally:
        engine.dispose()


def config_show(
    path_only: Annotated[
        bool,
        typer.Option(
            "--path-only",
            help="Print only the resolved config file path (for scripts).",
        ),
    ] = False,
) -> None:
    """Print the config file path and full TOML, or only the path with --path-only."""
    _print_config(path_only=path_only)


def config_path_legacy() -> None:
    """Deprecated alias for `tasker config show --path-only`."""
    warn_renamed("`tasker config path`", "`tasker config show --path-only`")
    _print_config(path_only=True)
