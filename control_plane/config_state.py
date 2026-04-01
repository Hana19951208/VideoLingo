from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from ruamel.yaml import YAML
from sqlmodel import select

from control_plane.models import GlobalSetting, ProjectOverride
from core.utils.config_utils import _get_config_path


yaml = YAML()

SECRET_KEYS = {
    'api.key',
    'openai_tts.api_key',
    'azure_tts.api_key',
    'fish_tts.api_key',
    'sf_cosyvoice2.api_key',
    'f5tts.302_api',
    'whisper.whisperX_302_api_key',
    'whisper.elevenlabs_api_key',
}
SUMMARY_KEYS = [
    'target_language',
    'whisper.runtime',
    'demucs',
    'tts_method',
    'api.base_url',
]


def load_raw_config() -> dict[str, Any]:
    with open(_get_config_path(), 'r', encoding='utf-8') as file:
        data = yaml.load(file) or {}
    return data


def flatten_dict(data: dict[str, Any], prefix: str = '') -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        dotted = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            flattened.update(flatten_dict(value, dotted))
        else:
            flattened[dotted] = value
    return flattened


def inflate_dict(data: dict[str, Any]) -> dict[str, Any]:
    inflated: dict[str, Any] = {}
    for dotted_key, value in data.items():
        set_nested_value(inflated, dotted_key, value)
    return inflated


def set_nested_value(data: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = data
    keys = dotted_key.split('.')
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def get_nested_value(data: dict[str, Any], dotted_key: str) -> Any:
    current: Any = data
    for key in dotted_key.split('.'):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def masked_value(key: str, value: Any) -> Any:
    if key in SECRET_KEYS and value:
        return '******'
    return value


def get_global_override_map(session) -> dict[str, Any]:
    rows = session.exec(select(GlobalSetting)).all()
    return {row.dotted_key: json.loads(row.value_json) for row in rows}


def get_project_override_map(session, project_id: int | None) -> dict[str, Any]:
    if project_id is None:
        return {}
    row = session.exec(select(ProjectOverride).where(ProjectOverride.project_id == project_id)).first()
    if row is None:
        return {}
    return json.loads(row.overrides_json)


def build_effective_settings(session, project_id: int | None = None) -> dict[str, dict[str, Any]]:
    file_config = flatten_dict(load_raw_config())
    global_overrides = get_global_override_map(session)
    project_overrides = get_project_override_map(session, project_id)

    effective = deepcopy(file_config)
    effective.update(global_overrides)
    effective.update(project_overrides)

    result: dict[str, dict[str, Any]] = {}
    for key in SUMMARY_KEYS:
        if key in effective:
            if key in project_overrides:
                source = 'project_override'
            elif key in global_overrides:
                source = 'global_override'
            else:
                source = 'global'
            result[key] = {'value': masked_value(key, effective[key]), 'source': source}
    return result


def build_masked_global_settings(session) -> dict[str, Any]:
    file_config = flatten_dict(load_raw_config())
    global_overrides = get_global_override_map(session)
    effective = deepcopy(file_config)
    effective.update(global_overrides)

    masked_flattened = {key: masked_value(key, value) for key, value in effective.items()}
    return inflate_dict(masked_flattened)
