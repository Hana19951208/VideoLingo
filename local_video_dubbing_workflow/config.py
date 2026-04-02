import os
from pathlib import Path

from ruamel.yaml import YAML


yaml = YAML(typ="safe")


def resolve_api_settings(config_path):
    config_path = Path(config_path)
    with config_path.open("r", encoding="utf-8") as file:
        payload = yaml.load(file) or {}

    api_config = payload.get("api", {})
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() or str(api_config.get("key", "")).strip()
    if not api_key:
        raise ValueError("API key is not set. Please export DEEPSEEK_API_KEY or configure api.key.")

    return {
        "api_key": api_key,
        "base_url": str(api_config.get("base_url", "")).strip(),
        "model": str(api_config.get("model", "")).strip(),
        "llm_support_json": bool(api_config.get("llm_support_json", False)),
    }
