"""Interactive `tasker setup` wizard (AI settings + projects via config helpers)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import questionary
import typer

from tasker.cli.common import console
from tasker.infrastructure.config.schema import ProjectConfig
from tasker.infrastructure.lifecycle import TaskerLayoutError, prepare_local_storage
from tasker.paths import CONFIG_FILENAME
from tasker.services.config_file import (
    ConfigMutationError,
    add_project,
    mutate_config_file,
    read_config_or_default,
    update_ai_config,
)


class SetupPrompter(Protocol):
    """Minimal prompt surface for `run_setup` (swap in fakes in tests)."""

    def text(self, message: str, *, default: str = "") -> str:
        """Return user text; implementation may raise on cancel."""

    def password(self, message: str) -> str:
        """Return a secret string; implementation may raise on cancel."""

    def confirm(self, message: str, *, default: bool = True) -> bool:
        """Return yes/no; implementation may raise on cancel."""


class QuestionaryPrompter:
    """Interactive prompts via questionary."""

    def text(self, message: str, *, default: str = "") -> str:
        result = questionary.text(message, default=default).ask()
        if result is None:
            raise KeyboardInterrupt
        return result

    def password(self, message: str) -> str:
        result = questionary.password(message).ask()
        if result is None:
            raise KeyboardInterrupt
        return result

    def confirm(self, message: str, *, default: bool = True) -> bool:
        result = questionary.confirm(message, default=default).ask()
        if result is None:
            raise KeyboardInterrupt
        return bool(result)


def _prompt_project(prompter: SetupPrompter) -> ProjectConfig:
    pid = prompter.text(
        "Project id (stable identifier, e.g. work or personal)",
        default="",
    ).strip()
    name = prompter.text("Project display name", default="").strip()
    root = prompter.text(
        "Project root (working directory path)",
        default="",
    ).strip()
    return ProjectConfig(id=pid, name=name, root=root)


def _add_project_with_retry(cfg_path: Path, prompter: SetupPrompter) -> None:
    while True:
        proj = _prompt_project(prompter)
        try:
            mutate_config_file(
                cfg_path,
                lambda c, p=proj: add_project(c, p),
            )
            return
        except ConfigMutationError as exc:
            console.print(f"[red]{exc}[/red]")
            console.print("[dim]Try again with corrected values.[/dim]")


def run_setup(prompter: SetupPrompter | None = None) -> None:
    """
    Ensure data directory and DB exist, then prompt for AI settings and projects.

    Persists with `mutate_config_file` / `update_ai_config` / `add_project`.
    """
    prompter = prompter or QuestionaryPrompter()
    try:
        home, initial_config, engine = prepare_local_storage()
    except TaskerLayoutError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    cfg_path = home / CONFIG_FILENAME
    try:
        console.print("[bold]Tasker setup[/bold]")
        console.print(
            "[dim]AI settings (including your API key) are saved to "
            f"[cyan]{cfg_path}[/cyan].[/dim]\n",
        )

        base_url = prompter.text(
            "OpenAI-compatible API base URL",
            default=initial_config.ai.base_url,
        ).strip()
        model = prompter.text(
            "Model name",
            default=initial_config.ai.model,
        ).strip()
        api_key = prompter.password(
            "API key (stored in your Tasker config; input is hidden)",
        ).strip()

        try:
            mutate_config_file(
                cfg_path,
                lambda c: update_ai_config(
                    c,
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                ),
            )
        except ConfigMutationError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc

        cfg = read_config_or_default(cfg_path)
        if not cfg.projects:
            console.print("\n[bold]Add at least one project[/bold]")
            _add_project_with_retry(cfg_path, prompter)
            cfg = read_config_or_default(cfg_path)

        while prompter.confirm("Add another project?", default=False):
            _add_project_with_retry(cfg_path, prompter)
            cfg = read_config_or_default(cfg_path)

        nproj = len(cfg.projects)
        console.print(
            f"\n[green]Setup complete.[/green] "
            f"[dim]{nproj} project(s). Config:[/dim] [cyan]{cfg_path}[/cyan]",
        )
    finally:
        engine.dispose()


def setup() -> None:
    """Interactive wizard: data directory, AI endpoints, and projects."""
    try:
        run_setup()
    except KeyboardInterrupt:
        console.print("\n[yellow]Setup aborted.[/yellow]")
        raise typer.Exit(130) from None
