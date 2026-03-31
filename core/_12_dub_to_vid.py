import platform
import subprocess

import cv2
import numpy as np
from rich.console import Console

from core._1_ytdlp import find_video_files
from core.asr_backend.audio_preprocess import normalize_audio_volume
from core.utils import *
from core.utils.models import *
from core._shared_video_filter import build_burn_subtitle_filter


console = Console()

DUB_VIDEO = "output/output_dub.mp4"
DUB_SUB_FILE = "output/dub.srt"
DUB_AUDIO = "output/dub.mp3"

TRANS_FONT_SIZE = 17
TRANS_FONT_NAME = "Arial"
if platform.system() == "Linux":
    TRANS_FONT_NAME = "NotoSansCJK-Regular"
if platform.system() == "Darwin":
    TRANS_FONT_NAME = "Arial Unicode MS"

TRANS_FONT_COLOR = "&H00FFFF"
TRANS_OUTLINE_COLOR = "&H000000"
TRANS_OUTLINE_WIDTH = 1
TRANS_BACK_COLOR = "&H33000000"


def build_audio_mix_filter():
    return (
        "[1:a]volume=0.35[bg];"
        "[bg][2:a]sidechaincompress=threshold=0.015:ratio=8:attack=20:release=250[bgduck];"
        "[bgduck][2:a]amix=inputs=2:duration=first:dropout_transition=3[a]"
    )


def build_merge_command(video_file, background_file, normalized_dub_audio, subtitle_filter, ffmpeg_gpu):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_file,
        "-i",
        background_file,
        "-i",
        normalized_dub_audio,
        "-filter_complex",
        f"[0:v]{subtitle_filter}[v];{build_audio_mix_filter()}",
    ]
    if ffmpeg_gpu:
        cmd.extend(["-map", "[v]", "-map", "[a]", "-c:v", "h264_nvenc"])
    else:
        cmd.extend(["-map", "[v]", "-map", "[a]"])
    cmd.extend(["-c:a", "aac", "-b:a", "96k", DUB_VIDEO])
    return cmd


def merge_video_audio():
    VIDEO_FILE = find_video_files()
    background_file = _BACKGROUND_AUDIO_FILE

    if not load_key("burn_subtitles"):
        rprint("[bold yellow]Warning: A 0-second black video will be generated as a placeholder as subtitles are not burned in.[/bold yellow]")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(DUB_VIDEO, fourcc, 1, (1920, 1080))
        out.write(frame)
        out.release()
        rprint("[bold green]Placeholder video has been generated.[/bold green]")
        return

    normalized_dub_audio = "output/normalized_dub.wav"
    normalize_audio_volume(DUB_AUDIO, normalized_dub_audio)

    video = cv2.VideoCapture(VIDEO_FILE)
    target_width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    target_height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    rprint(f"[bold green]Video resolution: {target_width}x{target_height}[/bold green]")

    subtitle_filter = build_burn_subtitle_filter(
        target_width=target_width,
        target_height=target_height,
        subtitle_mask=load_key("subtitle_mask"),
        subtitle_files=[
            {
                "path": DUB_SUB_FILE,
                "style": (
                    f"FontSize={TRANS_FONT_SIZE},FontName={TRANS_FONT_NAME},"
                    f"PrimaryColour={TRANS_FONT_COLOR},OutlineColour={TRANS_OUTLINE_COLOR},OutlineWidth={TRANS_OUTLINE_WIDTH},"
                    f"BackColour={TRANS_BACK_COLOR},Alignment=2,MarginV=27,BorderStyle=4"
                ),
            }
        ],
    )

    ffmpeg_gpu = load_key("ffmpeg_gpu")
    if ffmpeg_gpu:
        rprint("[bold green]Using GPU acceleration...[/bold green]")
    cmd = build_merge_command(
        video_file=VIDEO_FILE,
        background_file=background_file,
        normalized_dub_audio=normalized_dub_audio,
        subtitle_filter=subtitle_filter,
        ffmpeg_gpu=ffmpeg_gpu,
    )
    subprocess.run(cmd, check=True)
    rprint(f"[bold green]Video and audio successfully merged into {DUB_VIDEO}[/bold green]")


if __name__ == "__main__":
    merge_video_audio()
