import os
import tempfile
import unittest
from pathlib import Path


class ConfigUtilsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="videolingo_config_"))
        self.config_path = self.temp_dir / "config.local.yaml"

    def tearDown(self):
        __import__("shutil").rmtree(self.temp_dir, ignore_errors=True)

    def test_load_key_reads_custom_config_path_and_resolves_env_placeholder(self):
        from core.utils.config_utils import load_key

        self.config_path.write_text(
            "\n".join(
                [
                    "api:",
                    "  key: '${VIDEOLINGO_API_KEY}'",
                    "  model: 'deepseek-chat'",
                ]
            ),
            encoding="utf-8",
        )

        previous_config_path = os.environ.get("VIDEOLINGO_CONFIG_PATH")
        previous_api_key = os.environ.get("VIDEOLINGO_API_KEY")
        os.environ["VIDEOLINGO_CONFIG_PATH"] = str(self.config_path)
        os.environ["VIDEOLINGO_API_KEY"] = "env-secret"
        try:
            self.assertEqual(load_key("api.key"), "env-secret")
            self.assertEqual(load_key("api.model"), "deepseek-chat")
        finally:
            if previous_config_path is None:
                os.environ.pop("VIDEOLINGO_CONFIG_PATH", None)
            else:
                os.environ["VIDEOLINGO_CONFIG_PATH"] = previous_config_path
            if previous_api_key is None:
                os.environ.pop("VIDEOLINGO_API_KEY", None)
            else:
                os.environ["VIDEOLINGO_API_KEY"] = previous_api_key

    def test_load_key_raises_when_required_env_placeholder_is_missing(self):
        from core.utils.config_utils import load_key

        self.config_path.write_text(
            "\n".join(
                [
                    "api:",
                    "  key: '${VIDEOLINGO_MISSING_KEY}'",
                ]
            ),
            encoding="utf-8",
        )

        previous_config_path = os.environ.get("VIDEOLINGO_CONFIG_PATH")
        previous_api_key = os.environ.get("VIDEOLINGO_MISSING_KEY")
        os.environ["VIDEOLINGO_CONFIG_PATH"] = str(self.config_path)
        os.environ.pop("VIDEOLINGO_MISSING_KEY", None)
        try:
            with self.assertRaisesRegex(KeyError, "VIDEOLINGO_MISSING_KEY"):
                load_key("api.key")
        finally:
            if previous_config_path is None:
                os.environ.pop("VIDEOLINGO_CONFIG_PATH", None)
            else:
                os.environ["VIDEOLINGO_CONFIG_PATH"] = previous_config_path
            if previous_api_key is None:
                os.environ.pop("VIDEOLINGO_MISSING_KEY", None)
            else:
                os.environ["VIDEOLINGO_MISSING_KEY"] = previous_api_key


if __name__ == "__main__":
    unittest.main()
