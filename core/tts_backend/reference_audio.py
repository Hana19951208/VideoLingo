import io
from pathlib import Path

from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from core.utils.models import _AUDIO_DIR


AUTO_REFERENCE_AUDIO_FILE = Path(_AUDIO_DIR) / "reference_auto.wav"
MIN_REFERENCE_DURATION_MS = 4000
MAX_REFERENCE_DURATION_MS = 15000
TARGET_REFERENCE_DURATION_MS = 8000
MAX_SILENCE_RATIO = 0.45
MIN_LOUDNESS_DBFS = -38
CLIPPING_THRESHOLD = 0.01


def resolve_reference_audio_path(reference_mode, manual_path, auto_path=None):
    auto_file = Path(auto_path or AUTO_REFERENCE_AUDIO_FILE)
    if reference_mode == "auto_single":
        return auto_file
    return Path(manual_path)


def _build_hint_key(path):
    return Path(path).stem


def _load_audio(path):
    audio_path = Path(path)
    with open(audio_path, "rb") as audio_file:
        audio_bytes = io.BytesIO(audio_file.read())
    format_name = audio_path.suffix.lstrip(".") or None
    return AudioSegment.from_file(audio_bytes, format=format_name)


def _merge_segments(candidate_group):
    combined = AudioSegment.empty()
    for candidate in candidate_group:
        segment = _load_audio(candidate)
        if len(combined) > 0:
            combined += AudioSegment.silent(duration=120)
        combined += segment
    return combined


def _calc_clipping_ratio(segment):
    if segment.sample_width <= 0:
        return 1.0
    max_possible = float(1 << (8 * segment.sample_width - 1))
    if max_possible <= 0:
        return 1.0
    samples = segment.get_array_of_samples()
    if not samples:
        return 1.0
    clipped = sum(1 for sample in samples if abs(sample) >= max_possible - 1)
    return clipped / len(samples)


def _score_segment(segment):
    duration_ms = len(segment)
    if duration_ms < MIN_REFERENCE_DURATION_MS or duration_ms > MAX_REFERENCE_DURATION_MS:
        return None

    nonsilent_ranges = detect_nonsilent(segment, min_silence_len=250, silence_thresh=-40)
    nonsilent_ms = sum(end - start for start, end in nonsilent_ranges)
    silence_ratio = 1 - (nonsilent_ms / duration_ms if duration_ms else 0)
    if silence_ratio > MAX_SILENCE_RATIO:
        return None

    loudness = segment.dBFS
    if loudness == float("-inf") or loudness < MIN_LOUDNESS_DBFS:
        return None

    clipping_ratio = _calc_clipping_ratio(segment)
    if clipping_ratio > CLIPPING_THRESHOLD:
        return None

    duration_score = 1 - abs(duration_ms - TARGET_REFERENCE_DURATION_MS) / TARGET_REFERENCE_DURATION_MS
    loudness_score = min(max((loudness + 40) / 20, 0), 1)
    silence_score = 1 - silence_ratio
    clipping_score = 1 - clipping_ratio / CLIPPING_THRESHOLD
    return (
        duration_score * 0.4
        + silence_score * 0.3
        + loudness_score * 0.2
        + clipping_score * 0.1
    )


def _iter_candidate_groups(candidate_files, speaker_hints, main_speaker):
    candidate_paths = [Path(path) for path in candidate_files]
    if main_speaker:
        filtered = [
            path for path in candidate_paths if speaker_hints.get(_build_hint_key(path)) == main_speaker
        ]
        if filtered:
            candidate_paths = filtered

    for index, path in enumerate(candidate_paths):
        yield [path]
        next_paths = candidate_paths[index + 1 : index + 3]
        current_hint = speaker_hints.get(_build_hint_key(path))
        group = [path]
        for next_path in next_paths:
            next_hint = speaker_hints.get(_build_hint_key(next_path))
            if current_hint and next_hint and next_hint != current_hint:
                break
            group = [*group, next_path]
            yield group


def select_reference_audio(candidate_files, output_file, speaker_hints=None, main_speaker=None):
    speaker_hints = speaker_hints or {}
    if not candidate_files:
        raise RuntimeError("未找到可用的参考音频片段")

    best_group = None
    best_score = None
    best_audio = None

    for candidate_group in _iter_candidate_groups(candidate_files, speaker_hints, main_speaker):
        merged_audio = _merge_segments(candidate_group)
        score = _score_segment(merged_audio)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_group = candidate_group
            best_score = score
            best_audio = merged_audio

    if best_audio is None or best_group is None:
        raise RuntimeError("自动参考音频选择失败：没有找到足够干净的人声音频，请改用手动参考音频")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_buffer = io.BytesIO()
    best_audio.export(output_buffer, format="wav")
    output_path.write_bytes(output_buffer.getvalue())
    return output_path
