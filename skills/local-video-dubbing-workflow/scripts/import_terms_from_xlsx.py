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

from local_video_dubbing_workflow.terms import export_terms_file


def main():
    parser = argparse.ArgumentParser(description="将 xlsx 词表导入为 JSON。")
    parser.add_argument("--source", required=True, help="xlsx 或 json 输入文件")
    parser.add_argument("--output", required=True, help="输出 json 路径")
    args = parser.parse_args()

    payload = export_terms_file(args.source, args.output)
    print(f"terms_count={len(payload.get('terms', []))}")


if __name__ == "__main__":
    main()
