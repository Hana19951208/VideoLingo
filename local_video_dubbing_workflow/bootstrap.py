from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .terms import load_terms_file


DEFAULT_WORKSPACE_ROOT = Path(r"D:\Codes\VideoDubbingWorkspace")
SKILL_NAME = "local-video-dubbing-workflow"
SOURCE_COPY_FILES = ("requirements.txt",)
SOURCE_COPY_DIRS = ("core", "translations")
IGNORE_NAMES = shutil.ignore_patterns(
    "__pycache__",
    ".pytest_cache",
    "st_utils",
    "logs",
    "output",
    "history",
    "runtime",
    "control_plane_web",
    "stitch_videolingo",
)


def repo_root():
    return Path(__file__).resolve().parents[1]


def skill_root():
    return repo_root() / "skills" / SKILL_NAME


def write_sanitized_config(source_path, destination_path):
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized_lines = []
    for line in source_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("key:") or stripped.startswith("api_key:") or stripped.startswith("302_api:"):
            indent = line[: len(line) - len(line.lstrip())]
            sanitized_lines.append(f"{indent}{stripped.split(':', 1)[0]}: ''")
        elif stripped.startswith("cookies_path:"):
            indent = line[: len(line) - len(line.lstrip())]
            sanitized_lines.append(f"{indent}cookies_path: ''")
        else:
            sanitized_lines.append(line)
    destination_path.write_text("\n".join(sanitized_lines) + "\n", encoding="utf-8")


def import_terms_to_json(source_path, destination_path):
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    payload = load_terms_file(source_path)
    destination_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def copy_local_cookies(source_root, workspace_root):
    source_cookies = Path(source_root) / "cookies.txt"
    destination_cookies = Path(workspace_root) / "cookies.txt"
    if source_cookies.exists():
        shutil.copy2(source_cookies, destination_cookies)
        return destination_cookies
    return None


def _copy_tree(source_root, workspace_root):
    app_template = workspace_root / "app_template"
    if app_template.exists():
        shutil.rmtree(app_template)
    app_template.mkdir(parents=True, exist_ok=True)

    for directory in SOURCE_COPY_DIRS:
        shutil.copytree(source_root / directory, app_template / directory, ignore=IGNORE_NAMES)
    for file_name in SOURCE_COPY_FILES:
        shutil.copy2(source_root / file_name, app_template / file_name)

    return app_template


def _write_workspace_gitignore(workspace_root):
    (workspace_root / ".gitignore").write_text(
        "\n".join(
            [
                ".venv/",
                "runs/",
                "logs/",
                "current/",
                "config/config.local.yaml",
                "config/config.runtime.yaml",
                "cookies.txt",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _copy_skill_scripts(workspace_root):
    source_scripts = skill_root() / "scripts"
    target_scripts = workspace_root / "scripts"
    target_scripts.mkdir(parents=True, exist_ok=True)
    for script in source_scripts.glob("*.py"):
        shutil.copy2(script, target_scripts / script.name)
    bundled_package = workspace_root / "local_video_dubbing_workflow"
    if bundled_package.exists():
        shutil.rmtree(bundled_package)
    shutil.copytree(repo_root() / "local_video_dubbing_workflow", bundled_package, ignore=shutil.ignore_patterns("__pycache__"))


def _workspace_site_packages(venv_path):
    if sys.platform.startswith("win"):
        return venv_path / "Lib" / "site-packages"
    python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return venv_path / "lib" / python_version / "site-packages"


def _repo_site_packages(repo_venv):
    repo_venv = Path(repo_venv)
    if sys.platform.startswith("win"):
        return repo_venv / "Lib" / "site-packages"
    python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return repo_venv / "lib" / python_version / "site-packages"


def create_workspace_venv(workspace_root, repo_venv=None):
    workspace_root = Path(workspace_root)
    venv_path = workspace_root / ".venv"
    if not venv_path.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

    repo_venv = Path(repo_venv) if repo_venv else repo_root() / ".venv"
    site_packages_dir = _workspace_site_packages(venv_path)
    site_packages_dir.mkdir(parents=True, exist_ok=True)
    bridge_paths = [
        str(_repo_site_packages(repo_venv)),
        str(workspace_root / "app_template"),
        str(workspace_root / "local_video_dubbing_workflow"),
    ]
    (site_packages_dir / "videodubbing_workspace.pth").write_text(
        "\n".join(bridge_paths) + "\n",
        encoding="utf-8",
    )
    return venv_path


def initialize_workspace(workspace_root=DEFAULT_WORKSPACE_ROOT, terms_source_path=None, create_venv=False):
    source_root = repo_root()
    workspace_root = Path(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)

    for directory_name in ("config", "glossary", "runs", "current", "scripts", "logs"):
        (workspace_root / directory_name).mkdir(parents=True, exist_ok=True)

    app_template = _copy_tree(source_root, workspace_root)
    write_sanitized_config(source_root / "config.yaml", workspace_root / "config" / "config.example.yaml")
    config_local_path = workspace_root / "config" / "config.local.yaml"
    if not config_local_path.exists():
        shutil.copy2(workspace_root / "config" / "config.example.yaml", config_local_path)

    glossary_source = Path(terms_source_path) if terms_source_path else source_root / "custom_terms.xlsx"
    glossary_payload = import_terms_to_json(glossary_source, workspace_root / "glossary" / "custom_terms.json")
    copy_local_cookies(source_root, workspace_root)

    _write_workspace_gitignore(workspace_root)
    _copy_skill_scripts(workspace_root)

    manifest = {
        "workspace_root": str(workspace_root),
        "app_template": str(app_template),
        "terms_count": len(glossary_payload.get("terms", [])),
        "created_from": str(source_root),
    }
    (workspace_root / "workspace_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if create_venv:
        create_workspace_venv(workspace_root)

    return manifest
