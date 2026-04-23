"""Health checks for `tasker doctor`."""

from __future__ import annotations

import importlib.metadata
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sqlalchemy import exists, func
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from tasker.domain.enums import TaskStatus
from tasker.domain.exceptions import AIClientError
from tasker.infrastructure.config.schema import AppConfig
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.paths import CONFIG_FILENAME, DATABASE_FILENAME
from tasker.services.config_file import (
    ConfigMutationError,
    normalize_app_config,
    validate_app_config,
)


class CheckSeverity(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Check:
    severity: CheckSeverity
    code: str
    title: str
    detail: str = ""


def _mask_api_key(key: str) -> str:
    s = key.strip()
    if not s:
        return "(empty)"
    if len(s) <= 4:
        return "****"
    return f"****{s[-4:]}"


def check_layout(*, home: Path, config_path: Path, db_path: Path) -> list[Check]:
    return [
        Check(
            CheckSeverity.OK,
            "layout_home",
            "Tasker data directory",
            str(home.resolve()),
        ),
        Check(
            CheckSeverity.OK,
            "layout_config",
            "Config file",
            str(config_path.resolve()),
        ),
        Check(
            CheckSeverity.OK,
            "layout_db",
            "Database file",
            f"{db_path.resolve()} ({'exists' if db_path.is_file() else 'new'})",
        ),
    ]


def check_outlook_com_optional() -> list[Check]:
    """Optional local Outlook COM (pywin32); skipped or warned when unavailable."""
    if sys.platform != "win32":
        return [
            Check(
                CheckSeverity.WARN,
                "outlook_com_optional",
                "Outlook COM (optional)",
                "Windows only — skipped on this platform.",
            ),
        ]
    try:
        import win32com  # noqa: F401
    except ImportError:
        return [
            Check(
                CheckSeverity.WARN,
                "outlook_com_optional",
                "Outlook COM (optional)",
                "Install pywin32 for `tasker mail inbox` and related commands: "
                "pip install tasker[outlook]",
            ),
        ]
    return [
        Check(
            CheckSeverity.OK,
            "outlook_com_optional",
            "Outlook COM (optional)",
            "pywin32 import OK (does not start Outlook).",
        ),
    ]


def check_python_imports() -> list[Check]:
    results: list[Check] = []
    for module_name, dist_name in (
        ("extract_msg", "extract-msg"),
        ("httpx", "httpx"),
    ):
        try:
            __import__(module_name)
        except ImportError as exc:
            results.append(
                Check(
                    CheckSeverity.FAIL,
                    f"import_{module_name}",
                    f"Import `{module_name}`",
                    str(exc),
                ),
            )
            continue
        try:
            ver = importlib.metadata.version(dist_name)
            detail = f"{dist_name} {ver}"
        except importlib.metadata.PackageNotFoundError:
            detail = f"{module_name} (version unknown)"
        results.append(
            Check(
                CheckSeverity.OK,
                f"import_{module_name}",
                f"Import `{module_name}`",
                detail,
            ),
        )
    return results


def check_config_consistency(config: AppConfig) -> list[Check]:
    try:
        normalized = normalize_app_config(config)
        validate_app_config(normalized)
    except ConfigMutationError as exc:
        return [
            Check(
                CheckSeverity.FAIL,
                "config_validate",
                "Config consistency",
                str(exc),
            ),
        ]
    return [
        Check(
            CheckSeverity.OK,
            "config_validate",
            "Config consistency",
            f"{len(normalized.projects)} project(s)",
        ),
    ]


def check_ai_settings(config: AppConfig) -> list[Check]:
    results: list[Check] = []
    key = config.ai.api_key.strip()
    base = config.ai.base_url.strip()
    model = config.ai.model.strip()
    results.append(
        Check(
            CheckSeverity.OK,
            "ai_base_url",
            "AI base URL",
            base,
        ),
    )
    results.append(
        Check(
            CheckSeverity.OK,
            "ai_model",
            "AI model",
            model,
        ),
    )
    if not key:
        results.append(
            Check(
                CheckSeverity.WARN,
                "ai_api_key",
                "AI API key",
                "Empty — `tasker mail classify` will fail until you set ai.api_key "
                "(Configuration or `tasker setup`).",
            ),
        )
    else:
        results.append(
            Check(
                CheckSeverity.OK,
                "ai_api_key",
                "AI API key",
                _mask_api_key(key),
            ),
        )
    return results


def check_projects_on_disk(
    config: AppConfig,
    *,
    strict_projects: bool,
) -> list[Check]:
    results: list[Check] = []
    normalized = normalize_app_config(config)
    for proj in normalized.projects:
        root = Path(proj.root)
        pid = proj.id
        if not root.exists():
            sev = CheckSeverity.FAIL if strict_projects else CheckSeverity.WARN
            results.append(
                Check(
                    sev,
                    f"project_root_{pid}",
                    f"Project {pid!r} root",
                    f"Path does not exist: {root}",
                ),
            )
            continue
        if not root.is_dir():
            sev = CheckSeverity.FAIL if strict_projects else CheckSeverity.WARN
            results.append(
                Check(
                    sev,
                    f"project_root_{pid}",
                    f"Project {pid!r} root",
                    f"Not a directory: {root}",
                ),
            )
            continue
        writable = os.access(root, os.W_OK)
        resolved = str(root.resolve())
        if not writable:
            results.append(
                Check(
                    CheckSeverity.WARN,
                    f"project_root_{pid}",
                    f"Project {pid!r} root",
                    f"{resolved} (may not be writable)",
                ),
            )
        else:
            results.append(
                Check(
                    CheckSeverity.OK,
                    f"project_root_{pid}",
                    f"Project {pid!r} root",
                    resolved,
                ),
            )
        for bucket in proj.buckets:
            bucket_path = (root / bucket.relative_path).resolve()
            parent = bucket_path.parent
            if not parent.exists():
                results.append(
                    Check(
                        CheckSeverity.WARN,
                        f"bucket_{pid}_{bucket.name}",
                        f"Project {pid!r} bucket {bucket.name!r}",
                        f"Parent path missing: {parent}",
                    ),
                )
            else:
                results.append(
                    Check(
                        CheckSeverity.OK,
                        f"bucket_{pid}_{bucket.name}",
                        f"Project {pid!r} bucket {bucket.name!r}",
                        str(bucket_path),
                    ),
                )
    return results


def check_project_count_hint(config: AppConfig) -> list[Check]:
    if not config.projects:
        return [
            Check(
                CheckSeverity.WARN,
                "projects_empty",
                "Projects",
                "No projects configured — add some with `tasker setup` or "
                "`tasker project add` (required for classification).",
            ),
        ]
    return []


def check_database(engine: Engine) -> list[Check]:
    try:
        with Session(engine) as session:
            task_total = session.exec(select(func.count()).select_from(Task)).one()
            ref_total = session.exec(
                select(func.count()).select_from(MessageRef),
            ).one()
            lines = [f"tasks (all statuses): {task_total}"]
            for status in TaskStatus:
                n = session.exec(
                    select(func.count())
                    .select_from(Task)
                    .where(Task.status == status),
                ).one()
                lines.append(f"  {status.value}: {n}")
            lines.append(f"message_refs: {ref_total}")
            pending_orphan = session.exec(
                select(func.count())
                .select_from(Task)
                .where(Task.status == TaskStatus.PENDING)
                .where(~exists().where(MessageRef.task_id == Task.id)),
            ).one()
            lines.append(f"pending tasks without .msg ref: {pending_orphan}")
    except Exception as exc:
        return [
            Check(
                CheckSeverity.FAIL,
                "db_query",
                "Database",
                f"Query failed: {exc}",
            ),
        ]
    return [
        Check(
            CheckSeverity.OK,
            "db_query",
            "Database",
            "SQLite queries succeeded",
        ),
        Check(
            CheckSeverity.OK,
            "db_stats",
            "Database statistics",
            "\n".join(lines),
        ),
    ]


def check_ai_live(config: AppConfig, api_key: str) -> Check:
    from tasker.infrastructure.ai.client import chat_completion_content

    try:
        chat_completion_content(
            base_url=config.ai.base_url,
            api_key=api_key,
            model=config.ai.model,
            system_message="Reply with the single word OK.",
            user_message="ping",
            timeout_seconds=45.0,
            max_tokens=8,
        )
    except AIClientError as exc:
        return Check(
            CheckSeverity.FAIL,
            "ai_live",
            "AI endpoint (live check)",
            str(exc),
        )
    return Check(
        CheckSeverity.OK,
        "ai_live",
        "AI endpoint (live check)",
        "Chat completions request succeeded",
    )


def run_doctor_checks(
    *,
    home: Path,
    config: AppConfig,
    engine: Engine,
    strict_projects: bool,
    check_ai_live_request: bool,
) -> list[Check]:
    cfg_path = home / CONFIG_FILENAME
    db_path = home / DATABASE_FILENAME
    checks: list[Check] = []
    checks.extend(check_layout(home=home, config_path=cfg_path, db_path=db_path))
    checks.extend(check_python_imports())
    checks.extend(check_outlook_com_optional())
    checks.extend(check_config_consistency(config))
    checks.extend(check_ai_settings(config))
    checks.extend(check_project_count_hint(config))
    checks.extend(check_projects_on_disk(config, strict_projects=strict_projects))
    checks.extend(check_database(engine))
    if check_ai_live_request:
        key = config.ai.api_key.strip()
        if not key:
            checks.append(
                Check(
                    CheckSeverity.WARN,
                    "ai_live_skipped",
                    "AI endpoint (live check)",
                    "Skipped — no API key configured.",
                ),
            )
        else:
            checks.append(check_ai_live(config, key))
    return checks


def worst_severity(checks: list[Check]) -> CheckSeverity | None:
    if any(c.severity == CheckSeverity.FAIL for c in checks):
        return CheckSeverity.FAIL
    if any(c.severity == CheckSeverity.WARN for c in checks):
        return CheckSeverity.WARN
    if checks:
        return CheckSeverity.OK
    return None
