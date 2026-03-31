import unittest


class YtDlpOptionsTests(unittest.TestCase):
    def test_build_ydl_opts_disables_subtitles(self):
        from core._1_ytdlp import build_ydl_opts

        opts = build_ydl_opts(save_path="output", resolution="1080", cookies_path="")

        self.assertFalse(opts["writesubtitles"])
        self.assertFalse(opts["writeautomaticsub"])
        self.assertFalse(opts["allsubtitles"])
        self.assertFalse(opts["embedsubtitles"])


class SubtitleMaskFilterTests(unittest.TestCase):
    def test_mask_disabled_does_not_include_drawbox(self):
        from core._shared_video_filter import build_burn_subtitle_filter

        filter_text = build_burn_subtitle_filter(
            target_width=1920,
            target_height=1080,
            subtitle_files=[],
            subtitle_mask={"enabled": False},
        )

        self.assertNotIn("drawbox=", filter_text)

    def test_mask_enabled_inserts_drawbox_before_subtitles(self):
        from core._shared_video_filter import build_burn_subtitle_filter

        filter_text = build_burn_subtitle_filter(
            target_width=1920,
            target_height=1080,
            subtitle_files=[
                {
                    "path": "output/src.srt",
                    "style": "FontSize=15",
                }
            ],
            subtitle_mask={
                "enabled": True,
                "x_pct": 10,
                "y_pct": 80,
                "w_pct": 80,
                "h_pct": 15,
                "fill_color": "black@0.85",
            },
        )

        self.assertIn("drawbox=", filter_text)
        self.assertIn("subtitles=output/src.srt", filter_text)
        self.assertLess(
            filter_text.index("drawbox="),
            filter_text.index("subtitles=output/src.srt"),
        )


if __name__ == "__main__":
    unittest.main()
