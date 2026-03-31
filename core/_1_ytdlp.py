import glob
import os
import re
import subprocess
import sys

from core.utils import *


def sanitize_filename(filename):
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)
    filename = filename.strip(". ")
    return filename if filename else "video"


def update_ytdlp():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
        if "yt_dlp" in sys.modules:
            del sys.modules["yt_dlp"]
        rprint("[green]yt-dlp updated[/green]")
    except subprocess.CalledProcessError as error:
        rprint(f"[yellow]Warning: Failed to update yt-dlp: {error}[/yellow]")
    from yt_dlp import YoutubeDL

    return YoutubeDL


def build_ydl_opts(save_path="output", resolution="1080", cookies_path=""):
    ydl_opts = {
        "format": (
            "bestvideo+bestaudio/best"
            if resolution == "best"
            else f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]"
        ),
        "outtmpl": f"{save_path}/%(title)s.%(ext)s",
        "noplaylist": True,
        "writethumbnail": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "allsubtitles": False,
        "embedsubtitles": False,
        "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}],
    }
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = str(cookies_path)
    return ydl_opts


def download_video_ytdlp(url, save_path="output", resolution="1080"):
    os.makedirs(save_path, exist_ok=True)
    cookies_path = load_key("youtube.cookies_path")
    ydl_opts = build_ydl_opts(
        save_path=save_path,
        resolution=resolution,
        cookies_path=cookies_path,
    )

    YoutubeDL = update_ytdlp()
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for file in os.listdir(save_path):
        file_path = os.path.join(save_path, file)
        if not os.path.isfile(file_path):
            continue
        filename, ext = os.path.splitext(file)
        new_filename = sanitize_filename(filename)
        if new_filename != filename:
            os.rename(file_path, os.path.join(save_path, new_filename + ext))


def find_video_files(save_path="output"):
    video_files = [
        file
        for file in glob.glob(save_path + "/*")
        if os.path.splitext(file)[1][1:].lower() in load_key("allowed_video_formats")
    ]
    if sys.platform.startswith("win"):
        video_files = [file.replace("\\", "/") for file in video_files]
    video_files = [file for file in video_files if not file.startswith("output/output")]
    if len(video_files) != 1:
        raise ValueError(f"Number of videos found {len(video_files)} is not unique. Please check.")
    return video_files[0]


if __name__ == "__main__":
    url = input("Please enter the URL of the video you want to download: ")
    resolution = input("Please enter the desired resolution (360/480/720/1080, default 1080): ")
    resolution = int(resolution) if resolution.isdigit() else 1080
    download_video_ytdlp(url, resolution=resolution)
    print(f"Video has been downloaded to {find_video_files()}")
