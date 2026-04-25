# tasker

CLI and TUI for **email-linked task context**: ingest and work with mail (including Outlook and `.msg`), manage tasks and projects, and run setup/doctor checks.

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
