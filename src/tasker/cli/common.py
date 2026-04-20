"""Shared CLI helpers (console, parsing, formatting)."""

from __future__ import annotations

import importlib.metadata
import sys
from datetime import datetime

import typer
from rich.console import Console

from tasker.domain.enums import TaskStatus

console = Console()


def parse_task_status(value: str) -> TaskStatus:
    try:
        return TaskStatus(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(s.value for s in TaskStatus)
        raise typer.BadParameter(f"expected one of: {allowed}") from exc


def format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def package_version() -> str:
    try:
        return importlib.metadata.version("tasker")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


def print_python_runtime() -> None:
    console.print(f"Python: {sys.version}")
    console.print(f"Executable: {sys.executable}")
