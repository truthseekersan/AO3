from __future__ import annotations

import argparse

from nicegui import app, ui

from app.application.composition import build_container
from app.infrastructure.config.paths import CHARACTER_AVATAR_DIR, FANDOM_AVATAR_DIR, FONT_DIR
from app.presentation.ui.app_shell import AO3StudioShell
from app.presentation.ui.theme import apply_theme


def build_app() -> None:
    container = build_container()
    app.add_static_files("/fandom-avatars", str(FANDOM_AVATAR_DIR))
    app.add_static_files("/character-avatars", str(CHARACTER_AVATAR_DIR))
    app.add_static_files("/fonts", str(FONT_DIR))
    apply_theme()
    AO3StudioShell(container).build()


@ui.page("/")
def index() -> None:
    build_app()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AO3 Studio local-first NiceGUI client")
    parser.add_argument("--native", action="store_true", help="Launch in NiceGUI native desktop mode.")
    parser.add_argument("--port", type=int, default=8093, help="HTTP port for browser mode.")
    parser.add_argument("--show", action="store_true", help="Ask NiceGUI to open a browser window.")
    return parser.parse_args()


if __name__ in {"__main__", "__mp_main__"}:
    args = parse_args()
    ui.run(
        title="AO3 Studio",
        host="127.0.0.1",
        port=args.port,
        reload=False,
        dark=True,
        native=args.native,
        show=args.show if not args.native else False,
    )
