from __future__ import annotations

import glob
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import select

from control_plane.config_state import build_effective_settings, build_masked_global_settings
from control_plane.db import init_db, session_scope
from control_plane.execution import ControlPlaneRunManager, get_run_step
from control_plane.models import NodeExecution, Project, Run
from control_plane.repository import (
    create_project,
    create_run,
    get_active_run,
    get_project,
    list_projects,
    save_global_overrides,
    save_project_overrides,
    utc_now,
)
from control_plane.runtime import get_log_root, get_workspace_root
from control_plane.schemas import ProjectCreate, RunActionPayload, SettingsUpdate, SubtitleReviewPayload
from control_plane.source_ingest import RemoteSourceDownloadError, materialize_project_source
from control_plane.subtitle_review import read_review_payload, write_review_payload
from control_plane.workflow_state import get_workspace_stages


def serialize_project(project: Project) -> dict:
    return {
        'id': str(project.id),
        'name': project.name,
        'source_type': project.source_type,
        'source_uri_or_path': project.source_uri_or_path,
        'source_lang': project.source_lang,
        'target_lang': project.target_lang,
        'status': project.status,
        'progress_pct': project.progress_pct,
        'current_stage': project.current_stage,
        'current_step': project.current_step,
        'cover_path': project.cover_path,
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat(),
    }


def build_step_index() -> dict[str, dict]:
    return {
        step['step_id']: {**step, 'stage_id': stage['stage_id']}
        for stage in get_workspace_stages()
        for step in stage['steps']
    }


def collect_artifacts_for_pattern(pattern: str) -> list[str]:
    workspace_root = get_workspace_root()
    matches = sorted(glob.glob(str(workspace_root / pattern)))
    return [str(Path(match).relative_to(workspace_root)).replace('\\', '/') for match in matches]


def collect_log_entries() -> list[dict]:
    entries: list[dict] = []
    for log_file in sorted(get_log_root().glob('*.log')):
        entries.append(
            {
                'name': log_file.name,
                'content': log_file.read_text(encoding='utf-8'),
                'source': 'log_root',
            }
        )
    return entries


def resolve_workspace_file(relative_path: str) -> Path:
    workspace_root = get_workspace_root().resolve()
    target = (workspace_root / relative_path).resolve()
    if workspace_root not in target.parents and target != workspace_root:
        raise HTTPException(status_code=400, detail='invalid artifact path')
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail='artifact not found')
    return target


def create_app() -> FastAPI:
    init_db()
    run_manager = ControlPlaneRunManager()
    run_manager.recover_orphaned_runs()
    app = FastAPI(title='VideoLingo Control Plane')
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.get('/projects')
    def get_projects():
        with session_scope() as session:
            return [serialize_project(project) for project in list_projects(session)]

    @app.post('/projects', status_code=201)
    def post_project(payload: ProjectCreate):
        with session_scope() as session:
            project = create_project(session, payload)
            return serialize_project(project)

    @app.get('/projects/{project_id}')
    def get_project_detail(project_id: int):
        with session_scope() as session:
            project = get_project(session, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail='project not found')
            return serialize_project(project)

    @app.get('/projects/{project_id}/workspace')
    def get_project_workspace(project_id: int):
        with session_scope() as session:
            project = get_project(session, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail='project not found')
            latest_run = session.exec(
                select(Run).where(Run.project_id == project_id).order_by(Run.started_at.desc())
            ).first()
            return {
                'project': serialize_project(project),
                'stages': get_workspace_stages(),
                'effective_settings': build_effective_settings(session, project_id),
                'latest_run_id': str(latest_run.id) if latest_run is not None else None,
            }

    @app.post('/projects/{project_id}/runs', status_code=201)
    def post_project_run(project_id: int):
        with session_scope() as session:
            project = get_project(session, project_id)
            if project is None:
                raise HTTPException(status_code=404, detail='project not found')
            active_run = get_active_run(session)
            if active_run is not None and active_run.project_id != project_id:
                raise HTTPException(status_code=409, detail='active project is already running')

            try:
                source_state = materialize_project_source(project)
            except FileNotFoundError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except RemoteSourceDownloadError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            except Exception as error:
                raise HTTPException(status_code=500, detail=f'prepare project source failed: {error}') from error

            run = create_run(
                session,
                project,
                {key: data['value'] for key, data in build_effective_settings(session, project_id).items()},
                active_workspace_state=source_state['source_state'],
            )
            run_manager.start_run(run.id)
            return {
                'id': str(run.id),
                'project_id': str(run.project_id),
                'status': run.status,
                'started_at': run.started_at.isoformat(),
                'active_workspace_state': run.active_workspace_state,
            }

    @app.post('/runs/{run_id}/actions')
    def post_run_action(run_id: int, payload: RunActionPayload):
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail='run not found')
            project = session.get(Project, run.project_id)
            if payload.action == 'approve_subtitles_and_continue':
                if project is None:
                    raise HTTPException(status_code=404, detail='project not found')
                if run.status != 'review_required':
                    raise HTTPException(status_code=409, detail='run is not waiting for subtitle review')
                try:
                    run_manager.start_run(run.id, start_step_id='b6_burn_video')
                except RuntimeError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                return {'run_id': str(run_id), 'accepted': True, 'action': payload.action}

            if payload.action in {'run_step', 'rerun_step', 'rerun_from_step', 'cleanup_step_and_downstream'}:
                if not payload.step_id:
                    raise HTTPException(status_code=400, detail='step_id is required for step actions')
                try:
                    step = get_run_step(payload.step_id)
                except KeyError as error:
                    raise HTTPException(status_code=400, detail=str(error)) from error
                if payload.stage_id is not None and payload.stage_id != step.stage_id:
                    raise HTTPException(status_code=400, detail='stage_id does not match step_id')

                try:
                    if payload.action == 'run_step':
                        run_manager.start_run(run.id, only_step_id=step.step_id)
                    elif payload.action == 'rerun_step':
                        run_manager.reset_run_tail(run.id, step.step_id, include_downstream=False)
                        run_manager.start_run(run.id, only_step_id=step.step_id)
                    elif payload.action == 'rerun_from_step':
                        run_manager.reset_run_tail(run.id, step.step_id, include_downstream=True)
                        run_manager.start_run(run.id, start_step_id=step.step_id)
                    else:
                        run_manager.reset_run_tail(run.id, step.step_id, include_downstream=True)
                except RuntimeError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error

                return {'run_id': str(run_id), 'accepted': True, 'action': payload.action}

            raise HTTPException(status_code=400, detail='unknown run action')

    @app.get('/runs/{run_id}/nodes')
    def get_run_nodes(run_id: int):
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail='run not found')
            step_index = build_step_index()
            nodes = []
            rows = session.exec(select(NodeExecution).where(NodeExecution.run_id == run_id).order_by(NodeExecution.id.asc())).all()
            for row in rows:
                metadata = step_index.get(row.step_id, {})
                nodes.append(
                    {
                        'step_id': row.step_id,
                        'stage_id': row.stage_id,
                        'status': row.status,
                        'title': metadata.get('title', row.step_id),
                        'artifact_patterns': metadata.get('artifact_patterns', []),
                        'depends_on': metadata.get('depends_on', []),
                        'log_excerpt': row.log_excerpt,
                        'error_summary': row.error_summary,
                    }
                )
            return {'run_id': str(run_id), 'nodes': nodes}

    @app.get('/runs/{run_id}/artifacts')
    def get_run_artifacts(run_id: int):
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail='run not found')
            step_index = build_step_index()
            artifacts = []
            rows = session.exec(select(NodeExecution).where(NodeExecution.run_id == run_id).order_by(NodeExecution.id.asc())).all()
            for row in rows:
                metadata = step_index.get(row.step_id, {})
                files: list[str] = []
                for pattern in metadata.get('artifact_patterns', []):
                    files.extend(collect_artifacts_for_pattern(pattern))
                artifacts.append(
                    {
                        'step_id': row.step_id,
                        'stage_id': row.stage_id,
                        'files': sorted(dict.fromkeys(files)),
                    }
                )
            return {'run_id': str(run_id), 'artifacts': artifacts}

    @app.get('/runs/{run_id}/logs')
    def get_run_logs(run_id: int):
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail='run not found')
            return {'run_id': str(run_id), 'logs': collect_log_entries()}

    @app.get('/runs/{run_id}/stream')
    def get_run_stream(run_id: int):
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise HTTPException(status_code=404, detail='run not found')
            payload = {'run_id': str(run_id), 'logs': collect_log_entries()}

        def event_stream():
            yield f"event: snapshot\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    @app.get('/artifacts/file')
    def get_artifact_file(path: str = Query(..., min_length=1)):
        file_path = resolve_workspace_file(path)
        return FileResponse(file_path)

    @app.get('/projects/{project_id}/subtitle-review')
    def get_subtitle_review(project_id: int):
        return read_review_payload(project_id)

    @app.put('/projects/{project_id}/subtitle-review')
    def put_subtitle_review(project_id: int, payload: SubtitleReviewPayload):
        return write_review_payload(project_id, payload.model_dump())

    @app.get('/settings')
    def get_settings():
        with session_scope() as session:
            return {'global': build_masked_global_settings(session)}

    @app.put('/settings')
    def put_settings(payload: SettingsUpdate):
        with session_scope() as session:
            if payload.project_id is None:
                rows = save_global_overrides(session, payload.overrides)
                return {'scope': 'global', 'updated_keys': [row.dotted_key for row in rows]}

            project = get_project(session, payload.project_id)
            if project is None:
                raise HTTPException(status_code=404, detail='project not found')
            row = save_project_overrides(session, payload.project_id, payload.overrides)
            return {'scope': 'project', 'project_id': row.project_id, 'overrides': payload.overrides}

    return app
