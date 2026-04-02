from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from .terms import load_terms_file, merge_term_sets


@dataclass(frozen=True)
class Correction:
    original: str
    corrected_to: str
    translation: str
    reason: str
    confidence: float


def _normalize_text(text):
    return "".join(character.lower() for character in str(text).strip() if character.isalnum())


def _similarity(left, right):
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _is_short_term(text):
    return len(str(text).strip().split()) <= 3 and len(str(text).strip()) <= 24


def _find_high_confidence_term(source_text, glossary_terms):
    if not _is_short_term(source_text):
        return None

    candidates = []
    for term in glossary_terms:
        similarity = _similarity(source_text, term["src"])
        if source_text.strip().lower() == term["src"].strip().lower():
            continue
        if similarity >= 0.55:
            candidates.append((similarity, term))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    confidence, term = candidates[0]
    if len(candidates) > 1 and confidence - candidates[1][0] < 0.08:
        return None
    return confidence, term


def _append_glossary_alias(glossary, original_text, corrected_term):
    alias_term = {
        "src": str(original_text).strip(),
        "tgt": corrected_term["src"],
        "note": f"Auto-added from b4 review for {corrected_term['src']}",
    }
    merged = merge_term_sets({"terms": glossary.get("terms", [])}, {"terms": [alias_term]})
    return merged, alias_term


def review_and_correct_b4_outputs(split_path, remerged_path, glossary_path, report_dir):
    split_path = Path(split_path)
    remerged_path = Path(remerged_path)
    glossary_path = Path(glossary_path)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    split_df = pd.read_excel(split_path)
    remerged_df = pd.read_excel(remerged_path)
    glossary = load_terms_file(glossary_path)
    corrections = []
    glossary_updates = []

    for index, row in split_df.iterrows():
        source_text = str(row.get("Source", "")).strip()
        if not source_text:
            continue

        match = _find_high_confidence_term(source_text, glossary.get("terms", []))
        if not match:
            continue

        confidence, corrected_term = match
        correction = Correction(
            original=source_text,
            corrected_to=corrected_term["src"],
            translation=corrected_term["tgt"],
            reason="high_confidence_glossary_match",
            confidence=round(confidence, 3),
        )
        corrections.append(correction)

        split_df.at[index, "Source"] = corrected_term["src"]
        split_df.at[index, "Translation"] = corrected_term["tgt"]
        if index < len(remerged_df):
            remerged_df.at[index, "Source"] = corrected_term["src"]
            remerged_df.at[index, "Translation"] = corrected_term["tgt"]

        glossary, alias_term = _append_glossary_alias(glossary, source_text, corrected_term)
        glossary_updates.append(
            {
                "original": source_text,
                "corrected_to": corrected_term["src"],
                "alias_term": alias_term,
                "confidence": round(confidence, 3),
            }
        )

    split_df.to_excel(split_path, index=False)
    remerged_df.to_excel(remerged_path, index=False)
    glossary_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")

    (report_dir / "b4_corrections.json").write_text(
        json.dumps(
            {
                "auto_corrected_count": len(corrections),
                "corrections": [correction.__dict__ for correction in corrections],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (report_dir / "glossary_updates.json").write_text(
        json.dumps({"updates": glossary_updates}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "auto_corrected_count": len(corrections),
        "glossary_update_count": len(glossary_updates),
    }
