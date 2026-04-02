#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "local_video_dubbing_workflow").exists():
            return parent
    raise RuntimeError("Cannot locate local_video_dubbing_workflow package.")


sys.path.insert(0, str(_repo_root()))

from local_video_dubbing_workflow.bootstrap import DEFAULT_WORKSPACE_ROOT
from local_video_dubbing_workflow.review import review_and_correct_b4_outputs


def main():
    parser = argparse.ArgumentParser(description="审校并修正 b4 长字幕切分结果。")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE_ROOT), help="工作区根目录")
    parser.add_argument("--run-id", required=True, help="目标 run-id")
    args = parser.parse_args()

    run_dir = Path(args.workspace) / "runs" / args.run_id
    result = review_and_correct_b4_outputs(
        split_path=run_dir / "app" / "output" / "log" / "translation_results_for_subtitles.xlsx",
        remerged_path=run_dir / "app" / "output" / "log" / "translation_results_remerged.xlsx",
        glossary_path=run_dir / "glossary" / "custom_terms.json",
        report_dir=run_dir / "review",
    )

    state_path = run_dir / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "reviewed"
        state["review_result"] = result
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
