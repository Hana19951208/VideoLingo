from __future__ import annotations

import glob
import shutil
from pathlib import Path


def _normalize_path(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/")


def _expand_artifact_pattern(pattern: str) -> list[Path]:
    matches = [Path(match) for match in glob.glob(pattern)]
    if matches:
        return sorted(matches)

    path = Path(pattern)
    if any(token in pattern for token in ["*", "?", "["]):
        return []
    if path.exists():
        return [path]
    return []


def collect_existing_artifacts(patterns: tuple[str, ...] | list[str]) -> list[str]:
    existing_paths: list[str] = []
    seen = set()
    for pattern in patterns:
        for path in _expand_artifact_pattern(pattern):
            normalized = _normalize_path(path)
            if normalized in seen:
                continue
            seen.add(normalized)
            existing_paths.append(normalized)
    return sorted(existing_paths)


def step_has_all_artifacts(patterns: tuple[str, ...] | list[str]) -> bool:
    if not patterns:
        return False
    for pattern in patterns:
        if not _expand_artifact_pattern(pattern):
            return False
    return True


def cleanup_stage_outputs(
    stage_id: str,
    step_id: str,
    include_downstream: bool = True,
    stage_steps=None,
) -> list[str]:
    if stage_steps is None:
        from core.st_utils.workflow_registry import get_stage_steps

        stage_steps = get_stage_steps(stage_id)

    step_list = list(stage_steps)
    start_index = next(index for index, step in enumerate(step_list) if step.step_id == step_id)
    target_steps = step_list[start_index:] if include_downstream else [step_list[start_index]]
    target_patterns = [pattern for step in target_steps for pattern in step.artifact_patterns]
    existing_artifacts = collect_existing_artifacts(target_patterns)

    for artifact in existing_artifacts:
        artifact_path = Path(artifact)
        if artifact_path.is_dir():
            shutil.rmtree(artifact_path, ignore_errors=True)
        elif artifact_path.exists():
            artifact_path.unlink()

    return existing_artifacts
