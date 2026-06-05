from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.application.composition import build_container
from app.application.services import normalize_character_reader_style
from app.domain.entities import CharacterProfile, FandomProfile, ReaderAsset, ReaderChapter, Work, WorkTag
from app.domain.enums import RarityTier, TagType
from app.presentation.ui.app_shell import (
    AO3_METADATA_SORT_PILLS,
    FONT_CATEGORIES,
    FONT_COLORS,
    AO3StudioShell,
    _ao3_character_tag_label,
    _canonical_ao3_character_tag_url,
    _canonical_character_suggestions,
    _character_names_from_ao3_label,
    _character_profile_display_names,
    _reader_highlight_characters,
    _reader_visible_characters_for_chapter,
    _reader_apply_pov_paragraph_colors,
    _scriptstudio_lighten_color,
)
from app.presentation.ui.theme import apply_theme


def test_scriptstudio_font_options_include_recursive_family() -> None:
    monospace = FONT_CATEGORIES["monospace"]["fonts"]

    assert "'Recursive', monospace" in monospace
    assert "'Space Mono', monospace" in monospace
    assert "'Atkinson Hyperlegible Mono', monospace" in monospace
    assert FONT_COLORS["'Recursive', monospace"] == "#1ec718"


def test_reader_typography_uses_scriptstudio_font_specific_weights() -> None:
    assert AO3StudioShell._font_typography_css("'Recursive', monospace", 16) == (
        "font-weight: 360; font-variation-settings: 'MONO' 0, 'slnt' 0, 'CASL' 1, 'CRSV' 1;"
    )
    assert AO3StudioShell._font_typography_css("'Loretta Light', 'Loretta', serif", 16) == "font-weight: 300;"
    assert AO3StudioShell._font_typography_css("'Fraunces', serif", 16) == (
        "font-weight: 275; font-variation-settings: 'opsz' 16, 'SOFT' 70, 'WONK' 1;"
    )


def test_reader_character_font_style_overrides_are_toggle_gated() -> None:
    shell = AO3StudioShell.__new__(AO3StudioShell)
    settings = {"preview_font_family": "'Source Code Pro', monospace", "reader_font_size": 16.5}
    character = CharacterProfile(
        id="max",
        fandom_key="lis",
        name="Max",
        reader_style={
            "font_family": "'Newsreader', serif",
            "custom_font_enabled": False,
            "font_size": 22,
            "font_size_enabled": False,
        },
    )

    passive = shell._reader_font_style_for_character(settings, character)
    character.reader_style["custom_font_enabled"] = True
    font_only = shell._reader_font_style_for_character(settings, character)
    character.reader_style["font_size_enabled"] = True
    font_and_size = shell._reader_font_style_for_character(settings, character)

    assert normalize_character_reader_style({})["custom_font_enabled"] is False
    assert normalize_character_reader_style({})["font_size_enabled"] is False
    assert "font-family: 'Source Code Pro', monospace" in passive
    assert "font-size: 16.5px" in passive
    assert "font-family: 'Newsreader', serif" in font_only
    assert "font-size: 16.5px" in font_only
    assert "font-family: 'Newsreader', serif" in font_and_size
    assert "font-size: 22.0px" in font_and_size


def test_switch_event_bool_prefers_actual_value_over_empty_args() -> None:
    assert AO3StudioShell._event_bool(SimpleNamespace(value=True, args={})) is True
    assert AO3StudioShell._event_bool(SimpleNamespace(value=False, args={"value": True})) is False
    assert AO3StudioShell._event_bool(SimpleNamespace(args={"modelValue": True})) is True
    assert AO3StudioShell._event_bool(SimpleNamespace(args={"model-value": "false"})) is False
    assert AO3StudioShell._event_value(SimpleNamespace(args=[{"value": 3}])) == 3


def test_fandom_style_override_toggle_rerenders_and_saves_enabled_state() -> None:
    controls_source = inspect.getsource(AO3StudioShell._render_style_controls)
    dialog_source = inspect.getsource(AO3StudioShell._show_fandom_dialog)

    assert "def event_bool" in controls_source
    assert "def event_value" in controls_source
    assert "return self._event_bool(event, fallback=fallback)" in controls_source
    assert "return self._event_value(event, fallback=fallback)" in controls_source
    assert "def handle_enabled_toggle" in controls_source
    assert 'enabled_state[section] = event_bool' in controls_source
    assert 'STYLE_OVERRIDE_SECTIONS_KEY' in controls_source
    assert "def render_control_body" in controls_source
    assert 'refs["body"] = ui.element("div").classes("w-full")' in controls_source
    assert "render_control_body()" in controls_source
    assert 'enabled_state[section] = event_bool(event, not bool(enabled_state.get(section)))' in controls_source
    assert 'style_state[key] = event_bool(event, not bool(style_state.get(key)))' in controls_source
    assert 'lambda event: handle_enabled_toggle("font", event)' in controls_source
    assert 'lambda event: handle_enabled_toggle("rarity", event)' in controls_source
    assert 'js_handler="value => emit(value)"' in controls_source
    assert 'lambda event=None: handle_enabled_toggle' not in controls_source
    assert "Use fandom style override" not in controls_source
    assert "live_update_handler" in controls_source
    assert "def apply_live_update" in controls_source
    assert 'font_size.on("update:model-value"' in controls_source
    assert 'gradient_switch.on("update:model-value"' in controls_source
    assert '.bind_value(enabled_state, "enabled")' not in controls_source
    assert 'style_enabled = self.container.style_service.override_sections(style_override)' in dialog_source
    assert 'state[STYLE_OVERRIDE_SECTIONS_KEY] = dict(style_enabled)' in dialog_source
    assert "def preview_fandom_style" in dialog_source
    assert "live_update_handler=preview_fandom_style" in dialog_source
    assert 'self.container.style_service.save_fandom_override(active.fandom_key, any(style_enabled.values()), state)' in dialog_source


def test_reader_style_priority_is_global_then_fandom_then_character(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.save_profile(
        FandomProfile(
            fandom_key="lis",
            tag="Life is Strange",
            display_name="Life is Strange",
            color="#58a6ff",
            avatar_url=None,
            notes=None,
            default_filter={},
            created_at="",
            updated_at="",
            selected_at=None,
        )
    )
    container.style_service.save_global_settings({"preview_font_family": "'Source Code Pro', monospace", "reader_font_size": 16.5})
    container.style_service.save_fandom_override(
        profile.fandom_key,
        True,
        {"preview_font_family": "'Recursive', monospace", "reader_font_size": 19.5},
    )
    shell = AO3StudioShell(container)
    fandom_style = container.style_service.effective_settings(profile.fandom_key)

    no_pov = shell._reader_font_style_for_character(fandom_style, None)
    passive_character = CharacterProfile(
        id="max",
        fandom_key=profile.fandom_key,
        name="Max",
        reader_style={
            "font_family": "'Newsreader', serif",
            "custom_font_enabled": False,
            "font_size": 22,
            "font_size_enabled": False,
        },
    )
    active_character = CharacterProfile(
        id="loretta",
        fandom_key=profile.fandom_key,
        name="Loretta",
        reader_style={
            "font_family": "'Loretta Light', 'Loretta', serif",
            "custom_font_enabled": True,
            "font_size": 23,
            "font_size_enabled": True,
        },
    )
    passive_pov = shell._reader_font_style_for_character(fandom_style, passive_character)
    active_pov = shell._reader_font_style_for_character(fandom_style, active_character)

    assert "font-family: 'Recursive', monospace" in no_pov
    assert "font-size: 19.5px" in no_pov
    assert "font-family: 'Recursive', monospace" in passive_pov
    assert "font-size: 19.5px" in passive_pov
    assert "font-family: 'Loretta Light', 'Loretta', serif" in active_pov
    assert "font-size: 23.0px" in active_pov


def test_reader_character_pov_tint_uses_scriptstudio_alternating_tones_without_overwriting_names() -> None:
    fragment = (
        '<p>One <span style="color: rgb(1,2,3); text-shadow: old;">Chloe</span>.</p>'
        "<p>Two.</p>"
    )
    rendered = _reader_apply_pov_paragraph_colors(fragment, "#123456")
    neutral = _reader_apply_pov_paragraph_colors(fragment, None)

    assert _scriptstudio_lighten_color("#123456", 0.45) == "#7c8fa2"
    assert _scriptstudio_lighten_color("#123456", 0.65) == "#acb7c3"
    assert "color: #7c8fa2" in rendered
    assert "color: #acb7c3" in rendered
    assert "color: rgb(1,2,3); text-shadow: old;" in rendered
    assert neutral.count("<p") == rendered.count("<p")
    assert neutral.count("</p>") == rendered.count("</p>")
    assert "color: #c9d1d9" in neutral
    assert "color: #dde3ea" in neutral
    assert "color: rgb(1,2,3); text-shadow: old;" in neutral


def test_reader_character_highlighting_does_not_split_ao3_paragraphs() -> None:
    maxine = CharacterProfile(
        id="max",
        fandom_key="lis",
        name="Max",
        full_name="Maxine Caulfield",
        color="#58a6ff",
    )
    fragment = (
        "<p>She called me Max. Not Miss Caulfield. Max. This is the first time she's done that. "
        "It shifts the air between us, making the space suddenly feel strangely intimate. "
        "I take a step closer to her.</p>"
    )

    highlighted = _reader_highlight_characters(fragment, [maxine])
    rendered = _reader_apply_pov_paragraph_colors(highlighted, None)

    assert highlighted.count("<p") == 1
    assert highlighted.count("</p>") == 1
    assert rendered.count("<p") == 1
    assert rendered.count("</p>") == 1
    assert "Not Miss Caulfield. <span" in highlighted
    assert "<p><p" not in highlighted


def test_canonical_character_tag_helpers_normalize_ao3_urls_and_labels() -> None:
    max_url = "https://archiveofourown.org/tags/Maxine%20%22Max%22%20Caulfield/works"

    assert _ao3_character_tag_label(max_url) == 'Maxine "Max" Caulfield'
    assert _canonical_ao3_character_tag_url(max_url) == max_url
    assert _canonical_ao3_character_tag_url("Loretta Rice") == "https://archiveofourown.org/tags/Loretta%20Rice/works"
    assert _character_names_from_ao3_label("Loretta Rice") == ("Loretta", "Loretta Rice")
    assert _character_names_from_ao3_label("Safiya \"Safi\" Llewellyn-Fayyad") == (
        "Safi",
        "Safiya Llewellyn-Fayyad",
    )
    legacy_profile = CharacterProfile(
        id="safi",
        fandom_key="lis",
        name='Safiya "Safi" Llewellyn-Fayyad',
        tag_urls=["https://archiveofourown.org/tags/Safiya%20%22Safi%22%20Llewellyn-Fayyad/works"],
    )
    assert _character_profile_display_names(legacy_profile) == ("Safi", "Safiya Llewellyn-Fayyad")


def test_canonical_character_suggestions_suppress_safi_variants_when_quoted_full_tag_exists() -> None:
    suggestions = [
        SimpleNamespace(
            tag_text="Safi (Life is Strange: Double Exposure)",
            tag_url="https://archiveofourown.org/tags/Safi%20(Life%20is%20Strange:%20Double%20Exposure)/works",
            category="character",
        ),
        SimpleNamespace(
            tag_text="Safi Llewellyn-Fayyad",
            tag_url="https://archiveofourown.org/tags/Safi%20Llewellyn-Fayyad/works",
            category="character",
        ),
        SimpleNamespace(
            tag_text='Safiya "Safi" Llewellyn-Fayyad',
            tag_url="https://archiveofourown.org/tags/Safiya%20%22Safi%22%20Llewellyn-Fayyad/works",
            category="character",
        ),
        SimpleNamespace(
            tag_text='Safiya "Safi" Llewellyn-Fayyad (Mentioned)',
            tag_url="https://archiveofourown.org/tags/Safiya%20%22Safi%22%20Llewellyn-Fayyad%20(Mentioned)/works",
            category="character",
        ),
    ]

    filtered = _canonical_character_suggestions(suggestions, "safi")

    assert [item.tag_text for item in filtered] == ['Safiya "Safi" Llewellyn-Fayyad']


def test_reader_character_matching_uses_work_tags_then_chapter_mentions() -> None:
    chloe = CharacterProfile(
        id="chloe",
        fandom_key="lis",
        name="Chloe",
        full_name="Chloe Price",
        color="#58a6ff",
        tag_urls=["https://archiveofourown.org/tags/Chloe%20Price%20(Life%20is%20Strange)/works"],
    )
    maxine = CharacterProfile(
        id="max",
        fandom_key="lis",
        name="Max",
        full_name="Maxine Caulfield",
        color="#7ee787",
        tag_urls=["https://archiveofourown.org/tags/Maxine%20%22Max%22%20Caulfield/works"],
    )
    li = CharacterProfile(id="li", fandom_key="lis", name="Li", color="#f778ba")
    work_tags = [
        WorkTag(
            "work",
            TagType.CHARACTER,
            "Chloe Price (Life is Strange)",
            "https://archiveofourown.org/tags/Chloe%20Price%20(Life%20is%20Strange)/works",
        )
    ]
    chapter_html = "<p>Max checks the camera. Li is just letters in a word like lifeline.</p>"

    initial = _reader_visible_characters_for_chapter([chloe, maxine, li], work_tags, chapter_html, committed=False)
    committed = _reader_visible_characters_for_chapter([chloe, maxine, li], work_tags, chapter_html, committed=True)

    assert [character.id for character in initial] == ["chloe", "max"]
    assert [character.id for character in committed] == ["max"]


def test_reader_sticky_pov_is_per_work_and_respects_chapter_presence(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    shell = AO3StudioShell(container)
    chloe = CharacterProfile(
        id="chloe",
        fandom_key="lis",
        name="Chloe",
        full_name="Chloe Price",
        color="#58a6ff",
    )
    maxine = CharacterProfile(
        id="max",
        fandom_key="lis",
        name="Max",
        full_name="Maxine Caulfield",
        color="#7ee787",
        tag_urls=["https://archiveofourown.org/tags/Maxine%20%22Max%22%20Caulfield/works"],
    )

    container.preferences_service.set(shell._reader_pov_sticky_key("work-1"), True)
    shell._save_reader_pov_timeline("work-1", {1: "chloe", 4: "max", 5: "chloe", 8: "max"})
    shell._save_reader_pov_timeline("work-2", {1: "chloe"})

    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-1")) == {
        "1": "chloe",
        "4": "max",
        "5": "chloe",
        "8": "max",
    }
    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-2")) == {"1": "chloe"}
    assert shell._reader_timeline_character_id("work-1", 1) == "chloe"
    assert shell._reader_timeline_character_id("work-1", 4) == "max"
    assert shell._reader_timeline_character_id("work-1", 7) == "chloe"
    assert shell._reader_timeline_character_id("work-1", 17) == "max"
    assert shell._reader_selected_character_id("work-1", 2, [chloe, maxine], "<p>Chloe checks the truck.</p>") == "chloe"
    assert shell._reader_selected_character_id("work-1", 4, [chloe, maxine], "<p>Max checks the camera.</p>") == "max"
    assert shell._reader_selected_character_id("work-1", 4, [chloe, maxine], "<p>Chloe checks the truck.</p>") == ""
    assert shell._reader_character_view_committed("work-1", 2)

    container.preferences_service.set(shell._reader_selected_character_key("work-1", 9), "max")
    assert shell._reader_selected_character_id("work-1", 9, [chloe, maxine], "<p>Max checks the camera.</p>") == "max"
    shell._set_reader_character_selection("", "work-1", 9)
    assert shell._reader_no_pov_enabled("work-1")
    assert container.preferences_service.get(shell._reader_selected_character_key("work-1", 9)) == "max"
    assert shell._reader_selected_character_id("work-1", 9, [chloe, maxine], "<p>Max checks the camera.</p>") == ""
    assert shell._reader_selected_character_id("work-1", 2, [chloe, maxine], "<p>Chloe checks the truck.</p>") == ""
    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-1")) == {
        "1": "chloe",
        "4": "max",
        "5": "chloe",
        "8": "max",
    }
    shell._set_reader_character_selection("", "work-1", 2)
    assert not shell._reader_no_pov_enabled("work-1")
    assert container.preferences_service.get(shell._reader_selected_character_key("work-1", 9)) == "max"
    assert shell._reader_selected_character_id("work-1", 9, [chloe, maxine], "<p>Max checks the camera.</p>") == "max"
    assert shell._reader_selected_character_id("work-1", 2, [chloe, maxine], "<p>Chloe checks the truck.</p>") == "chloe"
    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-1")) == {
        "1": "chloe",
        "4": "max",
        "5": "chloe",
        "8": "max",
    }
    shell._set_reader_pov_sticky("work-1", 9, False)
    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-1")) == {
        "1": "chloe",
        "4": "max",
        "5": "chloe",
        "8": "max",
    }
    shell._set_reader_character_selection("", "work-1", 5)
    assert shell._reader_no_pov_enabled("work-1")
    shell._set_reader_character_selection("chloe", "work-1", 5)
    assert not shell._reader_no_pov_enabled("work-1")
    assert shell._reader_selected_character_id("work-1", 5, [chloe, maxine], "<p>Chloe checks the truck.</p>") == "chloe"
    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-1")) == {
        "1": "chloe",
        "4": "max",
        "5": "chloe",
        "8": "max",
    }

    shell._reset_reader_character_pool("work-1", 2)

    assert not container.preferences_service.get(shell._reader_character_commit_key("work-1", 2), True)
    assert not container.preferences_service.get(shell._reader_pov_sticky_key("work-1"), False)
    assert container.preferences_service.get(shell._reader_pov_timeline_key("work-1")) == {
        "1": "chloe",
        "4": "max",
        "5": "chloe",
        "8": "max",
    }
    assert not shell._reader_character_view_committed("work-1", 2)


def test_reader_side_panel_character_pills_and_left_expanding_avatar_tooltip_exist() -> None:
    right_header_source = inspect.getsource(AO3StudioShell._render_right_header)
    reader_side_source = inspect.getsource(AO3StudioShell._render_reader_side_panel)
    pill_source = inspect.getsource(AO3StudioShell._render_reader_character_pills)
    selection_source = (
        inspect.getsource(AO3StudioShell._reader_selected_character_id)
        + inspect.getsource(AO3StudioShell._reader_selected_character_key)
        + inspect.getsource(AO3StudioShell._reader_pov_sticky_key)
        + inspect.getsource(AO3StudioShell._reader_sticky_character_key)
        + inspect.getsource(AO3StudioShell._reader_pov_timeline_key)
        + inspect.getsource(AO3StudioShell._reader_no_pov_key)
        + inspect.getsource(AO3StudioShell._reader_no_pov_enabled)
        + inspect.getsource(AO3StudioShell._reader_pov_timeline)
        + inspect.getsource(AO3StudioShell._save_reader_pov_timeline)
        + inspect.getsource(AO3StudioShell._reader_timeline_character_id)
        + inspect.getsource(AO3StudioShell._reader_character_commit_key)
        + inspect.getsource(AO3StudioShell._reader_character_pool_reset_key)
        + inspect.getsource(AO3StudioShell._reader_character_view_committed)
        + inspect.getsource(AO3StudioShell._set_reader_pov_sticky)
        + inspect.getsource(AO3StudioShell._reset_reader_character_pool)
        + inspect.getsource(AO3StudioShell._set_reader_character_selection)
    )
    page_read_source = inspect.getsource(AO3StudioShell._page_read)
    avatar_source = inspect.getsource(AO3StudioShell._avatar_image)
    theme_source = inspect.getsource(apply_theme)

    assert "_render_reader_character_pills(active, work, chapter, chapter_index)" in reader_side_source
    assert "_reader_visible_characters_for_chapter" in pill_source
    assert "_reader_character_view_committed" in pill_source
    assert "visible_characters.append(selected_character)" in pill_source
    assert "reader-none-character-pill" not in pill_source
    assert "reader-pov-header" not in pill_source
    assert 'self.page == "Read"' in right_header_source
    assert "reader-pov-header-icon" in right_header_source
    assert "reader-no-pov" in pill_source
    assert "work-tag-pill browse-tag-pill reader-character-pill reader-no-pov" in pill_source
    assert "w-full gap-x-1 gap-y-1.5 flex-wrap items-center reader-character-pill-row px-2 -mt-1" in pill_source
    assert 'with ui.element("div").classes("soft-panel w-full p-2")' not in pill_source
    assert "No POV" in pill_source
    assert "link_off" in right_header_source
    assert "restart_alt" in right_header_source
    assert "reader-character-pill" in pill_source
    assert "reader_selected_character:{work_id}:{max(1, int(chapter_index or 1))}" in selection_source
    assert "reader_pov_sticky:{work_id}" in selection_source
    assert "reader_sticky_character:{work_id}" in selection_source
    assert "reader_pov_timeline:{work_id}" in selection_source
    assert "reader_no_pov:{work_id}" in selection_source
    assert "self._reader_no_pov_enabled(work_id)" in selection_source
    assert "reader_character_committed:" in selection_source
    assert "reader_character_pool_reset:" in selection_source
    assert 'expand_side="left"' in pill_source
    assert "_reader_apply_pov_paragraph_colors" in page_read_source
    assert "selected_character.color if selected_character else None" in page_read_source
    assert "_reader_highlight_characters(chapter.html, characters)" in page_read_source
    assert page_read_source.index("_reader_highlight_characters") < page_read_source.index("_reader_apply_pov_paragraph_colors")
    assert 'tooltip_anchor = "center left" if expand_side == "left" else "center right"' in avatar_source
    assert 'tooltip_self = "center right" if expand_side == "left" else "center left"' in avatar_source
    assert ".reader-character-pill" in theme_source
    assert ".reader-character-pill-label" in theme_source
    assert ".reader-pov-header {" not in theme_source
    assert ".reader-pov-header-icon" in theme_source
    assert ".reader-no-pov" in theme_source
    assert ".reader-none-character-pill" not in theme_source
    assert ".reader-character-pill-row {\n                align-content: flex-start;\n            }" in theme_source
    assert "max-width: none !important;" in theme_source
    assert "text-overflow: clip !important;" in theme_source


def test_fandom_character_tab_uses_compact_canonical_character_pills() -> None:
    source = inspect.getsource(AO3StudioShell._show_fandom_dialog)
    avatar_button_source = inspect.getsource(AO3StudioShell._character_avatar_button)
    avatar_dialog_source = inspect.getsource(AO3StudioShell._open_character_avatar_dialog)
    avatar_upload_source = inspect.getsource(AO3StudioShell._handle_character_avatar_upload)
    theme_source = inspect.getsource(apply_theme)

    assert "character-profile-pill" in source
    assert "reader-character-pill" in source
    assert "Canonical AO3 character tag URL" in source
    assert "Full Name" in source
    assert "_canonical_character_suggestions(" in source
    assert "target[\"name\"] = short_name or suggestion.tag_text" in source
    assert "target[\"full_name\"] = full_name or suggestion.tag_text" in source
    assert "full_name=full_name" in source
    assert "collapse_character_expansions" in source
    assert "character-profile-expanded" in source
    assert "box-shadow: 0 0 16px rgba" in source
    assert "open_character_font_dialog" in source
    assert "ui.icon(\"text_fields\", size=\"sm\")" in source
    assert "character-font-icon cursor-pointer px-1" in source
    assert "font_style_active" in source
    font_icon_source = source.split('font_icon = ui.icon("text_fields", size="sm")', 1)[1].split('font_icon.on("click.stop"', 1)[0]
    assert "text-shadow" not in font_icon_source
    assert "character_font_icon_style(character.color, font_style_active)" in font_icon_source
    assert "def character_font_icon_style" in source
    assert "--character-font-color" in source
    assert "def character_expanded_style" in source
    assert "def update_character_color_live" in source
    assert "expanded_ref.style(replace=character_expanded_style(color))" in source
    assert "pill_ref.style(replace=self._filter_pill_style(color, True))" in source
    assert "self._restyle_avatar_refs(live_refs.get(\"avatar\"), color" in source
    assert "self._restyle_avatar_refs(live_refs.get(\"pill_avatar\"), color" in source
    assert "font_icon_ref.style(replace=character_font_icon_style(color, font_active))" in source
    assert 'if self.page == "Read":' in source
    assert "self._render_right()" in source
    assert "self._render_center()" in source
    assert 'on_change=lambda event, d=draft, cid=character.id, lr=live_refs: update_character_color_live' in source
    assert ".character-font-icon:hover" in theme_source
    assert "text-shadow: 0 0 8px var(--character-font-color" in theme_source
    assert "ui.button(icon=\"font_download\")" not in source
    assert "font_download" not in source
    assert "Character reader font" in source
    assert "Custom Font" in source
    assert "Starting Font Size" in source
    assert "Disabled toggles keep this as passive character info." in source
    assert "reader_font_dialog_style = (" in source
    assert "width: 560px; max-width: 94vw; height: 85vh; max-height: calc(100vh - 24px);" in source
    assert "w-[640px]" not in source
    character_font_dialog_source = source.split("def open_character_font_dialog", 1)[1].split("with self.root:", 1)[0]
    assert "dialog.close()" not in character_font_dialog_source
    assert 'if self.page == "Read":' in character_font_dialog_source
    assert "self._render_center()" in character_font_dialog_source
    assert "normalize_character_reader_style(character.reader_style)" in source
    assert "reader_style=dict(draft.get(\"reader_style\") or {})" in source
    expanded_character_source = source.split(
        'with ui.element("div").classes("soft-panel w-full p-2 character-profile-expanded")',
        1,
    )[1].split('ui.separator().classes("bg-gray-800")', 1)[0]
    assert 'js_handler="value => emit(value)"' not in expanded_character_source
    assert 'ui.textarea("Notes"' not in expanded_character_source
    assert 'ui.button("Save"' not in expanded_character_source
    assert "save_btn" not in expanded_character_source
    assert "def autosave_character_draft" in source
    assert 'name_field.on("blur"' in source
    assert 'full_name_field.on("blur"' in source
    assert 'ui.color_input(\n                                    "Color",' in expanded_character_source
    assert "update_character_color_live(" in expanded_character_source
    assert 'character_live_refs[character.id]["pill_avatar"] = self._avatar_image' in source
    assert 'tag_input.on("blur"' in expanded_character_source
    assert "notify=False, rerender=False" in source
    assert 'footer_save.on("click.stop", lambda _=None: save_fandom())' in source
    assert 'event.target.closest(\'.q-btn, button, input, textarea, [role=\\"button\\"]\')' in source
    assert "render_character_panel" in source
    assert "_select_fandom_profile(saved.fandom_key)" not in source
    save_fandom_source = source.split("def save_fandom() -> None:", 1)[1].split("def save_fandom_style", 1)[0]
    save_style_source = source.split("def save_fandom_style", 1)[1].split("def render_avatar_slot", 1)[0]
    assert "close_dialog()" not in save_fandom_source
    assert "self._render_left()" not in save_fandom_source
    assert "self._refresh_fandom_rows()" not in save_fandom_source
    assert "self._render_left_footer()" not in save_fandom_source
    assert "self._update_fandom_row_in_place(saved)" in save_fandom_source
    assert "refresh_dialog_theme()" in save_fandom_source
    assert 'draft["color"] = saved.color' in save_fandom_source
    assert "self.refresh()" not in save_fandom_source
    assert "self.refresh()" not in save_style_source
    fandom_row_source = inspect.getsource(AO3StudioShell._fandom_row)
    fandom_avatar_button_source = inspect.getsource(AO3StudioShell._fandom_avatar_button)
    avatar_image_source = inspect.getsource(AO3StudioShell._avatar_image)
    avatar_visual_source = inspect.getsource(AO3StudioShell._avatar_visual_style)
    avatar_restyle_source = inspect.getsource(AO3StudioShell._restyle_avatar_refs)
    update_row_source = inspect.getsource(AO3StudioShell._update_fandom_row_in_place)
    assert "self.fandom_row_refs[profile.fandom_key]" in fandom_row_source
    assert 'row_refs["avatar"] = self._fandom_avatar_button' in fandom_row_source
    assert "return self._avatar_image(" in fandom_avatar_button_source
    assert 'avatar_refs["small"]' in avatar_image_source
    assert 'avatar_refs["small_label"]' in avatar_image_source
    assert 'avatar_refs["big"]' in avatar_image_source
    assert "background: rgba({r},{g},{b},0.20);" in avatar_visual_source
    assert "visual.style(replace=self._avatar_visual_style" in avatar_restyle_source
    assert "label_ref.set_text(initial)" in avatar_restyle_source
    assert "def _update_fandom_row_in_place" in update_row_source
    assert "set_text(profile.display_name)" in update_row_source
    assert "self._restyle_avatar_refs(refs.get(\"avatar\"), profile.color, profile.display_name)" in update_row_source
    assert "def refresh_dialog_theme() -> None:" in source
    assert 'refs["card"] = card' in source
    assert 'refs["header_icon"]' in source
    assert 'refs["header_title"]' in source
    assert 'refs["footer_save"] = footer_save' in source
    assert "dialog_style_for(current_color(), fullscreen=True)" in source
    assert "dialog_style_for(current_color(), fullscreen=False)" in source
    assert 'tag_urls=[canonical_tag_url] if canonical_tag_url else []' in source
    assert 'ui.input("Name", value=draft["name"]).bind_value(draft, "name").props(\n                                    "dark outlined dense"\n                                )' in source
    assert 'ui.input("Full Name", value=draft["full_name"]).bind_value(draft, "full_name").props(\n                                    "dark outlined dense"\n                                )' in source
    assert 'ui.input("Canonical AO3 character tag URL", value=draft["tag_urls"]).bind_value(draft, "tag_urls").props(\n                                    "dark outlined dense"\n                                )' in source
    assert "AO3 tag links, comma separated" not in source
    assert "tag_text = \", \".join(character.tag_urls[:2])" not in source
    assert "soft-panel w-full gap-2 p-2 cursor-pointer" not in source
    assert "AO3 character tag suggestions cached" not in source
    assert "tag_catalog_count" not in source
    assert "Refresh AO3 tag catalog for" not in source
    assert '"footer_left": None' in source
    assert "def render_character_footer() -> None:" in source
    assert 'if active_dialog_tab["value"] != "Characters":' in source
    assert "def disarm_character_cleanup() -> None:" in source
    assert "def dialog_background_click() -> None:" in source
    assert "'#f8fafc' if character_cleanup['mode'] else '#6b7280'" in source
    assert "'#ef4444' if character_cleanup['armed'] else '#6b7280'" in source
    assert "def input_event_text(event, fallback: Any = \"\") -> str:" in source
    assert 'if hasattr(event, "args"):' in source
    assert 'if args is None:\n                        return ""' in source
    assert 'if isinstance(args, dict):' in source
    assert 'for key in ("value", "modelValue", "model-value", "text"):' in source
    assert 'return "" if args[key] is None else str(args[key])' in source
    assert 'return "" if value is None else str(value)' in source
    assert "def character_tag_suggestion_js() -> str:" in source
    assert "event?.target?.value" in source
    assert "event?.target?.closest('.character-tag-suggestion-shell')" in source
    assert "row.classList.add('hidden')" in source
    assert "character-tag-suggestion-shell" in source
    assert "character-tag-suggestions hidden" in source
    assert 'row.classes(add="hidden")' in source
    assert 'row.classes(remove="hidden")' in source
    assert 'suggestions_row.classes(add="hidden")' in source
    assert 'suggestions_row.classes(remove="hidden")' in source
    assert 'tag_input.on("keyup", lambda event=None: render_suggestions(event), js_handler=character_tag_suggestion_js())' in source
    assert 'tag_input.on("input", lambda event=None: render_suggestions(event), js_handler=character_tag_suggestion_js())' in source
    assert 'tag_input.on("keyup", lambda event=None: render_edit_suggestions(event), js_handler=character_tag_suggestion_js())' in source
    assert 'tag_input.on("input", lambda event=None: render_edit_suggestions(event), js_handler=character_tag_suggestion_js())' in source
    assert 'tag_input.on("update:model-value"' not in source
    assert 'raw_query = input_event_text(event, ch_draft.get("tag_urls") or "")' in source
    assert 'raw_query = input_event_text(event, character_draft["tag_urls"])' in source
    assert 'ch_draft["tag_urls"] = raw_query' in source
    assert 'character_draft["tag_urls"] = raw_query' in source
    assert "query = raw_query.strip()" in source
    assert 'character_draft["tag_urls"] or character_draft["full_name"]' not in source
    assert "render_edit_suggestions()" not in source
    assert "render_edit_suggestions(event)" in source
    assert "render_suggestions(event)" in source
    assert source.index('ui.color_input("Color", value=character_draft["color"])') < source.index(
        'rich_tooltip("Refresh AO3 tags for this fandom"'
    ) < source.index('ui.button("Add Character", icon="add"')
    assert "fandom_key_value" in avatar_button_source
    assert "fandom_key_value" in avatar_dialog_source
    assert "color=character.color" in avatar_upload_source
    assert "reader_style=character.reader_style" in avatar_upload_source
    assert "str(result[\"avatar_color\"])" not in avatar_upload_source
    assert "self.refresh()" not in avatar_upload_source
    assert "rerender()" in avatar_upload_source


def test_reader_uses_character_font_overrides_without_mutating_global_font_size() -> None:
    read_source = inspect.getsource(AO3StudioShell._page_read)
    wheel_source = inspect.getsource(AO3StudioShell._handle_reader_font_wheel)
    adjust_source = inspect.getsource(AO3StudioShell._adjust_selected_character_font_size)
    save_source = inspect.getsource(AO3StudioShell._save_character_reader_style)
    scroll_source = inspect.getsource(AO3StudioShell._save_reader_scroll_position)
    restore_source = inspect.getsource(AO3StudioShell._restore_reader_scroll)
    theme_source = inspect.getsource(apply_theme)

    assert "_reader_font_style_for_character(style_settings, selected_character)" in read_source
    assert "on_scroll=lambda event, w=work.work_id, c=chapter_index: self._save_reader_scroll_position(w, c, event)" in read_source
    assert 'reader_scroll.classes(add="reader-scroll-restoring")' in read_source
    assert "self._restore_reader_scroll(s, p)" in read_source
    assert "scroll_area.scroll_to(percent=max(0.0, min(1.0" in restore_source
    assert "duration=0.0" in restore_source
    assert 's.classes(remove="reader-scroll-restoring")' in restore_source
    assert ".reader-panel-scroll.reader-scroll-restoring" in theme_source
    assert "opacity: 0" in theme_source.split(".reader-panel-scroll.reader-scroll-restoring", 1)[1].split(".reader-html-root", 1)[0]
    assert "result.scroll_percent" in read_source
    assert 'getattr(event, "vertical_percentage", 0.0)' in scroll_source
    assert "reader_service.set_position(work_id" in scroll_source
    assert wheel_source.index("_adjust_selected_character_font_size") < wheel_source.index("style_service.adjust_font_size")
    assert "reader_style.get(\"font_size_enabled\")" in adjust_source
    assert "reader_style[\"font_size\"] = next_size" in adjust_source
    assert "self.container.style_service.adjust_font_size" not in adjust_source
    assert "reader_style=reader_style" in save_source


def test_character_font_wheel_updates_character_size_not_global_style(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.save_profile(
        FandomProfile(
            fandom_key="lis",
            tag="Life is Strange",
            display_name="Life is Strange",
            color="#58a6ff",
            avatar_url=None,
            notes=None,
            default_filter={},
            created_at="",
            updated_at="",
            selected_at=None,
        )
    )
    container.fandom_service.select(profile.fandom_key)
    work = Work("reader", "https://archiveofourown.org/works/reader", title="Reader Work", chapters_current=1, last_scraped_at="2026-01-01T00:00:00Z")
    container.work_repo.upsert(work)
    container.reader_asset_repo.replace_document(
        ReaderAsset(
            work_id=work.work_id,
            source_format="html",
            source_url=work.ao3_url,
            download_url="https://archiveofourown.org/downloads/reader.html",
            content_hash="abc",
            downloaded_chapter_count=1,
            known_ao3_chapter_count=1,
            downloaded_at="2026-01-01T00:00:00Z",
            last_checked_at="2026-01-01T00:00:00Z",
        ),
        [
            ReaderChapter(
                work_id=work.work_id,
                chapter_index=1,
                title="One",
                ao3_url=work.ao3_url,
                anchor="chapter-1",
                html="<p>Max arrives.</p>",
                text_hash="h1",
            )
        ],
    )
    container.fandom_service.save_character(
        fandom_key=profile.fandom_key,
        character_id="max",
        name="Max",
        full_name="Maxine Caulfield",
        color="#58a6ff",
        reader_style={
            "font_family": "'Newsreader', serif",
            "custom_font_enabled": True,
            "font_size": 20.0,
            "font_size_enabled": True,
        },
    )
    container.style_service.save_global_settings({"preview_font_family": "'Source Code Pro', monospace", "reader_font_size": 16.5, "font_wheel_step_px": 1.0})
    shell = AO3StudioShell(container)
    shell.page = "Read"
    shell.selected_work_id = work.work_id
    container.preferences_service.set("reader_work_id", work.work_id)
    container.preferences_service.set(shell._reader_selected_character_key(work.work_id, 1), "max")

    shell._handle_reader_font_wheel(SimpleNamespace(args={"step": 1}))

    assert container.style_service.global_settings()["reader_font_size"] == 16.5
    [character] = container.fandom_service.list_characters(profile.fandom_key)
    assert character.reader_style["font_size"] == 21.0


def test_left_fandom_list_uses_persisted_search_and_full_width_rows() -> None:
    init_source = inspect.getsource(AO3StudioShell.__init__)
    left_source = inspect.getsource(AO3StudioShell._render_left)
    data_source = inspect.getsource(AO3StudioShell._left_data_panel)
    footer_source = inspect.getsource(AO3StudioShell._render_left_footer)
    render_source = inspect.getsource(AO3StudioShell._render_fandom_list)
    search_source = inspect.getsource(AO3StudioShell._handle_fandom_search)
    filter_source = inspect.getsource(AO3StudioShell._filtered_fandom_profiles)
    row_source = inspect.getsource(AO3StudioShell._fandom_row)
    select_source = inspect.getsource(AO3StudioShell._select_fandom_profile)
    set_page_source = inspect.getsource(AO3StudioShell._set_page)
    browse_state_source = inspect.getsource(AO3StudioShell._browse_filter_state)
    persist_browse_source = inspect.getsource(AO3StudioShell._persist_browse_state)
    create_source = inspect.getsource(AO3StudioShell._show_create_fandom_dialog)
    cleanup_source = (
        inspect.getsource(AO3StudioShell._toggle_fandom_cleanup)
        + inspect.getsource(AO3StudioShell._disarm_fandom_cleanup_delete)
        + inspect.getsource(AO3StudioShell._toggle_fandom_cleanup_selection)
        + inspect.getsource(AO3StudioShell._handle_fandom_cleanup_delete)
        + inspect.getsource(AO3StudioShell._show_fandom_cleanup_delete_dialog)
    )
    dialog_source = inspect.getsource(AO3StudioShell._show_fandom_dialog)
    analytics_source = inspect.getsource(AO3StudioShell._page_analytics)
    theme_source = inspect.getsource(apply_theme)

    split_source = inspect.getsource(AO3StudioShell._save_left_summary_split)

    assert "left_summary_split" in init_source
    assert "raw_left_summary_split" in init_source
    assert "0 if raw_left_summary_split <= 4 else raw_left_summary_split" in init_source
    assert "left_fandom_split" not in init_source
    assert "info_height" not in left_source
    assert "_save_left_summary_split" in left_source
    assert "cursor-row-resize" in left_source
    assert "summary_split = max(0, min(58, self.left_summary_split))" in left_source
    assert 'summary_style = f"height: {summary_split}%;" if summary_split else ""' in left_source
    assert "min-height: 64px" not in left_source
    assert "startHeight = top.getBoundingClientRect().height" in left_source
    assert "compactHeight = top.scrollHeight" in left_source
    assert "height <= compactHeight + 2" in left_source
    assert "applySplit" in left_source
    assert "splitFromEvent" in left_source
    assert "percentFromDelta" not in left_source
    assert "percentFromEvent" not in left_source
    assert "left_summary_split" in split_source
    assert "max(0, min(58, percent))" in split_source
    assert 'ui.label("Local Data")' not in data_source
    assert "identity_service.bootstrap" not in data_source
    assert 'ui.label(f"Fandom:' not in data_source
    assert 'ui.label("Recent")' not in data_source
    assert "recent_snapshots" not in data_source
    assert '"Works"' in data_source
    assert '"Cache"' in data_source
    assert '"Eval"' in data_source
    assert '"Queue"' in data_source
    assert "Works kept" not in data_source
    assert "Browse cache" not in data_source
    assert "work_library_service.count_for_fandom(active)" in data_source
    assert "work_library_service.cache_count_for_fandom(active)" in data_source
    assert "evaluation_service.count_for_fandom(active)" in data_source
    assert "queue_service.count_for_fandom(active.fandom_key)" in data_source
    assert "work_library_service.count()," not in data_source
    assert "work_library_service.cache_count()," not in data_source
    assert "evaluation_service.count()," not in data_source
    assert "#f59e0b" in data_source
    assert "text-xs text-gray-500" in data_source
    assert "text-sm font-bold" not in data_source
    assert 'ui.label(f"{label}:")' in data_source
    assert "RARITY_COLORS[RarityTier.COMMON]" in data_source
    assert "RARITY_COLORS[RarityTier.EPIC]" in data_source
    assert "RARITY_COLORS[RarityTier.RARE]" in data_source
    assert "LM:" in data_source
    assert "schema.name" in data_source
    assert "Schemas" in analytics_source
    assert "#f778ba" in analytics_source
    assert 'preferences_service.get("left_fandom_search", "")' in init_source
    assert 'ui.input("Search fandoms", value=self.left_fandom_search_text)' in render_source
    assert 'ui.label("Fandoms")' not in render_source
    assert "Create fandom" in render_source
    assert "self._show_create_fandom_dialog()" in render_source
    assert "self._show_fandom_dialog(None)" not in render_source
    assert "self._handle_fandom_search" in render_source
    assert 'preferences_service.set("left_fandom_search", self.left_fandom_search_text)' in search_source
    assert "self._refresh_fandom_rows()" in search_source
    assert "left-fandom-scroll w-full flex-grow min-h-0" in render_source
    assert "profile.display_name" in filter_source
    assert "profile.tag" in filter_source
    assert "short_fandom_name(profile.tag)" in filter_source
    assert "profile.fandom_key" in filter_source
    assert "_persist_fandom_page()" in select_source
    assert "_restore_fandom_page(profile.fandom_key)" in select_source
    assert 'self.page = "Browse"' not in select_source
    assert 'preferences_service.set("active_page", "Browse")' not in select_source
    assert "_persist_fandom_page(page)" in set_page_source
    assert "def _fandom_page_key" in inspect.getsource(AO3StudioShell._fandom_page_key)
    assert "def _browse_filter_state_key" in inspect.getsource(AO3StudioShell._browse_filter_state_key)
    assert 'f"active_page:{key}"' in inspect.getsource(AO3StudioShell._fandom_page_key)
    assert 'f"browse_filter_state:{key}"' in inspect.getsource(AO3StudioShell._browse_filter_state_key)
    assert "self._browse_filter_state_key(active.fandom_key)" in browse_state_source
    assert "legacy_fandom == active.tag" in browse_state_source
    assert "self._browse_filter_state_key(active.fandom_key)" in persist_browse_source
    assert "width: 100%; min-width: 100%; max-width: none;" in render_source
    assert "fandom-row w-full items-center gap-2 p-2 cursor-pointer no-wrap min-w-0" in row_source
    title_row_source = row_source.split('with ui.row().classes("w-full items-center gap-1 min-w-0"):', 1)[1].split(
        'ui.label(profile.tag)', 1
    )[0]
    assert 'icon="edit"' not in row_source
    assert 'ui.icon("more_horiz", size="16px")' in row_source
    assert "dark_button_color(profile.color)" in row_source
    assert "size=xs :ripple=false" in row_source
    assert "self.fandom_cleanup_mode" in row_source
    assert "_toggle_fandom_cleanup_selection" in row_source
    assert "more_horiz" not in title_row_source
    assert "cleaning_services" in footer_source
    assert "Return to active fandom browse" not in footer_source
    assert "self.fandom_cleanup_mode" in footer_source
    assert "self.fandom_cleanup_delete_armed" in cleanup_source
    assert "_show_fandom_cleanup_delete_dialog" in cleanup_source
    assert "Save Backup" in cleanup_source
    assert "Delete Fandom" in cleanup_source
    assert "fandom_service.suggest_fandoms" in create_source
    assert "suggest_fandom_tags" not in create_source
    assert "fandom_service.create_from_suggestion" in create_source
    assert 'ui.input("Search AO3 fandoms"' in create_source
    assert '.bind_value(draft, "query")' in create_source
    assert "schedule_suggestions_render" in create_source
    assert "ui.timer(0.03, render_suggestions, once=True)" in create_source
    assert "width: 560px; max-width: 94vw; height: 85vh" in create_source
    assert "_show_fandom_directory_cache_dialog" in create_source
    assert 'icon="travel_explore"' in create_source
    assert "suggestion.color" in create_source
    assert 'ui.button("Create", icon="add"' in create_source
    directory_source = inspect.getsource(AO3StudioShell._show_fandom_directory_cache_dialog)
    assert "ensure_fandom_directory_sources" in directory_source
    assert "cache_fandom_directory_sources" in directory_source
    assert "refresh_fandom_directory_sources" in directory_source
    assert "delete_fandom_directory_cache" in directory_source
    assert "ui.context_menu" in directory_source
    assert "Cache Selected" in directory_source
    assert "update_fandom_directory_source" in directory_source
    assert 'icon="check_box" if enabled else "check_box_outline_blank"' in directory_source
    assert "not bool(s.enabled)" in directory_source
    assert '"update:model-value"' not in directory_source
    assert "export_current_fandom" in dialog_source
    assert "open_fandom_backup_import_dialog" in dialog_source
    assert 'ui.button(icon="archive")' in dialog_source
    assert 'ui.button(icon="upload_file")' in dialog_source
    assert ".fandom-row {" in theme_source
    assert ".fandom-row.cleanup-select-row" in theme_source
    assert ".fandom-row.cleanup-row-selected" in theme_source
    assert ".left-fandom-scroll .q-scrollarea__content" in theme_source
    assert "align-self: stretch;" in theme_source
    assert "box-sizing: border-box;" in theme_source
    assert "width: 100%;" in theme_source


def test_no_archive_warnings_are_hidden_from_warning_groups() -> None:
    assert AO3StudioShell._is_no_archive_warning("No Archive Warnings Apply")
    assert not AO3StudioShell._is_no_archive_warning("Graphic Depictions Of Violence")


def test_schema_studio_parameter_colors_and_rounded_expanded_pills_exist() -> None:
    state_source = inspect.getsource(AO3StudioShell._schema_studio_state)
    save_source = inspect.getsource(AO3StudioShell._save_schema_studio_state)
    dialog_source = inspect.getsource(AO3StudioShell._show_schema_studio_dialog)
    theme_source = inspect.getsource(apply_theme)

    assert 'parameter["color"] = self._normalize_hex' in state_source
    assert '"color": parameter_colors.get(parameter_id, "")' in state_source
    assert '"color": ""' in state_source
    assert "raw_parameter_color" in save_source
    assert "color must be a hex color" in save_source
    assert '"parameter_colors"' in save_source
    assert 'ui_rules["parameter_colors"] = parameter_colors' in save_source
    assert 'return self._normalize_hex(str(parameter.get("color") or "")) or (' in dialog_source
    assert 'ui.color_input("Color", value=item.get("color") or color)' in dialog_source
    parameter_expanded_source = dialog_source.split('if item_id in expanded_parameters:', 1)[1].split("else:", 1)[0]
    assert parameter_expanded_source.index('ui.input("Parameter"') < parameter_expanded_source.index('ui.color_input("Color", value=item.get("color") or color)')
    parameter_color_source = parameter_expanded_source.split(
        'ui.color_input("Color", value=item.get("color") or color)', 1
    )[1].split('with ui.row().classes("w-full items-center gap-3 flex-wrap")', 1)[0]
    assert '"dark dense outlined"' in parameter_color_source
    assert '.classes("w-36")' in parameter_color_source
    assert "schema-parameter-color-input" not in parameter_color_source
    assert "hide-bottom-space" not in parameter_color_source
    assert parameter_expanded_source.index('ui.label(_impact_label') < parameter_expanded_source.index('ui.button(icon="expand_less")')
    schema_expanded_source = dialog_source.split("if schema_id in expanded_schemas:", 1)[1].split("else:", 1)[0]
    assert schema_expanded_source.count('icon="open_in_full"') == 1
    assert 'ui.button("Open editor", icon="open_in_full")' not in schema_expanded_source
    assert schema_expanded_source.index('ui.input("Schema"') < schema_expanded_source.index('ui.color_input("Color", value=schema.get("color") or schema_color)')
    assert ".schema-expanded-pill" in theme_source
    assert "border-radius: 8px !important;" in theme_source
    assert "schema-parameter-color-input" not in theme_source


def test_common_rarity_keeps_visible_static_border_even_when_gradients_are_enabled() -> None:
    static_classes, static_style = AO3StudioShell._rarity_border_style(
        RarityTier.COMMON,
        {"border_thickness": 2, "gradient_border_enabled": False},
    )
    gradient_classes, gradient_style = AO3StudioShell._rarity_border_style(
        RarityTier.COMMON,
        {"border_thickness": 2, "gradient_border_enabled": True, "gradient_border_mode": "twin"},
    )

    assert static_classes == ""
    assert "rgba(100,116,139,0.68)" in static_style
    assert gradient_classes == ""
    assert "rgba(100,116,139,0.68)" in gradient_style


def test_work_card_open_reveal_primes_contents_without_delayed_flash() -> None:
    click_js = AO3StudioShell._work_card_click_js()
    hydrate_branch = click_js.split("if (needsHydration) {", 1)[1].split("const expandedAbove =", 1)[0]

    assert "primeOpenInner" in click_js
    assert "nextPanelOpenToken" in click_js
    assert "inline-work-panel-unhydrated" in click_js
    assert "hydrate: true" in click_js
    assert "ao3HydrateOpenToken" in hydrate_branch
    assert "inline-work-panel-pending" in hydrate_branch
    assert "closeCard(other)" not in hydrate_branch
    assert "const frame = (callback)" in click_js
    assert "frame(() => {" in click_js
    assert "hydrating: true" not in click_js
    assert "delay: 42" not in click_js
    assert "blur(1.8px)" not in click_js
    assert "startHeight > 12 ? '1' : '0'" not in click_js
    assert "startHeight > 12 ? 1 : 0," not in click_js


def test_tab_switch_renders_center_without_rebuilding_left_panel() -> None:
    source = inspect.getsource(AO3StudioShell._set_page)

    assert "self.refresh()" not in source
    assert "self._render_center()" in source
    assert "self._render_top()" in source
    assert "self._render_right_header()" in source
    assert "self._render_right()" in source
    assert "self._render_left_footer()" in source
    assert "self._render_left()" not in source


def test_local_ao3_date_sort_keys_are_chronological_for_display_dates() -> None:
    newer = Work(
        "newer",
        "https://archiveofourown.org/works/newer",
        title="Newer",
        published_at="08 Jan 2026",
        last_ao3_updated_at="08 Jan 2026",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    older = Work(
        "older",
        "https://archiveofourown.org/works/older",
        title="Older",
        published_at="31 Dec 2025",
        last_ao3_updated_at="31 Dec 2025",
        last_scraped_at="2026-01-09T00:00:00Z",
    )
    undated_update = Work(
        "oneshot",
        "https://archiveofourown.org/works/oneshot",
        title="Oneshot",
        published_at="07 Jan 2026",
        last_ao3_updated_at=None,
        last_scraped_at="2026-06-01T00:00:00Z",
    )

    by_updated = sorted([older, newer], key=lambda work: AO3StudioShell._work_sort_value(work, "revised_at"), reverse=True)
    by_posted = sorted([older, newer], key=lambda work: AO3StudioShell._work_sort_value(work, "created_at"), reverse=True)

    assert [work.work_id for work in by_updated] == ["newer", "older"]
    assert [work.work_id for work in by_posted] == ["newer", "older"]
    assert AO3StudioShell._work_sort_value(undated_update, "revised_at").startswith("2026-01-07")


def test_browse_lazy_panel_and_lightweight_tag_markers_exist() -> None:
    placeholder_source = inspect.getsource(AO3StudioShell._inline_work_panel_placeholder)
    tag_source = inspect.getsource(AO3StudioShell._render_lightweight_tag_pill)
    hydrate_method_source = inspect.getsource(AO3StudioShell._hydrate_work_panel)
    hydrate_source = inspect.getsource(AO3StudioShell._animate_hydrated_work_panel)

    assert "inline-work-panel-unhydrated" in placeholder_source
    assert "aria-hidden=true inert" in placeholder_source
    assert "_inline_work_panel_slots[work_id]" in placeholder_source
    assert "ui.element(\"button\")" in tag_source
    assert "_open_tag_action_dialog" in tag_source
    assert "ui.button" not in tag_source
    assert "ui.menu" not in tag_source
    assert "self._render_center()" not in hydrate_method_source
    assert "panel_slot.clear()" in hydrate_method_source
    assert "_inline_work_panel_contents" in hydrate_method_source
    assert "restoreHydrationScroll" not in hydrate_source
    assert "restore.scrollTop" not in hydrate_source
    assert "expectedToken" in hydrate_source
    assert "watchOpenPanel" in hydrate_source
    assert "closeCard(other)" in hydrate_source
    assert "removeAttribute('inert')" in hydrate_source


def test_browse_tag_dialog_close_does_not_save_unchanged_default_color() -> None:
    dialog_source = inspect.getsource(AO3StudioShell._open_tag_action_dialog)
    menu_source = inspect.getsource(AO3StudioShell._render_tag_pill)
    finalize_source = dialog_source.split("def finalize_dialog() -> None:", 1)[1].split('dialog.on("hide"', 1)[0]

    assert 'saved = {"color": override_color or favorite_color or color, "dirty": False}' in dialog_source
    assert 'saved = {"color": override_color or favorite_color or color, "dirty": False}' in menu_source
    assert "auto_save_color" not in finalize_source
    assert "self.refresh()" in finalize_source


def test_cluster_pills_use_compact_tag_style_and_dialog() -> None:
    side_source = inspect.getsource(AO3StudioShell._render_batch_side_panel)
    pill_source = inspect.getsource(AO3StudioShell._render_cluster_pill)
    schema_pill_source = inspect.getsource(AO3StudioShell._render_schema_slot_pill)
    status_source = inspect.getsource(AO3StudioShell._render_selected_schema_status)
    filter_source = inspect.getsource(AO3StudioShell._render_cluster_filter_panel)
    evaluated_filter_source = inspect.getsource(AO3StudioShell._render_evaluated_filter_panel)
    works_side_source = inspect.getsource(AO3StudioShell._render_works_side_panel)
    cluster_sort_source = inspect.getsource(AO3StudioShell._render_cluster_sort_pills)
    browse_sort_source = inspect.getsource(AO3StudioShell._render_sort_pills)
    segmented_source = inspect.getsource(AO3StudioShell._segmented_cluster_pills)
    browse_source = inspect.getsource(AO3StudioShell._render_browse_lookup_panel)
    browse_direction_source = inspect.getsource(AO3StudioShell._render_browse_sort_direction_pills)
    cluster_state_source = inspect.getsource(AO3StudioShell._cluster_filter_state)
    cluster_apply_source = inspect.getsource(AO3StudioShell._apply_cluster_filters)
    cluster_set_sort_source = inspect.getsource(AO3StudioShell._set_cluster_sort)
    cluster_set_scalar_source = inspect.getsource(AO3StudioShell._set_cluster_scalar)
    cluster_filter_works_source = inspect.getsource(AO3StudioShell._filter_cluster_works)
    dialog_source = inspect.getsource(AO3StudioShell._open_cluster_action_dialog)
    cleanup_source = inspect.getsource(AO3StudioShell._render_cluster_cleanup_toolbar)
    header_source = inspect.getsource(AO3StudioShell._render_right_header)
    right_source = inspect.getsource(AO3StudioShell._render_right)
    top_source = inspect.getsource(AO3StudioShell._render_top)
    cleanup_handler_source = inspect.getsource(AO3StudioShell._handle_cluster_cleanup_trash)
    theme_source = inspect.getsource(apply_theme)
    cleanup_theme_source = theme_source.split(".right-panel-cleanup-host", 1)[1].split(".right-panel-search", 1)[0]
    cluster_hover_source = theme_source.split(".cluster-pill {", 1)[1].split(".browse-tag-pill-label", 1)[0]

    assert "Queue Clusters" not in side_source
    assert "Evaluated Clusters" not in side_source
    assert "Delete Evaluated Batch" not in side_source
    assert "w-full justify-start mt-2" not in side_source
    assert "visible_summaries" not in side_source
    assert "_cluster_summaries_for_mode" in side_source
    assert "right-panel-cleanup-content" in side_source
    assert "right-panel-cleanup-header" not in side_source
    assert "_render_cluster_cleanup_toolbar(mode" not in side_source
    assert "_render_cluster_cleanup_toolbar(\"queue\"" in header_source
    assert "_render_cluster_cleanup_toolbar(\"evaluated\"" in header_source
    assert "right-panel-header-hit" in header_source
    assert "_disarm_cluster_cleanup(\"queue\")" in header_source
    assert "_disarm_cluster_cleanup(\"evaluated\")" in header_source
    assert "right-panel-shell w-full h-full min-h-0 panel-bg overflow-hidden gap-0" in inspect.getsource(
        AO3StudioShell.build
    )
    assert 'self.page in {"Queue", "Evaluated"}' in right_source
    assert 'right-panel-batch-mode h-full min-h-full gap-0 p-0' in right_source
    assert ".right-panel-column.right-panel-batch-mode" in theme_source
    assert "height: 100% !important" in theme_source.split(".right-panel-column.right-panel-batch-mode", 1)[1].split(
        ".right-panel-cleanup-host",
        1,
    )[0]
    assert "right-panel-cleanup-host w-full h-full flex-grow" in side_source
    assert "right-panel-cleanup-content w-full h-full flex-grow gap-2" in side_source
    assert ".right-panel-scroll .q-scrollarea__content" in theme_source
    assert "padding: 0 !important" in theme_source.split(".right-panel-scroll .q-scrollarea__content", 1)[1].split(
        ".right-panel-column",
        1,
    )[0]
    assert "calc(100vh" not in cleanup_theme_source
    assert "padding: 4px 12px 12px !important" in cleanup_theme_source
    assert "self._render_schema_slot_pill" in side_source
    assert "self._render_selected_schema_status" in side_source
    assert 'ui.element("button")' in pill_source
    assert "work-tag-pill browse-tag-pill cluster-pill" in pill_source
    assert "cluster-pill-selected" in pill_source
    assert "rgba(255,255,255,0.42)" not in pill_source
    assert "_filter_pill_style(color, selected or cleanup_selected)" in pill_source
    assert "_tag_pill_style" not in pill_source
    assert ".cluster-pill:hover" in theme_source
    assert "filter: brightness(1.14)" in theme_source
    assert "translateY" not in cluster_hover_source
    assert "contextmenu" in pill_source
    assert "_open_cluster_action_dialog" in pill_source
    assert "filter-favorite-pill schema-slot-pill" in schema_pill_source
    assert "_schema_slot_color" in schema_pill_source
    assert "_handle_schema_slot_click" in schema_pill_source
    assert "cleaning_services" in cleanup_source
    assert "delete" in cleanup_source
    assert '"click.stop"' in cleanup_source
    assert "_render_cluster_cleanup_toolbar(\"queue\"" not in top_source
    assert "_render_cluster_cleanup_toolbar(\"evaluated\"" not in top_source
    assert "ui.label(\"Evaluation Queue\")" not in top_source
    assert "ui.label(\"Evaluated\")" not in top_source
    assert "clean_queue_schema_slot" in cleanup_handler_source
    assert "clean_queue_clusters" in cleanup_handler_source
    assert "clean_evaluated_schema_slot" in cleanup_handler_source
    assert "clean_evaluated_clusters" in cleanup_handler_source
    assert "soft-panel" not in status_source
    assert "Search cluster" in filter_source
    assert "search_label" in filter_source
    cluster_apply_row = filter_source.split("self._render_cluster_sort_pills", 1)[0]
    assert 'icon="refresh"' in cluster_apply_row
    assert "right-panel-icon-button" in cluster_apply_row
    assert "filter_alt" not in cluster_apply_row
    assert 'sort_mode="ao3"' in filter_source
    assert "Queue Sort and Filter" not in filter_source
    assert "Local AO3 Sort and Filter" not in filter_source
    assert "ui.label(title)" not in filter_source
    assert '"Direction"' not in filter_source
    assert '"Direction"' not in cluster_sort_source
    filter_body = filter_source.split('with ui.element("div").classes("soft-panel w-full p-3"):', 1)[1]
    assert filter_body.index('"Desc"') < filter_body.index("search_label")
    assert AO3_METADATA_SORT_PILLS == [
        ("revised_at", "Updated"),
        ("word_count", "Word Count"),
        ("bookmarks_count", "Bookmarks"),
        ("kudos_count", "Kudos"),
        ("hits", "Hits"),
        ("comments_count", "Comments"),
        ("authors_to_sort_on", "Creator"),
        ("title_to_sort_on", "Title"),
        ("created_at", "Posted"),
    ]
    assert "AO3_METADATA_SORT_PILLS" in cluster_sort_source
    assert "AO3_METADATA_SORT_PILLS" in browse_sort_source
    assert "_metadata_options" not in browse_sort_source
    assert "Evaluation Sort and Filter" not in evaluated_filter_source
    assert '"Order"' not in evaluated_filter_source
    assert evaluated_filter_source.index('"High"') < evaluated_filter_source.index('label="Score"')
    evaluated_apply_row = evaluated_filter_source.split('ui.input("Min"', 1)[0]
    assert 'icon="refresh"' in evaluated_apply_row
    assert "right-panel-icon-button" in evaluated_apply_row
    assert "filter_alt" not in evaluated_apply_row
    assert "Apply evaluated score filters" in evaluated_apply_row
    assert 'sort_mode="score"' in evaluated_filter_source
    assert '"sort_mode"' in cluster_state_source
    assert "state[\"sort_mode\"] = sort_mode" in cluster_apply_source
    assert 'sort_mode="ao3"' in cluster_set_sort_source
    assert 'key == "score_dir"' in cluster_set_scalar_source
    assert 'key == "sort_dir"' in cluster_set_scalar_source
    assert 'sort_mode == "score"' in cluster_filter_works_source
    assert "cluster-filter-segmented-row" in segmented_source
    assert "if label:" in segmented_source
    assert ".cluster-filter-segmented-row" in theme_source
    assert ".filter-sort-row {" in theme_source
    assert ".filter-page-row {" in theme_source
    assert "margin-bottom: 8px !important" in theme_source
    assert "Sort and Filter" not in browse_source
    assert browse_source.count('classes("soft-panel') == 1
    assert "right-panel-three-icon-grid" in browse_source
    assert ".right-panel-three-icon-grid" in theme_source
    assert browse_source.index("Apply search and filters") < browse_source.index(
        "Save current filters as this fandom's defaults"
    )
    assert browse_source.index("Save current filters as this fandom's defaults") < browse_source.index(
        "Open current AO3 page in your browser"
    )
    assert "_render_browse_sort_direction_pills" in browse_source
    assert "filter_alt" not in browse_source
    assert 'rich_tooltip("Apply filters"' not in browse_source
    assert '"sort_direction"' in browse_direction_source
    assert '"Desc"' in browse_direction_source
    assert '"Asc"' in browse_direction_source
    assert "filter-page-direction-row" in browse_direction_source
    assert ".filter-page-direction-row .q-btn" in theme_source
    assert 'ui.expansion("AO3 Metadata Filters"' in works_side_source
    assert "_render_cluster_filter_panel(" in works_side_source
    assert 'search_label="Search works"' in works_side_source
    assert "_set_works_metadata_open" in works_side_source
    assert "update_cluster_metadata" in dialog_source
    assert 'name=str(draft.get("name") or "")' in dialog_source
    assert 'ui.input("Queue name"' in dialog_source
    assert "schema_options_for_work_set" in dialog_source
    assert "requeue_work_set_under_schema" in dialog_source


def test_queue_evaluated_and_works_use_cached_lazy_work_render_models() -> None:
    queue_source = inspect.getsource(AO3StudioShell._page_queue)
    evaluated_source = inspect.getsource(AO3StudioShell._page_evaluated)
    works_source = inspect.getsource(AO3StudioShell._page_works)
    render_source = inspect.getsource(AO3StudioShell._render_work_list)
    queue_work_source = inspect.getsource(AO3StudioShell._queue_work)
    queue_dialog_source = inspect.getsource(AO3StudioShell._show_queue_work_dialog)
    hydrate_handler_source = inspect.getsource(AO3StudioShell._handle_work_card_body_click)
    hydrate_source = inspect.getsource(AO3StudioShell._hydrate_work_panel)
    invalidation_source = inspect.getsource(AO3StudioShell._invalidate_browse_page_model)
    summaries_source = inspect.getsource(AO3StudioShell._cluster_summaries_for_mode)

    assert "_cluster_summaries_for_mode(\"queue\")" in queue_source
    assert "if not self.selected_queue_cluster_id:" in queue_source
    assert "if not self.selected_queue_schema_key:" in queue_source
    assert "_cluster_page_model_for_mode(\"queue\"" in queue_source
    assert "pending_works_for_batch" not in queue_source
    assert "render_model=model" in queue_source
    assert "lazy_panels=True" in queue_source
    assert "show_queue_action=False" in queue_source
    assert "_cluster_summaries_for_mode(\"evaluated\")" in evaluated_source
    assert "if not self.selected_evaluated_cluster_id:" in evaluated_source
    assert "if not self.selected_evaluated_schema_key:" in evaluated_source
    assert "_cluster_page_model_for_mode(\"evaluated\"" in evaluated_source
    assert "evaluated_works_for_batch" not in evaluated_source
    assert "render_model=model" in evaluated_source
    assert "lazy_panels=True" in evaluated_source
    assert "show_queue_action=False" in evaluated_source
    assert "_works_page_model_for_current_state()" in works_source
    assert "list_collected" not in works_source
    assert '_filter_cluster_works(model.works, model, "works")' in works_source
    assert "lazy_panels=True" in works_source
    assert "lookup_model = browse_model or render_model" in render_source
    assert "show_queue_action: bool = True" in render_source
    assert "if show_queue_action:" in render_source
    assert "_show_queue_work_dialog(work_id, button)" in queue_work_source
    assert "queue_service.enqueue" not in queue_work_source
    assert "queue_work_to_named_cluster" in queue_dialog_source
    assert "cluster_targets" in queue_dialog_source
    assert '"Queue name"' in queue_dialog_source
    assert "Manual Queue" not in queue_dialog_source
    assert "lightweight=browse_actions or lazy_panels" in render_source
    assert "self.container.rarity_service.get(work.work_id)" in render_source
    assert "if lookup_model" in render_source
    assert "hydrate and desired == \"open\"" in hydrate_handler_source
    assert "self.page == \"Browse\"" not in hydrate_handler_source
    assert "_current_work_render_model()" in hydrate_source
    assert "_queue_page_model = None" in invalidation_source
    assert "_batch_summaries_cache.clear()" in invalidation_source
    assert "list_clusters_with_schema_slots" in summaries_source
    assert "\"cluster-slots\"" in summaries_source


def test_queue_runner_controls_and_api_settings_exist() -> None:
    top_source = inspect.getsource(AO3StudioShell._render_top)
    footer_source = inspect.getsource(AO3StudioShell._render_left_footer)
    config_source = inspect.getsource(AO3StudioShell._show_queue_eval_config_dialog)
    settings_source = inspect.getsource(AO3StudioShell._show_settings_dialog)
    api_source = inspect.getsource(AO3StudioShell._page_api_settings)

    assert "_toggle_queue_evaluation_run" in top_source
    assert "play_arrow" in top_source
    assert "stop_circle" in top_source
    assert "_queue_run_available" in top_source
    assert "psychology" in footer_source
    assert "rule_settings" not in footer_source
    assert "action-separator" in footer_source
    assert "_show_queue_eval_config_dialog" in footer_source
    assert "Queue Evaluation" in config_source
    assert "width: 560px" in config_source
    assert "height: 85vh" in config_source
    assert "border-b border-gray-700" in config_source
    assert "border-t border-gray-700" in config_source
    assert "soft-panel" in config_source
    assert "Start chapter" in config_source
    assert "Target words" in config_source
    assert 'ui.tab("API"' in settings_source
    assert "_page_api_settings" in settings_source
    assert "available_model_details" in api_source
    assert "load_selected_model" in api_source
    assert "unload_selected_model" in api_source


def test_unrated_work_gets_no_rarity_border_until_common_is_assigned(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        "unrated",
        "https://archiveofourown.org/works/unrated",
        title="Unrated",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(work)
    shell = AO3StudioShell(container)
    style = {"border_thickness": 2, "gradient_border_enabled": True, "gradient_border_mode": "twin"}

    assert shell._rarity_border_for_work(work.work_id, style) == ("", "")

    container.rarity_service.set_manual(work.work_id, RarityTier.COMMON)

    classes, inline_style = shell._rarity_border_for_work(work.work_id, style)
    assert classes == ""
    assert "rgba(100,116,139,0.68)" in inline_style
