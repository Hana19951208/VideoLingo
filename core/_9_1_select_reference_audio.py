from collections import Counter
from pathlib import Path

import pandas as pd
from rich.panel import Panel

from core.tts_backend.reference_audio import AUTO_REFERENCE_AUDIO_FILE, select_reference_audio
from core.utils import load_key, rprint
from core.utils.models import _2_CLEANED_CHUNKS, _8_1_AUDIO_TASK, _AUDIO_REFERS_DIR


def _parse_time_seconds(time_value):
    if pd.isna(time_value):
        return None
    if isinstance(time_value, (int, float)):
        return float(time_value)

    normalized = str(time_value).replace(",", ".").strip()
    parts = normalized.split(":")
    if len(parts) != 3:
        return float(normalized)

    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _build_speaker_hints(task_df, cleaned_df):
    if "speaker_id" not in cleaned_df.columns:
        return {}, None, False

    speaker_hints = {}
    speaker_counter = Counter()

    for _, task_row in task_df.iterrows():
        task_start = _parse_time_seconds(task_row["start_time"])
        task_end = _parse_time_seconds(task_row["end_time"])
        overlaps = []

        for _, chunk_row in cleaned_df.iterrows():
            speaker_id = chunk_row.get("speaker_id")
            chunk_start = _parse_time_seconds(chunk_row.get("start"))
            chunk_end = _parse_time_seconds(chunk_row.get("end"))
            if speaker_id in (None, "", "nan") or chunk_start is None or chunk_end is None:
                continue
            overlap = min(task_end, chunk_end) - max(task_start, chunk_start)
            if overlap > 0:
                overlaps.append((speaker_id, overlap))

        if not overlaps:
            continue

        dominant_speaker = Counter()
        for speaker_id, overlap in overlaps:
            dominant_speaker[speaker_id] += overlap
        speaker_id = dominant_speaker.most_common(1)[0][0]
        speaker_hints[str(task_row["number"])] = speaker_id
        speaker_counter[speaker_id] += 1

    main_speaker = speaker_counter.most_common(1)[0][0] if speaker_counter else None
    has_multiple_speakers = len(speaker_counter) > 1
    return speaker_hints, main_speaker, has_multiple_speakers


def select_reference_audio_main():
    if load_key("tts_method") != "custom_tts":
        rprint(Panel("当前 TTS 不是 custom_tts，跳过自动参考音频选择。", title="Skip", border_style="blue"))
        return

    if load_key("custom_tts.reference_mode") != "auto_single":
        rprint(Panel("当前参考音频模式不是 auto_single，跳过自动参考音频选择。", title="Skip", border_style="blue"))
        return

    refers_dir = Path(_AUDIO_REFERS_DIR)
    candidate_files = sorted(
        refers_dir.glob("*.wav"),
        key=lambda file: int(file.stem) if file.stem.isdigit() else file.stem,
    )
    if not candidate_files:
        raise RuntimeError("自动参考音频选择失败：未找到 output/audio/refers 下的参考片段")

    task_df = pd.read_excel(_8_1_AUDIO_TASK)
    cleaned_df = pd.read_excel(_2_CLEANED_CHUNKS) if Path(_2_CLEANED_CHUNKS).exists() else pd.DataFrame()
    speaker_hints, main_speaker, has_multiple_speakers = _build_speaker_hints(task_df, cleaned_df)

    if has_multiple_speakers:
        rprint(
            Panel(
                "检测到可能存在多位说话人。当前版本只支持整片单参考音频，结果可能混入不同人物音色，必要时请切回手动参考音频。",
                title="Warning",
                border_style="yellow",
            )
        )

    selected_path = select_reference_audio(
        candidate_files=candidate_files,
        output_file=AUTO_REFERENCE_AUDIO_FILE,
        speaker_hints=speaker_hints,
        main_speaker=main_speaker,
    )
    rprint(Panel(f"已生成自动参考音频：{selected_path}", title="Success", border_style="green"))


if __name__ == "__main__":
    select_reference_audio_main()
