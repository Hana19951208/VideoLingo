from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.tts_backend.reference_audio import AUTO_REFERENCE_AUDIO_FILE
from core.utils.models import (
    _2_CLEANED_CHUNKS,
    _3_1_SPLIT_BY_NLP,
    _3_2_SPLIT_BY_MEANING,
    _4_1_TERMINOLOGY,
    _4_2_TRANSLATION,
    _5_REMERGED,
    _5_SPLIT_SUB,
    _8_1_AUDIO_TASK,
)


@dataclass(frozen=True)
class WorkflowStep:
    stage_id: str
    step_id: str
    title: str
    run: Callable[[], None]
    artifact_patterns: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    preview_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowStage:
    stage_id: str
    title: str
    start_button_label: str
    runner_key: str
    video_path: str
    success_message: str
    steps: tuple[WorkflowStep, ...]


def _run_text_asr():
    from core import _2_asr

    _2_asr.transcribe()


def _run_text_split_sentences():
    from core import _3_1_split_nlp, _3_2_split_meaning

    _3_1_split_nlp.split_by_spacy()
    _3_2_split_meaning.split_sentences_by_meaning()


def _run_text_translate():
    from core import _4_1_summarize, _4_2_translate

    _4_1_summarize.get_summary()
    _4_2_translate.translate_all()


def _run_text_split_long_subtitles():
    from core import _5_split_sub

    _5_split_sub.split_for_sub_main()


def _run_text_generate_subtitles():
    from core import _6_gen_sub

    _6_gen_sub.align_timestamp_main()


def _run_text_burn_video():
    from core import _7_sub_into_vid

    _7_sub_into_vid.merge_subtitles_to_video()


def _run_audio_generate_tasks():
    from core import _8_1_audio_task, _8_2_dub_chunks

    _8_1_audio_task.gen_audio_task_main()
    _8_2_dub_chunks.gen_dub_chunks()


def _run_audio_extract_reference():
    from core import _9_refer_audio

    _9_refer_audio.extract_refer_audio_main()


def _run_audio_select_reference():
    from core import _9_1_select_reference_audio

    _9_1_select_reference_audio.select_reference_audio_main()


def _run_audio_generate_segments():
    from core import _10_gen_audio

    _10_gen_audio.gen_audio()


def _run_audio_merge_full_audio():
    from core import _11_merge_audio

    _11_merge_audio.merge_full_audio()


def _run_audio_merge_video():
    from core import _12_dub_to_vid

    _12_dub_to_vid.merge_video_audio()


TEXT_STAGE = WorkflowStage(
    stage_id="text",
    title="b. Translate and Generate Subtitles",
    start_button_label="Start Processing Subtitles",
    runner_key="_text_runner",
    video_path="output/output_sub.mp4",
    success_message="Subtitle processing is complete! You can check the generated subtitle files in the `output` folder.",
    steps=(
        WorkflowStep(
            stage_id="text",
            step_id="b1_asr",
            title="WhisperX word-level transcription",
            run=_run_text_asr,
            artifact_patterns=(_2_CLEANED_CHUNKS,),
            preview_patterns=("output/gpt_log/*.json", "logs/task_runner_errors.log"),
        ),
        WorkflowStep(
            stage_id="text",
            step_id="b2_split_sentences",
            title="Sentence segmentation using NLP and LLM",
            run=_run_text_split_sentences,
            artifact_patterns=(_3_1_SPLIT_BY_NLP, _3_2_SPLIT_BY_MEANING),
            depends_on=("b1_asr",),
            preview_patterns=("output/gpt_log/*.json", "logs/task_runner_errors.log"),
        ),
        WorkflowStep(
            stage_id="text",
            step_id="b3_translate",
            title="Summarization and multi-step translation",
            run=_run_text_translate,
            artifact_patterns=(_4_1_TERMINOLOGY, _4_2_TRANSLATION),
            depends_on=("b2_split_sentences",),
            preview_patterns=("output/gpt_log/*.json", "logs/task_runner_errors.log"),
        ),
        WorkflowStep(
            stage_id="text",
            step_id="b4_split_long_subtitles",
            title="Cutting and aligning long subtitles",
            run=_run_text_split_long_subtitles,
            artifact_patterns=(_5_SPLIT_SUB, _5_REMERGED),
            depends_on=("b3_translate",),
            preview_patterns=("output/gpt_log/*.json", "logs/task_runner_errors.log"),
        ),
        WorkflowStep(
            stage_id="text",
            step_id="b5_generate_subtitles",
            title="Generating timeline and subtitles",
            run=_run_text_generate_subtitles,
            artifact_patterns=(
                "output/src.srt",
                "output/trans.srt",
                "output/src_trans.srt",
                "output/trans_src.srt",
                "output/audio/src_subs_for_audio.srt",
                "output/audio/trans_subs_for_audio.srt",
            ),
            depends_on=("b4_split_long_subtitles",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
        WorkflowStep(
            stage_id="text",
            step_id="b6_burn_video",
            title="Merging subtitles into the video",
            run=_run_text_burn_video,
            artifact_patterns=("output/output_sub.mp4",),
            depends_on=("b5_generate_subtitles",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
    ),
)


AUDIO_STAGE = WorkflowStage(
    stage_id="audio",
    title="c. Dubbing",
    start_button_label="Start Audio Processing",
    runner_key="_audio_runner",
    video_path="output/output_dub.mp4",
    success_message="Audio processing is complete! The dubbed video keeps bilingual subtitles while replacing the audio track.",
    steps=(
        WorkflowStep(
            stage_id="audio",
            step_id="c1_generate_audio_tasks",
            title="Generate audio tasks and chunks",
            run=_run_audio_generate_tasks,
            artifact_patterns=(_8_1_AUDIO_TASK,),
            preview_patterns=("output/gpt_log/*.json", "logs/task_runner_errors.log"),
        ),
        WorkflowStep(
            stage_id="audio",
            step_id="c2_extract_reference_audio",
            title="Extract reference audio",
            run=_run_audio_extract_reference,
            artifact_patterns=("output/audio/refers/*.wav",),
            depends_on=("c1_generate_audio_tasks",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
        WorkflowStep(
            stage_id="audio",
            step_id="c3_select_reference_audio",
            title="Select automatic reference audio",
            run=_run_audio_select_reference,
            artifact_patterns=(str(AUTO_REFERENCE_AUDIO_FILE).replace("\\", "/"),),
            depends_on=("c2_extract_reference_audio",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
        WorkflowStep(
            stage_id="audio",
            step_id="c4_generate_audio_segments",
            title="Generate and merge audio files",
            run=_run_audio_generate_segments,
            artifact_patterns=("output/audio/tmp/*.wav", "output/audio/segs/*.wav"),
            depends_on=("c3_select_reference_audio",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
        WorkflowStep(
            stage_id="audio",
            step_id="c5_merge_full_audio",
            title="Merge full audio",
            run=_run_audio_merge_full_audio,
            artifact_patterns=("output/dub.mp3", "output/dub.srt", "output/dub_src.srt"),
            depends_on=("c4_generate_audio_segments",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
        WorkflowStep(
            stage_id="audio",
            step_id="c6_merge_video",
            title="Merge final audio and bilingual subtitles into video",
            run=_run_audio_merge_video,
            artifact_patterns=("output/output_dub.mp4",),
            depends_on=("c5_merge_full_audio",),
            preview_patterns=("logs/task_runner_errors.log",),
        ),
    ),
)


_STAGES = {
    TEXT_STAGE.stage_id: TEXT_STAGE,
    AUDIO_STAGE.stage_id: AUDIO_STAGE,
}


def get_stage(stage_id: str) -> WorkflowStage:
    return _STAGES[stage_id]


def get_stage_steps(stage_id: str) -> tuple[WorkflowStep, ...]:
    return get_stage(stage_id).steps


def get_step(stage_id: str, step_id: str) -> WorkflowStep:
    for step in get_stage_steps(stage_id):
        if step.step_id == step_id:
            return step
    raise KeyError(f"Unknown step: {stage_id}:{step_id}")


def build_runner_steps(
    stage_id: str,
    start_step_id: str | None = None,
    only_step_id: str | None = None,
) -> list[tuple[str, Callable[[], None]]]:
    stage_steps = list(get_stage_steps(stage_id))
    if only_step_id is not None:
        step = get_step(stage_id, only_step_id)
        return [(step.title, step.run)]

    if start_step_id is not None:
        start_index = next(
            index for index, step in enumerate(stage_steps) if step.step_id == start_step_id
        )
        stage_steps = stage_steps[start_index:]
    return [(step.title, step.run) for step in stage_steps]


def describe_stage_steps(stage_id: str) -> list[str]:
    return [step.title for step in get_stage_steps(stage_id)]


def get_dependency_steps(stage_id: str, step_id: str) -> tuple[WorkflowStep, ...]:
    steps = {step.step_id: step for step in get_stage_steps(stage_id)}
    return tuple(steps[dependency_id] for dependency_id in steps[step_id].depends_on)


def normalize_preview_patterns(step: WorkflowStep) -> tuple[str, ...]:
    combined_patterns = [*step.artifact_patterns, *step.preview_patterns]
    return tuple(dict.fromkeys(combined_patterns))


def normalize_path(path: str | Path) -> str:
    return str(Path(path)).replace("\\", "/")
