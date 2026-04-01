from __future__ import annotations

import json
from pathlib import Path

from control_plane.runtime import get_history_root


def get_review_file(project_id: int) -> Path:
    review_dir = get_history_root() / str(project_id) / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    return review_dir / "subtitle_review.json"


def read_review_payload(project_id: int) -> dict:
    review_file = get_review_file(project_id)
    if not review_file.exists():
        return {"rows": []}
    return json.loads(review_file.read_text(encoding="utf-8"))


def write_review_payload(project_id: int, payload: dict) -> dict:
    review_file = get_review_file(project_id)
    review_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

