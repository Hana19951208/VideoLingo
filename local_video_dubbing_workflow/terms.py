from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


HEADER_ALIASES = {
    "src": ["source", "src"],
    "tgt": ["trans", "target", "translation", "tgt"],
    "note": ["explain(optional)", "explain", "note", "description"],
}


def _clean_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return " ".join(str(value).split()).strip()


def _normalize_key(text):
    text = _clean_value(text).lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _select_column(frame, aliases, fallback_index):
    normalized_columns = {str(column).strip().lower(): column for column in frame.columns}
    for alias in aliases:
        if alias in normalized_columns:
            return normalized_columns[alias]
    if fallback_index < len(frame.columns):
        return frame.columns[fallback_index]
    return None


def _normalize_term_record(term):
    src = _clean_value(term.get("src"))
    tgt = _clean_value(term.get("tgt")) or src
    note = _clean_value(term.get("note"))
    return {"src": src, "tgt": tgt, "note": note}


def deduplicate_terms(terms):
    deduped = []
    seen = set()
    for term in terms:
        normalized_term = _normalize_term_record(term)
        if not normalized_term["src"]:
            continue
        normalized_key = _normalize_key(normalized_term["src"])
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        deduped.append(normalized_term)
    return {"terms": deduped}


def load_terms_file(source_path):
    source_path = Path(source_path)
    if source_path.suffix.lower() == ".json":
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        return deduplicate_terms(payload.get("terms", []))

    frame = pd.read_excel(source_path)
    src_column = _select_column(frame, HEADER_ALIASES["src"], 0)
    tgt_column = _select_column(frame, HEADER_ALIASES["tgt"], 1)
    note_column = _select_column(frame, HEADER_ALIASES["note"], 2)

    terms = []
    for _, row in frame.iterrows():
        src = _clean_value(row[src_column]) if src_column is not None else ""
        tgt = _clean_value(row[tgt_column]) if tgt_column is not None else ""
        note = _clean_value(row[note_column]) if note_column is not None else ""
        if not src:
            continue
        terms.append({"src": src, "tgt": tgt or src, "note": note})
    return deduplicate_terms(terms)


def merge_term_sets(*term_sets):
    merged = []
    for term_set in term_sets:
        merged.extend((term_set or {}).get("terms", []))
    return deduplicate_terms(merged)


def export_terms_file(source_path, destination_path):
    source_path = Path(source_path)
    destination_path = Path(destination_path)
    payload = load_terms_file(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
