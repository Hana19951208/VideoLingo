import os
import platform
import subprocess
import time

import cv2
import numpy as np

from core._1_ytdlp import find_video_files
from core.utils import *
from core._shared_video_filter import build_burn_subtitle_filter


SRC_FONT_SIZE = 15
TRANS_FONT_SIZE = 17
FONT_NAME = "Arial"
TRANS_FONT_NAME = "Arial"

if platform.system() == "Linux":
    FONT_NAME = "NotoSansCJK-Regular"
    TRANS_FONT_NAME = "NotoSansCJK-Regular"
elif platform.system() == "Darwin":
    FONT_NAME = "Arial Unicode MS"
    TRANS_FONT_NAME = "Arial Unicode MS"

SRC_FONT_COLOR = "&HFFFFFF"
SRC_OUTLINE_COLOR = "&H000000"
SRC_OUTLINE_WIDTH = 1
SRC_SHADOW_COLOR = "&H80000000"
TRANS_FONT_COLOR = "&H00FFFF"
TRANS_OUTLINE_COLOR = "&H000000"
TRANS_OUTLINE_WIDTH = 1
TRANS_BACK_COLOR = "&H33000000"

OUTPUT_DIR = "output"
OUTPUT_VIDEO = f"{OUTPUT_DIR}/output_sub.mp4"
SRC_SRT = f"{OUTPUT_DIR}/src.srt"
TRANS_SRT = f"{OUTPUT_DIR}/trans.srt"


def check_gpu_available():
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


def merge_subtitles_to_video():
    video_file = find_video_files()
    os.makedirs(os.path.dirname(OUTPUT_VIDEO), exist_ok=True)

    if not load_key("burn_subtitles"):
        rprint("[bold yellow]Warning: A 0-second black video will be generated as a placeholder as subtitles are not burned in.[/bold yellow]")
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, 1, (1920, 1080))
        out.write(frame)
        out.release()
        rprint("[bold green]Placeholder video has been generated.[/bold green]")
        return

    if not os.path.exists(SRC_SRT) or not os.path.exists(TRANS_SRT):
        rprint("Subtitle files not found in the 'output' directory.")
        raise FileNotFoundError("Missing subtitle files for burn-in")

    video = cv2.VideoCapture(video_file)
    target_width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    target_height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video.release()
    rprint(f"[bold green]Video resolution: {target_width}x{target_height}[/bold green]")

    video_filter = build_burn_subtitle_filter(
        target_width=target_width,
        target_height=target_height,
        subtitle_mask=load_key("subtitle_mask"),
        subtitle_files=[
            {
                "path": SRC_SRT,
                "style": (
                    f"FontSize={SRC_FONT_SIZE},FontName={FONT_NAME},"
                    f"PrimaryColour={SRC_FONT_COLOR},OutlineColour={SRC_OUTLINE_COLOR},OutlineWidth={SRC_OUTLINE_WIDTH},"
                    f"ShadowColour={SRC_SHADOW_COLOR},BorderStyle=1"
                ),
            },
            {
                "path": TRANS_SRT,
                "style": (
                    f"FontSize={TRANS_FONT_SIZE},FontName={TRANS_FONT_NAME},"
                    f"PrimaryColour={TRANS_FONT_COLOR},OutlineColour={TRANS_OUTLINE_COLOR},OutlineWidth={TRANS_OUTLINE_WIDTH},"
                    f"BackColour={TRANS_BACK_COLOR},Alignment=2,MarginV=27,BorderStyle=4"
                ),
            },
        ],
    )

    ffmpeg_cmd = ["ffmpeg", "-i", video_file, "-vf", video_filter]
    if load_key("ffmpeg_gpu"):
        rprint("[bold green]will use GPU acceleration.[/bold green]")
        ffmpeg_cmd.extend(["-c:v", "h264_nvenc"])
    ffmpeg_cmd.extend(["-y", OUTPUT_VIDEO])

    rprint("Start merging subtitles to video...")
    start_time = time.time()
    process = subprocess.Popen(ffmpeg_cmd)

    try:
        process.wait()
        if process.returncode == 0:
            rprint(f"\nDone! Time taken: {time.time() - start_time:.2f} seconds")
        else:
            rprint("\nFFmpeg execution error")
    except Exception as error:
        rprint(f"\nError occurred: {error}")
        if process.poll() is None:
            process.kill()


if __name__ == "__main__":
    merge_subtitles_to_video()
