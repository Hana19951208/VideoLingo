import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class DubSubtitlePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_dub_subs_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_srt_subtitle_files_generates_translated_and_source_tracks(self):
        from core import _11_merge_audio as merge_audio

        excel_path = self.temp_dir / "tts_tasks.xlsx"
        pd.DataFrame(
            [
                {
                    "number": 1,
                    "lines": '["你好，世界"]',
                    "src_lines": '["Hello, world"]',
                    "new_sub_times": "[[0.0, 1.5]]",
                }
            ]
        ).to_excel(excel_path, index=False)

        dub_sub = self.temp_dir / "dub.srt"
        dub_src_sub = self.temp_dir / "dub_src.srt"

        with patch.object(merge_audio, "_8_1_AUDIO_TASK", str(excel_path)), \
             patch.object(merge_audio, "DUB_SUB_FILE", str(dub_sub)), \
             patch.object(merge_audio, "DUB_SRC_SUB_FILE", str(dub_src_sub)):
            merge_audio.create_srt_subtitle_files()

        self.assertTrue(dub_sub.exists())
        self.assertTrue(dub_src_sub.exists())
        self.assertIn("你好，世界", dub_sub.read_text(encoding="utf-8"))
        self.assertIn("Hello, world", dub_src_sub.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
