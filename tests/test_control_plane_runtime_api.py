import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ControlPlaneRuntimeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix='videolingo_runtime_api_'))
        self.db_path = self.temp_dir / 'control_plane.db'
        self.workspace_root = self.temp_dir / 'workspace'
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.history_root = self.temp_dir / 'history'
        self.history_root.mkdir(parents=True, exist_ok=True)
        self.logs_root = self.temp_dir / 'logs'
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.temp_dir / 'config.yaml'
        self.config_path.write_text(
            "\n".join(
                [
                    'display_language: "zh-CN"',
                    'api:',
                    "  key: 'secret-key'",
                    "  base_url: 'https://example.com'",
                    "  model: 'deepseek-chat'",
                    '  llm_support_json: false',
                    "target_language: '简体中文'",
                    'demucs: true',
                    'whisper:',
                    "  model: 'large-v3'",
                    "  language: 'en'",
                    "  detected_language: 'en'",
                    "  runtime: 'local'",
                    'burn_subtitles: true',
                    "tts_method: 'edge_tts'",
                ]
            ),
            encoding='utf-8',
        )
        self.source_video = self.temp_dir / 'runtime.mp4'
        self.source_video.write_bytes(b'runtime-video')

        import os

        os.environ['VIDEOLINGO_CONTROL_DB'] = str(self.db_path)
        os.environ['VIDEOLINGO_ACTIVE_WORKSPACE'] = str(self.workspace_root)
        os.environ['VIDEOLINGO_HISTORY_ROOT'] = str(self.history_root)
        os.environ['VIDEOLINGO_LOG_ROOT'] = str(self.logs_root)
        os.environ['VIDEOLINGO_CONFIG_PATH'] = str(self.config_path)
        os.environ['VIDEOLINGO_CONTROL_PLANE_WORKFLOW_MODE'] = 'fixture'
        os.environ['VIDEOLINGO_CONTROL_PLANE_STEP_DELAY_MS'] = '50'

        from control_plane.app import create_app

        self.client = TestClient(create_app())
        self.project = self.client.post(
            '/projects',
            json={
                'name': 'Runtime Demo',
                'source_type': 'upload',
                'source_uri_or_path': str(self.source_video),
                'source_lang': 'en',
                'target_lang': 'zh-CN',
            },
        ).json()
        self.run = self.client.post(f"/projects/{self.project['id']}/runs").json()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        import os

        for key in [
            'VIDEOLINGO_CONTROL_DB',
            'VIDEOLINGO_ACTIVE_WORKSPACE',
            'VIDEOLINGO_HISTORY_ROOT',
            'VIDEOLINGO_LOG_ROOT',
            'VIDEOLINGO_CONFIG_PATH',
            'VIDEOLINGO_CONTROL_PLANE_WORKFLOW_MODE',
            'VIDEOLINGO_CONTROL_PLANE_STEP_DELAY_MS',
        ]:
            os.environ.pop(key, None)

    def test_nodes_endpoint_returns_registered_workflow_nodes(self):
        response = self.client.get(f"/runs/{self.run['id']}/nodes")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['nodes']), 12)
        self.assertEqual(payload['nodes'][0]['step_id'], 'b1_asr')
        self.assertEqual(payload['nodes'][4]['step_id'], 'b5_generate_subtitles')

    def test_artifacts_endpoint_groups_existing_files_by_node(self):
        subtitle_file = self.workspace_root / 'output' / 'src_trans.srt'
        subtitle_file.parent.mkdir(parents=True, exist_ok=True)
        subtitle_file.write_text('demo', encoding='utf-8')

        response = self.client.get(f"/runs/{self.run['id']}/artifacts")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        subtitle_group = next(item for item in payload['artifacts'] if item['step_id'] == 'b5_generate_subtitles')
        self.assertIn('output/src_trans.srt', subtitle_group['files'])

    def test_logs_endpoint_reads_error_log_files(self):
        log_file = self.logs_root / 'task_runner_errors.log'
        log_file.write_text('traceback line', encoding='utf-8')

        response = self.client.get(f"/runs/{self.run['id']}/logs")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any('traceback line' in entry['content'] for entry in payload['logs']))

    def test_artifact_file_endpoint_returns_workspace_file(self):
        subtitle_file = self.workspace_root / 'output' / 'src_trans.srt'
        subtitle_file.parent.mkdir(parents=True, exist_ok=True)
        subtitle_file.write_text('subtitle preview', encoding='utf-8')

        response = self.client.get('/artifacts/file', params={'path': 'output/src_trans.srt'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, 'subtitle preview')


if __name__ == '__main__':
    unittest.main()
