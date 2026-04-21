"""Assemble the Typer application and entrypoint."""

from __future__ import annotations

import typer
from typer import Context

from tasker.cli.classify_cmd import classify_task
from tasker.cli.common import console
from tasker.cli.config_cmd import config_app, config_path_legacy, config_show
from tasker.cli.doctor import doctor
from tasker.cli.ingest_cmd import ingest
from tasker.cli.ingest_outlook_cmd import ingest_outlook
from tasker.cli.legacy_cmd import (
    add_legacy,
    classify_legacy,
    edit_legacy,
    ingest_legacy,
    remove_legacy,
    route_attachments_legacy,
    view_legacy,
)
from tasker.cli.outlook_cmd import outlook_recent
from tasker.cli.project_cmd import project_app
from tasker.cli.route_cmd import route_attachments
from tasker.cli.setup_cmd import setup
from tasker.cli.tasks import add, delete_task, edit, list_tasks, show_task
from tasker.infrastructure.lifecycle import TaskerLayoutError
from tasker.ui.app import run_tui

app = typer.Typer(help="Tasker - email-linked task context.")
task_app = typer.Typer(help="Create, list, show, edit, and delete tasks.")
mail_app = typer.Typer(
    help="Ingest .msg files, classify with AI, save attachments, and Outlook COM.",
)

app.add_typer(task_app, name="task")
app.add_typer(mail_app, name="mail")
app.add_typer(config_app, name="config")
app.add_typer(project_app, name="project")

task_app.command("list")(list_tasks)
task_app.command("show")(show_task)
task_app.command("add")(add)
task_app.command("edit")(edit)
task_app.command("delete")(delete_task)

mail_app.command("ingest")(ingest)
mail_app.command("ingest-outlook")(ingest_outlook)
mail_app.command("classify")(classify_task)
mail_app.command("save-attachments")(route_attachments)
mail_app.command("outlook-recent")(outlook_recent)


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
app.command()(setup)

app.command("add", hidden=True)(add_legacy)
app.command("view", hidden=True)(view_legacy)
app.command("edit", hidden=True)(edit_legacy)
app.command("remove", hidden=True)(remove_legacy)
app.command("ingest", hidden=True)(ingest_legacy)
app.command("classify", hidden=True)(classify_legacy)
app.command("route-attachments", hidden=True)(route_attachments_legacy)

config_app.command("show")(config_show)
config_app.command("path", hidden=True)(config_path_legacy)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
