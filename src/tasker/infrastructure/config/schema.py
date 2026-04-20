"""Pydantic models for persisted user configuration (TOML)."""

from __future__ import annotations

from pydantic import BaseModel, Field

CONFIG_FORMAT_VERSION = 1


class AIConfig(BaseModel):
    """BYOK / OpenAI-compatible API settings."""

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"


class BucketConfig(BaseModel):
    """Named attachment destination under a project root."""

    name: str
    relative_path: str


class RoutingRuleConfig(BaseModel):
    """Attachment routing rule for bucket selection."""

    bucket: str
    pattern: str


class ProjectConfig(BaseModel):
    """User-defined project: working root plus buckets and routing rules."""

    id: str
    name: str
    root: str
    buckets: list[BucketConfig] = Field(default_factory=list)
    rules: list[RoutingRuleConfig] = Field(default_factory=list)
    default_bucket: str | None = None


class AppConfig(BaseModel):
    """Top-level Tasker configuration file."""

    version: int = CONFIG_FORMAT_VERSION
    ai: AIConfig = Field(default_factory=AIConfig)
    projects: list[ProjectConfig] = Field(default_factory=list)
