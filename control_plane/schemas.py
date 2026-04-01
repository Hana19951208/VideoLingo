from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    source_type: str
    source_uri_or_path: str
    source_lang: str
    target_lang: str


class SettingsUpdate(BaseModel):
    project_id: Optional[int] = None
    overrides: dict[str, Any]


class SubtitleReviewRow(BaseModel):
    row_id: str
    start: str
    end: str
    source_text: str
    target_text: str


class SubtitleReviewPayload(BaseModel):
    rows: list[SubtitleReviewRow]


class RunActionPayload(BaseModel):
    action: str
    stage_id: Optional[str] = None
    step_id: Optional[str] = None

