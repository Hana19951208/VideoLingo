from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlmodel import select

from control_plane.db import session_scope
from control_plane.models import NodeExecution, Project, Run
from control_plane.repository import get_project, utc_now
from control_plane.runtime import get_log_root, get_workspace_root
from control_plane.subtitle_review import write_review_payload
from core.st_utils.workflow_registry import get_stage_steps


@dataclass(frozen=True)
class RunStep:
    index: int
    stage_id: str
    step_id: str
    title: str
    run: Callable[[], None]
    artifact_patterns: tuple[str, ...]


def _build_run_steps() -> tuple[RunStep, ...]:
    steps: list[RunStep] = []
    for stage_id in ('text', 'audio'):
        for step in get_stage_steps(stage_id):
            steps.append(
                RunStep(
                    index=len(steps),
                    stage_id=stage_id,
                    step_id=step.step_id,
                    title=step.title,
                    run=step.run,
                    artifact_patterns=tuple(step.artifact_patterns),
                )
            )
    return tuple(steps)


RUN_STEPS = _build_run_steps()
RUN_STEP_MAP = {step.step_id: step for step in RUN_STEPS}


def get_run_step(step_id: str) -> RunStep:
    if step_id not in RUN_STEP_MAP:
        raise KeyError(f'unknown step: {step_id}')
    return RUN_STEP_MAP[step_id]


def get_run_steps(start_step_id: str | None = None, only_step_id: str | None = None) -> list[RunStep]:
    if only_step_id is not None:
        return [get_run_step(only_step_id)]
    if start_step_id is None:
        return list(RUN_STEPS)
    start_step = get_run_step(start_step_id)
    return [step for step in RUN_STEPS if step.index >= start_step.index]


def _normalize_path(path: Path) -> str:
    return str(path).replace('\\', '/')


def _relative_to_workspace(path: Path) -> str:
    workspace_root = get_workspace_root().resolve()
    try:
        return _normalize_path(path.resolve().relative_to(workspace_root))
    except Exception:
        return _normalize_path(path)


def _resolve_pattern(pattern: str) -> str:
    path = Path(pattern)
    if path.is_absolute():
        return str(path)
    return str(get_workspace_root() / path)


def collect_artifacts_for_patterns(patterns: tuple[str, ...]) -> list[str]:
    from core.utils.rerun_cleanup import collect_existing_artifacts

    resolved_patterns = [_resolve_pattern(pattern) for pattern in patterns]
    existing = collect_existing_artifacts(resolved_patterns)
    return [_relative_to_workspace(Path(item)) for item in existing]


def cleanup_run_outputs(step_id: str, include_downstream: bool) -> list[str]:
    from core.utils.rerun_cleanup import collect_existing_artifacts

    target_steps = get_run_steps(start_step_id=step_id) if include_downstream else get_run_steps(only_step_id=step_id)
    target_patterns: list[str] = []
    for step in target_steps:
        target_patterns.extend(_resolve_pattern(pattern) for pattern in step.artifact_patterns)
    existing = collect_existing_artifacts(target_patterns)
    for item in existing:
        artifact = Path(item)
        if artifact.exists() and artifact.is_file():
            artifact.unlink()
    return [_relative_to_workspace(Path(item)) for item in existing]


def _artifact_target_for_pattern(step: RunStep, pattern: str) -> Path:
    resolved_pattern = Path(_resolve_pattern(pattern))
    if '*' not in pattern:
        return resolved_pattern
    filename = resolved_pattern.name
    filename = re.sub(r'\*+', step.step_id, filename)
    return resolved_pattern.parent / filename


def _write_fixture_artifact(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in {'.json'}:
        path.write_text(json.dumps({'fixture': True, 'path': path.name}, ensure_ascii=False, indent=2), encoding='utf-8')
        return
    if suffix in {'.srt', '.txt', '.md', '.log', '.yaml', '.yml'}:
        path.write_text(f'fixture:{path.name}\n', encoding='utf-8')
        return
    path.write_bytes(f'fixture:{path.name}'.encode('utf-8'))


def _run_fixture_step(project_id: int, step: RunStep) -> str:
    delay_ms = int(os.environ.get('VIDEOLINGO_CONTROL_PLANE_STEP_DELAY_MS', '20'))
    time.sleep(delay_ms / 1000)
    for pattern in step.artifact_patterns:
        _write_fixture_artifact(_artifact_target_for_pattern(step, pattern))
    if step.step_id == 'b5_generate_subtitles':
        write_review_payload(
            project_id,
            {
                'rows': [
                    {
                        'row_id': '1',
                        'start': '00:00:00,000',
                        'end': '00:00:02,000',
                        'source_text': 'Fixture subtitle',
                        'target_text': '夹具字幕',
                    }
                ]
            },
        )
    message = f'fixture step completed: {step.step_id}'
    log_file = get_log_root() / f'{step.step_id}.log'
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(message, encoding='utf-8')
    return message


@contextmanager
def workspace_cwd():
    workspace_root = get_workspace_root()
    workspace_root.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    os.chdir(workspace_root)
    try:
        yield
    finally:
        os.chdir(previous)


def execute_step(project_id: int, step: RunStep) -> str:
    if os.environ.get('VIDEOLINGO_CONTROL_PLANE_WORKFLOW_MODE') == 'fixture':
        return _run_fixture_step(project_id, step)
    with workspace_cwd():
        step.run()
    return f'completed: {step.step_id}'


class ControlPlaneRunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}

    def recover_orphaned_runs(self) -> None:
        with session_scope() as session:
            active_runs = session.exec(select(Run).where(Run.status.in_(('processing', 'review_required')))).all()
            for run in active_runs:
                run.status = 'failed'
                run.ended_at = utc_now()
                session.add(run)
                project = get_project(session, run.project_id)
                if project is None:
                    continue
                project.status = 'failed'
                project.updated_at = utc_now()
                session.add(project)
            session.commit()

    def has_active_thread(self, run_id: int) -> bool:
        thread = self._threads.get(run_id)
        return thread is not None and thread.is_alive()

    def start_run(self, run_id: int, start_step_id: str | None = None, only_step_id: str | None = None) -> None:
        with self._lock:
            if self.has_any_active_thread():
                raise RuntimeError('another run action is already executing')
            thread = threading.Thread(
                target=self._execute_steps,
                args=(run_id, start_step_id, only_step_id),
                daemon=True,
            )
            self._threads[run_id] = thread
            thread.start()

    def has_any_active_thread(self) -> bool:
        return any(thread.is_alive() for thread in self._threads.values())

    def reset_run_tail(self, run_id: int, step_id: str, include_downstream: bool) -> list[str]:
        deleted_artifacts = cleanup_run_outputs(step_id=step_id, include_downstream=include_downstream)
        target_steps = get_run_steps(start_step_id=step_id) if include_downstream else get_run_steps(only_step_id=step_id)
        target_step_ids = {step.step_id for step in target_steps}
        target_step = get_run_step(step_id)
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise KeyError(f'run not found: {run_id}')
            run.status = 'processing'
            run.ended_at = None
            session.add(run)

            project = get_project(session, run.project_id)
            if project is not None:
                project.status = 'processing'
                project.current_stage = target_step.stage_id
                project.current_step = target_step.step_id
                project.updated_at = utc_now()
                session.add(project)

            rows = session.exec(select(NodeExecution).where(NodeExecution.run_id == run_id)).all()
            for row in rows:
                if row.step_id not in target_step_ids:
                    continue
                row.status = 'pending'
                row.started_at = None
                row.ended_at = None
                row.artifact_manifest_json = '[]'
                row.log_excerpt = None
                row.error_summary = None
                session.add(row)
            session.commit()
        return deleted_artifacts

    def _execute_steps(self, run_id: int, start_step_id: str | None, only_step_id: str | None) -> None:
        steps = get_run_steps(start_step_id=start_step_id, only_step_id=only_step_id)
        for step in steps:
            try:
                self._mark_step_running(run_id, step)
                log_excerpt = execute_step(self._get_project_id(run_id), step)
            except Exception as error:
                try:
                    self._mark_step_failed(run_id, step, error)
                except Exception:
                    log_file = get_log_root() / 'task_runner_errors.log'
                    log_file.parent.mkdir(parents=True, exist_ok=True)
                    log_file.write_text(traceback.format_exc(), encoding='utf-8')
                return

            self._mark_step_completed(run_id, step, log_excerpt)
            if step.step_id == 'b5_generate_subtitles':
                self._mark_review_required(run_id, step)
                return

        self._mark_run_completed(run_id, steps[-1] if steps else None)

    def _get_project_id(self, run_id: int) -> int:
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise KeyError(f'run not found: {run_id}')
            return run.project_id

    def _mark_step_running(self, run_id: int, step: RunStep) -> None:
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise KeyError(f'run not found: {run_id}')
            run.status = 'processing'
            session.add(run)

            project = get_project(session, run.project_id)
            if project is not None:
                project.status = 'processing'
                project.current_stage = step.stage_id
                project.current_step = step.step_id
                project.progress_pct = min(int((step.index / len(RUN_STEPS)) * 100), 99)
                project.updated_at = utc_now()
                session.add(project)

            node = session.exec(
                select(NodeExecution).where(NodeExecution.run_id == run_id, NodeExecution.step_id == step.step_id)
            ).first()
            if node is not None:
                node.status = 'running'
                node.started_at = utc_now()
                node.ended_at = None
                node.error_summary = None
                session.add(node)
            session.commit()

    def _mark_step_completed(self, run_id: int, step: RunStep, log_excerpt: str) -> None:
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.status = 'processing'
                session.add(run)
            node = session.exec(
                select(NodeExecution).where(NodeExecution.run_id == run_id, NodeExecution.step_id == step.step_id)
            ).first()
            if node is not None:
                node.status = 'completed'
                node.ended_at = utc_now()
                node.log_excerpt = log_excerpt
                node.error_summary = None
                node.artifact_manifest_json = json.dumps(collect_artifacts_for_patterns(step.artifact_patterns), ensure_ascii=False)
                session.add(node)

            project = get_project(session, run.project_id) if run is not None else None
            if project is not None:
                project.progress_pct = min(int(((step.index + 1) / len(RUN_STEPS)) * 100), 99)
                project.updated_at = utc_now()
                session.add(project)
            session.commit()

    def _mark_review_required(self, run_id: int, step: RunStep) -> None:
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.status = 'review_required'
                session.add(run)
            project = get_project(session, run.project_id) if run is not None else None
            if project is not None:
                project.status = 'review_required'
                project.current_stage = step.stage_id
                project.current_step = step.step_id
                project.progress_pct = min(int(((step.index + 1) / len(RUN_STEPS)) * 100), 99)
                project.updated_at = utc_now()
                session.add(project)
            session.commit()

    def _mark_step_failed(self, run_id: int, step: RunStep, error: Exception) -> None:
        traceback_text = traceback.format_exc()
        log_file = get_log_root() / 'task_runner_errors.log'
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(traceback_text, encoding='utf-8')
        with session_scope() as session:
            run = session.get(Run, run_id)
            node = session.exec(
                select(NodeExecution).where(NodeExecution.run_id == run_id, NodeExecution.step_id == step.step_id)
            ).first()
            if node is not None:
                node.status = 'failed'
                node.ended_at = utc_now()
                node.error_summary = str(error)
                node.log_excerpt = traceback_text[-1000:]
                session.add(node)
            if run is not None:
                run.status = 'failed'
                run.ended_at = utc_now()
                session.add(run)
            project = get_project(session, run.project_id) if run is not None else None
            if project is not None:
                project.status = 'failed'
                project.current_stage = step.stage_id
                project.current_step = step.step_id
                project.updated_at = utc_now()
                session.add(project)
            session.commit()

    def _mark_run_completed(self, run_id: int, last_step: RunStep | None) -> None:
        with session_scope() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.status = 'completed'
                run.ended_at = utc_now()
                session.add(run)
            project = get_project(session, run.project_id) if run is not None else None
            if project is not None:
                project.status = 'completed'
                project.current_stage = last_step.stage_id if last_step is not None else project.current_stage
                project.current_step = last_step.step_id if last_step is not None else project.current_step
                project.progress_pct = 100
                project.updated_at = utc_now()
                session.add(project)
            session.commit()
