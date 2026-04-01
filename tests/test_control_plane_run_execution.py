import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ControlPlaneRunExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix='videolingo_run_execution_'))
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
        self.source_video = self.temp_dir / 'fixture.mp4'
        self.source_video.write_bytes(b'fixture-video')

        os.environ['VIDEOLINGO_CONTROL_DB'] = str(self.db_path)
        os.environ['VIDEOLINGO_ACTIVE_WORKSPACE'] = str(self.workspace_root)
        os.environ['VIDEOLINGO_HISTORY_ROOT'] = str(self.history_root)
        os.environ['VIDEOLINGO_LOG_ROOT'] = str(self.logs_root)
        os.environ['VIDEOLINGO_CONFIG_PATH'] = str(self.config_path)
        os.environ['VIDEOLINGO_CONTROL_PLANE_WORKFLOW_MODE'] = 'fixture'
        os.environ['VIDEOLINGO_CONTROL_PLANE_STEP_DELAY_MS'] = '5'

        from control_plane.app import create_app

        self.client = TestClient(create_app())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
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

    def create_project(self, name: str = 'Execution Demo') -> dict:
        response = self.client.post(
            '/projects',
            json={
                'name': name,
                'source_type': 'upload',
                'source_uri_or_path': str(self.source_video),
                'source_lang': 'en',
                'target_lang': 'zh-CN',
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def wait_for_project_status(self, project_id: str, expected_status: str, timeout_seconds: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self.client.get(f'/projects/{project_id}')
            payload = response.json()
            if payload['status'] == expected_status:
                return payload
            time.sleep(0.05)
        self.fail(f'project {project_id} did not reach status {expected_status}')

    def wait_for_run_node_status(self, run_id: str, step_id: str, expected_status: str, timeout_seconds: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self.client.get(f'/runs/{run_id}/nodes')
            payload = response.json()
            node = next(item for item in payload['nodes'] if item['step_id'] == step_id)
            if node['status'] == expected_status:
                return node
            time.sleep(0.05)
        self.fail(f'run {run_id} step {step_id} did not reach status {expected_status}')

    def complete_run(self, name: str = 'Completed Demo') -> tuple[dict, dict]:
        project = self.create_project(name)
        run = self.client.post(f"/projects/{project['id']}/runs").json()
        self.wait_for_project_status(project['id'], 'review_required')
        approve_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'approve_subtitles_and_continue'},
        )
        self.assertEqual(approve_response.status_code, 200)
        self.wait_for_project_status(project['id'], 'completed')
        return project, run

    def test_run_blocks_at_review_required_after_b5(self):
        project = self.create_project()
        start_response = self.client.post(f"/projects/{project['id']}/runs")

        self.assertEqual(start_response.status_code, 201)
        run = start_response.json()
        project_payload = self.wait_for_project_status(project['id'], 'review_required')
        self.assertEqual(project_payload['current_step'], 'b5_generate_subtitles')

        self.wait_for_run_node_status(run['id'], 'b5_generate_subtitles', 'completed')
        nodes_response = self.client.get(f"/runs/{run['id']}/nodes")
        nodes = {item['step_id']: item for item in nodes_response.json()['nodes']}
        self.assertEqual(nodes['b6_burn_video']['status'], 'pending')
        self.assertEqual(nodes['c1_generate_audio_tasks']['status'], 'pending')

        review_response = self.client.get(f"/projects/{project['id']}/subtitle-review")
        self.assertEqual(review_response.status_code, 200)
        self.assertGreater(len(review_response.json()['rows']), 0)

    def test_approve_subtitles_and_continue_completes_remaining_steps(self):
        project = self.create_project('Approve Demo')
        run = self.client.post(f"/projects/{project['id']}/runs").json()
        self.wait_for_project_status(project['id'], 'review_required')

        action_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'approve_subtitles_and_continue'},
        )
        self.assertEqual(action_response.status_code, 200)

        project_payload = self.wait_for_project_status(project['id'], 'completed')
        self.assertEqual(project_payload['current_step'], 'c6_merge_video')

        nodes_response = self.client.get(f"/runs/{run['id']}/nodes")
        nodes = {item['step_id']: item for item in nodes_response.json()['nodes']}
        self.assertEqual(nodes['b6_burn_video']['status'], 'completed')
        self.assertEqual(nodes['c6_merge_video']['status'], 'completed')
        self.assertTrue((self.workspace_root / 'output' / 'output_dub.mp4').exists())

    def test_review_required_run_blocks_second_project(self):
        first_project = self.create_project('First Project')
        second_project = self.create_project('Second Project')
        self.client.post(f"/projects/{first_project['id']}/runs")
        self.wait_for_project_status(first_project['id'], 'review_required')

        blocked = self.client.post(f"/projects/{second_project['id']}/runs")
        self.assertEqual(blocked.status_code, 409)

    def test_create_app_marks_orphaned_processing_run_failed(self):
        project = self.create_project('Recovery Project')

        from control_plane.db import init_db, session_scope
        from control_plane.models import Project, Run

        init_db()
        with session_scope() as session:
            stored_project = session.get(Project, int(project['id']))
            stored_project.status = 'processing'
            stored_project.current_stage = 'text'
            stored_project.current_step = 'b3_translate'
            session.add(stored_project)
            session.add(Run(project_id=stored_project.id, status='processing'))
            session.commit()

        from control_plane.app import create_app

        recovery_client = TestClient(create_app())
        response = recovery_client.get(f"/projects/{project['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'failed')

    def test_cleanup_run_step_and_downstream_resets_entire_tail(self):
        project, run = self.complete_run('Cleanup Demo')

        cleanup_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'cleanup_step_and_downstream', 'step_id': 'b6_burn_video'},
        )
        self.assertEqual(cleanup_response.status_code, 200)

        nodes = {item['step_id']: item for item in self.client.get(f"/runs/{run['id']}/nodes").json()['nodes']}
        self.assertEqual(nodes['b5_generate_subtitles']['status'], 'completed')
        self.assertEqual(nodes['b6_burn_video']['status'], 'pending')
        self.assertEqual(nodes['c1_generate_audio_tasks']['status'], 'pending')
        self.assertFalse((self.workspace_root / 'output' / 'output_sub.mp4').exists())
        self.assertFalse((self.workspace_root / 'output' / 'output_dub.mp4').exists())

        project_payload = self.client.get(f"/projects/{project['id']}").json()
        self.assertEqual(project_payload['status'], 'processing')
        self.assertEqual(project_payload['current_step'], 'b6_burn_video')

    def test_run_step_and_rerun_from_step_follow_run_tail_semantics(self):
        project, run = self.complete_run('Tail Demo')

        cleanup_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'cleanup_step_and_downstream', 'step_id': 'b6_burn_video'},
        )
        self.assertEqual(cleanup_response.status_code, 200)

        run_step_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'run_step', 'step_id': 'b6_burn_video'},
        )
        self.assertEqual(run_step_response.status_code, 200)
        self.wait_for_run_node_status(run['id'], 'b6_burn_video', 'completed')
        nodes_after_single = {item['step_id']: item for item in self.client.get(f"/runs/{run['id']}/nodes").json()['nodes']}
        self.assertEqual(nodes_after_single['c1_generate_audio_tasks']['status'], 'pending')

        rerun_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'rerun_from_step', 'step_id': 'b6_burn_video'},
        )
        self.assertEqual(rerun_response.status_code, 200)
        self.wait_for_project_status(project['id'], 'completed')
        final_nodes = {item['step_id']: item for item in self.client.get(f"/runs/{run['id']}/nodes").json()['nodes']}
        self.assertEqual(final_nodes['b6_burn_video']['status'], 'completed')
        self.assertEqual(final_nodes['c6_merge_video']['status'], 'completed')

    def test_rerun_step_requires_matching_stage_when_stage_is_provided(self):
        _, run = self.complete_run('Validate Demo')

        mismatch_response = self.client.post(
            f"/runs/{run['id']}/actions",
            json={'action': 'rerun_step', 'step_id': 'b6_burn_video', 'stage_id': 'audio'},
        )
        self.assertEqual(mismatch_response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
