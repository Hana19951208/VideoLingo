import math
import os
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path


def _write_wave(path: Path, duration_sec: float, amplitude: int = 12000):
    sample_rate = 16000
    total_frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(total_frames):
            value = int(amplitude * math.sin(2 * math.pi * 220 * index / sample_rate))
            frames.extend(struct.pack("<h", value))
        wav_file.writeframes(bytes(frames))


def _write_silence(path: Path, duration_sec: float):
    sample_rate = 16000
    total_frames = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * total_frames)


class ReferenceAudioSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_ref_test_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_select_reference_audio_prefers_clean_clip(self):
        from core.tts_backend.reference_audio import select_reference_audio

        poor_clip = self.temp_dir / "poor.wav"
        good_clip = self.temp_dir / "good.wav"
        _write_silence(poor_clip, 2.0)
        _write_wave(good_clip, 8.0)

        selected = select_reference_audio(
            candidate_files=[poor_clip, good_clip],
            output_file=self.temp_dir / "reference_auto.wav",
            speaker_hints={},
        )

        self.assertTrue(selected.exists())
        self.assertEqual(selected.name, "reference_auto.wav")

    def test_resolve_reference_audio_path_uses_auto_file(self):
        from core.tts_backend.reference_audio import resolve_reference_audio_path

        auto_file = self.temp_dir / "reference_auto.wav"
        auto_file.touch()

        resolved = resolve_reference_audio_path(
            reference_mode="auto_single",
            manual_path="reference_audio.wav",
            auto_path=auto_file,
        )

        self.assertEqual(resolved, auto_file)

    def test_resolve_reference_audio_path_uses_manual_file(self):
        from core.tts_backend.reference_audio import resolve_reference_audio_path

        manual_file = self.temp_dir / "manual.wav"
        manual_file.touch()

        resolved = resolve_reference_audio_path(
            reference_mode="manual",
            manual_path=str(manual_file),
            auto_path=self.temp_dir / "reference_auto.wav",
        )

        self.assertEqual(resolved, manual_file)


if __name__ == "__main__":
    unittest.main()
