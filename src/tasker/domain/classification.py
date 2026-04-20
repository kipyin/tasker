"""Structured AI output for project classification."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClassificationProposal(BaseModel):
    """AI output: chosen project for an email; apply only after user confirms."""

    project_id: str = Field(
        min_length=1,
        description="Must match a project `id` from the user config.",
    )
    rationale: str = Field(
        min_length=1,
        description="Short explanation for the user.",
    )
    suggested_title: str | None = Field(
        default=None,
        description="Optional improved task title; omit to keep the current title.",
    )
