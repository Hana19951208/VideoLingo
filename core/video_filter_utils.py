from pathlib import Path


def _normalize_subtitle_path(path):
    return str(Path(path)).replace("\\", "/")


def _build_drawbox_filter(target_width, target_height, subtitle_mask):
    x_pct = float(subtitle_mask.get("x_pct", 0))
    y_pct = float(subtitle_mask.get("y_pct", 0))
    w_pct = float(subtitle_mask.get("w_pct", 0))
    h_pct = float(subtitle_mask.get("h_pct", 0))
    fill_color = subtitle_mask.get("fill_color", "black@1.0")

    x_expr = f"{target_width}*{x_pct / 100:.6f}"
    y_expr = f"{target_height}*{y_pct / 100:.6f}"
    w_expr = f"{target_width}*{w_pct / 100:.6f}"
    h_expr = f"{target_height}*{h_pct / 100:.6f}"
    return f"drawbox=x={x_expr}:y={y_expr}:w={w_expr}:h={h_expr}:color={fill_color}:t=fill"


def build_burn_subtitle_filter(target_width, target_height, subtitle_files, subtitle_mask=None):
    subtitle_mask = subtitle_mask or {}
    filters = [
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease",
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2",
    ]

    if subtitle_mask.get("enabled"):
        filters.append(
            _build_drawbox_filter(
                target_width=target_width,
                target_height=target_height,
                subtitle_mask=subtitle_mask,
            )
        )

    for subtitle_file in subtitle_files:
        subtitle_path = _normalize_subtitle_path(subtitle_file["path"])
        style = subtitle_file.get("style")
        if style:
            filters.append(f"subtitles={subtitle_path}:force_style='{style}'")
        else:
            filters.append(f"subtitles={subtitle_path}")

    return ",".join(filters)
