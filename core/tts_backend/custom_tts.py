import io
import json
import os
import zipfile
from pathlib import Path

import requests
from pydub import AudioSegment

from core.tts_backend.reference_audio import AUTO_REFERENCE_AUDIO_FILE, resolve_reference_audio_path
from core.utils import load_key, rprint


def _safe_load_key(key, default=None):
    try:
        return load_key(key)
    except KeyError:
        return default


def _resolve_reference_path():
    reference_mode = _safe_load_key("custom_tts.reference_mode", "manual") or "manual"
    manual_reference = _safe_load_key("custom_tts.spk_audio", "reference_audio.wav") or "reference_audio.wav"
    reference_path = resolve_reference_audio_path(
        reference_mode=reference_mode,
        manual_path=manual_reference,
        auto_path=AUTO_REFERENCE_AUDIO_FILE,
    )
    return reference_mode, reference_path


def _ensure_reference_audio(reference_mode, reference_path):
    if reference_mode == "auto_single":
        if not reference_path.exists():
            raise FileNotFoundError(
                f"自动参考音频不存在：{reference_path}。请先执行参考音频提取和自动选择步骤，或切回手动参考音频模式。"
            )
        return

    if reference_path.exists():
        return

    rprint(f"[yellow]未找到参考音频 {reference_path}，将生成 1 秒静音占位文件。建议改为有效的克隆参考音频。[/yellow]")
    AudioSegment.silent(duration=1000).export(reference_path, format="wav")


def _resolve_single_url():
    return _safe_load_key("custom_tts.url", "http://127.0.0.1:8000/v1/tts") or "http://127.0.0.1:8000/v1/tts"


def _resolve_batch_url():
    batch_url = _safe_load_key("custom_tts.batch_url")
    if batch_url:
        return batch_url
    return _resolve_single_url().rstrip("/") + "/batch"


def custom_tts(text, save_path):
    """
    Custom TTS interface for local Docker index-tts.

    Args:
        text (str): Text to be converted to speech.
        save_path (str): Path to save the audio file.
    """
    speech_file_path = Path(save_path)
    speech_file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        url = _resolve_single_url()
        reference_mode, reference_path = _resolve_reference_path()
        _ensure_reference_audio(reference_mode, reference_path)

        with open(reference_path, "rb") as audio_file:
            files = {
                "text": (None, text.encode("utf-8")),
                "spk_audio": (os.path.basename(reference_path), audio_file, "audio/wav"),
            }
            response = requests.post(url, files=files, timeout=120)

        if response.status_code == 200:
            with open(save_path, "wb") as output_file:
                output_file.write(response.content)
            rprint(f"[green]音频已保存到 {speech_file_path}[/green]")
            return

        raise Exception(f"请求 index-tts 失败: HTTP {response.status_code} - {response.text}")
    except Exception as error:
        rprint(f"[red]TTS 转换失败: {error}[/red]")
        raise


def custom_tts_batch(items):
    if not items:
        return

    try:
        reference_mode, reference_path = _resolve_reference_path()
        _ensure_reference_audio(reference_mode, reference_path)
        batch_url = _resolve_batch_url()

        request_items = []
        output_by_id = {}
        for item in items:
            request_items.append(
                {
                    "id": item["id"],
                    "text": item["text"],
                    "emotion": item.get("emotion"),
                    "max_text_tokens": item.get("max_text_tokens"),
                }
            )
            output_by_id[item["id"]] = Path(item["save_path"])

        with open(reference_path, "rb") as audio_file:
            files = {
                "spk_audio": (os.path.basename(reference_path), audio_file, "audio/wav"),
            }
            data = {
                "items": json.dumps(request_items, ensure_ascii=False),
            }
            response = requests.post(batch_url, data=data, files=files, timeout=600)

        if response.status_code in {404, 405}:
            for item in items:
                custom_tts(item["text"], item["save_path"])
            return

        if response.status_code != 200:
            raise Exception(f"批量请求 index-tts 失败: HTTP {response.status_code} - {response.text}")

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

        for result in manifest.get("items", []):
            if result.get("status") != "ok":
                raise Exception(f"批量 TTS 子任务失败: {result.get('id')} - {result.get('error')}")
            output_path = output_by_id[result["id"]]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(archive.read(result["filename"]))
    except Exception as error:
        rprint(f"[red]批量 TTS 失败: {error}[/red]")
        raise


if __name__ == "__main__":
    custom_tts("这只是一条测试语音。", "custom_tts_test.wav")
