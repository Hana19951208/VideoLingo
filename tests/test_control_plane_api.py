import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ControlPlaneApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_control_plane_"))
        self.db_path = self.temp_dir / "control_plane.db"
        self.workspace_root = self.temp_dir / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.history_root = self.temp_dir / "history"
        self.history_root.mkdir(parents=True, exist_ok=True)
        self.logs_root = self.temp_dir / "logs"
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.temp_dir / "config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    'display_language: "zh-CN"',
                    "api:",
                    "  key: 'secret-key'",
                    "  base_url: 'https://example.com'",
                    "  model: 'deepseek-chat'",
                    "  llm_support_json: false",
                    "target_language: '简体中文'",
                    "demucs: true",
                    "whisper:",
                    "  model: 'large-v3'",
                    "  language: 'en'",
                    "  detected_language: 'en'",
                    "  runtime: 'local'",
                    "burn_subtitles: true",
                    "tts_method: 'edge_tts'",
                    "edge_tts:",
                    "  voice: 'zh-CN-XiaoxiaoNeural'",
                ]
            ),
            encoding="utf-8",
        )

        os.environ["VIDEOLINGO_CONTROL_DB"] = str(self.db_path)
        os.environ["VIDEOLINGO_ACTIVE_WORKSPACE"] = str(self.workspace_root)
        os.environ["VIDEOLINGO_HISTORY_ROOT"] = str(self.history_root)
        os.environ["VIDEOLINGO_LOG_ROOT"] = str(self.logs_root)
        os.environ["VIDEOLINGO_CONFIG_PATH"] = str(self.config_path)

        from control_plane.app import create_app

        self.client = TestClient(create_app())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for key in [
            "VIDEOLINGO_CONTROL_DB",
            "VIDEOLINGO_ACTIVE_WORKSPACE",
            "VIDEOLINGO_HISTORY_ROOT",
            "VIDEOLINGO_LOG_ROOT",
            "VIDEOLINGO_CONFIG_PATH",
        ]:
            os.environ.pop(key, None)

    def test_create_project_returns_summary_and_masked_settings(self):
        response = self.client.post(
            "/projects",
            json={
                "name": "Claude Demo",
                "source_type": "upload",
                "source_uri_or_path": "D:/videos/demo.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["name"], "Claude Demo")
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["source_type"], "upload")
        self.assertEqual(payload["progress_pct"], 0)

        settings_response = self.client.get("/settings")
        self.assertEqual(settings_response.status_code, 200)
        settings_payload = settings_response.json()
        self.assertEqual(settings_payload["global"]["api"]["key"], "******")
        self.assertEqual(settings_payload["global"]["api"]["base_url"], "https://example.com")

    def test_start_run_blocks_second_active_project(self):
        first_project = self.client.post(
            "/projects",
            json={
                "name": "First",
                "source_type": "upload",
                "source_uri_or_path": "first.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        ).json()
        second_project = self.client.post(
            "/projects",
            json={
                "name": "Second",
                "source_type": "upload",
                "source_uri_or_path": "second.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        ).json()

        start_first = self.client.post(f"/projects/{first_project['id']}/runs")
        self.assertEqual(start_first.status_code, 201)
        first_run = start_first.json()
        self.assertEqual(first_run["status"], "processing")

        blocked = self.client.post(f"/projects/{second_project['id']}/runs")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("active project", blocked.json()["detail"])

    def test_workspace_contains_stage_and_node_metadata(self):
        project = self.client.post(
            "/projects",
            json={
                "name": "Workspace Demo",
                "source_type": "upload",
                "source_uri_or_path": "workspace.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        ).json()

        response = self.client.get(f"/projects/{project['id']}/workspace")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([stage["stage_id"] for stage in payload["stages"]], ["text", "audio"])
        text_stage = payload["stages"][0]
        self.assertEqual(text_stage["steps"][4]["step_id"], "b5_generate_subtitles")
        self.assertIn("output/src_trans.srt", text_stage["steps"][4]["artifact_patterns"])

    def test_subtitle_review_reads_and_updates_structured_rows(self):
        project = self.client.post(
            "/projects",
            json={
                "name": "Subtitle Review",
                "source_type": "upload",
                "source_uri_or_path": "review.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        ).json()

        review_dir = self.history_root / project["id"] / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        review_file = review_dir / "subtitle_review.json"
        review_file.write_text(
            json.dumps(
                {
                    "rows": [
                        {
                            "row_id": "1",
                            "start": "00:00:01,000",
                            "end": "00:00:03,000",
                            "source_text": "Hello",
                            "target_text": "你好",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        get_response = self.client.get(f"/projects/{project['id']}/subtitle-review")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["rows"][0]["target_text"], "你好")

        put_response = self.client.put(
            f"/projects/{project['id']}/subtitle-review",
            json={
                "rows": [
                    {
                        "row_id": "1",
                        "start": "00:00:01,000",
                        "end": "00:00:03,000",
                        "source_text": "Hello",
                        "target_text": "你好，世界",
                    }
                ]
            },
        )
        self.assertEqual(put_response.status_code, 200)
        updated_payload = json.loads(review_file.read_text(encoding="utf-8"))
        self.assertEqual(updated_payload["rows"][0]["target_text"], "你好，世界")

    def test_settings_show_project_override_source(self):
        project = self.client.post(
            "/projects",
            json={
                "name": "Override Demo",
                "source_type": "upload",
                "source_uri_or_path": "override.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        ).json()

        update_response = self.client.put(
            "/settings",
            json={
                "project_id": project["id"],
                "overrides": {
                    "tts_method": "openai_tts",
                    "whisper.runtime": "cloud",
                },
            },
        )
        self.assertEqual(update_response.status_code, 200)

        workspace_response = self.client.get(f"/projects/{project['id']}/workspace")
        self.assertEqual(workspace_response.status_code, 200)
        settings = workspace_response.json()["effective_settings"]
        self.assertEqual(settings["tts_method"]["value"], "openai_tts")
        self.assertEqual(settings["tts_method"]["source"], "project_override")
        self.assertEqual(settings["api.base_url"]["source"], "global")

    def test_global_settings_override_is_persisted_and_applied(self):
        update_response = self.client.put(
            "/settings",
            json={
                "overrides": {
                    "tts_method": "openai_tts",
                    "whisper.runtime": "cloud",
                    "api.base_url": "https://override.example.com",
                },
            },
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["scope"], "global")

        settings_response = self.client.get("/settings")
        self.assertEqual(settings_response.status_code, 200)
        settings_payload = settings_response.json()
        self.assertEqual(settings_payload["global"]["tts_method"], "openai_tts")
        self.assertEqual(settings_payload["global"]["whisper"]["runtime"], "cloud")
        self.assertEqual(settings_payload["global"]["api"]["base_url"], "https://override.example.com")

    def test_workspace_marks_global_override_source(self):
        self.client.put(
            "/settings",
            json={
                "overrides": {
                    "tts_method": "openai_tts",
                },
            },
        )
        project = self.client.post(
            "/projects",
            json={
                "name": "Global Override Demo",
                "source_type": "upload",
                "source_uri_or_path": "global-override.mp4",
                "source_lang": "en",
                "target_lang": "zh-CN",
            },
        ).json()

        workspace_response = self.client.get(f"/projects/{project['id']}/workspace")
        self.assertEqual(workspace_response.status_code, 200)
        settings = workspace_response.json()["effective_settings"]
        self.assertEqual(settings["tts_method"]["value"], "openai_tts")
        self.assertEqual(settings["tts_method"]["source"], "global_override")


if __name__ == "__main__":
    unittest.main()
