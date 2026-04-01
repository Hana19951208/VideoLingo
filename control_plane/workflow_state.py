from __future__ import annotations

from core.st_utils.workflow_registry import get_stage_steps


def serialize_stage(stage_id: str) -> dict:
    steps = []
    for step in get_stage_steps(stage_id):
        steps.append(
            {
                "step_id": step.step_id,
                "title": step.title,
                "depends_on": list(step.depends_on),
                "artifact_patterns": list(step.artifact_patterns),
                "preview_patterns": list(step.preview_patterns),
            }
        )
    return {"stage_id": stage_id, "steps": steps}


def get_workspace_stages() -> list[dict]:
    return [serialize_stage("text"), serialize_stage("audio")]

