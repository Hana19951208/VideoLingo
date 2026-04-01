import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from control_plane import source_ingest
from yt_dlp.utils import DownloadError


class _FakeYoutubeDL:
    last_options = None
    last_urls = None

    def __init__(self, options):
        _FakeYoutubeDL.last_options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def download(self, urls):
        _FakeYoutubeDL.last_urls = urls


class _RetryYoutubeDL:
    calls = []
    attempt = 0

    def __init__(self, options):
        self.options = options
        _RetryYoutubeDL.calls.append(options)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def download(self, urls):
        _RetryYoutubeDL.attempt += 1
        if _RetryYoutubeDL.attempt == 1:
            raise DownloadError("ERROR: [youtube] demo: Sign in to confirm you're not a bot")


class _AlwaysFailYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def download(self, urls):
        raise DownloadError("ERROR: [youtube] demo: Sign in to confirm you're not a bot")


class ControlPlaneSourceIngestTests(unittest.TestCase):
    def test_download_video_retries_with_configured_cookiefile_after_bot_challenge(self):
        with tempfile.TemporaryDirectory(prefix='videolingo_source_ingest_') as temp_dir:
            configured_cookie = Path(temp_dir) / 'configured.txt'
            configured_cookie.write_text('cookie', encoding='utf-8')
            _RetryYoutubeDL.calls = []
            _RetryYoutubeDL.attempt = 0

            with patch('control_plane.source_ingest.safe_load_key', side_effect=[configured_cookie.as_posix()]), patch(
                'control_plane.source_ingest.get_project_root',
                return_value=Path(temp_dir),
                create=True,
            ), patch('control_plane.source_ingest.detect_node_runtime', return_value='D:/node.exe'), patch.dict(
                'sys.modules',
                {'yt_dlp': SimpleNamespace(YoutubeDL=_RetryYoutubeDL)},
            ):
                source_ingest.download_video(
                    url='https://www.youtube.com/watch?v=test',
                    save_path=temp_dir,
                    resolution='1080',
                )

        self.assertEqual(len(_RetryYoutubeDL.calls), 2)
        self.assertNotIn('cookiefile', _RetryYoutubeDL.calls[0])
        self.assertEqual(Path(_RetryYoutubeDL.calls[1]['cookiefile']), configured_cookie)
        self.assertEqual(_RetryYoutubeDL.calls[0]['js_runtimes'], {'node': {'path': 'D:/node.exe'}})

    def test_download_video_uses_repo_cookiefile_only_for_retry_when_config_empty(self):
        with tempfile.TemporaryDirectory(prefix='videolingo_source_ingest_') as temp_dir:
            old_cookie = Path(temp_dir) / 'www.youtube.com_cookies.txt'
            old_cookie.write_text('cookie-old', encoding='utf-8')
            fallback_cookie = Path(temp_dir) / 'www.youtube.com_cookies_v2.txt'
            fallback_cookie.write_text('cookie-v2', encoding='utf-8')
            _RetryYoutubeDL.calls = []
            _RetryYoutubeDL.attempt = 0

            with patch('control_plane.source_ingest.safe_load_key', return_value=''), patch(
                'control_plane.source_ingest.get_project_root',
                return_value=Path(temp_dir),
                create=True,
            ), patch('control_plane.source_ingest.detect_node_runtime', return_value=None), patch.dict(
                'sys.modules',
                {'yt_dlp': SimpleNamespace(YoutubeDL=_RetryYoutubeDL)},
            ):
                source_ingest.download_video(
                    url='https://www.youtube.com/watch?v=test',
                    save_path=temp_dir,
                    resolution='1080',
                )

        self.assertEqual(len(_RetryYoutubeDL.calls), 2)
        self.assertNotIn('cookiefile', _RetryYoutubeDL.calls[0])
        self.assertEqual(Path(_RetryYoutubeDL.calls[1]['cookiefile']), fallback_cookie)

    def test_resolve_youtube_cookiefile_prefers_newer_root_export_when_config_empty(self):
        with tempfile.TemporaryDirectory(prefix='videolingo_source_ingest_') as temp_dir:
            old_cookie = Path(temp_dir) / 'www.youtube.com_cookies.txt'
            old_cookie.write_text('cookie-old', encoding='utf-8')
            latest_cookie = Path(temp_dir) / 'www.youtube.com_cookies_v2.txt'
            latest_cookie.write_text('cookie-v2', encoding='utf-8')
            old_cookie.touch()
            latest_cookie.touch()

            with patch('control_plane.source_ingest.get_project_root', return_value=Path(temp_dir), create=True):
                resolved = source_ingest.resolve_youtube_cookiefile('')

        self.assertEqual(Path(resolved), latest_cookie)

    def test_download_video_raises_clear_error_after_cookie_retry_fails(self):
        with tempfile.TemporaryDirectory(prefix='videolingo_source_ingest_') as temp_dir:
            fallback_cookie = Path(temp_dir) / 'www.youtube.com_cookies.txt'
            fallback_cookie.write_text('cookie', encoding='utf-8')

            with patch('control_plane.source_ingest.safe_load_key', return_value=''), patch(
                'control_plane.source_ingest.get_project_root',
                return_value=Path(temp_dir),
                create=True,
            ), patch('control_plane.source_ingest.detect_node_runtime', return_value='D:/node.exe'), patch.dict(
                'sys.modules',
                {'yt_dlp': SimpleNamespace(YoutubeDL=_AlwaysFailYoutubeDL)},
            ):
                with self.assertRaises(source_ingest.RemoteSourceDownloadError) as context:
                    source_ingest.download_video(
                        url='https://www.youtube.com/watch?v=test',
                        save_path=temp_dir,
                        resolution='1080',
                    )

        self.assertIn('YouTube 当前要求额外的人机校验', str(context.exception))


if __name__ == '__main__':
    unittest.main()
