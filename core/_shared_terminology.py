import json
import os
import re
from difflib import SequenceMatcher

import pandas as pd

from core.utils.models import _4_1_TERMINOLOGY

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


def load_custom_terms(path="custom_terms.xlsx"):
    if not os.path.exists(path):
        return {"terms": []}

    frame = pd.read_excel(path)
    src_column = _select_column(frame, HEADER_ALIASES["src"], 0)
    tgt_column = _select_column(frame, HEADER_ALIASES["tgt"], 1)
    note_column = _select_column(frame, HEADER_ALIASES["note"], 2)

    terms = []
    seen = set()
    for _, row in frame.iterrows():
        src = _clean_value(row[src_column]) if src_column is not None else ""
        tgt = _clean_value(row[tgt_column]) if tgt_column is not None else ""
        note = _clean_value(row[note_column]) if note_column is not None else ""
        if not src:
            continue
        normalized = _normalize_key(src)
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append({"src": src, "tgt": tgt or src, "note": note})
    return {"terms": terms}


def load_terminology_terms(path=_4_1_TERMINOLOGY):
    if not os.path.exists(path):
        return {"terms": []}
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return {"terms": data.get("terms", [])}


def merge_terms(*term_sets):
    merged = []
    seen = set()
    for term_set in term_sets:
        for term in (term_set or {}).get("terms", []):
            src = _clean_value(term.get("src"))
            if not src:
                continue
            normalized = _normalize_key(src)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(
                {
                    "src": src,
                    "tgt": _clean_value(term.get("tgt")) or src,
                    "note": _clean_value(term.get("note")),
                }
            )
    return {"terms": merged}


def format_terms_list(terms_json, max_terms=None):
    lines = []
    for index, term in enumerate(terms_json.get("terms", [])):
        if max_terms is not None and index >= max_terms:
            break
        note = f" | note: {term['note']}" if term.get("note") else ""
        lines.append(f"- {term['src']} => {term['tgt']}{note}")
    return "\n".join(lines)


def build_asr_hints(terms_json, max_terms=50, max_prompt_chars=200):
    selected_terms = terms_json.get("terms", [])[:max_terms]
    hotwords = ", ".join(term["src"] for term in selected_terms if term.get("src"))
    prompt_terms = []
    current_length = 0
    for term in selected_terms:
        src = term.get("src", "")
        if not src:
            continue
        candidate = src if not prompt_terms else f", {src}"
        if current_length + len(candidate) > max_prompt_chars:
            break
        prompt_terms.append(src)
        current_length += len(candidate)
    return {
        "hotwords": hotwords,
        "initial_prompt": ", ".join(prompt_terms),
    }


def build_glossary_prompt(terms_json, title="User Glossary", include_normalization_rule=True):
    if not terms_json.get("terms"):
        return ""
    glossary_lines = format_terms_list(terms_json)
    rule = ""
    if include_normalization_rule:
        rule = (
            "\nUse this glossary as the source of truth. "
            "If the transcript contains near-homophones, misspellings, or contextually obvious ASR mistakes, "
            "normalize them to the glossary term before continuing."
        )
    return f"### {title}\n{glossary_lines}{rule}"


def _contains_approximate_match(text, candidate):
    normalized_text = _normalize_key(text)
    normalized_candidate = _normalize_key(candidate)
    if not normalized_text or not normalized_candidate:
        return False
    if normalized_candidate in normalized_text:
        return True

    text_tokens = normalized_text.split()
    candidate_tokens = normalized_candidate.split()
    window_size = max(1, len(candidate_tokens))
    if len(text_tokens) < window_size:
        windows = [normalized_text]
    else:
        windows = [
            " ".join(text_tokens[index:index + window_size])
            for index in range(len(text_tokens) - window_size + 1)
        ]
    threshold = 0.7 if window_size == 1 else 0.72
    return any(
        SequenceMatcher(None, window, normalized_candidate).ratio() >= threshold
        for window in windows
    )


def build_relevant_terms_prompt(text, terms_json, max_terms=8):
    relevant_terms = []
    for term in terms_json.get("terms", []):
        if _contains_approximate_match(text, term.get("src", "")):
            relevant_terms.append(term)
        if len(relevant_terms) >= max_terms:
            break
    if not relevant_terms:
        return None
    return build_glossary_prompt({"terms": relevant_terms}, title="Relevant Terminology", include_normalization_rule=True)
