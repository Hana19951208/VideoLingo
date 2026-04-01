import os
import shutil
import tempfile
import unittest
from pathlib import Path


class ConfigEnvOverrideTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_config_override_"))
        self.config_path = self.temp_dir / "custom_config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "api:",
                    "  key: 'env-secret'",
                    "  base_url: 'https://override.example.com'",
                    "display_language: 'zh-CN'",
                    "target_language: '简体中文'",
                ]
            ),
            encoding="utf-8",
        )
        os.environ["VIDEOLINGO_CONFIG_PATH"] = str(self.config_path)

    def tearDown(self):
        os.environ.pop("VIDEOLINGO_CONFIG_PATH", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_key_uses_environment_override_path(self):
        from core.utils.config_utils import load_key

        self.assertEqual(load_key("api.base_url"), "https://override.example.com")
        self.assertEqual(load_key("api.key"), "env-secret")


if __name__ == "__main__":
    unittest.main()
