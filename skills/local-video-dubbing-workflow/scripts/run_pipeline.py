#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "local_video_dubbing_workflow").exists():
            return parent
    raise RuntimeError("Cannot locate local_video_dubbing_workflow package.")


sys.path.insert(0, str(_repo_root()))

from local_video_dubbing_workflow.bootstrap import DEFAULT_WORKSPACE_ROOT
from local_video_dubbing_workflow.pipeline import resume_run, start_new_run


def main():
    parser = argparse.ArgumentParser(description="运行独立的视频翻译配音流水线。")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE_ROOT), help="工作区根目录")
    parser.add_argument("--input-url", default="", help="YouTube 链接")
    parser.add_argument("--input-file", default="", help="本地视频或音频文件")
    parser.add_argument("--resolution", default="best", help="下载分辨率")
    parser.add_argument("--resume", default="", help="恢复指定 run-id")
    parser.add_argument("--from-step", default="", help="从指定 step_id 恢复")
    args = parser.parse_args()

    if args.resume:
        exit_code = resume_run(
            workspace_root=args.workspace,
            run_id=args.resume,
            start_step_id=args.from_step or None,
        )
        print(f"resume_run={args.resume}")
        raise SystemExit(exit_code)

    exit_code, run_id = start_new_run(
        workspace_root=args.workspace,
        input_url=args.input_url or None,
        input_file=args.input_file or None,
        resolution=args.resolution,
    )
    print(f"run_id={run_id}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
