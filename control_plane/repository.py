from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select

from control_plane.models import GlobalSetting, NodeExecution, Project, ProjectOverride, Run


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_project(session, payload) -> Project:
    project = Project(**payload.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def get_project(session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def list_projects(session) -> list[Project]:
    return list(session.exec(select(Project).order_by(Project.updated_at.desc())).all())


def get_active_run(session) -> Run | None:
    return session.exec(select(Run).where(Run.status.in_(('processing', 'review_required')))).first()


def create_run(
    session,
    project: Project,
    config_snapshot: dict[str, Any],
    active_workspace_state: str | None = None,
) -> Run:
    project.status = 'processing'
    project.current_stage = 'text'
    project.current_step = 'b1_asr'
    project.progress_pct = 1
    project.updated_at = utc_now()
    run = Run(
        project_id=project.id,
        status='processing',
        active_workspace_state=active_workspace_state,
        config_snapshot_json=json.dumps(config_snapshot, ensure_ascii=False),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    for stage_id, step_id in [
        ('text', 'b1_asr'),
        ('text', 'b2_split_sentences'),
        ('text', 'b3_translate'),
        ('text', 'b4_split_long_subtitles'),
        ('text', 'b5_generate_subtitles'),
        ('text', 'b6_burn_video'),
        ('audio', 'c1_generate_audio_tasks'),
        ('audio', 'c2_extract_reference_audio'),
        ('audio', 'c3_select_reference_audio'),
        ('audio', 'c4_generate_audio_segments'),
        ('audio', 'c5_merge_full_audio'),
        ('audio', 'c6_merge_video'),
    ]:
        session.add(NodeExecution(run_id=run.id, stage_id=stage_id, step_id=step_id))
    session.commit()
    return run


def save_project_overrides(session, project_id: int, overrides: dict[str, Any]) -> ProjectOverride:
    row = session.exec(select(ProjectOverride).where(ProjectOverride.project_id == project_id)).first()
    if row is None:
        row = ProjectOverride(project_id=project_id, overrides_json=json.dumps(overrides, ensure_ascii=False))
        session.add(row)
    else:
        row.overrides_json = json.dumps(overrides, ensure_ascii=False)
        row.updated_at = utc_now()
        session.add(row)
    session.commit()
    session.refresh(row)
    return row


def save_global_overrides(session, overrides: dict[str, Any]) -> list[GlobalSetting]:
    rows = []
    for dotted_key, value in overrides.items():
        row = session.exec(select(GlobalSetting).where(GlobalSetting.dotted_key == dotted_key)).first()
        if row is None:
            row = GlobalSetting(dotted_key=dotted_key, value_json=json.dumps(value, ensure_ascii=False))
        else:
            row.value_json = json.dumps(value, ensure_ascii=False)
            row.updated_at = utc_now()
        session.add(row)
        rows.append(row)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows
