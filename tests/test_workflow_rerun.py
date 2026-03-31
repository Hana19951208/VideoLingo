import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class WorkflowRerunTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_workflow_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_text_workflow_registry_exposes_ordered_steps(self):
        from core.st_utils.workflow_registry import build_runner_steps, get_stage_steps

        steps = get_stage_steps("text")

        self.assertEqual(
            [step.step_id for step in steps],
            [
                "b1_asr",
                "b2_split_sentences",
                "b3_translate",
                "b4_split_long_subtitles",
                "b5_generate_subtitles",
                "b6_burn_video",
            ],
        )

        runner_steps = build_runner_steps("text", start_step_id="b3_translate")
        self.assertEqual(len(runner_steps), 4)
        self.assertEqual(runner_steps[0][0], steps[2].title)

    def test_audio_workflow_registry_contains_reference_outputs(self):
        from core.st_utils.workflow_registry import get_stage_steps

        steps = get_stage_steps("audio")
        extract_reference_step = next(
            step for step in steps if step.step_id == "c2_extract_reference_audio"
        )

        self.assertIn("output/audio/refers/*.wav", extract_reference_step.artifact_patterns)

    def test_cleanup_stage_outputs_removes_downstream_only(self):
        from core.st_utils.workflow_registry import WorkflowStep
        from core.utils.rerun_cleanup import cleanup_stage_outputs

        upstream = self.temp_dir / "upstream.txt"
        current = self.temp_dir / "current.txt"
        downstream = self.temp_dir / "downstream.txt"
        for path in [upstream, current, downstream]:
            path.write_text("data", encoding="utf-8")

        stage_steps = (
            WorkflowStep(
                stage_id="text",
                step_id="b1",
                title="Upstream",
                run=lambda: None,
                artifact_patterns=(str(upstream),),
            ),
            WorkflowStep(
                stage_id="text",
                step_id="b2",
                title="Current",
                run=lambda: None,
                artifact_patterns=(str(current),),
            ),
            WorkflowStep(
                stage_id="text",
                step_id="b3",
                title="Downstream",
                run=lambda: None,
                artifact_patterns=(str(downstream),),
            ),
        )

        deleted = cleanup_stage_outputs(
            stage_id="text",
            step_id="b2",
            include_downstream=True,
            stage_steps=stage_steps,
        )

        self.assertTrue(upstream.exists())
        self.assertFalse(current.exists())
        self.assertFalse(downstream.exists())
        self.assertEqual(
            {Path(path).name for path in deleted},
            {"current.txt", "downstream.txt"},
        )

    def test_prepare_step_run_plan_for_single_step_rerun_keeps_downstream(self):
        from core.st_utils.workflow_actions import prepare_step_run_plan
        from core.st_utils.workflow_registry import WorkflowStep

        upstream = self.temp_dir / "upstream.txt"
        current = self.temp_dir / "current.txt"
        downstream = self.temp_dir / "downstream.txt"
        for path in [upstream, current, downstream]:
            path.write_text("data", encoding="utf-8")

        stage_steps = (
            WorkflowStep(
                stage_id="text",
                step_id="b1",
                title="Upstream",
                run=lambda: None,
                artifact_patterns=(str(upstream),),
            ),
            WorkflowStep(
                stage_id="text",
                step_id="b2",
                title="Current",
                run=lambda: None,
                artifact_patterns=(str(current),),
            ),
            WorkflowStep(
                stage_id="text",
                step_id="b3",
                title="Downstream",
                run=lambda: None,
                artifact_patterns=(str(downstream),),
            ),
        )

        plan = prepare_step_run_plan(
            stage_id="text",
            step_id="b2",
            action="rerun_only",
            stage_steps=stage_steps,
        )

        self.assertTrue(upstream.exists())
        self.assertFalse(current.exists())
        self.assertTrue(downstream.exists())
        self.assertEqual(plan.deleted_artifacts, [str(current).replace("\\", "/")])
        self.assertEqual(len(plan.runner_steps), 1)
        self.assertEqual(plan.runner_steps[0][0], "Current")

    def test_log_viewer_previews_text_json_and_xlsx(self):
        from core.st_utils.log_viewer import load_preview_content

        text_file = self.temp_dir / "task_runner_errors.log"
        text_file.write_text("traceback line", encoding="utf-8")
        json_file = self.temp_dir / "summary.json"
        json_file.write_text(json.dumps({"theme": "demo"}, ensure_ascii=False), encoding="utf-8")
        xlsx_file = self.temp_dir / "translation.xlsx"
        pd.DataFrame([{"Source": "hello", "Translation": "你好"}]).to_excel(
            xlsx_file,
            index=False,
        )

        text_preview = load_preview_content(text_file)
        json_preview = load_preview_content(json_file)
        xlsx_preview = load_preview_content(xlsx_file)

        self.assertEqual(text_preview["kind"], "text")
        self.assertIn("traceback line", text_preview["content"])
        self.assertEqual(json_preview["kind"], "json")
        self.assertIn('"theme": "demo"', json_preview["content"])
        self.assertEqual(xlsx_preview["kind"], "dataframe")
        self.assertEqual(xlsx_preview["content"].iloc[0]["Translation"], "你好")


if __name__ == "__main__":
    unittest.main()
