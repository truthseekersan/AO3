from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

from app.infrastructure.config.paths import CHARACTER_AVATAR_DIR, FANDOM_AVATAR_DIR

try:
    from PIL import Image
except ImportError:  # pragma: no cover - surfaced as a UI upload error
    Image = None


def process_fandom_avatar_upload(fandom_key: str, upload_content: bytes) -> dict[str, Any]:
    return _process_avatar_upload(FANDOM_AVATAR_DIR, f"fandom_{_safe_name(fandom_key)}.png", upload_content)


def process_character_avatar_upload(character_id: str, upload_content: bytes) -> dict[str, Any]:
    return _process_avatar_upload(CHARACTER_AVATAR_DIR, f"character_{_safe_name(character_id)}.png", upload_content)


def _process_avatar_upload(directory: Path, filename: str, upload_content: bytes) -> dict[str, Any]:
    if Image is None:
        raise ImportError("Pillow is required for avatar uploads. Install with: pip install Pillow")

    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / filename

    img = Image.open(io.BytesIO(upload_content)).convert("RGBA")
    target_size = 256
    width, height = img.size

    if width < height:
        new_width = target_size
        new_height = int(target_size * (height / width))
    else:
        new_height = target_size
        new_width = int(target_size * (width / height))

    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - target_size) / 2
    top = (new_height - target_size) / 2
    right = (new_width + target_size) / 2
    bottom = (new_height + target_size) / 2
    img = img.crop((left, top, right, bottom))

    color = _dominant_color(img)
    img.save(file_path, "PNG")

    return {
        "avatar_path": filename,
        "avatar_url": f"/fandom-avatars/{filename}" if directory == FANDOM_AVATAR_DIR else f"/character-avatars/{filename}",
        "avatar_color": color,
        "timestamp": int(time.time()),
    }


def _dominant_color(img) -> str:
    if Image is None:
        return "#58a6ff"
    thumb = img.copy().convert("RGB").resize((1, 1), resample=Image.Resampling.BOX)
    r, g, b = thumb.getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})[:80] or "avatar"
