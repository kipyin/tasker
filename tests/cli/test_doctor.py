"""Tests for `tasker doctor`."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tasker.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_doctor_happy_path_reports_checks(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    work = tmp_path / "work"
    work.mkdir()
    tasker_dir = tmp_path / "Tasker"
    tasker_dir.mkdir()
    cfg = tasker_dir / "config.toml"
    cfg.write_text(
        "\n".join(
            [
                "version = 1",
                "",
                '[ai]',
                'base_url = "https://api.openai.com/v1"',
                'model = "gpt-4o-mini"',
                'api_key = "sk-test"',
                "",
                "[[projects]]",
                'id = "p1"',
                'name = "One"',
                f'root = "{work.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 0
    assert "Tasker version" in r.stdout
    assert "Config consistency" in r.stdout
    assert "Database" in r.stdout
    assert "extract_msg" in r.stdout
    assert "Outlook COM" in r.stdout


def test_doctor_invalid_config_exits_error(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    tasker_dir = tmp_path / "Tasker"
    tasker_dir.mkdir()
    cfg = tasker_dir / "config.toml"
    cfg.write_text(
        "\n".join(
            [
                "version = 1",
                "",
                '[ai]',
                'base_url = "https://api.openai.com/v1"',
                'model = "gpt-4o-mini"',
                "",
                "[[projects]]",
                'id = "dup"',
                'name = "A"',
                f'root = "{tmp_path.as_posix()}"',
                "",
                "[[projects]]",
                'id = "dup"',
                'name = "B"',
                f'root = "{tmp_path.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 1
    assert "duplicate" in r.stdout.lower()


def test_doctor_strict_projects_missing_root_fails(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    tasker_dir = tmp_path / "Tasker"
    tasker_dir.mkdir()
    missing = tmp_path / "nope"
    cfg = tasker_dir / "config.toml"
    cfg.write_text(
        "\n".join(
            [
                "version = 1",
                "",
                '[ai]',
                'base_url = "https://api.openai.com/v1"',
                'model = "gpt-4o-mini"',
                "",
                "[[projects]]",
                'id = "p1"',
                'name = "One"',
                f'root = "{missing.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    r = runner.invoke(app, ["doctor", "--strict-projects"])
    assert r.exit_code == 1
    assert "does not exist" in r.stdout


def test_doctor_check_ai_uses_mocked_completion(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    work = tmp_path / "work"
    work.mkdir()
    tasker_dir = tmp_path / "Tasker"
    tasker_dir.mkdir()
    cfg = tasker_dir / "config.toml"
    cfg.write_text(
        "\n".join(
            [
                "version = 1",
                "",
                '[ai]',
                'base_url = "https://api.openai.com/v1"',
                'model = "gpt-4o-mini"',
                'api_key = "sk-test"',
                "",
                "[[projects]]",
                'id = "p1"',
                'name = "One"',
                f'root = "{work.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    def _fake_completion(**_kwargs: object) -> str:
        return "OK"

    monkeypatch.setattr(
        "tasker.infrastructure.ai.client.chat_completion_content",
        _fake_completion,
    )

    r = runner.invoke(app, ["doctor", "--check-ai"])
    assert r.exit_code == 0
    assert "live check" in r.stdout.lower()
