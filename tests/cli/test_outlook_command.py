"""`tasker mail inbox` and legacy `outlook-recent` commands."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from tasker.cli import app
from tasker.infrastructure.outlook import InboxMessageSummary


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_mail_inbox_json_mocked(runner: CliRunner) -> None:
    dt = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    fake = InboxMessageSummary(
        entry_id="e1",
        subject="Subj",
        received=dt,
        sender_display="Bob",
        unread=False,
    )

    with patch(
        "tasker.cli.mail_subcommands.list_recent_inbox",
        return_value=[fake],
    ):
        r = runner.invoke(app, ["mail", "inbox", "--json"])
    assert r.exit_code == 0
    assert "Subj" in r.stdout
    assert "Bob" in r.stdout
    assert '"index": 1' in r.stdout
    assert "e1" not in r.stdout


def test_outlook_recent_hidden_alias_mocked(runner: CliRunner) -> None:
    dt = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    fake = InboxMessageSummary(
        entry_id="e1",
        subject="X",
        received=dt,
        sender_display="Y",
        unread=True,
    )
    with patch(
        "tasker.cli.mail_subcommands.list_recent_inbox",
        return_value=[fake],
    ):
        r = runner.invoke(app, ["mail", "outlook-recent", "--json"])
    assert r.exit_code == 0
    assert "X" in r.stdout
