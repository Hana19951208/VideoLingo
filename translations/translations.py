import json


DISPLAY_LANGUAGES = {
    "English": "en",
    "简体中文": "zh-CN",
    "繁體中文": "zh-HK",
    "日本語": "ja",
    "Español": "es",
    "Русский": "ru",
    "Français": "fr",
}

FALLBACK_TRANSLATIONS = {
    "zh-CN": {
        "If downloaded video still shows subtitles, they are likely hard subtitles embedded in the source video.": "如果下载后的视频仍然有字幕，通常是源视频自带的硬字幕。",
        "Mask hard subtitles": "遮挡源视频硬字幕",
        "Cover source hard subtitles before burning translated subtitles": "在烧录翻译字幕前，先用矩形遮挡部分源视频硬字幕。",
        "Mask X (%)": "遮挡 X (%)",
        "Mask Y (%)": "遮挡 Y (%)",
        "Mask Width (%)": "遮挡宽度 (%)",
        "Mask Height (%)": "遮挡高度 (%)",
        "Mask Fill Color": "遮挡填充颜色",
        "Custom TTS URL": "自定义 TTS 服务地址",
        "Reference Audio Mode": "参考音频模式",
        "Manual reference audio": "手动指定参考音频",
        "Auto single-speaker reference": "自动单人参考音频",
        "Reference Audio Path": "参考音频路径",
        "Auto mode will choose one clean single-speaker clip from the video vocals track.": "自动模式会从视频人声轨中选择一段较干净的单人音频作为参考。",
        "Select automatic reference audio": "自动选择参考音频",
    }
}


def load_translations(language="en"):
    with open(f"translations/{language}.json", "r", encoding="utf-8") as file:
        return json.load(file)


def translate(key):
    from core.utils.config_utils import load_key

    try:
        display_language = load_key("display_language")
        translations = load_translations(display_language)
        translation = translations.get(key)
        if translation is None:
            fallback_translation = FALLBACK_TRANSLATIONS.get(display_language, {}).get(key)
            if fallback_translation is not None:
                return fallback_translation
            print(f"Warning: Translation not found for key '{key}' in language '{display_language}'")
            return key
        return translation
    except Exception:
        return key
