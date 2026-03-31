from __future__ import annotations

import json
import glob
from pathlib import Path

import pandas as pd


def _normalize_path(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/")


def list_preview_files(patterns: tuple[str, ...] | list[str], limit: int = 8) -> list[Path]:
    matches: list[Path] = []
    seen = set()
    for pattern in patterns:
        pattern_matches = [Path(match) for match in glob.glob(pattern)]
        if pattern_matches:
            for path in pattern_matches:
                normalized = _normalize_path(path)
                if normalized in seen:
                    continue
                seen.add(normalized)
                matches.append(path)
            continue

        path = Path(pattern)
        if path.exists():
            normalized = _normalize_path(path)
            if normalized not in seen:
                seen.add(normalized)
                matches.append(path)

    matches.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[:limit]


def load_preview_content(path: str | Path, max_rows: int = 20, max_chars: int = 4000) -> dict:
    preview_path = Path(path)
    suffix = preview_path.suffix.lower()

    if suffix == ".xlsx":
        return {
            "kind": "dataframe",
            "content": pd.read_excel(preview_path).head(max_rows),
        }

    raw_text = preview_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".json":
        try:
            parsed = json.loads(raw_text)
            return {
                "kind": "json",
                "content": json.dumps(parsed, ensure_ascii=False, indent=2)[:max_chars],
            }
        except json.JSONDecodeError:
            return {"kind": "text", "content": raw_text[:max_chars]}

    return {"kind": "text", "content": raw_text[:max_chars]}
