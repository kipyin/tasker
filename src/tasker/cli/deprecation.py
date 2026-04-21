"""One-line stderr notices for legacy CLI spellings."""

from __future__ import annotations

import typer


def warn_renamed(old: str, new: str) -> None:
    typer.echo(f"Warning: {old} is deprecated; use {new} instead.", err=True)
