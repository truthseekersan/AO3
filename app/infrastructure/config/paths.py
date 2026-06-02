from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "config"
DATABASE_PATH = CONFIG_DIR / "ao3_studio.sqlite"
FANDOM_AVATAR_DIR = CONFIG_DIR / "fandom_avatars"
CHARACTER_AVATAR_DIR = CONFIG_DIR / "character_avatars"
STATIC_DIR = ROOT_DIR / "app" / "presentation" / "static"
FONT_DIR = STATIC_DIR / "fonts"


def ensure_config_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    FANDOM_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTER_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    FONT_DIR.mkdir(parents=True, exist_ok=True)
