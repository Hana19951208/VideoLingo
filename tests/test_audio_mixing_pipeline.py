import unittest


class AudioMixingPipelineTests(unittest.TestCase):
    def test_build_audio_mix_filter_includes_ducking_and_background_gain(self):
        from core._12_dub_to_vid import build_audio_mix_filter

        filter_text = build_audio_mix_filter()

        self.assertIn("volume=", filter_text)
        self.assertIn("sidechaincompress=", filter_text)
        self.assertIn("amix=inputs=2", filter_text)

    def test_build_merge_command_uses_audio_mix_filter(self):
        from core._12_dub_to_vid import build_merge_command

        command = build_merge_command(
            video_file="video.mp4",
            background_file="background.mp3",
            normalized_dub_audio="dub.wav",
            subtitle_filter="subtitles=test.srt",
            ffmpeg_gpu=False,
        )

        filter_index = command.index("-filter_complex") + 1
        self.assertIn("sidechaincompress=", command[filter_index])
        self.assertIn("[v]", command)
        self.assertIn("[a]", command)


if __name__ == "__main__":
    unittest.main()
