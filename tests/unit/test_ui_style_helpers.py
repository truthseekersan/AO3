from __future__ import annotations

import inspect

from app.application.composition import build_container
from app.domain.entities import Work
from app.domain.enums import RarityTier
from app.presentation.ui.app_shell import FONT_CATEGORIES, FONT_COLORS, AO3StudioShell


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


def test_no_archive_warnings_are_hidden_from_warning_groups() -> None:
    assert AO3StudioShell._is_no_archive_warning("No Archive Warnings Apply")
    assert not AO3StudioShell._is_no_archive_warning("Graphic Depictions Of Violence")


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
    assert "self._render_right()" in source
    assert "self._render_left_footer()" in source
    assert "self._render_left()" not in source


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
    dialog_source = inspect.getsource(AO3StudioShell._open_cluster_action_dialog)
    cleanup_source = inspect.getsource(AO3StudioShell._render_evaluated_cleanup_toolbar)

    assert "Queue Clusters" not in side_source
    assert "Evaluated Clusters" not in side_source
    assert "Delete Evaluated Batch" not in side_source
    assert "w-full justify-start mt-2" not in side_source
    assert "visible_summaries" not in side_source
    assert "_cluster_summaries_for_mode" in side_source
    assert "self._render_schema_slot_pill" in side_source
    assert "self._render_selected_schema_status" in side_source
    assert 'ui.element("button")' in pill_source
    assert "work-tag-pill browse-tag-pill cluster-pill" in pill_source
    assert "cluster-pill-selected" in pill_source
    assert "_tag_pill_style" in pill_source
    assert "contextmenu" in pill_source
    assert "_open_cluster_action_dialog" in pill_source
    assert "filter-favorite-pill schema-slot-pill" in schema_pill_source
    assert "_schema_slot_color" in schema_pill_source
    assert "_handle_schema_slot_click" in schema_pill_source
    assert "cleaning_services" in cleanup_source
    assert "delete" in cleanup_source
    assert "soft-panel" not in status_source
    assert "Search cluster" in filter_source
    assert "filter_alt" in filter_source.split("self._render_cluster_sort_pills", 1)[0]
    assert "update_cluster_metadata" in dialog_source
    assert "schema_options_for_work_set" in dialog_source
    assert "requeue_work_set_under_schema" in dialog_source


def test_queue_evaluated_and_works_use_cached_lazy_work_render_models() -> None:
    queue_source = inspect.getsource(AO3StudioShell._page_queue)
    evaluated_source = inspect.getsource(AO3StudioShell._page_evaluated)
    works_source = inspect.getsource(AO3StudioShell._page_works)
    render_source = inspect.getsource(AO3StudioShell._render_work_list)
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
    assert "_cluster_summaries_for_mode(\"evaluated\")" in evaluated_source
    assert "if not self.selected_evaluated_cluster_id:" in evaluated_source
    assert "if not self.selected_evaluated_schema_key:" in evaluated_source
    assert "_cluster_page_model_for_mode(\"evaluated\"" in evaluated_source
    assert "evaluated_works_for_batch" not in evaluated_source
    assert "render_model=model" in evaluated_source
    assert "lazy_panels=True" in evaluated_source
    assert "_works_page_model_for_current_state()" in works_source
    assert "list_collected" not in works_source
    assert "lazy_panels=True" in works_source
    assert "lookup_model = browse_model or render_model" in render_source
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
