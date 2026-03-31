import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class TerminologyPipelineTests(unittest.TestCase):
    def _write_terms_file(self, rows, columns):
        temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_terms_"))
        path = temp_dir / "custom_terms.xlsx"
        pd.DataFrame(rows, columns=columns).to_excel(path, index=False)
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_dir, ignore_errors=True))
        return path

    def test_load_custom_terms_prefers_named_headers_and_deduplicates(self):
        from core._shared_terminology import load_custom_terms

        path = self._write_terms_file(
            rows=[
                [" Claude Code ", "Claude Code", "Anthropic CLI"],
                ["Claude Code", "Claude Code", "重复项"],
                ["", "忽略", "空源词"],
                ["Openclaw", "Openclaw", None],
            ],
            columns=["Source", "Trans", "Explain(Optional)"],
        )

        result = load_custom_terms(path)

        self.assertEqual(
            result["terms"],
            [
                {"src": "Claude Code", "tgt": "Claude Code", "note": "Anthropic CLI"},
                {"src": "Openclaw", "tgt": "Openclaw", "note": ""},
            ],
        )

    def test_load_custom_terms_falls_back_to_first_three_columns(self):
        from core._shared_terminology import load_custom_terms

        path = self._write_terms_file(
            rows=[
                ["Cloud Code", "Claude Code", "需要纠偏"],
                ["vLLM", "vLLM", "推理引擎"],
            ],
            columns=["A", "B", "C"],
        )

        result = load_custom_terms(path)

        self.assertEqual(result["terms"][0]["src"], "Cloud Code")
        self.assertEqual(result["terms"][0]["tgt"], "Claude Code")
        self.assertEqual(result["terms"][0]["note"], "需要纠偏")

    def test_build_asr_hints_returns_hotwords_and_trimmed_prompt(self):
        from core._shared_terminology import build_asr_hints

        terms = {
            "terms": [
                {"src": f"Claude Code {index}", "tgt": f"Claude Code {index}", "note": "测试"}
                for index in range(8)
            ]
        }

        hints = build_asr_hints(terms, max_terms=3, max_prompt_chars=60)

        self.assertIn("hotwords", hints)
        self.assertIn("initial_prompt", hints)
        self.assertIn("Claude Code 0", hints["hotwords"])
        self.assertNotIn("Claude Code 4", hints["hotwords"])
        self.assertLessEqual(len(hints["initial_prompt"]), 60)
        self.assertTrue(hints["initial_prompt"].strip())

    def test_build_relevant_terms_prompt_supports_approximate_match(self):
        from core._shared_terminology import build_relevant_terms_prompt

        prompt = build_relevant_terms_prompt(
            "Cloud Code can open apps while OpenCloud keeps sessions alive.",
            {
                "terms": [
                    {"src": "Claude Code", "tgt": "Claude Code", "note": "正确产品名"},
                    {"src": "Openclaw", "tgt": "Openclaw", "note": "正确项目名"},
                ]
            },
        )

        self.assertIn("Claude Code", prompt)
        self.assertIn("Openclaw", prompt)

    def test_prompts_include_glossary_and_normalization_rule(self):
        from core._shared_prompts import (
            generate_shared_prompt,
            get_prompt_expressiveness,
            get_prompt_faithfulness,
            get_summary_prompt,
        )

        glossary = {
            "terms": [
                {"src": "Claude Code", "tgt": "Claude Code", "note": "Anthropic CLI"},
                {"src": "Openclaw", "tgt": "Openclaw", "note": "项目名"},
            ]
        }

        with patch("core._shared_prompts.load_key", side_effect=lambda key: {
            "whisper.detected_language": "en",
            "target_language": "简体中文",
        }[key]):
            summary_prompt = get_summary_prompt("Cloud Code is shipping fast.", glossary)
            shared_prompt = generate_shared_prompt(
                ["previous line"],
                ["next line"],
                "主题摘要",
                "补充术语",
                glossary,
            )
            faith_prompt = get_prompt_faithfulness("Cloud Code is shipping fast.", shared_prompt)
            express_prompt = get_prompt_expressiveness(
                {"1": {"origin": "Cloud Code", "direct": "Cloud Code"}},
                "Cloud Code",
                shared_prompt,
            )

        for prompt in [summary_prompt, faith_prompt, express_prompt]:
            self.assertIn("Claude Code", prompt)
            self.assertIn("Openclaw", prompt)
            self.assertIn("normalize", prompt.lower())


if __name__ == "__main__":
    unittest.main()
