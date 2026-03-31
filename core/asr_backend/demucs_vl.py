import gc
import json
import os
from typing import Optional

import torch
from demucs.api import Separator
from demucs.apply import BagOfModels
from demucs.audio import save_audio
from demucs.pretrained import get_model
from rich import print as rprint
from rich.console import Console
from torch.cuda import is_available as is_cuda_available

from core.utils import load_key
from core.utils.models import *


class PreloadedSeparator(Separator):
    def __init__(self, model: BagOfModels, shifts: int = 1, overlap: float = 0.25,
                 split: bool = True, segment: Optional[int] = None, jobs: int = 0):
        self._model, self._audio_channels, self._samplerate = model, model.audio_channels, model.samplerate
        device = "cuda" if is_cuda_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.update_parameter(
            device=device,
            shifts=shifts,
            overlap=overlap,
            split=split,
            segment=segment,
            jobs=jobs,
            progress=True,
            callback=None,
            callback_arg=None,
        )


def _load_demucs_setting(key, default):
    try:
        return load_key(f"demucs_config.{key}")
    except KeyError:
        return default


def get_demucs_settings():
    return {
        "model": _load_demucs_setting("model", "htdemucs_ft"),
        "shifts": int(_load_demucs_setting("shifts", 2)),
        "overlap": float(_load_demucs_setting("overlap", 0.25)),
    }


def _build_input_metadata(input_file):
    stat = os.stat(input_file)
    return {
        "path": os.path.abspath(input_file),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def should_skip_demucs(input_file, vocal_file, background_file, manifest_path, model_name, shifts, overlap):
    if not (os.path.exists(vocal_file) and os.path.exists(background_file) and os.path.exists(manifest_path)):
        return False
    try:
        with open(manifest_path, "r", encoding="utf-8") as file:
            manifest = json.load(file)
    except (OSError, json.JSONDecodeError):
        return False

    if manifest.get("config") != {
        "model": model_name,
        "shifts": shifts,
        "overlap": overlap,
    }:
        return False
    return manifest.get("input") == _build_input_metadata(input_file)


def _write_demucs_manifest(manifest_path, input_file, model_name, shifts, overlap):
    manifest = {
        "input": _build_input_metadata(input_file),
        "config": {
            "model": model_name,
            "shifts": shifts,
            "overlap": overlap,
        },
    }
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)


def demucs_audio(input_file: str = _RAW_DEMUCS_AUDIO_FILE):
    settings = get_demucs_settings()
    if should_skip_demucs(
        input_file=input_file,
        vocal_file=_VOCAL_AUDIO_FILE,
        background_file=_BACKGROUND_AUDIO_FILE,
        manifest_path=_DEMUCS_MANIFEST_FILE,
        model_name=settings["model"],
        shifts=settings["shifts"],
        overlap=settings["overlap"],
    ):
        rprint(f"[yellow]⚠️ {_VOCAL_AUDIO_FILE} and {_BACKGROUND_AUDIO_FILE} already exist, skip Demucs processing.[/yellow]")
        return

    console = Console()
    os.makedirs(_AUDIO_DIR, exist_ok=True)

    console.print(f"🤖 Loading <{settings['model']}> model...")
    model = get_model(settings["model"])
    separator = PreloadedSeparator(model=model, shifts=settings["shifts"], overlap=settings["overlap"])

    console.print("🎵 Separating audio...")
    _, outputs = separator.separate_audio_file(input_file)

    kwargs = {
        "samplerate": model.samplerate,
        "bitrate": 128,
        "preset": 2,
        "clip": "rescale",
        "as_float": False,
        "bits_per_sample": 16,
    }

    console.print("🎤 Saving vocals track...")
    save_audio(outputs["vocals"].cpu(), _VOCAL_AUDIO_FILE, **kwargs)

    console.print("🎹 Saving background music...")
    background = sum(audio for source, audio in outputs.items() if source != "vocals")
    save_audio(background.cpu(), _BACKGROUND_AUDIO_FILE, **kwargs)
    _write_demucs_manifest(_DEMUCS_MANIFEST_FILE, input_file, settings["model"], settings["shifts"], settings["overlap"])

    del outputs, background, model, separator
    gc.collect()

    console.print("[green]✨ Audio separation completed![/green]")


if __name__ == "__main__":
    demucs_audio()
