from __future__ import annotations

import colorsys

from nicegui import ui


def rgb_from_hex(hex_color: str) -> tuple[int, int, int]:
    value = (hex_color or "#58a6ff").lstrip("#")
    if len(value) != 6:
        value = "58a6ff"
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return 88, 166, 255


def normalized_label_color(hex_color: str) -> str:
    r, g, b = rgb_from_hex(hex_color)
    h, _, _ = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    nr, ng, nb = colorsys.hls_to_rgb(h, 0.66, 0.58)
    return f"rgb({int(nr * 255)},{int(ng * 255)},{int(nb * 255)})"


def dark_button_color(hex_color: str) -> str:
    r, g, b = rgb_from_hex(hex_color)
    h, _, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    nr, ng, nb = colorsys.hls_to_rgb(h, 0.30, max(s * 0.45, 0.18))
    return f"rgb({int(nr * 255)},{int(ng * 255)},{int(nb * 255)})"


def glow_text(hex_color: str, glow_px: int = 6) -> str:
    color = normalized_label_color(hex_color)
    return (
        f"color: {color}; "
        "text-shadow: 0 0 1px rgba(0,0,0,1), 0 1px 2px rgba(0,0,0,0.9), "
        f"0 0 4px rgba(0,0,0,0.7), 0 0 {glow_px}px {color};"
    )


def wash_background(hex_color: str, alpha: float = 0.16) -> str:
    r, g, b = rgb_from_hex(hex_color)
    return (
        f"background: linear-gradient(160deg, rgba({r},{g},{b},{alpha}) 0%, "
        f"rgba({r},{g},{b},{alpha * 0.54}) 52%, rgba({r},{g},{b},{alpha * 0.18}) 100%), #0d1117 !important;"
    )


def tooltip_style(hex_color: str = "#58a6ff") -> str:
    r, g, b = rgb_from_hex(hex_color)
    color = normalized_label_color(hex_color)
    return (
        f"color: {color}; text-shadow: 0 0 1px rgba(0,0,0,1), 0 1px 2px rgba(0,0,0,0.9), 0 0 5px {color}; "
        f"background: linear-gradient(160deg, rgba({r},{g},{b},0.15), rgba({r},{g},{b},0.06)), #0d1117 !important; "
        f"border: 1px solid rgba({r},{g},{b},0.30);"
    )


def rich_tooltip(text: str, color: str = "#58a6ff") -> ui.tooltip:
    return ui.tooltip(text).classes("text-sm").style(tooltip_style(color))


def apply_theme() -> None:
    ui.dark_mode().enable()
    ui.add_head_html(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@400;500;600;700&family=Courier+Prime:wght@400;700&family=Space+Mono&family=Atkinson+Hyperlegible+Mono:wght@300&family=Recursive:wght,CASL,CRSV,MONO,slnt@300..1000,0..1,0..1,0..1,0&display=swap');
            @font-face { font-family: 'Loretta Light'; src: url('/fonts/loretta-light.otf') format('opentype'); font-weight: 300; }
            @font-face { font-family: 'Loretta Light'; src: url('/fonts/loretta-medium.otf') format('opentype'); font-weight: 500; }
            @font-face { font-family: 'Loretta Light'; src: url('/fonts/loretta-medium.otf') format('opentype'); font-weight: bold; }
            @font-face { font-family: 'Loretta Medium'; src: url('/fonts/loretta-medium.otf') format('opentype'); }
            @font-face { font-family: 'Charter'; src: url('/fonts/Charter Regular.otf') format('opentype'); }
            @font-face { font-family: 'Cascadia Mono'; src: url('/fonts/CascadiaMono.ttf') format('truetype'); }
            @font-face { font-family: 'Monaspace Argon'; src: url('/fonts/Monaspace-Argon-Var.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'Sono'; src: url('/fonts/Sono-VariableFont_MONO,wght.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'Reddit Mono'; src: url('/fonts/RedditMono-VariableFont_wght.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'iA Writer Quattro S'; src: url('/fonts/ia-writer-quattro.ttf') format('truetype'); }
            @font-face { font-family: 'DM Mono Light'; src: url('/fonts/DMMono-Light.ttf') format('truetype'); }
            @font-face { font-family: 'Monaspace Neon'; src: url('/fonts/Monaspace-Neon-Var.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'Merienda'; src: url('/fonts/Merienda-VariableFont_wght.ttf') format('truetype'); font-weight: 300 900; }
            @font-face { font-family: 'Cause Light'; src: url('/fonts/cause-light.ttf') format('truetype'); }
            @font-face { font-family: 'Coming Soon'; src: url('/fonts/coming-soon.ttf') format('truetype'); }
            @font-face { font-family: 'Maple Mono'; src: url('/fonts/MapleMono-Variable.ttf') format('truetype'); font-weight: 100 900; }
            @font-face { font-family: 'Monaspace Krypton'; src: url('/fonts/MonaspaceKrypton-Variable.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'Monaspace Xenon'; src: url('/fonts/MonaspaceXenon-Variable.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'Fraunces'; src: url('/fonts/Fraunces-VariableFont_SOFT,WONK,opsz,wght.ttf') format('truetype'); }
            @font-face { font-family: 'Newsreader'; src: url('/fonts/Newsreader-Variable.ttf') format('truetype'); font-weight: 200 800; }
            @font-face { font-family: 'Kalam Light'; src: url('/fonts/Kalam-Light.ttf') format('truetype'); }
            @font-face { font-family: 'Architects Daughter'; src: url('/fonts/ArchitectsDaughter-Regular.ttf') format('truetype'); }
            @font-face { font-family: 'Reenie Beanie'; src: url('/fonts/ReenieBeanie-Regular.ttf') format('truetype'); }
            @font-face { font-family: 'M PLUS Code'; src: url('/fonts/MPLUSCode-Var.ttf') format('truetype'); font-weight: 100 700; }
            @font-face { font-family: 'Martian Mono'; src: url('/fonts/MartianMono-Variable.ttf') format('truetype'); font-weight: 100 800; font-stretch: 75% 112.5%; font-display: swap; }
            @font-face { font-family: 'Source Code Pro'; src: url('/fonts/SourceCodePro-Variable.ttf') format('truetype'); font-weight: 200 900; font-style: normal; font-display: swap; }
            @font-face { font-family: 'Shantell Sans'; src: url('/fonts/ShantellSans-VariableFont_BNCE,INFM,SPAC,wght.ttf') format('truetype'); font-weight: 300 800; }
            @font-face { font-family: 'Caveat'; src: url('/fonts/Caveat-VariableFont_wght.ttf') format('truetype'); font-weight: 400 700; }
            @font-face { font-family: 'Neucha'; src: url('/fonts/Neucha-Regular.ttf') format('truetype'); }
            @font-face { font-family: 'Gaegu'; src: url('/fonts/gaegu-v23-latin-300.woff2') format('woff2'); font-weight: 300; }
            @font-face { font-family: 'Gaegu'; src: url('/fonts/gaegu-v23-latin-regular.woff2') format('woff2'); font-weight: 400; }
            @keyframes gradient-border-rotate {
                0% { background-position: 0% 50%; }
                50% { background-position: 100% 50%; }
                100% { background-position: 0% 50%; }
            }
            @keyframes gradient-border-reverse-spin {
                0% { background-position: 100% 50%; }
                50% { background-position: 0% 50%; }
                100% { background-position: 100% 50%; }
            }
            @keyframes gradient-border-pulse {
                0%, 100% { filter: saturate(1.1) brightness(1); opacity: 0.82; }
                50% { filter: saturate(1.7) brightness(1.35); opacity: 1; }
            }
            @keyframes gradient-border-sonar-sweep {
                0% { background-position: 0% 50%; opacity: 0.50; }
                45% { opacity: 1; }
                100% { background-position: 100% 50%; opacity: 0.50; }
            }
            .gradient-border {
                position: relative;
                border: 0 !important;
                isolation: isolate;
            }
            .gradient-border::before {
                content: '';
                position: absolute;
                inset: 0;
                border-radius: inherit;
                padding: var(--gb-thickness, 1px);
                background: var(--gb-gradient, linear-gradient(120deg, var(--gb-a), var(--gb-b), var(--gb-c), var(--gb-a)));
                background-size: var(--gb-size, 260% 260%);
                animation: var(--gb-animation, gradient-border-rotate 8s linear infinite);
                -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
                -webkit-mask-composite: xor;
                mask-composite: exclude;
                pointer-events: none;
                z-index: 2;
            }
            .gradient-border > * {
                position: relative;
                z-index: 3;
            }
            .gradient-border-single { --gb-gradient: linear-gradient(120deg, var(--gb-a), var(--gb-b), var(--gb-a)); }
            .gradient-border-twin { --gb-gradient: linear-gradient(120deg, var(--gb-a), var(--gb-b), var(--gb-c), var(--gb-b), var(--gb-a)); }
            .gradient-border-duotone { --gb-gradient: linear-gradient(90deg, var(--gb-a), var(--gb-b)); --gb-animation: gradient-border-rotate 10s ease infinite; }
            .gradient-border-tritone { --gb-gradient: linear-gradient(130deg, var(--gb-a), var(--gb-b), var(--gb-c), var(--gb-a)); --gb-animation: gradient-border-rotate 9s linear infinite; }
            .gradient-border-clash { --gb-gradient: conic-gradient(from 180deg, var(--gb-a), var(--gb-d), var(--gb-b), var(--gb-c), var(--gb-a)); --gb-size: 100% 100%; }
            .gradient-border-traffic { --gb-gradient: linear-gradient(90deg, var(--gb-a) 0%, var(--gb-a) 24%, var(--gb-b) 25%, var(--gb-b) 49%, var(--gb-c) 50%, var(--gb-c) 74%, var(--gb-d) 75%, var(--gb-d) 100%); --gb-size: 320% 100%; }
            .gradient-border-glitch { --gb-gradient: linear-gradient(90deg, var(--gb-a), var(--gb-d), var(--gb-b), var(--gb-c), var(--gb-a)); --gb-animation: gradient-border-rotate 2.8s steps(9) infinite; }
            .gradient-border-wildcard { --gb-gradient: conic-gradient(from 90deg, #ff2d95, #00e5ff, #ffe45c, #9b5cff, #6cff87, #ff2d95); --gb-size: 100% 100%; --gb-animation: gradient-border-rotate 5s linear infinite; }
            .gradient-border-ignition { --gb-gradient: radial-gradient(circle, var(--gb-d), var(--gb-a), var(--gb-b), transparent 72%); --gb-size: 220% 220%; --gb-animation: gradient-border-pulse 6s cubic-bezier(0.85, 0, 0.15, 1) infinite, gradient-border-rotate 13s linear infinite; }
            .gradient-border-reverse { --gb-gradient: linear-gradient(120deg, var(--gb-a), var(--gb-b), var(--gb-c), var(--gb-a)); --gb-animation: gradient-border-reverse-spin 36s linear infinite; }
            .gradient-border-sonar { --gb-gradient: linear-gradient(90deg, transparent, var(--gb-a), var(--gb-b), transparent); --gb-size: 240% 100%; --gb-animation: gradient-border-sonar-sweep 15s linear infinite; }
            .gradient-border-overload { --gb-gradient: repeating-linear-gradient(115deg, var(--gb-a) 0 8px, var(--gb-b) 8px 16px, var(--gb-c) 16px 24px, var(--gb-d) 24px 32px); --gb-size: 420% 420%; --gb-animation: gradient-border-rotate 1.7s linear infinite; }
            .gradient-border-nebula { --gb-gradient: radial-gradient(circle at 20% 20%, var(--gb-a), transparent 32%), radial-gradient(circle at 70% 25%, var(--gb-b), transparent 36%), radial-gradient(circle at 50% 80%, var(--gb-c), transparent 42%), linear-gradient(120deg, var(--gb-d), var(--gb-a)); --gb-size: 240% 240%; --gb-animation: gradient-border-rotate 18s ease infinite; }
            .gradient-border-abyss { --gb-gradient: linear-gradient(135deg, rgba(9,14,28,0.85), var(--gb-a), rgba(25,20,60,0.9), var(--gb-b)); --gb-animation: gradient-border-reverse-spin 22s ease infinite; }
            .gradient-border-uncommon { --gb-a: #7ee787; --gb-b: #34d399; --gb-c: #58a6ff; --gb-d: #d1fae5; }
            .gradient-border-rare { --gb-a: #58a6ff; --gb-b: #22d3ee; --gb-c: #a5b4fc; --gb-d: #e0f2fe; }
            .gradient-border-epic { --gb-a: #a78bfa; --gb-b: #f778ba; --gb-c: #c084fc; --gb-d: #f0abfc; }
            .gradient-border-legendary { --gb-a: #facc15; --gb-b: #fb923c; --gb-c: #f778ba; --gb-d: #fff7ed; }
            .gradient-border-best { --gb-a: #ffffff; --gb-b: #facc15; --gb-c: #58a6ff; --gb-d: #f778ba; }
            :root {
                --ao3-bg: #0d1117;
                --ao3-panel: #161b22;
                --ao3-border: #30363d;
                --ao3-text: #e6edf3;
                --ao3-muted: #8b949e;
                --ao3-blue: #58a6ff;
                --ao3-green: #7ee787;
                --ao3-pink: #f778ba;
                --ao3-amber: #facc15;
            }
            body, .q-page, .nicegui-content {
                margin: 0 !important;
                padding: 0 !important;
                background: var(--ao3-bg);
                color: var(--ao3-text);
                font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
                min-height: 100vh;
            }
            pre, code, textarea, input {
                font-family: "Fira Code", ui-monospace, SFMono-Regular, monospace !important;
            }
            .q-btn { text-transform: none !important; }
            .main-content {
                height: 100vh;
                width: 100%;
                overflow: hidden;
                background:
                    radial-gradient(circle at 24% 0%, rgba(88, 166, 255, 0.14), transparent 31%),
                    radial-gradient(circle at 88% 12%, rgba(247, 120, 186, 0.10), transparent 28%),
                    #0d1117;
            }
            .top-bar {
                background: linear-gradient(145deg, rgba(22, 27, 34, 0.96), rgba(13, 17, 23, 0.92));
                border-bottom: 1px solid var(--ao3-border);
                min-height: 52px;
            }
            .center-tab-strip {
                position: relative;
                height: 34px;
                min-height: 34px;
                background: linear-gradient(180deg, rgba(22, 27, 34, 0.96), rgba(13, 17, 23, 0.92));
                border-bottom: 1px solid var(--ao3-border);
                box-shadow: inset 0 -1px 0 rgba(88, 166, 255, 0.05);
            }
            .center-toolbar-left,
            .center-toolbar-right,
            .workspace-tab-rail-centered {
                position: absolute;
                top: 0;
                height: 34px;
                min-height: 34px;
            }
            .center-toolbar-left {
                left: 4px;
                z-index: 2;
                max-width: calc(50% - 260px);
            }
            .center-toolbar-right {
                right: 4px;
                z-index: 2;
                max-width: calc(50% - 260px);
            }
            .workspace-tab-rail-centered {
                left: 50%;
                transform: translateX(-50%);
                z-index: 1;
            }
            .workspace-tab-rail {
                height: 34px;
                min-height: 34px;
            }
            .workspace-tab {
                border-radius: 0 !important;
                color: #8b949e !important;
                border: 0 !important;
                border-right: 1px solid rgba(48, 54, 61, 0.56) !important;
                border-bottom: 2px solid transparent !important;
                background: transparent !important;
                height: 34px !important;
                min-height: 34px !important;
                padding: 0 13px !important;
                margin: 0 !important;
                box-shadow: none !important;
            }
            .workspace-tab:hover {
                background: rgba(88, 166, 255, 0.10) !important;
                color: #c7d2fe !important;
            }
            .workspace-tab-active {
                background: rgba(88, 166, 255, 0.13) !important;
                color: #dbeafe !important;
                border-bottom-color: rgba(88, 166, 255, 0.80) !important;
                box-shadow: inset 0 1px 0 rgba(88, 166, 255, 0.15) !important;
            }
            .top-action-button {
                min-height: 30px !important;
                height: 30px !important;
                min-width: 30px !important;
            }
            .top-action-button .q-icon,
            .work-action-button .q-icon {
                font-size: 22px !important;
            }
            .action-separator {
                color: rgba(148, 163, 184, 0.58);
                font-size: 15px;
                line-height: 1;
                padding: 0 2px;
                user-select: none;
            }
            .center-mode-select .q-field__control {
                min-height: 28px !important;
                height: 28px !important;
                padding: 0 4px !important;
            }
            .center-mode-select .q-field__native,
            .center-mode-select .q-field__append {
                min-height: 28px !important;
                height: 28px !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
            }
            .panel-bg {
                background: rgba(13, 17, 23, 0.84);
            }
            .right-panel-header-strip {
                position: relative;
                height: 34px;
                min-height: 34px;
                padding: 0 4px;
                box-sizing: border-box;
                background: linear-gradient(180deg, rgba(22, 27, 34, 0.96), rgba(13, 17, 23, 0.92));
                border-bottom: 1px solid var(--ao3-border);
                box-shadow: inset 0 -1px 0 rgba(88, 166, 255, 0.05);
            }
            .right-panel-header-hit {
                height: 100%;
                min-height: 100%;
            }
            .soft-panel {
                background: linear-gradient(155deg, rgba(22, 27, 34, 0.94), rgba(13, 17, 23, 0.76));
                border: 1px solid var(--ao3-border);
                border-radius: 8px;
            }
            .right-panel-scroll .q-scrollarea__content,
            .right-panel-scroll .q-scrollarea__content > div {
                width: 100% !important;
                min-width: 100% !important;
                max-width: none !important;
                min-height: 100% !important;
                padding: 0 !important;
                box-sizing: border-box !important;
            }
            .right-panel-column {
                width: 100% !important;
                min-width: 100% !important;
                max-width: none !important;
                min-height: 100% !important;
                align-items: stretch !important;
                box-sizing: border-box !important;
            }
            .right-panel-column > * {
                width: 100% !important;
                max-width: none !important;
                align-self: stretch !important;
                box-sizing: border-box !important;
            }
            .right-panel-column.right-panel-batch-mode {
                flex: 1 1 auto !important;
                height: 100% !important;
                min-height: 100% !important;
                gap: 0 !important;
                padding: 0 !important;
                justify-content: flex-start !important;
            }
            .right-panel-cleanup-host {
                position: relative;
                display: flex;
                flex-direction: column;
                flex: 1 1 auto;
                height: 100%;
                min-height: 100%;
                margin: 0 !important;
                padding: 0 !important;
            }
            .right-panel-cleanup-content {
                flex: 1 1 auto;
                height: 100%;
                min-height: 0;
                margin: 0 !important;
                padding: 4px 12px 12px !important;
                box-sizing: border-box;
                justify-content: flex-start !important;
            }
            .right-panel-batch-mode .cluster-pill-row,
            .right-panel-batch-mode .schema-slot-row {
                margin-top: 0 !important;
                padding-top: 0 !important;
                min-height: 0 !important;
            }
            .right-panel-search {
                width: 100% !important;
                max-width: none !important;
                align-self: stretch !important;
                box-sizing: border-box !important;
            }
            .right-panel-control-row {
                display: grid;
                width: 100%;
                align-items: center;
                gap: 8px;
            }
            .right-panel-two-icon-grid {
                grid-template-columns: minmax(0, 1fr) 32px 32px;
            }
            .right-panel-three-icon-grid {
                grid-template-columns: minmax(0, 1fr) 32px 32px 32px;
            }
            .right-panel-reader-grid {
                grid-template-columns: 20px 20px minmax(0, 1fr) 20px;
                gap: 7px;
            }
            .right-panel-main-field {
                width: 100% !important;
                min-width: 0 !important;
                max-width: none !important;
                justify-self: stretch !important;
            }
            .right-panel-main-field.q-field,
            .right-panel-main-field .q-field,
            .right-panel-search .q-field {
                width: 100% !important;
                min-width: 0 !important;
                max-width: none !important;
            }
            .right-panel-icon-button {
                width: 32px !important;
                min-width: 32px !important;
                height: 32px !important;
                min-height: 32px !important;
                padding: 0 !important;
                justify-self: center !important;
            }
            .right-panel-icon-spacer {
                width: 32px;
                height: 32px;
            }
            .right-panel-search > .nicegui-row {
                width: 100% !important;
                flex-wrap: nowrap !important;
            }
            .right-panel-search .q-field__control {
                min-height: 44px !important;
            }
            .right-panel-search .q-btn {
                flex: 0 0 auto;
            }
            .reader-side-icon {
                width: 20px !important;
                min-width: 20px !important;
                height: 28px !important;
                min-height: 28px !important;
                padding: 0 !important;
                justify-self: center !important;
            }
            .reader-side-icon .q-icon {
                font-size: 19px !important;
            }
            .work-card {
                background: linear-gradient(135deg, rgba(88, 166, 255, 0.11), rgba(22, 27, 34, 0.94) 42%, rgba(126, 231, 135, 0.055));
                border: 1px solid rgba(88, 166, 255, 0.24);
                border-radius: 8px;
                transition: border-color 0.12s ease, filter 0.12s ease, box-shadow 0.16s ease;
                max-width: 100%;
                overflow: hidden;
                scroll-margin: 10px;
            }
            .work-card,
            .work-card * {
                min-width: 0;
            }
            .work-card:hover {
                border-color: rgba(88, 166, 255, 0.55);
                filter: brightness(1.04);
            }
            .work-card-clickable {
                cursor: pointer;
            }
            .work-card-actions {
                position: absolute;
                top: 8px;
                right: 8px;
                z-index: 30;
                background: rgba(13, 17, 23, 0.48);
                border: 1px solid rgba(48, 54, 61, 0.52);
                border-radius: 999px;
                backdrop-filter: blur(8px);
                pointer-events: auto;
            }
            .work-card-actions .q-btn,
            .work-action-button {
                pointer-events: auto;
            }
            .work-card-body {
                position: relative;
                z-index: 2;
                padding-right: 132px;
                width: 100%;
            }
            .inline-work-panel {
                position: relative;
                height: 0;
                opacity: 1;
                overflow: hidden;
                transform-origin: top;
                will-change: height;
                pointer-events: none;
            }
            .work-card-expanded > .inline-work-panel {
                opacity: 1;
                pointer-events: auto;
            }
            .inline-work-panel-inner {
                position: relative;
                z-index: 2;
                min-height: 0;
                overflow: visible;
                opacity: 1;
                filter: none;
                clip-path: inset(0 0 0 0);
                will-change: opacity, filter, clip-path;
            }
            .inline-work-panel-pending {
                pointer-events: none;
            }
            .inline-work-panel-closing {
                pointer-events: none;
            }
            .blocked-pill,
            .blocked-nested-work {
                width: fit-content;
                max-width: 100%;
                min-height: 23px;
                padding: 1px 7px !important;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 400;
                cursor: pointer;
                transition: filter 0.14s ease, border-color 0.14s ease, background 0.14s ease;
            }
            .blocked-pill:hover,
            .blocked-nested-work:hover {
                filter: brightness(1.12);
            }
            .blocked-nested-work {
                border-radius: 8px;
            }
            .blocked-tag-restore-pill {
                min-height: 24px !important;
                padding: 1px 7px !important;
                font-size: 11px !important;
            }
            .blocked-expanded-card {
                cursor: pointer;
                box-shadow: 0 0 0 1px rgba(0,0,0,0.28);
            }
            .blocked-expanded-title {
                min-height: 28px;
                height: 28px;
                line-height: 28px;
                font-size: 13px;
                font-weight: 700;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .blocked-expanded-text {
                width: 100%;
                margin-top: 4px;
                padding: 4px 8px;
                border: 1px solid rgba(48, 54, 61, 0.82);
                border-radius: 6px;
                color: #94a3b8;
                font-size: 12px;
                line-height: 1.35;
                background: rgba(13, 17, 23, 0.52);
                overflow-wrap: anywhere;
            }
            .blocked-expanded-work {
                padding: 4px 6px;
                border: 1px solid rgba(48, 54, 61, 0.72);
                border-radius: 6px;
                background: rgba(13, 17, 23, 0.46);
            }
            .work-title,
            .work-summary,
            .work-meta-line,
            .category-designation {
                white-space: normal !important;
                overflow-wrap: anywhere;
                word-break: normal;
            }
            .category-designation-char {
                line-height: 1;
                font-size: 12px;
                font-weight: 700;
            }
            .work-meta-date {
                display: inline-block;
                min-width: 88px;
                white-space: nowrap !important;
            }
            .evaluation-notes-field {
                border-radius: 7px;
                margin-top: 9px;
                background:
                    radial-gradient(circle at 14% 0%, rgba(var(--note-r), var(--note-g), var(--note-b), 0.105), transparent 42%),
                    linear-gradient(135deg, rgba(var(--note-r), var(--note-g), var(--note-b), 0.052), rgba(13, 17, 23, 0.67) 54%, rgba(var(--note-r), var(--note-g), var(--note-b), 0.035));
            }
            .evaluation-notes-field .q-field__control,
            .evaluation-notes-field .q-field__control::before,
            .evaluation-notes-field .q-field__control::after {
                border: 0 !important;
                box-shadow: none !important;
                outline: 0 !important;
                background: transparent !important;
            }
            .evaluation-notes-field .q-field__control {
                min-height: 62px !important;
                padding: 3px 7px 4px 7px !important;
            }
            .evaluation-notes-field textarea {
                color: #dbeafe !important;
                min-height: 58px !important;
                line-height: 1.35 !important;
                padding: 2px 1px !important;
            }
            .evaluation-notes-field .q-field__label {
                color: rgba(var(--note-r), var(--note-g), var(--note-b), 0.86) !important;
            }
            .filter-suggestion-row {
                padding-top: 6px;
            }
            .filter-suggestion-pill {
                max-width: 100%;
                min-height: 24px !important;
                height: 24px !important;
                padding: 0 8px !important;
                font-size: 11px !important;
            }
            .filter-suggestion-pill .q-btn__content {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .reader-top-muted {
                color: #8b949e;
                font-weight: 400 !important;
                white-space: nowrap;
            }
            .reader-top-accent,
            .reader-top-chapter {
                font-weight: 400 !important;
                max-width: 300px;
                min-width: 0;
            }
            .reader-title-link {
                cursor: pointer;
            }
            .reader-title-link:hover {
                filter: brightness(1.24);
                text-decoration: underline;
                text-underline-offset: 3px;
            }
            .reader-stage {
                height: 100%;
                min-height: 0;
                overflow: hidden;
                background:
                    radial-gradient(circle at 18% 0%, rgba(88, 166, 255, 0.09), transparent 30%),
                    radial-gradient(circle at 92% 9%, rgba(247, 120, 186, 0.07), transparent 24%),
                    #0d1117;
            }
            .reader-toolbar {
                background: #161b22;
                border-bottom: 1px solid #30363d;
                min-height: 42px;
            }
            .reader-status-row {
                background: #0d1117;
                border-bottom: 1px solid #21262d;
                min-height: 28px;
            }
            .reader-vertical-rule {
                width: 1px;
                height: 24px;
                margin: 0 8px;
                background: #30363d;
            }
            .reader-toolbar-title {
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 700;
                min-width: 0;
            }
            .reader-chapter-select {
                min-width: 220px;
                max-width: 42vw;
            }
            .reader-chapter-select .q-field__control {
                min-height: 30px !important;
                height: 30px !important;
                background: rgba(13, 17, 23, 0.58) !important;
            }
            .reader-panels-container {
                display: flex;
                gap: 0;
                overflow: hidden;
                padding: 0;
            }
            .reader-panel {
                min-width: 0;
            }
            .reader-border-container {
                min-height: 0;
                border-radius: 0 !important;
            }
            .reader-panel-scroll {
                background: #0d1117;
            }
            .reader-html-root {
                width: 100%;
                min-height: 100%;
                box-sizing: border-box;
            }
            .reader-prose {
                line-height: 1.82;
                font-family: "Fira Code", ui-monospace, SFMono-Regular, monospace;
                font-size: 16px;
                color: #d7dee8;
                background: #161b22;
                border-radius: 8px;
                box-sizing: border-box;
                min-height: 100%;
                width: 100%;
                padding: 16px;
                max-width: none;
            }
            .reader-prose p,
            .reader-prose blockquote,
            .reader-prose div {
                padding: 2px 8px;
                margin: 0 0 14px;
                max-width: none;
                white-space: normal;
                overflow-wrap: anywhere;
            }
            .reader-prose p:last-child,
            .reader-prose blockquote:last-child,
            .reader-prose div:last-child {
                margin-bottom: 0 !important;
            }
            .reader-prose blockquote {
                padding: 8px 12px;
                background: rgba(251, 191, 36, 0.08);
                border-left: 3px solid rgba(251, 191, 36, 0.74);
                border-radius: 0 4px 4px 0;
            }
            .reader-prose strong,
            .reader-prose b {
                color: inherit;
                font-weight: 700;
            }
            .reader-prose em,
            .reader-prose i {
                color: inherit;
                font-style: italic;
            }
            .reader-prose a {
                color: #93c5fd;
            }
            .work-tag-pill {
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: normal;
                overflow-wrap: anywhere;
                min-height: 24px !important;
                padding: 2px 8px !important;
            }
            .browse-tag-pill {
                appearance: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 999px;
                cursor: pointer;
                font: inherit;
                line-height: 1.2;
            }
            .cluster-pill {
                transition: filter 0.14s ease, border-color 0.14s ease, background 0.14s ease;
            }
            .cluster-pill:hover {
                filter: brightness(1.14);
            }
            .cluster-pill:active {
                filter: brightness(1.04);
            }
            .browse-tag-pill-label {
                display: block;
                max-width: 100%;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .reader-character-pill-row {
                align-content: flex-start;
            }
            .reader-character-pill {
                gap: 6px;
                justify-content: flex-start;
                min-height: 28px !important;
                padding: 2px 8px 2px 3px !important;
                transition: filter 0.14s ease, border-color 0.14s ease, background 0.14s ease;
            }
            .reader-character-pill:hover {
                filter: brightness(1.14);
            }
            .reader-character-pill-label {
                min-width: 0;
                max-width: calc(100% - 32px);
                white-space: nowrap;
            }
            .tag-type-label {
                color: #64748b;
                font-size: 10px;
                font-weight: 700;
                min-width: 72px;
                text-transform: uppercase;
                letter-spacing: 0;
            }
            .tag-favorite-menu {
                background: rgba(22, 27, 34, 0.98) !important;
                border: 1px solid rgba(48, 54, 61, 0.95) !important;
                border-radius: 8px !important;
            }
            .score-pill {
                border-radius: 7px;
                min-width: 150px;
            }
            .filter-expansion .q-expansion-item__container,
            .filter-expansion-nested .q-expansion-item__container {
                background: transparent !important;
                margin: 0 !important;
            }
            .filter-expansion .q-item,
            .filter-expansion-nested .q-item {
                min-height: 24px !important;
                padding: 0 2px !important;
            }
            .filter-expansion .q-item__label,
            .filter-expansion .q-item__section--avatar .q-icon,
            .filter-expansion .q-item__section--side .q-icon,
            .filter-expansion-nested .q-item__label,
            .filter-expansion-nested .q-item__section--avatar .q-icon,
            .filter-expansion-nested .q-item__section--side .q-icon {
                color: var(--filter-group-color, #58a6ff) !important;
            }
            .filter-expansion .q-focus-helper,
            .filter-expansion-nested .q-focus-helper {
                background: color-mix(in srgb, var(--filter-group-color, #58a6ff) 18%, transparent) !important;
            }
            .filter-expansion .q-expansion-item__content,
            .filter-expansion-nested .q-expansion-item__content {
                padding: 0 !important;
            }
            .filter-expansion .nicegui-expansion-content,
            .filter-expansion-nested .nicegui-expansion-content {
                width: 100% !important;
                padding: 0 !important;
                gap: 2px !important;
                box-sizing: border-box;
            }
            .filter-expansion {
                border-top: 1px solid rgba(48, 54, 61, 0.34);
                margin: 0 !important;
            }
            .filter-expansion-nested {
                border-left: 2px solid color-mix(in srgb, var(--filter-group-color, #58a6ff) 42%, transparent);
                padding-left: 3px;
                margin: 0 !important;
            }
            .filter-expansion-nested + .filter-expansion-nested {
                margin-top: 2px !important;
            }
            .filter-expansion .q-expansion-item__content > .nicegui-column,
            .filter-expansion-nested .q-expansion-item__content > .nicegui-column {
                gap: 2px !important;
            }
            .filter-option-row {
                width: 100% !important;
                flex-wrap: nowrap !important;
                min-height: 22px;
                margin: 0 0 2px 0;
                padding: 0 1px;
                border-radius: 6px;
                background: linear-gradient(90deg, color-mix(in srgb, var(--filter-group-color, #58a6ff) 8%, transparent), transparent);
            }
            .filter-option-row .q-checkbox__label {
                line-height: 1.15 !important;
                padding-left: 2px !important;
            }
            .filter-option-checkbox {
                min-height: 24px !important;
                height: auto !important;
                flex: 1 1 auto;
                min-width: 0;
            }
            .filter-option-checkbox .q-checkbox__inner {
                width: 24px !important;
                min-width: 24px !important;
                height: 24px !important;
                font-size: 22px !important;
            }
            .filter-option-checkbox .q-checkbox__label {
                min-width: 0;
                overflow-wrap: anywhere;
            }
            .filter-option-star {
                width: 22px !important;
                min-width: 22px !important;
                height: 22px !important;
                min-height: 22px !important;
            }
            .filter-favorite-strip {
                padding: 1px 0 3px;
                border-bottom: 1px solid rgba(48, 54, 61, 0.32);
            }
            .filter-favorite-pill,
            .filter-suggestion-pill,
            .filter-tag-pill {
                min-height: 24px !important;
                padding: 1px 7px !important;
                font-size: 11px !important;
            }
            .filter-tag-input {
                padding: 1px 0;
            }
            .filter-tag-box {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: 4px;
                min-height: 34px;
                padding: 4px 6px;
                border: 1px solid color-mix(in srgb, var(--filter-group-color, #58a6ff) 28%, #30363d);
                border-radius: 7px;
                background: rgba(7, 11, 18, 0.46);
            }
            .filter-tag-box-label {
                color: color-mix(in srgb, var(--filter-group-color, #58a6ff) 74%, #d1d5db);
                font-size: 10px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0;
            }
            .filter-tag-catalog-count {
                color: #64748b;
                font-size: 10px;
            }
            .filter-selected-tag-chip {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                max-width: 100%;
                min-height: 24px;
                padding: 0 4px 0 2px;
                border: 1px solid rgba(88, 166, 255, 0.34);
                border-radius: 999px;
                line-height: 1;
            }
            .filter-selected-tag-label {
                max-width: min(270px, 100%);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: 11px;
                line-height: 1.1;
            }
            .filter-chip-star,
            .filter-chip-close {
                width: 20px !important;
                min-width: 20px !important;
                height: 20px !important;
                min-height: 20px !important;
            }
            .filter-tag-entry {
                flex: 1 1 150px;
                min-width: 120px;
            }
            .filter-tag-entry .q-field__control {
                min-height: 24px !important;
                height: 24px !important;
                padding: 0 !important;
            }
            .filter-tag-entry .q-field__native {
                min-height: 22px !important;
                padding: 0 !important;
                color: #d1d5db !important;
            }
            .filter-two-col-row {
                flex-wrap: nowrap;
            }
            .filter-half-field {
                flex: 1 1 0;
                min-width: 0;
            }
            .date-popover .q-date,
            .date-popover .q-time {
                background: transparent !important;
                color: #e6edf3 !important;
                box-shadow: none !important;
            }
            .date-popover .q-date__header,
            .date-popover .q-time__header {
                background: linear-gradient(135deg, rgba(var(--field-r), var(--field-g), var(--field-b), 0.32), rgba(var(--field-r), var(--field-g), var(--field-b), 0.12)) !important;
                color: #f8fafc !important;
                border-radius: 7px;
            }
            .date-popover .q-date__calendar-item--selected,
            .date-popover .q-date__calendar-item--in {
                background: rgba(var(--field-r), var(--field-g), var(--field-b), 0.16) !important;
                color: #f8fafc !important;
            }
            .date-popover .q-date__calendar-item--selected .q-btn,
            .date-popover .q-date__calendar-item--selected .q-btn:before,
            .date-popover .q-date__calendar-item--selected .q-btn__content,
            .date-popover .q-date__calendar-item--today .q-btn,
            .date-popover .q-date__calendar-item--today .q-btn:before {
                border-color: rgba(var(--field-r), var(--field-g), var(--field-b), 0.58) !important;
                background: radial-gradient(circle at 35% 30%, rgba(255,255,255,0.20), rgba(var(--field-r), var(--field-g), var(--field-b), 0.26) 42%, rgba(var(--field-r), var(--field-g), var(--field-b), 0.10) 72%) !important;
                color: #f8fafc !important;
            }
            .date-popover .q-date__calendar-item--selected .q-btn {
                box-shadow: 0 0 0 1px rgba(var(--field-r), var(--field-g), var(--field-b), 0.72), 0 0 8px rgba(var(--field-r), var(--field-g), var(--field-b), 0.24) !important;
            }
            .date-popover .bg-primary,
            .date-popover .q-btn.bg-primary,
            .date-popover .q-btn--standard.bg-primary,
            .body--dark .date-popover .q-date button.q-btn.bg-primary,
            .date-popover .q-date button.q-btn.q-btn-item.bg-primary {
                background: var(--date-selected-bg) !important;
                background-color: rgba(var(--field-r), var(--field-g), var(--field-b), 0.20) !important;
                background-image: var(--date-selected-bg) !important;
                color: #f8fafc !important;
                box-shadow: 0 0 0 1px rgba(var(--field-r), var(--field-g), var(--field-b), 0.78), 0 0 8px rgba(var(--field-r), var(--field-g), var(--field-b), 0.24) !important;
            }
            .date-popover .text-primary {
                color: rgb(var(--field-r), var(--field-g), var(--field-b)) !important;
            }
            .date-field-input .date-field-action {
                opacity: 0.82;
                transition: color 0.12s ease, opacity 0.12s ease, transform 0.12s ease;
            }
            .date-field-input .date-field-action:hover {
                opacity: 1;
                transform: translateY(-1px);
            }
            .filter-language-row .q-btn {
                min-height: 22px !important;
                padding: 1px 7px !important;
                font-size: 11px !important;
            }
            .filter-sort-row .q-btn,
            .filter-segmented-row .q-btn,
            .filter-page-direction-row .q-btn {
                min-height: 22px !important;
                padding: 1px 7px !important;
                font-size: 11px !important;
            }
            .filter-sort-row {
                margin-bottom: 8px !important;
            }
            .cluster-filter-segmented-row {
                margin-bottom: 8px !important;
            }
            .filter-page-row {
                margin-bottom: 8px !important;
            }
            .filter-page-row .q-field__control {
                min-height: 31px !important;
                height: 31px !important;
            }
            .filter-page-input {
                width: 92px !important;
            }
            .filter-page-input .q-field__control {
                min-height: 34px !important;
                height: 34px !important;
                overflow: hidden;
                position: relative;
                padding-right: 22px !important;
            }
            .filter-page-input .q-field__native {
                padding-right: 2px !important;
            }
            .filter-page-input .q-field__append {
                position: absolute !important;
                right: 0 !important;
                top: 0 !important;
                bottom: 0 !important;
                align-self: stretch !important;
                height: 34px !important;
                min-height: 34px !important;
                width: 22px !important;
                min-width: 22px !important;
                padding: 0 !important;
                margin: 0 !important;
                border-left: 1px solid rgba(148, 163, 184, 0.20);
                background: rgba(148, 163, 184, 0.08);
            }
            .filter-page-spinner {
                width: 22px !important;
                height: 34px !important;
                justify-content: center;
                align-items: center;
            }
            .filter-page-spinner .q-btn {
                width: 20px !important;
                min-width: 20px !important;
                height: 15px !important;
                min-height: 15px !important;
                padding: 0 !important;
                color: #94a3b8 !important;
            }
            .filter-page-spinner .q-icon {
                font-size: 16px !important;
                line-height: 1 !important;
            }
            .queue-card-cleanup-selected {
                border-color: rgba(239, 68, 68, 0.82) !important;
                box-shadow: 0 0 14px rgba(239, 68, 68, 0.24);
            }
            .fandom-row {
                border: 1px solid transparent;
                border-radius: 7px;
                transition: background 0.15s ease, border 0.15s ease, filter 0.15s ease;
            }
            .fandom-row:hover {
                background: rgba(48, 54, 61, 0.55);
                filter: brightness(1.08);
            }
            .fandom-row-selected {
                background: linear-gradient(135deg, rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.22), rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.07));
                border-left: 2px solid rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.72);
            }
            .fandom-avatar {
                width: 34px;
                height: 34px;
                border-radius: 7px;
                background-size: cover;
                background-position: center;
                border: 1px solid rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.44);
                box-shadow: 0 0 10px rgba(var(--accent-r), var(--accent-g), var(--accent-b), 0.18);
            }
            .nav-button-active {
                background: rgba(88, 166, 255, 0.18) !important;
                color: #dbeafe !important;
                border-left: 2px solid var(--ao3-blue);
            }
            .status-local {
                color: #7ee787;
                border: 1px solid rgba(126, 231, 135, 0.34);
                background: rgba(126, 231, 135, 0.10);
                border-radius: 999px;
            }
            .status-shared {
                color: #facc15;
                border: 1px solid rgba(250, 204, 21, 0.36);
                background: rgba(250, 204, 21, 0.10);
                border-radius: 999px;
            }
            .q-card {
                background: #161b22 !important;
                border: 1px solid #30363d !important;
                border-radius: 8px !important;
            }
            .q-splitter__separator {
                background: #30363d !important;
            }
            .q-splitter__separator:hover {
                background: #58a6ff !important;
            }
            .q-splitter__panel {
                min-width: 0 !important;
                overflow: hidden;
            }
            .nicegui-scroll-area,
            .q-scrollarea__container,
            .q-scrollarea__content {
                min-width: 0 !important;
                max-width: 100% !important;
            }
            .q-checkbox__label {
                white-space: normal !important;
                overflow-wrap: anywhere;
                line-height: 1.25;
            }
            .q-field__native,
            .q-field__input {
                min-width: 0 !important;
            }
            .schema-footer-btn {
                min-width: 112px !important;
                padding-left: 10px !important;
                padding-right: 10px !important;
            }
            .schema-footer-save {
                min-width: 82px !important;
                padding-left: 10px !important;
                padding-right: 10px !important;
            }
            .schema-editor-scroll .q-scrollarea__content {
                width: 100% !important;
                min-width: 100% !important;
            }
            .schema-editor-body,
            .schema-editor-body .q-field,
            .schema-editor-body .q-textarea,
            .schema-editor-body .q-input {
                width: 100% !important;
                max-width: 100% !important;
            }
            .schema-prompt-editor textarea {
                min-height: 360px !important;
            }
            @property --gradient-angle {
                syntax: '<angle>';
                initial-value: 0deg;
                inherits: false;
            }
            @property --overload-1 { syntax: '<angle>'; inherits: false; initial-value: 0deg; }
            @property --overload-2 { syntax: '<angle>'; inherits: false; initial-value: 90deg; }
            @property --overload-3 { syntax: '<angle>'; inherits: false; initial-value: 180deg; }
            @property --overload-4 { syntax: '<angle>'; inherits: false; initial-value: 45deg; }
            @property --nebula-ccw { syntax: '<angle>'; inherits: false; initial-value: 360deg; }
            @property --abyss-slow { syntax: '<angle>'; inherits: false; initial-value: 0deg; }
            @property --abyss-fast { syntax: '<angle>'; inherits: false; initial-value: 90deg; }
            @keyframes ao3-gradient-border-rotate {
                0% { --gradient-angle: 0deg; }
                100% { --gradient-angle: 360deg; }
            }
            @keyframes ao3-glow-breathe {
                0%, 28.6%, 100% {
                    box-shadow: 0 0 1px rgba(0,0,0,1), 0 1px 2px rgba(0,0,0,0.9),
                                0 0 4px rgba(0,0,0,0.7),
                                0 0 3px var(--gb-glow, rgba(90,53,124,0.15));
                }
                52.4%, 81% {
                    box-shadow: 0 0 1px rgba(0,0,0,1), 0 1px 2px rgba(0,0,0,0.9),
                                0 0 5px rgba(0,0,0,0.6),
                                0 0 10px var(--gb-glow, rgba(90,53,124,0.55)),
                                0 0 16px var(--gb-glow-soft, rgba(90,53,124,0.15));
                }
            }
            @keyframes ao3-gradient-border-pulse {
                0% { --gradient-angle: 0deg; }
                100% { --gradient-angle: 360deg; }
            }
            @keyframes ao3-gradient-border-reverse-spin {
                0% { --gradient-angle: 0deg; animation-timing-function: ease-in-out; }
                35% { --gradient-angle: 360deg; animation-timing-function: cubic-bezier(0.85, 0, 0.15, 1); }
                70% { --gradient-angle: -360deg; animation-timing-function: ease-in-out; }
                100% { --gradient-angle: 0deg; }
            }
            @keyframes ao3-gradient-border-sonar-sweep {
                0% { --gradient-angle: 0deg; }
                100% { --gradient-angle: 360deg; }
            }
            @keyframes ao3-o-drift-1 { 0% { --overload-1: 0deg; } 100% { --overload-1: 360deg; } }
            @keyframes ao3-o-drift-2 { 0% { --overload-2: 90deg; } 100% { --overload-2: -270deg; } }
            @keyframes ao3-o-drift-3 { 0% { --overload-3: 180deg; } 100% { --overload-3: 540deg; } }
            @keyframes ao3-o-drift-4 { 0% { --overload-4: 45deg; } 100% { --overload-4: 405deg; } }
            @keyframes ao3-nebula-drift-cw { 0% { --gradient-angle: 0deg; } 100% { --gradient-angle: 360deg; } }
            @keyframes ao3-nebula-drift-ccw { 0% { --nebula-ccw: 360deg; } 100% { --nebula-ccw: 0deg; } }
            @keyframes ao3-abyss-flow-slow { 0% { --abyss-slow: 0deg; } 100% { --abyss-slow: 360deg; } }
            @keyframes ao3-abyss-flow-fast { 0% { --abyss-fast: 90deg; } 100% { --abyss-fast: 450deg; } }
            .gradient-border::before {
                display: none !important;
            }
            .gradient-border {
                border: var(--gb-thickness, 1.4px) solid transparent !important;
                border-radius: 8px;
                background-origin: border-box !important;
                animation: ao3-gradient-border-rotate 8s linear infinite,
                           ao3-glow-breathe 10.5s ease-in-out infinite;
            }
            .gradient-border-single {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), var(--gb-base) 0%, var(--gb-mid) 4%, var(--gb-peak) 7.5%, var(--gb-mid) 11%, var(--gb-base) 15%, var(--gb-base) 100%) border-box !important;
            }
            .gradient-border-twin {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), var(--gb-base) 0%, var(--gb-mid) 2.5%, var(--gb-peak) 5%, var(--gb-mid) 7.5%, var(--gb-base) 10%, var(--gb-base) 50%, var(--gb-mid) 52.5%, var(--gb-peak) 55%, var(--gb-mid) 57.5%, var(--gb-base) 60%, var(--gb-base) 100%) border-box !important;
            }
            .gradient-border-duotone {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), var(--gb-base) 0%, var(--gb-mid) 2.5%, var(--gb-peak) 5%, var(--gb-mid) 7.5%, var(--gb-base) 10%, var(--gb-base) 50%, var(--gb-mid2, var(--gb-mid)) 52.5%, var(--gb-peak2, var(--gb-peak)) 55%, var(--gb-mid2, var(--gb-mid)) 57.5%, var(--gb-base) 60%, var(--gb-base) 100%) border-box !important;
            }
            .gradient-border-tritone {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), var(--gb-base) 0%, var(--gb-mid) 2.5%, var(--gb-peak) 5%, var(--gb-mid) 7.5%, var(--gb-base) 10%, var(--gb-base) 33.33%, var(--gb-mid2, var(--gb-mid)) 35.83%, var(--gb-peak2, var(--gb-peak)) 38.33%, var(--gb-mid2, var(--gb-mid)) 40.83%, var(--gb-base) 43.33%, var(--gb-base) 66.66%, var(--gb-mid3, var(--gb-mid)) 69.16%, var(--gb-peak3, var(--gb-peak)) 71.66%, var(--gb-mid3, var(--gb-mid)) 74.16%, var(--gb-base) 76.66%, var(--gb-base) 100%) border-box !important;
                animation: ao3-gradient-border-rotate 9s linear infinite,
                           ao3-glow-breathe 10.5s ease-in-out infinite !important;
            }
            .gradient-border-clash,
            .gradient-border-glitch,
            .gradient-border-wildcard,
            .gradient-border-ignition {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), #000000 0%, var(--gb-mid) 2.5%, var(--gb-peak) 5%, var(--gb-mid) 7.5%, #000000 10%, #000000 50%, var(--gb-mid2, var(--gb-mid)) 52.5%, var(--gb-peak2, var(--gb-peak)) 55%, var(--gb-mid2, var(--gb-mid)) 57.5%, #000000 60%, #000000 100%) border-box,
                    conic-gradient(from calc(360deg - var(--gradient-angle, 0deg)), var(--gb-base) 0%, var(--gb-mid2, var(--gb-mid)) 2.5%, var(--gb-peak2, var(--gb-peak)) 5%, var(--gb-mid2, var(--gb-mid)) 7.5%, var(--gb-base) 10%, var(--gb-base) 50%, var(--gb-mid) 52.5%, var(--gb-peak) 55%, var(--gb-mid) 57.5%, var(--gb-base) 60%, var(--gb-base) 100%) border-box !important;
                background-blend-mode: normal, screen, normal;
                background-repeat: no-repeat;
                background-clip: padding-box, border-box, border-box;
            }
            .gradient-border-traffic,
            .gradient-border-overload {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--overload-1, 0deg), #000000 0%, #000000 20%, var(--gb-peak) 21%, #000000 22%, #000000 50%, var(--gb-mid) 51%, #000000 52%, #000000 80%, var(--gb-peak) 81%, #000000 82%, #000000 100%) border-box,
                    conic-gradient(from var(--overload-2, 90deg), #000000 0%, #000000 30%, var(--gb-base2, var(--gb-base)) 31%, #000000 32%, #000000 70%, var(--gb-mid2, var(--gb-mid)) 71%, #000000 72%, #000000 100%) border-box,
                    conic-gradient(from var(--overload-3, 180deg), #000000 0%, #000000 10%, var(--gb-peak) 11%, #000000 12%, #000000 60%, var(--gb-mid) 61%, #000000 62%, #000000 100%) border-box,
                    conic-gradient(from var(--overload-4, 45deg), #000000 0%, #000000 40%, var(--gb-peak2, var(--gb-peak)) 41%, #000000 42%, #000000 90%, var(--gb-mid2, var(--gb-mid)) 91%, #000000 92%, #000000 100%) border-box !important;
                background-blend-mode: normal, screen, screen, screen, normal;
                background-repeat: no-repeat;
                background-clip: padding-box, border-box, border-box, border-box, border-box;
                animation: ao3-o-drift-1 12s linear infinite,
                           ao3-o-drift-2 15s linear infinite,
                           ao3-o-drift-3 9s linear infinite,
                           ao3-o-drift-4 20s linear infinite,
                           ao3-glow-breathe 10.5s ease-in-out infinite !important;
            }
            .gradient-border-reverse {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), #000000 0%, var(--gb-mid) 2.5%, var(--gb-peak) 5%, var(--gb-mid) 7.5%, #000000 10%, #000000 25%, var(--gb-mid2, var(--gb-mid)) 27.5%, var(--gb-peak2, var(--gb-peak)) 30%, var(--gb-mid2, var(--gb-mid)) 32.5%, #000000 35%, #000000 50%, var(--gb-mid) 52.5%, var(--gb-peak) 55%, var(--gb-mid) 57.5%, #000000 60%, #000000 75%, var(--gb-mid2, var(--gb-mid)) 77.5%, var(--gb-peak2, var(--gb-peak)) 80%, var(--gb-mid2, var(--gb-mid)) 82.5%, #000000 85%, #000000 100%) border-box !important;
                animation: ao3-gradient-border-reverse-spin 36s linear infinite,
                           ao3-glow-breathe 10.5s ease-in-out infinite !important;
            }
            .gradient-border-sonar {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), #000000 0%, #000000 50%, var(--gb-peak) 52.5%, var(--gb-mid) 60%, #000000 100%) border-box,
                    conic-gradient(from calc(360deg - var(--gradient-angle, 0deg)), #000000 0%, #000000 50%, var(--gb-base2, var(--gb-base)) 52.5%, #000000 70%, #000000 100%) border-box !important;
                background-blend-mode: normal, screen, normal;
                background-repeat: no-repeat;
                background-clip: padding-box, border-box, border-box;
                animation: ao3-gradient-border-sonar-sweep 15s linear infinite,
                           ao3-glow-breathe 10.5s ease-in-out infinite !important;
            }
            .gradient-border-nebula {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--gradient-angle, 0deg), #000000 0%, #000000 25%, var(--gb-mid) 35%, var(--gb-peak) 50%, var(--gb-mid) 65%, #000000 75%, #000000 100%) border-box,
                    conic-gradient(from var(--nebula-ccw, 360deg), #000000 0%, #000000 25%, var(--gb-mid2, var(--gb-mid)) 35%, var(--gb-peak2, var(--gb-peak)) 50%, var(--gb-mid2, var(--gb-mid)) 65%, #000000 75%, #000000 100%) border-box !important;
                background-blend-mode: normal, screen, normal;
                background-repeat: no-repeat;
                background-clip: padding-box, border-box, border-box;
                animation: ao3-nebula-drift-cw 40s linear infinite,
                           ao3-nebula-drift-ccw 55s linear infinite,
                           ao3-glow-breathe 15s ease-in-out infinite !important;
            }
            .gradient-border-abyss {
                background:
                    linear-gradient(var(--gb-bg, #161b22), var(--gb-bg, #161b22)) padding-box,
                    conic-gradient(from var(--abyss-slow, 0deg), #000000 0%, #000000 40%, var(--gb-mid) 45%, var(--gb-peak) 50%, var(--gb-mid) 55%, #000000 60%, #000000 100%) border-box,
                    conic-gradient(from var(--abyss-fast, 90deg), #000000 0%, #000000 40%, var(--gb-mid2, var(--gb-mid)) 45%, var(--gb-peak2, var(--gb-peak)) 50%, var(--gb-mid2, var(--gb-mid)) 55%, #000000 60%, #000000 100%) border-box !important;
                background-blend-mode: normal, screen, normal;
                background-repeat: no-repeat;
                background-clip: padding-box, border-box, border-box;
                animation: ao3-abyss-flow-slow 14s linear infinite,
                           ao3-abyss-flow-fast 9s linear infinite,
                           ao3-glow-breathe 10.5s ease-in-out infinite !important;
            }
            .gradient-border-best {
                --gb-base: #7c6235;
                --gb-mid: #b18233;
                --gb-peak: #cb963d;
                --gb-mid2: #b4a362;
                --gb-peak2: #cdba73;
                --gb-mid3: #a39562;
                --gb-peak3: #bba871;
                --gb-glow: rgba(124,98,53,0.45);
                --gb-glow-soft: rgba(124,98,53,0.12);
            }
            .gradient-border-legendary {
                --gb-base: #7c4d35;
                --gb-mid: #b15d33;
                --gb-peak: #cb6c3d;
                --gb-mid2: #b13333;
                --gb-peak2: #cb3d3d;
                --gb-mid3: #a46b53;
                --gb-peak3: #bc7c62;
                --gb-glow: rgba(124,77,53,0.45);
                --gb-glow-soft: rgba(124,77,53,0.12);
            }
            .gradient-border-epic {
                --gb-base: #5a357c;
                --gb-mid: #7433b1;
                --gb-peak: #863dcb;
                --gb-mid2: #b13382;
                --gb-peak2: #cb3d96;
                --gb-mid3: #8a64a4;
                --gb-peak3: #9b72b8;
                --gb-glow: rgba(90,53,124,0.45);
                --gb-glow-soft: rgba(90,53,124,0.12);
            }
            .gradient-border-rare {
                --gb-base: #35507c;
                --gb-mid: #3363b1;
                --gb-peak: #3d73cb;
                --gb-mid2: #33a1b1;
                --gb-peak2: #3db8cb;
                --gb-mid3: #5880a4;
                --gb-peak3: #6892b8;
                --gb-glow: rgba(53,80,124,0.45);
                --gb-glow-soft: rgba(53,80,124,0.12);
            }
            .gradient-border-uncommon {
                --gb-base: #357c4f;
                --gb-mid: #33b162;
                --gb-peak: #3dcb71;
                --gb-mid2: #84b17b;
                --gb-peak2: #97cb8d;
                --gb-mid3: #6a956a;
                --gb-peak3: #7aa87a;
                --gb-glow: rgba(53,124,79,0.45);
                --gb-glow-soft: rgba(53,124,79,0.12);
            }
            .gradient-border-common {
                --gb-base: #334155;
                --gb-mid: #64748b;
                --gb-peak: #94a3b8;
                --gb-mid2: #475569;
                --gb-peak2: #cbd5e1;
                --gb-mid3: #64748b;
                --gb-peak3: #e2e8f0;
                --gb-glow: rgba(100,116,139,0.42);
                --gb-glow-soft: rgba(100,116,139,0.12);
            }
            ::-webkit-scrollbar { width: 10px; height: 10px; }
            ::-webkit-scrollbar-track { background: #0d1117; }
            ::-webkit-scrollbar-thumb {
                background: #30363d;
                border-radius: 5px;
                border: 2px solid #0d1117;
            }
            ::-webkit-scrollbar-thumb:hover { background: #484f58; }
        </style>
        """
    )
