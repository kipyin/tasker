"""Route email attachments (`.msg` file or Outlook COM) into project buckets."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from extract_msg import openMsg
from extract_msg.exceptions import InvalidFileFormatError

from tasker.domain.exceptions import OutlookCOMError, RoutingError
from tasker.domain.routing import AttachmentRouteRecord
from tasker.infrastructure.config.schema import AppConfig, ProjectConfig
from tasker.infrastructure.db.models import MessageRef, Task
from tasker.infrastructure.repositories import MessageRefRepository, TaskRepository

_WIN_INVALID = frozenset('<>:"/\\|?*')


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def sanitize_attachment_filename(name: str) -> str:
    """Strip Windows-invalid characters and control chars from an attachment name."""
    cleaned = "".join(c for c in name.strip() if c not in _WIN_INVALID and ord(c) >= 32)
    cleaned = cleaned.strip().rstrip(".")
    return cleaned or "attachment.bin"


def _bucket_names(project: ProjectConfig) -> set[str]:
    return {b.name for b in project.buckets}


def _bucket_defined(project: ProjectConfig, bucket_name: str | None) -> bool:
    return bool(bucket_name) and bucket_name in _bucket_names(project)


def match_bucket(filename: str, project: ProjectConfig) -> str | None:
    """
    Return the bucket name for `filename` using ordered rules, then `default_bucket`.

    Patterns are case-insensitive `fnmatch` shell-style globs (e.g. ``*.pdf``).
    """
    fn = filename.strip()
    if not fn:
        db = project.default_bucket
        return db if _bucket_defined(project, db) else None

    for rule in project.rules:
        if not _bucket_defined(project, rule.bucket):
            continue
        if fnmatch(fn.lower(), rule.pattern.lower()):
            return rule.bucket

    db = project.default_bucket
    if _bucket_defined(project, db):
        return db
    return None


def bucket_directory(project: ProjectConfig, bucket_name: str) -> Path:
    """Resolved absolute directory for a named bucket under the project root."""
    root = Path(project.root).expanduser().resolve()
    cfg = next((b for b in project.buckets if b.name == bucket_name), None)
    if cfg is None:
        msg = f"Bucket {bucket_name!r} is not defined for this project."
        raise RoutingError(msg)
    dest = (root / cfg.relative_path).resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        msg = "Bucket relative_path escapes the project root."
        raise RoutingError(msg) from None
    return dest


def _attachment_names_from_ref(ref: MessageRef) -> list[str]:
    if not ref.attachment_names_json:
        return []
    data = json.loads(ref.attachment_names_json)
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def _files_byte_identical(a: Path, b: Path) -> bool:
    if not a.is_file() or not b.is_file():
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        ha = hashlib.file_digest(fa, "sha256").hexdigest()
        hb = hashlib.file_digest(fb, "sha256").hexdigest()
    return ha == hb


def _disambiguated_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suf = dest.stem, dest.suffix
    for n in range(1, 10_000):
        cand = dest.with_name(f"{stem}.tasker-{n}{suf}")
        if not cand.exists():
            return cand
    msg = f"No free filename near {dest}"
    raise RoutingError(msg)


def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, default=str) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def _load_task_ref(
    *,
    tasks: TaskRepository,
    refs: MessageRefRepository,
    task_id: int,
) -> tuple[Task, MessageRef]:
    task = tasks.get(task_id)
    if task is None:
        raise RoutingError(f"Task {task_id} not found.")
    ref_list = refs.list_for_task(task_id)
    if not ref_list:
        msg = (
            f"Task {task_id} has no linked message; run `tasker mail ingest` "
            "or `tasker mail capture` first."
        )
        raise RoutingError(msg)
    if not (task.project_id or "").strip():
        msg = (
            "Task has no project_id; run `tasker mail classify` "
            "(or set a project) first."
        )
        raise RoutingError(msg)
    return task, ref_list[0]


def _project_for_id(config: AppConfig, project_id: str) -> ProjectConfig:
    for p in config.projects:
        if p.id == project_id:
            return p
    msg = f"Unknown project_id {project_id!r} in config."
    raise RoutingError(msg)


def _export_outlook_attachment_to_scratch(
    attachment: object,
    *,
    scratch_dir: Path,
    logical_name: str,
) -> Path:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    dest = scratch_dir / logical_name
    try:
        attachment.SaveAsFile(str(dest))  # type: ignore[union-attr]
    except Exception as exc:
        msg = f"Could not save attachment {logical_name!r} via Outlook: {exc}"
        raise RoutingError(msg) from exc
    if not dest.is_file():
        msg = f"Outlook did not write attachment {logical_name!r}."
        raise RoutingError(msg)
    return dest.resolve()


def _export_attachment_to_scratch(
    attachment: object,
    *,
    scratch_dir: Path,
    logical_name: str,
) -> Path:
    scratch_dir.mkdir(parents=True, exist_ok=True)
    attachment.save(  # type: ignore[union-attr]
        customPath=str(scratch_dir),
        customFilename=logical_name,
        skipHidden=True,
    )
    direct = scratch_dir / logical_name
    if direct.is_file():
        return direct.resolve()
    files = [p for p in scratch_dir.iterdir() if p.is_file()]
    if len(files) == 1:
        return files[0].resolve()
    msg = f"Could not locate saved bytes for attachment {logical_name!r}."
    raise RoutingError(msg)


def _com_enumerate_attachments(mail_item: Any) -> list[Any]:
    """Outlook ``Attachments`` collection is 1-based; normalize to a Python list."""
    try:
        collection = mail_item.Attachments
        n = int(collection.Count)
    except Exception as exc:
        msg = f"Could not read Outlook attachments: {exc}"
        raise RoutingError(msg) from exc
    result: list[Any] = []
    for i in range(1, n + 1):
        try:
            result.append(collection.Item(i))
        except Exception:
            continue
    return result


def _logical_attachment_name(
    *,
    index: int,
    att: object,
    stored_names: list[str],
    outlook: bool,
) -> str:
    if stored_names:
        return sanitize_attachment_filename(stored_names[index])
    if outlook:
        raw = getattr(att, "FileName", None) or ""
        return sanitize_attachment_filename(str(raw).strip() or f"file-{index}")
    raw = getattr(att, "name", None) or ""
    return sanitize_attachment_filename(str(raw).strip() or f"file-{index}")


def _route_attachments_process_list(
    *,
    attachments: list[Any],
    stored_names: list[str],
    source_label: str,
    export_to_scratch: Callable[..., Path],
    attachment_names_from_com: bool,
    home: Path,
    task_id: int,
    project: ProjectConfig,
    dry_run: bool,
) -> list[AttachmentRouteRecord]:
    log_path = home / "logs" / "routing.jsonl"
    records: list[AttachmentRouteRecord] = []

    if stored_names and len(stored_names) != len(attachments):
        msg_err = (
            f"Attachment count mismatch: {source_label} has {len(attachments)} "
            f"attachments but the database snapshot lists {len(stored_names)}."
        )
        raise RoutingError(msg_err)
    for index, att in enumerate(attachments):
        logical = _logical_attachment_name(
            index=index,
            att=att,
            stored_names=stored_names,
            outlook=attachment_names_from_com,
        )

        bucket = match_bucket(logical, project)
        if bucket is None:
            rec = AttachmentRouteRecord(
                filename=logical,
                bucket=None,
                dest_path="",
                action="skipped_unmatched",
                detail="No matching rule and no default_bucket.",
            )
            records.append(rec)
            _append_jsonl(
                log_path,
                {
                    "ts": _utc_iso(),
                    "task_id": task_id,
                    "filename": logical,
                    "action": rec.action,
                    "detail": rec.detail,
                },
            )
            continue

        dest_dir = bucket_directory(project, bucket)
        dest_path = (dest_dir / logical).resolve()

        if dry_run:
            rec = AttachmentRouteRecord(
                filename=logical,
                bucket=bucket,
                dest_path=str(dest_path),
                action="skipped_dry_run",
            )
            records.append(rec)
            _append_jsonl(
                log_path,
                {
                    "ts": _utc_iso(),
                    "task_id": task_id,
                    "filename": logical,
                    "bucket": bucket,
                    "dest_path": str(dest_path),
                    "action": rec.action,
                },
            )
            continue

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            src = export_to_scratch(
                att,
                scratch_dir=td_path,
                logical_name=logical,
            )

            detail: str | None = None
            action = "moved"
            final_dest = dest_path

            if dest_path.exists():
                if _files_byte_identical(src, dest_path):
                    src.unlink(missing_ok=True)
                    action = "skipped_identical"
                    final_dest = dest_path
                else:
                    final_dest = _disambiguated_dest(dest_path)
                    detail = (
                        "Destination existed with different content; "
                        f"wrote to {final_dest.name!r}."
                    )
                    shutil.move(str(src), str(final_dest))
                    action = "moved_disambiguated"
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(final_dest))

        rec = AttachmentRouteRecord(
            filename=logical,
            bucket=bucket,
            dest_path=str(final_dest),
            action=action,
            detail=detail,
        )
        records.append(rec)
        _append_jsonl(
            log_path,
            {
                "ts": _utc_iso(),
                "task_id": task_id,
                "filename": logical,
                "bucket": bucket,
                "dest_path": str(final_dest),
                "action": action,
                "detail": detail,
            },
        )

    return records


def route_task_attachments(
    *,
    home: Path,
    config: AppConfig,
    tasks: TaskRepository,
    refs: MessageRefRepository,
    task_id: int,
    dry_run: bool = False,
    msg_opener: Callable[[str], Any] | None = None,
    outlook_mail_item_getter: Callable[[str, str | None], Any] | None = None,
) -> list[AttachmentRouteRecord]:
    """
    Extract attachments from the task's linked message, match rules, move into buckets.

    Writes JSONL events to ``<home>/logs/routing.jsonl``. Updates
    ``task.attachment_routes_json`` when not ``dry_run``.

    ``msg_opener`` defaults to ``extract_msg.openMsg`` (file-backed refs only).

    ``outlook_mail_item_getter`` resolves a COM ``MailItem`` (tests may inject).
    """
    task, ref = _load_task_ref(tasks=tasks, refs=refs, task_id=task_id)
    project = _project_for_id(config, task.project_id)
    if not project.buckets:
        msg = f"Project {project.id!r} has no buckets configured."
        raise RoutingError(msg)

    stored_names = _attachment_names_from_ref(ref)
    use_outlook = bool((ref.outlook_entry_id or "").strip())

    if use_outlook:
        getter = outlook_mail_item_getter
        if getter is None:
            from tasker.infrastructure.outlook._mail_item_win32 import (  # noqa: PLC0415
                get_mail_item,
            )

            getter = get_mail_item

        try:
            mail_item = getter(ref.outlook_entry_id or "", ref.outlook_store_id)
        except OutlookCOMError as exc:
            raise RoutingError(
                "Could not open the Outlook message for attachment routing "
                "(it may have been moved or deleted).",
            ) from exc
        attachments = _com_enumerate_attachments(mail_item)

        records = _route_attachments_process_list(
            attachments=attachments,
            stored_names=stored_names,
            source_label="Outlook message",
            export_to_scratch=_export_outlook_attachment_to_scratch,
            attachment_names_from_com=True,
            home=home,
            task_id=task_id,
            project=project,
            dry_run=dry_run,
        )
    else:
        msg_path = Path(ref.msg_path)
        if not msg_path.is_file():
            raise RoutingError(f"Message file not found: {msg_path}")

        opener = msg_opener or openMsg
        try:
            ctx = opener(str(msg_path))
        except (InvalidFileFormatError, OSError) as exc:
            raise RoutingError(f"Cannot open .msg: {msg_path}: {exc}") from exc

        with ctx as msg:
            attachments = list(msg.attachments)
            records = _route_attachments_process_list(
                attachments=attachments,
                stored_names=stored_names,
                source_label=".msg",
                export_to_scratch=_export_attachment_to_scratch,
                attachment_names_from_com=False,
                home=home,
                task_id=task_id,
                project=project,
                dry_run=dry_run,
            )

    payload = json.dumps([r.to_json_dict() for r in records])
    if not dry_run:
        updated = tasks.update(task_id, attachment_routes_json=payload)
        if updated is None:
            raise RoutingError(f"Task {task_id} not found.")

    return records
