"""Assemble the Typer application and entrypoint."""

from __future__ import annotations

import typer
from typer import Context

from tasker.cli.classify_cmd import classify_task
from tasker.cli.common import console
from tasker.cli.config_cmd import config_app, config_path_cmd, config_show
from tasker.cli.doctor import doctor
from tasker.cli.ingest_cmd import ingest
from tasker.cli.route_cmd import route_attachments
from tasker.cli.tasks import add, edit, remove_task, view
from tasker.infrastructure.lifecycle import TaskerLayoutError
from tasker.ui.app import run_tui

app = typer.Typer(help="Tasker - email-linked task context.")
app.add_typer(config_app, name="config")


@app.callback(invoke_without_command=True)
def _main_callback(ctx: Context) -> None:
    """Run the TUI when no subcommand is given; otherwise delegate to Typer."""
    if ctx.invoked_subcommand is None:
        try:
            run_tui()
        except TaskerLayoutError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            raise typer.Exit(code=1) from exc


app.command()(doctor)
app.command()(add)
app.command()(view)
app.command()(edit)
app.command("remove")(remove_task)
config_app.command("show")(config_show)
config_app.command("path")(config_path_cmd)
app.command()(ingest)
app.command("classify")(classify_task)
app.command("route-attachments")(route_attachments)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
