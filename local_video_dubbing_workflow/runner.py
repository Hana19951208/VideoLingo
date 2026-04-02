from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


SUCCESS_EXIT_CODE = 0
REVIEW_REQUIRED_EXIT_CODE = 10
ERROR_EXIT_CODE = 20
CONFIG_ERROR_EXIT_CODE = 30


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    title: str
    action: Callable[[], None]


class WorkflowRunner:
    def __init__(self, run_dir):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.state_path = self.run_dir / "state.json"

    def _append_event(self, event_type, **payload):
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": event_type,
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _write_state(self, status, **payload):
        state = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            **payload,
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def run(self, steps, stop_after_step=None, review_payload=None):
        executed_steps = []
        self._write_state("running", current_step=None, executed_steps=executed_steps)
        self._append_event("run_started")

        try:
            for step in steps:
                self._write_state("running", current_step=step.step_id, executed_steps=executed_steps)
                self._append_event("step_started", step_id=step.step_id, title=step.title)
                step.action()
                executed_steps.append(step.step_id)
                self._append_event("step_completed", step_id=step.step_id, title=step.title)

                if stop_after_step and step.step_id == stop_after_step:
                    review_required_path = self.run_dir / "review_required.json"
                    review_required_path.write_text(
                        json.dumps(review_payload or {"step": step.step_id}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    self._write_state(
                        "review_required",
                        current_step=step.step_id,
                        executed_steps=executed_steps,
                    )
                    self._append_event("review_required", step_id=step.step_id)
                    return REVIEW_REQUIRED_EXIT_CODE

            self._write_state("completed", current_step=None, executed_steps=executed_steps)
            self._append_event("run_completed")
            return SUCCESS_EXIT_CODE
        except Exception as error:
            error_path = self.run_dir / "error.json"
            error_payload = {
                "message": str(error),
                "traceback": traceback.format_exc(),
                "executed_steps": executed_steps,
            }
            error_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._write_state("error", current_step=None, executed_steps=executed_steps, error=str(error))
            self._append_event("run_failed", error=str(error))
            return ERROR_EXIT_CODE
