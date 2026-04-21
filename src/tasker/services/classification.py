"""AI project classification with preview; DB updates only after confirm."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from tasker.domain.classification import ClassificationProposal
from tasker.domain.enums import TaskStatus
from tasker.domain.exceptions import ClassificationError
from tasker.infrastructure.ai.client import chat_completion_content
from tasker.infrastructure.config.schema import AppConfig, ProjectConfig
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository

_JSON_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)

_MAX_BODY_IN_PROMPT = 12_000


def _project_ids(config: AppConfig) -> set[str]:
    return {p.id for p in config.projects}


def _format_projects_for_prompt(projects: list[ProjectConfig]) -> str:
    lines: list[str] = []
    for p in projects:
        lines.append(
            f"- id={p.id!r} name={p.name!r} root={p.root!r} "
            f"buckets={[b.name for b in p.buckets]!r}"
        )
    return "\n".join(lines) if lines else "(no projects)"


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_json_object(raw: str) -> dict[str, object]:
    text = raw.strip()
    fence = _JSON_FENCE_RE.match(text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"Model output is not valid JSON: {exc}"
        raise ClassificationError(msg) from exc
    if not isinstance(parsed, dict):
        msg = "Model JSON must be an object at the top level."
        raise ClassificationError(msg)
    return parsed


def build_classification_prompt(
    *,
    config: AppConfig,
    task: Task,
    ref: MessageRef,
) -> tuple[str, str]:
    """Return (system_message, user_message) for the chat completion."""
    system = (
        "You classify Outlook emails into the user's Tasker projects. "
        "Reply with a single JSON object only (no markdown, no prose outside JSON) "
        "using this shape exactly:\n"
        '{"project_id": "<one of the configured project ids>", '
        '"rationale": "<brief reason>", '
        '"suggested_title": "<optional string or null>"}\n'
        "project_id must be exactly one of the ids listed in the user message. "
        "If no project fits well, pick the closest match and explain in rationale."
    )
    user_lines = [
        "Configured projects:",
        _format_projects_for_prompt(config.projects),
        "",
        f"Current task id={task.id} title={task.title!r} status={task.status.value!r}",
        "Email snapshot:",
        f"  subject: {ref.subject!r}",
        f"  sender: {ref.sender!r}",
        f"  to: {ref.recipients_to!r}",
        f"  cc: {ref.recipients_cc!r}",
        f"  body:\n{_truncate(ref.body_text, _MAX_BODY_IN_PROMPT)!r}",
    ]
    if ref.attachment_names_json:
        user_lines.append(f"  attachment_names_json: {ref.attachment_names_json!r}")
    user = "\n".join(user_lines)
    return system, user


def request_classification_proposal(
    *,
    config: AppConfig,
    task: Task,
    ref: MessageRef,
    api_key: str,
    complete: Callable[..., str] | None = None,
) -> ClassificationProposal:
    """
    Call the configured OpenAI-compatible API and parse a `ClassificationProposal`.

    `complete` is injectable for tests (defaults to `chat_completion_content`).
    """
    if not config.projects:
        msg = (
            "No projects are configured; "
            "add projects in Tasker config before classifying."
        )
        raise ClassificationError(msg)

    ids = _project_ids(config)
    system, user = build_classification_prompt(config=config, task=task, ref=ref)
    complete_fn = complete or chat_completion_content
    raw = complete_fn(
        base_url=config.ai.base_url,
        api_key=api_key,
        model=config.ai.model,
        system_message=system,
        user_message=user,
    )

    data = _extract_json_object(raw)
    try:
        proposal = ClassificationProposal.model_validate(data)
    except Exception as exc:
        msg = f"Model JSON does not match the expected proposal shape: {exc}"
        raise ClassificationError(msg) from exc

    if proposal.project_id not in ids:
        msg = (
            f"Model returned unknown project_id {proposal.project_id!r}; "
            f"expected one of: {sorted(ids)!r}"
        )
        raise ClassificationError(msg)

    return proposal


def resolve_api_key(config: AppConfig) -> str:
    """Read the API key from persisted AI config."""
    value = config.ai.api_key.strip()
    if not value:
        msg = (
            "Config ai.api_key is empty; set it under Configuration in the app "
            "or run `tasker setup`."
        )
        raise ClassificationError(msg)
    return value


def apply_confirmed_proposal(
    *,
    tasks: TaskRepository,
    task_id: int,
    proposal: ClassificationProposal,
) -> Task:
    """
    Persist project assignment and activate the task after user confirmation.

    Does not create or alter `MessageRef` rows (ingest already linked the `.msg`).
    """
    row = tasks.get(task_id)
    if row is None:
        msg = f"Task {task_id} not found."
        raise ClassificationError(msg)

    new_title: str | None = (
        proposal.suggested_title.strip() if proposal.suggested_title else None
    )
    if new_title == "":
        new_title = None

    notes = row.notes or ""
    rationale_block = f"Classifier rationale: {proposal.rationale.strip()}"
    if notes.strip():
        merged_notes = f"{notes.rstrip()}\n\n{rationale_block}"
    else:
        merged_notes = rationale_block

    update_kwargs: dict[str, Any] = {
        "status": TaskStatus.ACTIVE,
        "project_id": proposal.project_id,
        "notes": merged_notes,
    }
    if new_title is not None:
        update_kwargs["title"] = new_title

    updated = tasks.update(task_id, **update_kwargs)
    if updated is None:
        msg = f"Task {task_id} not found."
        raise ClassificationError(msg)
    return updated


def load_task_primary_ref(
    *,
    tasks: TaskRepository,
    refs: MessageRefRepository,
    task_id: int,
) -> tuple[Task, MessageRef]:
    """Return the task and its first linked message reference."""
    task = tasks.get(task_id)
    if task is None:
        msg = f"Task {task_id} not found."
        raise ClassificationError(msg)
    ref_list = refs.list_for_task(task_id)
    if not ref_list:
        msg = (
            f"Task {task_id} has no linked message; run `tasker mail ingest` "
            "or `tasker mail ingest-outlook` first."
        )
        raise ClassificationError(msg)
    return task, ref_list[0]
