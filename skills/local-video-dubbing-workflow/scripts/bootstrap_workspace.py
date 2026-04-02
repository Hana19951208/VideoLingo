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

from local_video_dubbing_workflow.bootstrap import DEFAULT_WORKSPACE_ROOT, initialize_workspace


def main():
    parser = argparse.ArgumentParser(description="初始化独立的视频翻译配音工作区。")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE_ROOT), help="工作区根目录")
    parser.add_argument("--terms-source", default="", help="初始词表来源，支持 xlsx 或 json")
    parser.add_argument("--create-venv", action="store_true", help="创建工作区 .venv")
    args = parser.parse_args()

    manifest = initialize_workspace(
        workspace_root=args.workspace,
        terms_source_path=args.terms_source or None,
        create_venv=args.create_venv,
    )
    print(f"workspace={manifest['workspace_root']}")
    print(f"terms_count={manifest['terms_count']}")


if __name__ == "__main__":
    main()
