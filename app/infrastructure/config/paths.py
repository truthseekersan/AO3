from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "config"
DATABASE_PATH = CONFIG_DIR / "ao3_studio.sqlite"
FANDOM_AVATAR_DIR = CONFIG_DIR / "fandom_avatars"
CHARACTER_AVATAR_DIR = CONFIG_DIR / "character_avatars"
AUDIO_CACHE_DIR = CONFIG_DIR / "audio_cache"
STATIC_DIR = ROOT_DIR / "app" / "presentation" / "static"
FONT_DIR = STATIC_DIR / "fonts"


def ensure_config_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    FANDOM_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTER_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FONT_DIR.mkdir(parents=True, exist_ok=True)


def resolve_audio_path(work_id: str, chapter_idx: int, pid: int, dam_seq: int) -> Path:
    """Build the local path for a DAM audio cache file."""
    return AUDIO_CACHE_DIR / str(work_id) / f"ch{chapter_idx}" / f"{pid}_{dam_seq}.wav"
