"""Load, validate, and persist `AppConfig` mutations (projects + AI settings)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tasker.infrastructure.config.schema import (
    AIConfig,
    AppConfig,
    BucketConfig,
    ProjectConfig,
    RoutingRuleConfig,
)
from tasker.infrastructure.config.store import default_config, load_config, save_config

ERR_PROJECT_ID_EMPTY = "project id must not be empty"
ERR_DUPLICATE_PROJECT_ID = "duplicate project id: {id!r}"
ERR_PROJECT_NOT_FOUND = "no project with id {id!r}"
ERR_PROJECT_ROOT_EMPTY = "project {id!r}: root path must not be empty"
ERR_BUCKET_NAME_EMPTY = "project {id!r}: bucket name must not be empty"
ERR_BUCKET_PATH_EMPTY = (
    "project {id!r}: bucket {name!r} must have a non-empty relative_path"
)
ERR_DUPLICATE_BUCKET_NAME = "project {id!r}: duplicate bucket name: {name!r}"
ERR_DEFAULT_BUCKET_UNKNOWN = (
    "project {id!r}: default_bucket {bucket!r} is not a defined bucket"
)
ERR_RULE_BUCKET_EMPTY = "project {id!r}: routing rule must reference a non-empty bucket"
ERR_RULE_PATTERN_EMPTY = "project {id!r}: routing rule must have a non-empty pattern"
ERR_RULE_BUCKET_UNKNOWN = "project {id!r}: rule references unknown bucket {bucket!r}"
ERR_AI_FIELD_EMPTY = "ai.{field} must not be empty"
ERR_UPDATE_PROJECT_NO_FIELDS = (
    "update_project: provide at least one field to change"
)
ERR_UPDATE_AI_NO_FIELDS = "update_ai_config: provide at least one field to change"


class ConfigMutationError(ValueError):
    """Invalid config state or mutation (stable message for UI and tests)."""


def _normalize_root(root: str) -> str:
    s = root.strip()
    if not s:
        return s
    return str(Path(s).expanduser())


def normalize_app_config(config: AppConfig) -> AppConfig:
    """Return a copy with trimmed string fields and normalized project roots."""
    ai = config.ai
    new_ai = AIConfig(
        base_url=ai.base_url.strip(),
        model=ai.model.strip(),
        api_key=ai.api_key.strip(),
    )
    new_projects: list[ProjectConfig] = []
    for p in config.projects:
        buckets = [
            BucketConfig(
                name=b.name.strip(),
                relative_path=b.relative_path.strip(),
            )
            for b in p.buckets
        ]
        rules = [
            RoutingRuleConfig(
                bucket=r.bucket.strip(),
                pattern=r.pattern.strip(),
            )
            for r in p.rules
        ]
        db = (p.default_bucket or "").strip()
        new_projects.append(
            ProjectConfig(
                id=p.id.strip(),
                name=p.name.strip(),
                root=_normalize_root(p.root),
                buckets=buckets,
                rules=rules,
                default_bucket=db or None,
            )
        )
    return AppConfig(version=config.version, ai=new_ai, projects=new_projects)


def validate_app_config(config: AppConfig) -> None:
    """Raise ConfigMutationError when the config is inconsistent."""
    seen_ids: set[str] = set()
    for proj in config.projects:
        pid = proj.id
        if not pid:
            raise ConfigMutationError(ERR_PROJECT_ID_EMPTY)
        if pid in seen_ids:
            raise ConfigMutationError(ERR_DUPLICATE_PROJECT_ID.format(id=pid))
        seen_ids.add(pid)

        if not proj.root:
            raise ConfigMutationError(ERR_PROJECT_ROOT_EMPTY.format(id=pid))

        bucket_names: set[str] = set()
        for b in proj.buckets:
            name = b.name
            if not name:
                raise ConfigMutationError(ERR_BUCKET_NAME_EMPTY.format(id=pid))
            if not b.relative_path:
                raise ConfigMutationError(
                    ERR_BUCKET_PATH_EMPTY.format(id=pid, name=name),
                )
            if name in bucket_names:
                raise ConfigMutationError(
                    ERR_DUPLICATE_BUCKET_NAME.format(id=pid, name=name),
                )
            bucket_names.add(name)

        if proj.default_bucket is not None and proj.default_bucket not in bucket_names:
            raise ConfigMutationError(
                ERR_DEFAULT_BUCKET_UNKNOWN.format(id=pid, bucket=proj.default_bucket),
            )

        for rule in proj.rules:
            if not rule.bucket:
                raise ConfigMutationError(ERR_RULE_BUCKET_EMPTY.format(id=pid))
            if not rule.pattern:
                raise ConfigMutationError(ERR_RULE_PATTERN_EMPTY.format(id=pid))
            if rule.bucket not in bucket_names:
                raise ConfigMutationError(
                    ERR_RULE_BUCKET_UNKNOWN.format(id=pid, bucket=rule.bucket),
                )

    for field in ("base_url", "model"):
        val = getattr(config.ai, field)
        if not val:
            raise ConfigMutationError(ERR_AI_FIELD_EMPTY.format(field=field))


def read_config_or_default(path: Path) -> AppConfig:
    """Load TOML from `path`, or return defaults when the file is missing."""
    if path.is_file():
        return load_config(path)
    return default_config()


def mutate_config_file(
    cfg_path: Path,
    mutator: Callable[[AppConfig], AppConfig],
) -> AppConfig:
    """
    Load config (or defaults), apply `mutator`, normalize, validate, save, return.

    Creates parent directories as needed via `save_config`.
    """
    current = read_config_or_default(cfg_path)
    updated = mutator(current)
    normalized = normalize_app_config(updated)
    validate_app_config(normalized)
    save_config(normalized, cfg_path)
    return normalized


def add_project(config: AppConfig, project: ProjectConfig) -> AppConfig:
    """Append a project; raises if validation fails after normalization."""
    candidate = config.model_copy(update={"projects": [*config.projects, project]})
    normalized = normalize_app_config(candidate)
    validate_app_config(normalized)
    return normalized


def remove_project(config: AppConfig, project_id: str) -> AppConfig:
    """Remove the project whose id matches `project_id` (trimmed)."""
    key = project_id.strip()
    kept = [p for p in config.projects if p.id.strip() != key]
    if len(kept) == len(config.projects):
        raise ConfigMutationError(ERR_PROJECT_NOT_FOUND.format(id=key))
    candidate = config.model_copy(update={"projects": kept})
    normalized = normalize_app_config(candidate)
    validate_app_config(normalized)
    return normalized


def update_project(
    config: AppConfig,
    project_id: str,
    *,
    name: str | None = None,
    root: str | None = None,
    new_id: str | None = None,
    buckets: list[BucketConfig] | None = None,
    rules: list[RoutingRuleConfig] | None = None,
    default_bucket: str | None = None,
    unset_default_bucket: bool = False,
) -> AppConfig:
    """Update one project by id; raises if no project matches or no fields given."""
    key = project_id.strip()
    idx: int | None = None
    for i, p in enumerate(config.projects):
        if p.id.strip() == key:
            idx = i
            break
    if idx is None:
        raise ConfigMutationError(ERR_PROJECT_NOT_FOUND.format(id=key))

    if all(
        v is None
        for v in (name, root, new_id, buckets, rules, default_bucket)
    ) and not unset_default_bucket:
        raise ConfigMutationError(ERR_UPDATE_PROJECT_NO_FIELDS)

    current = config.projects[idx]
    next_id = new_id.strip() if new_id is not None else current.id
    next_name = name.strip() if name is not None else current.name
    next_root = _normalize_root(root) if root is not None else current.root
    next_buckets = buckets if buckets is not None else list(current.buckets)
    next_rules = rules if rules is not None else list(current.rules)
    if unset_default_bucket:
        next_default: str | None = None
    elif default_bucket is not None:
        s = default_bucket.strip()
        next_default = s or None
    else:
        next_default = current.default_bucket

    replacement = ProjectConfig(
        id=next_id,
        name=next_name,
        root=next_root,
        buckets=next_buckets,
        rules=next_rules,
        default_bucket=next_default,
    )
    projects = list(config.projects)
    projects[idx] = replacement
    candidate = config.model_copy(update={"projects": projects})
    normalized = normalize_app_config(candidate)
    validate_app_config(normalized)
    return normalized


def update_ai_config(
    config: AppConfig,
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> AppConfig:
    """Merge AI fields into `config.ai`; raises if no field is provided."""
    if all(v is None for v in (base_url, model, api_key)):
        raise ConfigMutationError(ERR_UPDATE_AI_NO_FIELDS)

    ai = config.ai
    next_ai = AIConfig(
        base_url=base_url.strip() if base_url is not None else ai.base_url,
        model=model.strip() if model is not None else ai.model,
        api_key=api_key.strip() if api_key is not None else ai.api_key,
    )
    candidate = config.model_copy(update={"ai": next_ai})
    normalized = normalize_app_config(candidate)
    validate_app_config(normalized)
    return normalized
