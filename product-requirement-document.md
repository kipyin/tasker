# Tasker

Tasker is an integrated CLI tool that aims to reduce the friction among Outlook, file system, and 
to-do lifecycle.

## Main workflow

### Integrated task creation and file management

(I) Getting a new email from Outlook -> 
(II) user drags the email (`.msg`) into terminal (auto-pasted as a file path) -> 
(III) Tasker analyzes the email by extracting the sender, receiver, subject, body, and attachments, 
and engages an AI agent (BYOK, OpenAI Compatible for MVP) to determine which project this email is 
referring to (projects are configured by the user). ->
(IV) Tasker creates a task under the project (tracked internally using a db possibly, SQLite for 
MVP, and tracks the original `.msg` for reference) ->
(V) Tasker puts the attachments into the correct file system folder (for example, "From Client", 
"From Other Teams", the exact rules can be configured by the user)

### Task lifecycle

1. Supports normal task CRUD via a CLI or terminla UI like `Textual`.
2. Supports rich task viewing. Since the goal is to integrate the source of the task and the working
directory of the task, the task view should not only provide rich context from the original email
(summarized via AI Agents) but also provide one-click folder / file opening.
3. Supports linking multiple emails / working dir with one Task, and vice versa.


## Tech stack

- Python managed via uv
- Typer, Rich, Textual, Questionary
- SQLModel for db (sqlite3)
- Ruff for lint and format
- Pytest for testing
- use `src/tasker` layout
- clean architecture and separation between functions/modules/layers (model, ui, service, etc.)


## MVP goal

- single CLI entrypoint `tasker` summons the TUI app.
- normal CLI commands like `tasker add/view/edit/remove/doctor/config`. Everything should be 
viewable or editable via CLI command at least, and optionally add `-i/--interactive` mode for 
viewing or editing in the TUI.
- database and config files are stored locally (on Windows, `%APPDATA%/Tasker` for example.)
- dragging an outlook message will successfully calls an AI agent to parse the content and create
a Task.
- a working user configuration (project management / app / AI service)
