from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    source_type: str
    source_uri_or_path: str
    source_lang: str
    target_lang: str
    status: str = Field(default='draft')
    progress_pct: int = Field(default=0)
    current_stage: Optional[str] = Field(default=None)
    current_step: Optional[str] = Field(default=None)
    cover_path: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key='project.id')
    status: str = Field(default='processing')
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: Optional[datetime] = Field(default=None)
    active_workspace_state: Optional[str] = Field(default=None)
    archive_path: Optional[str] = Field(default=None)
    config_snapshot_json: str = Field(default='{}')


class NodeExecution(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True, foreign_key='run.id')
    stage_id: str
    step_id: str
    status: str = Field(default='pending')
    started_at: Optional[datetime] = Field(default=None)
    ended_at: Optional[datetime] = Field(default=None)
    artifact_manifest_json: str = Field(default='[]')
    log_excerpt: Optional[str] = Field(default=None)
    error_summary: Optional[str] = Field(default=None)


class ProjectOverride(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(index=True, foreign_key='project.id', unique=True)
    overrides_json: str = Field(default='{}')
    updated_at: datetime = Field(default_factory=utc_now)


class GlobalSetting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    dotted_key: str = Field(index=True, unique=True)
    value_json: str
    updated_at: datetime = Field(default_factory=utc_now)
