from __future__ import annotations

from dataclasses import dataclass

from core.st_utils.workflow_registry import build_runner_steps, get_stage_steps
from core.utils.rerun_cleanup import cleanup_stage_outputs


@dataclass(frozen=True)
class StepRunPlan:
    deleted_artifacts: list[str]
    runner_steps: list[tuple[str, object]]


def _build_runner_steps_from_stage_steps(stage_steps, step_id: str, downstream: bool) -> list[tuple[str, object]]:
    step_list = list(stage_steps)
    step_index = next(index for index, step in enumerate(step_list) if step.step_id == step_id)
    target_steps = step_list[step_index:] if downstream else [step_list[step_index]]
    return [(step.title, step.run) for step in target_steps]


def prepare_step_run_plan(
    stage_id: str,
    step_id: str,
    action: str,
    stage_steps=None,
) -> StepRunPlan:
    if action == "run_only":
        return StepRunPlan(
            deleted_artifacts=[],
            runner_steps=(
                _build_runner_steps_from_stage_steps(stage_steps, step_id, downstream=False)
                if stage_steps is not None
                else build_runner_steps(stage_id, only_step_id=step_id)
            ),
        )

    if stage_steps is None:
        stage_steps = get_stage_steps(stage_id)

    if action == "rerun_only":
        deleted_artifacts = cleanup_stage_outputs(
            stage_id=stage_id,
            step_id=step_id,
            include_downstream=False,
            stage_steps=stage_steps,
        )
        return StepRunPlan(
            deleted_artifacts=deleted_artifacts,
            runner_steps=_build_runner_steps_from_stage_steps(stage_steps, step_id, downstream=False),
        )

    if action == "rerun_from_here":
        deleted_artifacts = cleanup_stage_outputs(
            stage_id=stage_id,
            step_id=step_id,
            include_downstream=True,
            stage_steps=stage_steps,
        )
        return StepRunPlan(
            deleted_artifacts=deleted_artifacts,
            runner_steps=_build_runner_steps_from_stage_steps(stage_steps, step_id, downstream=True),
        )

    raise ValueError(f"Unknown action: {action}")
