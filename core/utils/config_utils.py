import os
import re
import threading
from pathlib import Path

from ruamel.yaml import YAML

CONFIG_PATH = 'config.yaml'
CONFIG_PATH_ENV = "VIDEOLINGO_CONFIG_PATH"
lock = threading.Lock()
ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

yaml = YAML()
yaml.preserve_quotes = True

# -----------------------
# load & update config
# -----------------------

def get_config_path():
    configured_path = os.getenv(CONFIG_PATH_ENV, "").strip()
    if configured_path:
        return Path(configured_path)
    return Path(CONFIG_PATH)


def _resolve_env_placeholders(value):
    if isinstance(value, str):
        def replace(match):
            env_name = match.group(1)
            if env_name not in os.environ:
                raise KeyError(f"Environment variable '{env_name}' is not set")
            return os.environ[env_name]

        return ENV_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [_resolve_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_env_placeholders(item) for key, item in value.items()}
    return value


def load_key(key):
    with lock:
        with get_config_path().open('r', encoding='utf-8') as file:
            data = yaml.load(file)

    keys = key.split('.')
    value = data
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            raise KeyError(f"Key '{k}' not found in configuration")
    return _resolve_env_placeholders(value)

def update_key(key, new_value):
    with lock:
        config_path = get_config_path()
        with config_path.open('r', encoding='utf-8') as file:
            data = yaml.load(file)

        keys = key.split('.')
        current = data
        for k in keys[:-1]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False

        if isinstance(current, dict) and keys[-1] in current:
            current[keys[-1]] = new_value
            with config_path.open('w', encoding='utf-8') as file:
                yaml.dump(data, file)
            return True
        else:
            raise KeyError(f"Key '{keys[-1]}' not found in configuration")
        
# basic utils
def get_joiner(language):
    if language in load_key('language_split_with_space'):
        return " "
    elif language in load_key('language_split_without_space'):
        return ""
    else:
        raise ValueError(f"Unsupported language code: {language}")

if __name__ == "__main__":
    print(load_key('language_split_with_space'))
