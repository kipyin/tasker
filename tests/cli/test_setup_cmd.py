"""`tasker setup` wizard and `run_setup` helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from tasker.cli import app
from tasker.cli.setup_cmd import run_setup
from tasker.infrastructure.config.store import load_config
from tasker.paths import CONFIG_FILENAME, tasker_home


class FakePrompter:
    def __init__(self, texts: list[str], confirms: list[bool]) -> None:
        self._texts = list(texts)
        self._confirms = list(confirms)

    def text(self, message: str, *, default: str = "") -> str:
        if not self._texts:
            msg = f"unexpected text prompt: {message!r} (default={default!r})"
            raise AssertionError(msg)
        return self._texts.pop(0)

    def password(self, message: str) -> str:
        return self.text(message, default="")

    def confirm(self, message: str, *, default: bool = True) -> bool:
        if not self._confirms:
            msg = f"unexpected confirm: {message!r}"
            raise AssertionError(msg)
        return self._confirms.pop(0)


def test_run_setup_writes_ai_and_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    work = tmp_path / "projroot"
    work.mkdir()
    texts = [
        "https://custom.example/v1",
        "custom-model",
        "sk-my-api-secret",
        "app",
        "Application",
        str(work),
    ]
    confirms = [False]

    run_setup(FakePrompter(texts, confirms))

    home = tasker_home()
    assert home is not None
    cfg = load_config(home / CONFIG_FILENAME)
    assert cfg.ai.base_url == "https://custom.example/v1"
    assert cfg.ai.model == "custom-model"
    assert cfg.ai.api_key == "sk-my-api-secret"
    assert len(cfg.projects) == 1
    assert cfg.projects[0].id == "app"
    assert cfg.projects[0].name == "Application"
    assert cfg.projects[0].root == str(work)


def test_run_setup_updates_ai_keeps_existing_projects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    home = tasker_home()
    assert home is not None
    home.mkdir(parents=True)
    work = tmp_path / "existing"
    work.mkdir()
    root_toml = work.as_posix()
    (home / CONFIG_FILENAME).write_text(
        "\n".join(
            [
                "version = 1",
                (
                    'ai = { base_url = "https://old/v1", model = "old", '
                    'api_key = "OLD_SECRET" }'
                ),
                "[[projects]]",
                'id = "keep"',
                'name = "Kept"',
                f'root = "{root_toml}"',
            ]
        ),
        encoding="utf-8",
    )

    texts = ["https://new/v1", "newmodel", "NEW_SECRET"]
    confirms = [False]

    run_setup(FakePrompter(texts, confirms))

    cfg = load_config(home / CONFIG_FILENAME)
    assert cfg.ai.base_url == "https://new/v1"
    assert cfg.ai.model == "newmodel"
    assert cfg.ai.api_key == "NEW_SECRET"
    assert len(cfg.projects) == 1
    assert cfg.projects[0].id == "keep"


def test_run_setup_project_retry_then_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    work = tmp_path / "okroot"
    work.mkdir()
    texts = [
        "https://u/v1",
        "m",
        "K",
        "",
        "",
        "",
        "good",
        "Good",
        str(work),
    ]
    confirms = [False]

    run_setup(FakePrompter(texts, confirms))

    home = tasker_home()
    assert home is not None
    cfg = load_config(home / CONFIG_FILENAME)
    assert len(cfg.projects) == 1
    assert cfg.projects[0].id == "good"


def test_run_setup_ai_validation_exits(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    texts = ["", "model", "pw"]

    with pytest.raises(typer.Exit) as excinfo:
        run_setup(FakePrompter(texts, []))

    assert excinfo.value.exit_code == 1


def test_run_setup_tasker_layout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPDATA", raising=False)

    with pytest.raises(typer.Exit) as excinfo:
        run_setup(FakePrompter([], []))

    assert excinfo.value.exit_code == 1


def test_cli_setup_aborts_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    runner = CliRunner()

    with patch(
        "tasker.cli.setup_cmd.run_setup",
        side_effect=KeyboardInterrupt,
    ):
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 130
    assert "aborted" in result.stdout.lower()
