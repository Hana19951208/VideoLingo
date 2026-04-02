import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videodub_workflow_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_custom_terms_supports_json_files(self):
        from core._shared_terminology import load_custom_terms

        terms_path = self.temp_dir / "custom_terms.json"
        terms_path.write_text(
            json.dumps(
                {
                    "terms": [
                        {"src": "Claude", "tgt": "Claude", "note": "Anthropic model"},
                        {"src": "Haiku", "tgt": "Haiku", "note": "Anthropic model"},
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = load_custom_terms(terms_path)

        self.assertEqual(len(result["terms"]), 2)
        self.assertEqual(result["terms"][0]["src"], "Claude")
        self.assertEqual(result["terms"][1]["tgt"], "Haiku")

    def test_resolve_api_settings_prefers_environment_variable(self):
        from local_video_dubbing_workflow.config import resolve_api_settings

        config_path = self.temp_dir / "config.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "api:",
                    "  key: 'config-key'",
                    "  base_url: 'https://api.deepseek.com'",
                    "  model: 'deepseek-chat'",
                    "  llm_support_json: false",
                ]
            ),
            encoding="utf-8",
        )

        previous = __import__("os").environ.get("DEEPSEEK_API_KEY")
        __import__("os").environ["DEEPSEEK_API_KEY"] = "env-key"
        try:
            settings = resolve_api_settings(config_path)
        finally:
            if previous is None:
                __import__("os").environ.pop("DEEPSEEK_API_KEY", None)
            else:
                __import__("os").environ["DEEPSEEK_API_KEY"] = previous

        self.assertEqual(settings["api_key"], "env-key")
        self.assertEqual(settings["base_url"], "https://api.deepseek.com")
        self.assertEqual(settings["model"], "deepseek-chat")

    def test_runner_stops_at_review_checkpoint_with_exit_code_10(self):
        from local_video_dubbing_workflow.runner import (
            REVIEW_REQUIRED_EXIT_CODE,
            StepSpec,
            WorkflowRunner,
        )

        run_dir = self.temp_dir / "runs" / "run-001"
        runner = WorkflowRunner(run_dir)
        executed_steps = []

        result = runner.run(
            [
                StepSpec(step_id="download", title="download", action=lambda: executed_steps.append("download")),
                StepSpec(step_id="b4_split", title="b4_split", action=lambda: executed_steps.append("b4_split")),
                StepSpec(step_id="b5_subtitles", title="b5_subtitles", action=lambda: executed_steps.append("b5")),
            ],
            stop_after_step="b4_split",
            review_payload={"step": "b4_split"},
        )

        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        review_required = json.loads((run_dir / "review_required.json").read_text(encoding="utf-8"))

        self.assertEqual(result, REVIEW_REQUIRED_EXIT_CODE)
        self.assertEqual(executed_steps, ["download", "b4_split"])
        self.assertEqual(state["status"], "review_required")
        self.assertEqual(review_required["step"], "b4_split")

    def test_review_updates_short_high_confidence_terms_and_glossary(self):
        from local_video_dubbing_workflow.review import review_and_correct_b4_outputs

        split_path = self.temp_dir / "translation_results_for_subtitles.xlsx"
        remerged_path = self.temp_dir / "translation_results_remerged.xlsx"
        glossary_path = self.temp_dir / "custom_terms.json"
        report_dir = self.temp_dir / "review"

        pd.DataFrame(
            [
                {"Source": "Cloud", "Translation": "Cloud"},
                {"Source": "heyku", "Translation": "heyku"},
                {"Source": "This is normal.", "Translation": "这很正常。"},
            ]
        ).to_excel(split_path, index=False)
        pd.DataFrame(
            [
                {"Source": "Cloud", "Translation": "Cloud"},
                {"Source": "heyku", "Translation": "heyku"},
                {"Source": "This is normal.", "Translation": "这很正常。"},
            ]
        ).to_excel(remerged_path, index=False)
        glossary_path.write_text(
            json.dumps(
                {
                    "terms": [
                        {"src": "Claude", "tgt": "Claude", "note": "Anthropic model"},
                        {"src": "Haiku", "tgt": "Haiku", "note": "Anthropic model"},
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        result = review_and_correct_b4_outputs(
            split_path=split_path,
            remerged_path=remerged_path,
            glossary_path=glossary_path,
            report_dir=report_dir,
        )

        split_df = pd.read_excel(split_path)
        remerged_df = pd.read_excel(remerged_path)
        glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
        glossary_updates = json.loads((report_dir / "glossary_updates.json").read_text(encoding="utf-8"))

        self.assertEqual(result["auto_corrected_count"], 2)
        self.assertEqual(split_df.loc[0, "Source"], "Claude")
        self.assertEqual(split_df.loc[1, "Source"], "Haiku")
        self.assertEqual(remerged_df.loc[0, "Translation"], "Claude")
        self.assertEqual(remerged_df.loc[1, "Translation"], "Haiku")
        self.assertTrue(any(term["src"] == "Cloud" and term["tgt"] == "Claude" for term in glossary["terms"]))
        self.assertTrue(any(update["corrected_to"] == "Claude" for update in glossary_updates["updates"]))

    def test_create_workspace_venv_bridges_repo_site_packages(self):
        from local_video_dubbing_workflow.bootstrap import create_workspace_venv

        workspace_root = self.temp_dir / "workspace"
        workspace_root.mkdir(parents=True, exist_ok=True)
        repo_venv = self.temp_dir / "repo_venv"
        repo_site_packages = repo_venv / "Lib" / "site-packages"
        repo_site_packages.mkdir(parents=True, exist_ok=True)

        def fake_run(command, check):
            self.assertIn("-m", command)
            venv_site_packages = workspace_root / ".venv" / "Lib" / "site-packages"
            venv_site_packages.mkdir(parents=True, exist_ok=True)
            python_path = workspace_root / ".venv" / "Scripts" / "python.exe"
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
            return None

        with patch("local_video_dubbing_workflow.bootstrap.subprocess.run", side_effect=fake_run):
            venv_path = create_workspace_venv(workspace_root, repo_venv=repo_venv)

        pth_path = workspace_root / ".venv" / "Lib" / "site-packages" / "videodubbing_workspace.pth"
        self.assertEqual(venv_path, workspace_root / ".venv")
        self.assertTrue(pth_path.exists())
        pth_content = pth_path.read_text(encoding="utf-8")
        self.assertIn(str(repo_site_packages), pth_content)
        self.assertIn(str(workspace_root / "app_template"), pth_content)

    def test_pick_run_id_prefers_video_title_and_deduplicates(self):
        from local_video_dubbing_workflow.pipeline import pick_run_id

        runs_dir = self.temp_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "Interesting Video").mkdir()

        run_id = pick_run_id(runs_dir, "Interesting Video")
        another = pick_run_id(runs_dir, "Interesting Video")

        self.assertEqual(run_id, "Interesting Video-2")
        self.assertEqual(another, "Interesting Video-2")

    def test_initialize_workspace_copies_local_cookies_file(self):
        from local_video_dubbing_workflow.bootstrap import initialize_workspace

        source_root = self.temp_dir / "source"
        workspace_root = self.temp_dir / "workspace"
        (source_root / "core").mkdir(parents=True)
        (source_root / "translations").mkdir(parents=True)
        (source_root / "requirements.txt").write_text("pandas\n", encoding="utf-8")
        (source_root / "config.yaml").write_text("api:\n  key: ''\n", encoding="utf-8")
        (source_root / "custom_terms.xlsx").write_bytes(b"")
        (source_root / "cookies.txt").write_text("cookie-data", encoding="utf-8")

        with patch("local_video_dubbing_workflow.bootstrap.repo_root", return_value=source_root):
            with patch("local_video_dubbing_workflow.bootstrap.skill_root", return_value=Path(r"D:\Codes\VideoLingo\skills\local-video-dubbing-workflow")):
                with patch("local_video_dubbing_workflow.bootstrap.import_terms_to_json", return_value={"terms": []}):
                    with patch("local_video_dubbing_workflow.bootstrap._copy_skill_scripts"):
                        initialize_workspace(workspace_root=workspace_root)

        self.assertEqual((workspace_root / "cookies.txt").read_text(encoding="utf-8"), "cookie-data")


if __name__ == "__main__":
    unittest.main()
