from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from shutil import which

from core.utils.config_utils import load_key

from control_plane.runtime import get_workspace_root


DEFAULT_VIDEO_FORMATS = ['mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv', 'webm']
DEFAULT_AUDIO_FORMATS = ['wav', 'mp3', 'flac', 'm4a', 'aac']


class RemoteSourceDownloadError(RuntimeError):
    pass


def safe_load_key(key: str, default):
    try:
        value = load_key(key)
    except Exception:
        return default
    return default if value in (None, '') else value


def get_output_dir() -> Path:
    return get_workspace_root() / 'output'


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def reset_output_dir() -> Path:
    output_dir = get_output_dir()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def sanitize_filename(filename: str) -> str:
    filename = filename.replace(' ', '_')
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = filename.strip('. ')
    return filename or 'video'


def copy_source_file(source_path: str) -> Path:
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f'未找到源文件: {source_path}')

    output_dir = reset_output_dir()
    clean_name = sanitize_filename(source.stem) + source.suffix.lower()
    target_path = output_dir / clean_name
    shutil.copy2(source, target_path)
    return target_path


def convert_audio_to_video(audio_file: Path) -> Path:
    output_video = audio_file.parent / 'black_screen.mp4'
    ffmpeg_cmd = [
        'ffmpeg',
        '-y',
        '-f',
        'lavfi',
        '-i',
        'color=c=black:s=640x360',
        '-i',
        str(audio_file),
        '-shortest',
        '-c:v',
        'libx264',
        '-c:a',
        'aac',
        '-pix_fmt',
        'yuv420p',
        str(output_video),
    ]
    subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
    audio_file.unlink(missing_ok=True)
    return output_video


def prepare_remote_source(url: str) -> None:
    output_dir = reset_output_dir()
    resolution = str(safe_load_key('ytb_resolution', '1080'))
    download_video(url, save_path=str(output_dir), resolution=resolution)


def iter_root_youtube_cookiefiles() -> list[Path]:
    project_root = get_project_root()
    return sorted(
        (
            candidate
            for candidate in project_root.glob('www.youtube.com_cookies*.txt')
            if candidate.is_file()
        ),
        key=lambda item: (item.stat().st_mtime, item.name),
        reverse=True,
    )


def resolve_youtube_cookiefile(configured_path: str | None) -> str | None:
    candidates: list[Path] = []
    if configured_path:
        candidates.append(Path(configured_path).expanduser())
    candidates.extend(iter_root_youtube_cookiefiles())

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def detect_node_runtime() -> str | None:
    return which('node')


def build_ytdlp_options(save_path: str, resolution: str, cookiefile: str | None = None) -> dict:
    options = {
        'format': (
            'bestvideo+bestaudio/best'
            if resolution == 'best'
            else f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]'
        ),
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'writethumbnail': True,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'allsubtitles': False,
        'embedsubtitles': False,
        'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
        'quiet': False,
    }
    node_path = detect_node_runtime()
    if node_path:
        options['js_runtimes'] = {'node': {'path': node_path}}
    if cookiefile and os.path.exists(cookiefile):
        options['cookiefile'] = cookiefile
    return options


def is_youtube_auth_challenge_error(message: str) -> bool:
    lowered = message.lower()
    markers = [
        "sign in to confirm you're not a bot",
        'use --cookies-from-browser or --cookies',
        'youtube account cookies are no longer valid',
        'authentication',
    ]
    return any(marker in lowered for marker in markers)


def normalize_ytdlp_error_message(error: Exception, cookiefile_used: bool) -> str:
    message = str(error)
    if is_youtube_auth_challenge_error(message):
        if cookiefile_used:
            return (
                'YouTube 当前要求额外的人机校验，现有 cookies 仍未通过校验。'
                '请刷新浏览器导出的 cookies 后重试，或更换网络环境后再试。'
            )
        return (
            'YouTube 当前要求额外的人机校验，匿名下载未通过。'
            '系统已经尝试无 cookies 下载；如仍失败，请提供新的 YouTube cookies 后重试。'
        )
    return message


def run_ytdlp_download(url: str, options: dict) -> None:
    from yt_dlp import YoutubeDL

    with YoutubeDL(options) as ydl:
        ydl.download([url])


def download_video(url: str, save_path: str, resolution: str) -> None:
    try:
        from yt_dlp.utils import DownloadError
    except ImportError as error:
        raise RuntimeError('yt-dlp 未安装，无法下载远程视频') from error

    cookies_path = resolve_youtube_cookiefile(str(safe_load_key('youtube.cookies_path', '')))
    try:
        run_ytdlp_download(url, build_ytdlp_options(save_path=save_path, resolution=resolution))
    except DownloadError as error:
        should_retry_with_cookie = cookies_path and is_youtube_auth_challenge_error(str(error))
        if should_retry_with_cookie:
            try:
                run_ytdlp_download(
                    url,
                    build_ytdlp_options(save_path=save_path, resolution=resolution, cookiefile=cookies_path),
                )
            except DownloadError as retry_error:
                raise RemoteSourceDownloadError(
                    normalize_ytdlp_error_message(retry_error, cookiefile_used=True)
                ) from retry_error
        else:
            raise RemoteSourceDownloadError(
                normalize_ytdlp_error_message(error, cookiefile_used=False)
            ) from error

    for file_path in Path(save_path).glob('*'):
        if file_path.is_file():
            sanitized_name = sanitize_filename(file_path.stem) + file_path.suffix.lower()
            if sanitized_name != file_path.name:
                file_path.rename(file_path.with_name(sanitized_name))


def materialize_project_source(project) -> dict[str, str]:
    source_type = project.source_type
    source = project.source_uri_or_path
    video_formats = {item.lower() for item in safe_load_key('allowed_video_formats', DEFAULT_VIDEO_FORMATS)}
    audio_formats = {item.lower() for item in safe_load_key('allowed_audio_formats', DEFAULT_AUDIO_FORMATS)}

    if source_type == 'remote_url':
        prepare_remote_source(source)
        return {'source_state': 'downloaded', 'source_type': source_type}

    copied_path = copy_source_file(source)
    extension = copied_path.suffix.lower().lstrip('.')
    if extension in audio_formats and extension not in video_formats:
        convert_audio_to_video(copied_path)
        return {'source_state': 'audio_wrapped_as_video', 'source_type': source_type}

    return {'source_state': 'copied', 'source_type': source_type}
