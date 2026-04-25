# tasker

**Tasker** is a local-first tool for people who live in email. It **connects Outlook and `.msg` files to a task list**: you pull message content and attachments in, file work under **projects** you define, and keep a **traceable link** from each task back to the original message—so “what did the client ask for?” and “where did I save that attachment?” stay in one place. Use a **full-screen terminal app** (run `tasker` with no args) or **plain commands** for the same data.

## Use cases

- **“This email is now a real task”** — Ingest a message (e.g. drag a saved `.msg` into the terminal), classify it (optionally with your own AI), and create tasks with the mail on record instead of a sticky note in your head.
- **Triage the inbox from the shell** — List, read, flag, archive, or delete mail via `tasker mail …` (and on **Windows** with the optional Outlook extra, work closer to a live Outlook mailbox).
- **Route attachments to the right project folders** — After ingest, **save** attachments to configured destinations so “From client” / “from other teams” file layouts stay consistent with your project rules.
- **Projects and configuration in one place** — Define projects, AI, and storage layout through **`tasker setup`**, and verify the environment with **`tasker doctor`**.

## Requirements

- **Python** 3.13+
- [**uv**](https://docs.astral.sh/uv/) (recommended for install and running commands)

## Quick start

```bash
uv sync
uv run tasker --help
```

Optional **Outlook (Windows)** integration:

```bash
uv sync --extra outlook
```

## Development

```bash
uv run pytest
uv run ruff check .
```
