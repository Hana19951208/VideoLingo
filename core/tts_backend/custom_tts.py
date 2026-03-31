import os
from pathlib import Path

import requests
from pydub import AudioSegment

from core.tts_backend.reference_audio import AUTO_REFERENCE_AUDIO_FILE, resolve_reference_audio_path
from core.utils import load_key, rprint


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
        url = load_key("custom_tts.url") or "http://127.0.0.1:8000/v1/tts"
        reference_mode = load_key("custom_tts.reference_mode") or "manual"
        manual_reference = load_key("custom_tts.spk_audio") or "reference_audio.wav"
        reference_path = resolve_reference_audio_path(
            reference_mode=reference_mode,
            manual_path=manual_reference,
            auto_path=AUTO_REFERENCE_AUDIO_FILE,
        )

        if reference_mode == "auto_single":
            if not reference_path.exists():
                raise FileNotFoundError(
                    f"自动参考音频不存在：{reference_path}。请先执行参考音频提取和自动选择步骤，或切回手动参考音频模式。"
                )
        elif not reference_path.exists():
            rprint(f"[yellow]未找到参考音频 {reference_path}，将生成 1 秒静音占位文件。建议改为有效的克隆参考音频。[/yellow]")
            AudioSegment.silent(duration=1000).export(reference_path, format="wav")

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


if __name__ == "__main__":
    custom_tts("这只是一条测试语音。", "custom_tts_test.wav")
