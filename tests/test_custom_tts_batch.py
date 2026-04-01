import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch


class CustomTtsBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_custom_tts_"))
        self.reference_audio = self.temp_dir / "reference.wav"
        self.reference_audio.write_bytes(b"RIFF")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_custom_tts_batch_writes_all_files_from_zip_response(self):
        from core.tts_backend.custom_tts import custom_tts_batch

        output_a = self.temp_dir / "a.wav"
        output_b = self.temp_dir / "b.wav"
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "items": [
                            {"id": "a", "status": "ok", "filename": "a.wav"},
                            {"id": "b", "status": "ok", "filename": "b.wav"},
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("a.wav", b"AUDIO_A")
            archive.writestr("b.wav", b"AUDIO_B")

        response = MagicMock(status_code=200, content=zip_buffer.getvalue(), headers={"content-type": "application/zip"})

        with patch("core.tts_backend.custom_tts.load_key", side_effect=lambda key: {
            "custom_tts.url": "http://127.0.0.1:8000/v1/tts",
            "custom_tts.batch_url": "http://127.0.0.1:8000/v1/tts/batch",
            "custom_tts.reference_mode": "manual",
            "custom_tts.spk_audio": str(self.reference_audio),
        }[key]), \
             patch("core.tts_backend.custom_tts.requests.post", return_value=response):
            custom_tts_batch(
                [
                    {"id": "a", "text": "第一句", "save_path": str(output_a)},
                    {"id": "b", "text": "第二句", "save_path": str(output_b)},
                ]
            )

        self.assertEqual(output_a.read_bytes(), b"AUDIO_A")
        self.assertEqual(output_b.read_bytes(), b"AUDIO_B")

    def test_custom_tts_batch_falls_back_to_single_requests_when_batch_endpoint_missing(self):
        from core.tts_backend.custom_tts import custom_tts_batch

        output_a = self.temp_dir / "a.wav"
        output_b = self.temp_dir / "b.wav"
        missing_batch = MagicMock(status_code=404, text="missing")

        with patch("core.tts_backend.custom_tts.load_key", side_effect=lambda key: {
            "custom_tts.url": "http://127.0.0.1:8000/v1/tts",
            "custom_tts.batch_url": "http://127.0.0.1:8000/v1/tts/batch",
            "custom_tts.reference_mode": "manual",
            "custom_tts.spk_audio": str(self.reference_audio),
        }[key]), \
             patch("core.tts_backend.custom_tts.requests.post", return_value=missing_batch), \
             patch("core.tts_backend.custom_tts.custom_tts") as single_tts:
            custom_tts_batch(
                [
                    {"id": "a", "text": "第一句", "save_path": str(output_a)},
                    {"id": "b", "text": "第二句", "save_path": str(output_b)},
                ]
            )

        self.assertEqual(single_tts.call_count, 2)


if __name__ == "__main__":
    unittest.main()
