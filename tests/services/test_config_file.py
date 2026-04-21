"""Unit tests for config file mutations and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tasker.infrastructure.config import (
    AppConfig,
    ProjectConfig,
    load_config,
    save_config,
)
from tasker.infrastructure.config.schema import (
    AIConfig,
    BucketConfig,
    RoutingRuleConfig,
)
from tasker.services.config_file import (
    ConfigMutationError,
    add_project,
    mutate_config_file,
    normalize_app_config,
    read_config_or_default,
    remove_project,
    update_ai_config,
    update_project,
    validate_app_config,
)


def test_normalize_app_config_trims_and_normalizes_root(tmp_path: Path) -> None:
    work = tmp_path / "work"
    cfg = AppConfig(
        projects=[
            ProjectConfig(
                id="  p1  ",
                name="  Name ",
                root=f"  {work}  ",
            ),
        ],
    )
    norm = normalize_app_config(cfg)
    assert norm.projects[0].id == "p1"
    assert norm.projects[0].name == "Name"
    assert norm.projects[0].root == str(work.expanduser())


def test_validate_rejects_duplicate_project_ids(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(id="p1", name="A", root=str(tmp_path / "a")),
            ProjectConfig(id="p1", name="B", root=str(tmp_path / "b")),
        ],
    )
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="duplicate project id"):
        validate_app_config(cfg)


def test_validate_rejects_empty_project_id(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(id="   ", name="A", root=str(tmp_path / "a")),
        ],
    )
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="project id must not be empty"):
        validate_app_config(cfg)


def test_validate_rejects_empty_root(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(id="p1", name="A", root="  "),
        ],
    )
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="root path must not be empty"):
        validate_app_config(cfg)


def test_validate_rejects_duplicate_bucket_names(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(
                id="p1",
                name="A",
                root=str(tmp_path),
                buckets=[
                    BucketConfig(name="inbox", relative_path="in"),
                    BucketConfig(name="inbox", relative_path="in2"),
                ],
            ),
        ],
    )
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="duplicate bucket name"):
        validate_app_config(cfg)


def test_validate_rejects_unknown_default_bucket(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(
                id="p1",
                name="A",
                root=str(tmp_path),
                buckets=[BucketConfig(name="inbox", relative_path="in")],
                default_bucket="nope",
            ),
        ],
    )
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="default_bucket"):
        validate_app_config(cfg)


def test_validate_rejects_rule_with_unknown_bucket(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(
                id="p1",
                name="A",
                root=str(tmp_path),
                buckets=[BucketConfig(name="inbox", relative_path="in")],
                rules=[RoutingRuleConfig(bucket="other", pattern="*.pdf")],
            ),
        ],
    )
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="unknown bucket"):
        validate_app_config(cfg)


def test_validate_rejects_empty_ai_field() -> None:
    cfg = AppConfig(ai=AIConfig(base_url=" ", model="m", api_key="K"))
    cfg = normalize_app_config(cfg)
    with pytest.raises(ConfigMutationError, match="ai.base_url"):
        validate_app_config(cfg)


def test_add_project_persists_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    p = ProjectConfig(id="alpha", name="Alpha", root=str(tmp_path / "work"))
    updated = mutate_config_file(path, lambda c: add_project(c, p))
    assert len(updated.projects) == 1
    assert updated.projects[0].id == "alpha"

    loaded = load_config(path)
    assert loaded.projects[0].id == "alpha"


def test_remove_project_not_found(tmp_path: Path) -> None:
    cfg = AppConfig()
    with pytest.raises(ConfigMutationError, match="no project with id"):
        remove_project(cfg, "missing")


def test_update_project_requires_fields(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[ProjectConfig(id="p1", name="A", root=str(tmp_path))],
    )
    with pytest.raises(ConfigMutationError, match="at least one field"):
        update_project(cfg, "p1")


def test_update_project_rename_and_edit(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[ProjectConfig(id="p1", name="A", root=str(tmp_path / "r1"))],
    )
    cfg = normalize_app_config(cfg)
    updated = update_project(
        cfg,
        "p1",
        new_id="p2",
        name="B",
        root=str(tmp_path / "r2"),
    )
    assert updated.projects[0].id == "p2"
    assert updated.projects[0].name == "B"


def test_update_ai_config(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_config(AppConfig(), path)
    updated = mutate_config_file(
        path,
        lambda c: update_ai_config(c, model="gpt-test", api_key="TASKER_KEY"),
    )
    assert updated.ai.model == "gpt-test"
    assert updated.ai.api_key == "TASKER_KEY"


def test_read_config_or_default_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.toml"
    cfg = read_config_or_default(missing)
    assert cfg == AppConfig()


def test_validate_accepts_project_with_buckets_and_rules(tmp_path: Path) -> None:
    cfg = AppConfig(
        projects=[
            ProjectConfig(
                id="p1",
                name="A",
                root=str(tmp_path),
                buckets=[BucketConfig(name="inbox", relative_path="in")],
                rules=[RoutingRuleConfig(bucket="inbox", pattern="*.pdf")],
                default_bucket="inbox",
            ),
        ],
    )
    validate_app_config(normalize_app_config(cfg))
