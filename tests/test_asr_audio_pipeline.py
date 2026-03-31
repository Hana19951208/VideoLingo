import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class AsrAudioPipelineTests(unittest.TestCase):
    def test_transcribe_uses_vocal_audio_for_local_asr_when_demucs_enabled(self):
        import core._2_asr as asr_module

        transcribe_spy = MagicMock(return_value={"segments": []})
        fake_module = types.SimpleNamespace(transcribe_audio=transcribe_spy)

        with patch.dict(sys.modules, {"core.asr_backend.whisperX_local": fake_module}):
            with patch("core._2_asr.find_video_files", return_value="video.mp4"), \
                 patch("core._2_asr.convert_video_to_audio"), \
                 patch("core._2_asr.convert_video_to_demucs_audio"), \
                 patch("core._2_asr.demucs_audio"), \
                 patch("core._2_asr.normalize_audio_volume", return_value="output/audio/vocal.mp3"), \
                 patch("core._2_asr.split_audio", return_value=[(0, 10)]), \
                 patch("core._2_asr.process_transcription", return_value="df"), \
                 patch("core._2_asr.save_results"), \
                 patch("core._2_asr.rprint"), \
                 patch(
                     "core._2_asr.load_key",
                     side_effect=lambda key: {
                         "demucs": True,
                         "whisper.runtime": "local",
                     }[key],
                 ):
                asr_module.transcribe.__wrapped__()

        transcribe_spy.assert_called_once_with(
            "output/audio/vocal.mp3",
            "output/audio/vocal.mp3",
            0,
            10,
        )

    def test_convert_video_to_demucs_audio_uses_high_quality_wav(self):
        from core.asr_backend.audio_preprocess import convert_video_to_demucs_audio

        with patch("core.asr_backend.audio_preprocess.os.path.exists", return_value=False), \
             patch("core.asr_backend.audio_preprocess.subprocess.run") as run_mock, \
             patch("core.asr_backend.audio_preprocess.rprint"):
            convert_video_to_demucs_audio("video.mp4", "output/audio/raw_demucs.wav")

        command = run_mock.call_args.args[0]
        self.assertIn("pcm_s16le", command)
        self.assertIn("44100", command)
        self.assertIn("2", command)
        self.assertEqual(command[-1], "output/audio/raw_demucs.wav")

    def test_demucs_cache_invalidates_when_config_changes(self):
        from core.asr_backend.demucs_vl import should_skip_demucs

        temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_demucs_manifest_"))
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_dir, ignore_errors=True))
        input_file = temp_dir / "raw_demucs.wav"
        input_file.write_bytes(b"audio")
        vocal_file = temp_dir / "vocal.mp3"
        vocal_file.write_bytes(b"vocal")
        background_file = temp_dir / "background.mp3"
        background_file.write_bytes(b"background")
        manifest_path = temp_dir / "demucs_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "input": {
                        "path": str(input_file),
                        "size": input_file.stat().st_size,
                        "mtime": input_file.stat().st_mtime,
                    },
                    "config": {
                        "model": "htdemucs_ft",
                        "shifts": 2,
                        "overlap": 0.25,
                    },
                }
            ),
            encoding="utf-8",
        )

        self.assertTrue(
            should_skip_demucs(
                input_file=str(input_file),
                vocal_file=str(vocal_file),
                background_file=str(background_file),
                manifest_path=str(manifest_path),
                model_name="htdemucs_ft",
                shifts=2,
                overlap=0.25,
            )
        )
        self.assertFalse(
            should_skip_demucs(
                input_file=str(input_file),
                vocal_file=str(vocal_file),
                background_file=str(background_file),
                manifest_path=str(manifest_path),
                model_name="htdemucs",
                shifts=2,
                overlap=0.25,
            )
        )


if __name__ == "__main__":
    unittest.main()
