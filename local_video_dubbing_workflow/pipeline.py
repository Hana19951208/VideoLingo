from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .bootstrap import DEFAULT_WORKSPACE_ROOT
from .runner import REVIEW_REQUIRED_EXIT_CODE, StepSpec, WorkflowRunner


TEXT_STEPS = (
    ("b1_asr", "WhisperX word-level transcription", "from core._2_asr import transcribe; transcribe()"),
    (
        "b2_split_sentences",
        "Sentence segmentation using NLP and LLM",
        "from core._3_1_split_nlp import split_by_spacy; from core._3_2_split_meaning import split_sentences_by_meaning; split_by_spacy(); split_sentences_by_meaning()",
    ),
    (
        "b3_translate",
        "Summarization and multi-step translation",
        "from core._4_1_summarize import get_summary; from core._4_2_translate import translate_all; get_summary(); translate_all()",
    ),
    (
        "b4_split_long_subtitles",
        "Cutting and aligning long subtitles",
        "from core._5_split_sub import split_for_sub_main; split_for_sub_main()",
    ),
    (
        "b5_generate_subtitles",
        "Generating timeline and subtitles",
        "from core._6_gen_sub import align_timestamp_main; align_timestamp_main()",
    ),
    (
        "b6_burn_video",
        "Merging subtitles into the video",
        "from core._7_sub_into_vid import merge_subtitles_to_video; merge_subtitles_to_video()",
    ),
)

AUDIO_STEPS = (
    (
        "c1_generate_audio_tasks",
        "Generate audio tasks and chunks",
        "from core._8_1_audio_task import gen_audio_task_main; from core._8_2_dub_chunks import gen_dub_chunks; gen_audio_task_main(); gen_dub_chunks()",
    ),
    (
        "c2_extract_reference_audio",
        "Extract reference audio",
        "from core._9_refer_audio import extract_refer_audio_main; extract_refer_audio_main()",
    ),
    (
        "c3_select_reference_audio",
        "Select automatic reference audio",
        "from core._9_1_select_reference_audio import select_reference_audio_main; select_reference_audio_main()",
    ),
    (
        "c4_generate_audio_segments",
        "Generate and merge audio files",
        "from core._10_gen_audio import gen_audio; gen_audio()",
    ),
    (
        "c5_merge_full_audio",
        "Merge full audio",
        "from core._11_merge_audio import merge_full_audio; merge_full_audio()",
    ),
    (
        "c6_merge_video",
        "Merge final audio and bilingual subtitles into video",
        "from core._12_dub_to_vid import merge_video_audio; merge_video_audio()",
    ),
)


def _workspace_python(workspace_root):
    workspace_root = Path(workspace_root)
    if os.name == "nt":
        candidate = workspace_root / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = workspace_root / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else Path(sys.executable)


def _run_python_snippet(python_executable, cwd, env, snippet, log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        subprocess.run(
            [str(python_executable), "-c", snippet],
            cwd=str(cwd),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=True,
        )


def _run_download(python_executable, cwd, env, url, resolution, log_path):
    snippet = (
        "from core._1_ytdlp import download_video_ytdlp; "
        f"download_video_ytdlp({url!r}, save_path='output', resolution={resolution!r})"
    )
    _run_python_snippet(python_executable, cwd, env, snippet, log_path)


def _prepare_local_input(run_app_dir, input_file):
    input_path = Path(input_file)
    output_dir = run_app_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_dir / input_path.name)


def _materialize_run(workspace_root, run_id):
    workspace_root = Path(workspace_root)
    run_dir = workspace_root / "runs" / run_id
    app_dir = run_dir / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    shutil.copytree(workspace_root / "app_template", app_dir)

    shutil.copy2(workspace_root / "config" / "config.local.yaml", app_dir / "config.yaml")
    glossary_dir = run_dir / "glossary"
    glossary_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(workspace_root / "glossary" / "custom_terms.json", glossary_dir / "custom_terms.json")

    current_dir = workspace_root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)
    (current_dir / "run.json").write_text(
        json.dumps({"run_id": run_id, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return run_dir, app_dir


def _build_env(run_dir):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["VIDEOLINGO_CUSTOM_TERMS_PATH"] = str(run_dir / "glossary" / "custom_terms.json")
    return env


def _step_specs(python_executable, run_dir, app_dir, start_step_id=None):
    all_steps = [*TEXT_STEPS, *AUDIO_STEPS]
    if start_step_id is not None:
        start_index = next(index for index, step in enumerate(all_steps) if step[0] == start_step_id)
        all_steps = all_steps[start_index:]

    env = _build_env(run_dir)
    specs = []
    for step_id, title, snippet in all_steps:
        log_path = run_dir / "logs" / f"{step_id}.log"
        specs.append(
            StepSpec(
                step_id=step_id,
                title=title,
                action=lambda snippet=snippet, log_path=log_path: _run_python_snippet(
                    python_executable,
                    app_dir,
                    env,
                    snippet,
                    log_path,
                ),
            )
        )
    return specs


def create_run_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def start_new_run(workspace_root=DEFAULT_WORKSPACE_ROOT, input_url=None, input_file=None, resolution="best"):
    if not input_url and not input_file:
        raise ValueError("Either input_url or input_file must be provided.")

    run_id = create_run_id()
    run_dir, app_dir = _materialize_run(workspace_root, run_id)
    python_executable = _workspace_python(workspace_root)
    env = _build_env(run_dir)
    download_log = run_dir / "logs" / "download.log"

    if input_url:
        _run_download(python_executable, app_dir, env, input_url, resolution, download_log)
    else:
        _prepare_local_input(app_dir, input_file)

    runner = WorkflowRunner(run_dir)
    review_payload = {
        "run_id": run_id,
        "step": "b4_split_long_subtitles",
        "split_path": str(run_dir / "app" / "output" / "log" / "translation_results_for_subtitles.xlsx"),
        "remerged_path": str(run_dir / "app" / "output" / "log" / "translation_results_remerged.xlsx"),
    }
    exit_code = runner.run(
        _step_specs(python_executable, run_dir, app_dir),
        stop_after_step="b4_split_long_subtitles",
        review_payload=review_payload,
    )
    return exit_code, run_id


def resume_run(workspace_root=DEFAULT_WORKSPACE_ROOT, run_id=None, start_step_id=None):
    if not run_id:
        raise ValueError("run_id is required for resume.")

    workspace_root = Path(workspace_root)
    run_dir = workspace_root / "runs" / run_id
    app_dir = run_dir / "app"
    python_executable = _workspace_python(workspace_root)

    if start_step_id is None:
        state_path = run_dir / "state.json"
        if not state_path.exists():
            raise ValueError("state.json is missing. Cannot resume run.")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") in {"review_required", "reviewed"}:
            start_step_id = "b5_generate_subtitles"
        else:
            executed_steps = state.get("executed_steps", [])
            start_step_id = executed_steps[-1] if executed_steps else "b1_asr"

    runner = WorkflowRunner(run_dir)
    exit_code = runner.run(_step_specs(python_executable, run_dir, app_dir, start_step_id=start_step_id))
    return exit_code
