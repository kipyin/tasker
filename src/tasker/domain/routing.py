"""Attachment routing result records (persisted on `Task`)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AttachmentRouteRecord:
    """One attachment routing outcome for a task."""

    filename: str
    bucket: str | None
    dest_path: str
    action: str
    detail: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d.get("detail") is None:
            d.pop("detail", None)
        return d
