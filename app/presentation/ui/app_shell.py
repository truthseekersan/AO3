from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, unquote, urlparse

from bs4 import BeautifulSoup, NavigableString
from nicegui import background_tasks, context, events, run, ui

from app.application.composition import ApplicationContainer
from app.application.dto import ServiceResult
from app.application.services import (
    DEFAULT_FANDOM,
    default_fandom_filter,
    fandom_key,
    normalize_ao3_date_filter,
    normalize_ao3_sort_column,
    normalize_word_count_filter,
    short_fandom_name,
    utc_now_iso,
)
from app.domain.entities import (
    BrowseSnapshot,
    CharacterProfile,
    Evaluation,
    EvaluationSchema,
    FandomProfile,
    ScoreDimension,
    ScoreRange,
    Work,
    WorkRarity,
    WorkTag,
)
from app.domain.enums import (
    AuthState,
    EvaluationStatus,
    OverlayVisibility,
    QueueStatus,
    RarityTier,
    RemoteRole,
    RuntimeMode,
    ScorePolarity,
    TagType,
)
from app.infrastructure import images
from app.presentation.ui.theme import (
    dark_button_color,
    glow_text,
    normalized_label_color,
    rgb_from_hex,
    rich_tooltip,
    wash_background,
)

WORKSPACE_TABS = [
    ("Browse", "travel_explore"),
    ("Works", "library_books"),
    ("Read", "menu_book"),
    ("Queue", "playlist_add_check"),
    ("Evaluated", "fact_check"),
    ("Analytics", "query_stats"),
]
OPTIONAL_TABS = [("Shared", "groups"), ("Admin", "admin_panel_settings")]
AO3_LANGUAGE_FILTERS = [
    ("", "Any"),
    ("en", "English"),
    ("ru", "Russian"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
]
AO3_METADATA_SORT_PILLS = [
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
TAG_TYPE_ORDER = [
    TagType.RATING,
    TagType.WARNING,
    TagType.CATEGORY,
    TagType.FANDOM,
    TagType.RELATIONSHIP,
    TagType.CHARACTER,
    TagType.FREEFORM,
    TagType.OTHER,
]
TAG_TYPE_COLORS = {
    TagType.RATING: "#fbbf24",
    TagType.WARNING: "#fb7185",
    TagType.CATEGORY: "#a78bfa",
    TagType.FANDOM: "#58a6ff",
    TagType.RELATIONSHIP: "#f472b6",
    TagType.CHARACTER: "#7ee787",
    TagType.FREEFORM: "#2dd4bf",
    TagType.OTHER: "#94a3b8",
}
FILTER_GROUP_COLORS = {
    "ratings": TAG_TYPE_COLORS[TagType.RATING],
    "rating": TAG_TYPE_COLORS[TagType.RATING],
    "warnings": TAG_TYPE_COLORS[TagType.WARNING],
    "warning": TAG_TYPE_COLORS[TagType.WARNING],
    "categories": TAG_TYPE_COLORS[TagType.CATEGORY],
    "category": TAG_TYPE_COLORS[TagType.CATEGORY],
    "fandoms": TAG_TYPE_COLORS[TagType.FANDOM],
    "fandom": TAG_TYPE_COLORS[TagType.FANDOM],
    "relationships": TAG_TYPE_COLORS[TagType.RELATIONSHIP],
    "relationship": TAG_TYPE_COLORS[TagType.RELATIONSHIP],
    "characters": TAG_TYPE_COLORS[TagType.CHARACTER],
    "character": TAG_TYPE_COLORS[TagType.CHARACTER],
    "freeforms": TAG_TYPE_COLORS[TagType.FREEFORM],
    "additional tags": TAG_TYPE_COLORS[TagType.FREEFORM],
    "freeform": TAG_TYPE_COLORS[TagType.FREEFORM],
}
FONT_CATEGORIES = {
    "monospace": {
        "color": "#f2a979",
        "fonts": {
            "'Maple Mono', monospace": "Maple Mono | monospace",
            "'Source Code Pro', monospace": "Source Code Pro | monospace",
            "'Fira Code', monospace": "Fira Code | monospace",
            "'Cascadia Mono', monospace": "Cascadia Mono | monospace",
            "'Sono', monospace": "Sono | monospace",
            "'M PLUS Code', monospace": "M PLUS Code | monospace",
            "'iA Writer Quattro S', monospace": "iA Writer Quattro | proportional",
            "'Atkinson Hyperlegible Mono', monospace": "Atkinson Hyperlegible Mono | monospace",
            "'DM Mono Light', monospace": "Darkmode Mono | monospace",
            "'Recursive', monospace": "Recursive Mono | monospace",
            "'Space Mono', monospace": "Space Mono | monospace",
            "'Martian Mono', monospace": "Martian Mono | monospace",
            "'Monaspace Krypton', monospace": "Monaspace Krypton | monospace",
            "'Monaspace Neon', monospace": "Monaspace Neon | monospace",
            "'Monaspace Argon', monospace": "Monaspace Argon | monospace",
            "'Monaspace Xenon', monospace": "Monaspace Xenon | monospace",
            "'Reddit Mono', monospace": "Reddit Mono | monospace",
        },
    },
    "serif": {
        "color": "#b89576",
        "fonts": {
            "'Charter', serif": "Charter | serif",
            "'Loretta Light', 'Loretta', serif": "Loretta | serif",
            "'Fraunces', serif": "Fraunces | serif",
            "'Newsreader', serif": "Newsreader | serif",
        },
    },
    "handwritten": {
        "color": "#c084fc",
        "fonts": {
            "'Cause Light', cursive": "Cause Light | handwritten",
            "'Coming Soon', cursive": "Coming Soon | handwritten",
            "'Kalam Light', cursive": "Kalam Light | handwritten",
            "'Architects Daughter', cursive": "Architects Daughter | handwritten",
            "'Merienda', cursive": "Merienda | handwritten",
            "'Shantell Sans', cursive": "Shantell Sans | handwritten",
            "'Neucha', cursive": "Neucha | handwritten",
            "'Caveat', cursive": "Caveat | handwritten",
            "'Gaegu', cursive": "Gaegu | handwritten",
            "'Reenie Beanie', cursive": "Reenie Beanie | handwritten",
        },
    },
}
FONT_COLORS = {
    "'Source Code Pro', monospace": "#00E5CC",
    "'Maple Mono', monospace": "#f2a979",
    "'Fira Code', monospace": "#F5A623",
    "'Cascadia Mono', monospace": "#7EC8E3",
    "'Space Mono', monospace": "#4DBFA8",
    "'Monaspace Argon', monospace": "#cdd417",
    "'Sono', monospace": "#b5b5b0",
    "'Reddit Mono', monospace": "#e39191",
    "'iA Writer Quattro S', monospace": "#799c7f",
    "'Atkinson Hyperlegible Mono', monospace": "#e34f6a",
    "'DM Mono Light', monospace": "#9B5CF6",
    "'Recursive', monospace": "#1ec718",
    "'Monaspace Neon', monospace": "#38d2fc",
    "'Martian Mono', monospace": "#FF6B2B",
    "'Monaspace Krypton', monospace": "#1fbddb",
    "'Monaspace Xenon', monospace": "#6bbf8d",
    "'M PLUS Code', monospace": "#38ff84",
    "'Charter', serif": "#b37d64",
    "'Loretta Light', 'Loretta', serif": "#d6b274",
    "'Fraunces', serif": "#8fb2c7",
    "'Newsreader', serif": "#788fff",
    "'Cause Light', cursive": "#B09FD8",
    "'Coming Soon', cursive": "#c084fc",
    "'Kalam Light', cursive": "#dbdaa4",
    "'Architects Daughter', cursive": "#de8666",
    "'Reenie Beanie', cursive": "#e86fce",
    "'Merienda', cursive": "#9ee6c8",
    "'Shantell Sans', cursive": "#f28acc",
    "'Neucha', cursive": "#a175ff",
    "'Caveat', cursive": "#52abff",
    "'Gaegu', cursive": "#a1e65c",
}
GRADIENT_MODE_LABELS = [
    ("single", "Single"),
    ("twin", "Twin"),
    ("duotone", "Duotone"),
    ("tritone", "Tritone"),
    ("clash", "Clash"),
    ("traffic", "Traffic"),
    ("glitch", "Glitch"),
    ("wildcard", "Wildcard"),
    ("ignition", "Ignition"),
    ("reverse", "Reverse"),
    ("sonar", "Sonar"),
    ("overload", "Overload"),
    ("nebula", "Nebula"),
    ("abyss", "Abyss"),
]
RARITY_LABELS = {
    RarityTier.COMMON: "Common",
    RarityTier.UNCOMMON: "Uncommon",
    RarityTier.RARE: "Rare",
    RarityTier.EPIC: "Epic",
    RarityTier.LEGENDARY: "Legendary",
    RarityTier.BEST: "Best",
}
RARITY_COLORS = {
    RarityTier.COMMON: "#64748b",
    RarityTier.UNCOMMON: "#7ee787",
    RarityTier.RARE: "#58a6ff",
    RarityTier.EPIC: "#a78bfa",
    RarityTier.LEGENDARY: "#facc15",
    RarityTier.BEST: "#ffffff",
}


@dataclass(slots=True)
class BrowsePageModel:
    cache_key: tuple[Any, ...]
    snapshot: BrowseSnapshot
    state: dict[str, Any]
    visible_ids: list[str]
    works: list[Work]
    tags_by_work: dict[str, list[WorkTag]]
    favorite_lookup: dict[tuple[TagType, str], str]
    tag_color_lookup: dict[tuple[TagType, str], str]
    queued_work_ids: set[str]
    collected_ids: set[str]
    rarities_by_work: dict[str, WorkRarity]
    latest_evaluations: dict[str, Evaluation]
    style_settings: dict[str, Any]
    schema: EvaluationSchema


@dataclass(slots=True)
class WorkListRenderModel:
    cache_key: tuple[Any, ...]
    works: list[Work]
    tags_by_work: dict[str, list[WorkTag]]
    favorite_lookup: dict[tuple[TagType, str], str]
    tag_color_lookup: dict[tuple[TagType, str], str]
    queued_work_ids: set[str]
    collected_ids: set[str]
    rarities_by_work: dict[str, WorkRarity]
    latest_evaluations: dict[str, Evaluation]
    style_settings: dict[str, Any]
    schema: EvaluationSchema
    summary: Any | None = None


class AO3StudioShell:
    def __init__(self, container: ApplicationContainer) -> None:
        self.container = container
        self.page = str(container.preferences_service.get("active_page", "Browse") or "Browse")
        if self.page in {"Work Detail", "Schemas", "Settings"}:
            self.page = "Browse"
        self.selected_work_id = str(container.preferences_service.get("selected_work_id", "") or "")
        self.root = None
        self.top_container = None
        self.left_container = None
        self.left_footer_container = None
        self.center_container = None
        self.right_header_container = None
        self.right_container = None
        self.filter_metadata: Any | None = container.preferences_service.get("last_filter_metadata", None)
        self.left_fandom_split = int(container.preferences_service.get("left_fandom_split", 44) or 44)
        self.block_armed_work_id = ""
        self.work_remove_armed_id = ""
        self.queue_cleanup_mode = False
        self.queue_delete_armed = False
        self.queue_cleanup_selected_clusters: set[str] = set()
        self.queue_cleanup_selected_schemas: set[str] = set()
        self.selected_queue_batch_id = str(container.preferences_service.get("selected_queue_batch_id", "") or "")
        self.selected_evaluated_batch_id = str(container.preferences_service.get("selected_evaluated_batch_id", "") or "")
        self.selected_queue_cluster_id = str(container.preferences_service.get("selected_queue_cluster_id", "") or "")
        self.selected_queue_schema_key = str(container.preferences_service.get("selected_queue_schema_key", "") or "")
        self.selected_evaluated_cluster_id = str(container.preferences_service.get("selected_evaluated_cluster_id", "") or "")
        self.selected_evaluated_schema_key = str(container.preferences_service.get("selected_evaluated_schema_key", "") or "")
        self.evaluated_cleanup_mode = False
        self.evaluated_cleanup_armed = False
        self.evaluated_cleanup_selected_clusters: set[str] = set()
        self.evaluated_cleanup_selected_schemas: set[str] = set()
        self._browse_fetch_inflight_url = ""
        self._browse_fetch_serial = 0
        self._reader_download_inflight = ""
        self._pubdate_enrichment_ids: set[str] = set()
        self._pubdate_labels: dict[str, Any] = {}
        self._updatedate_labels: dict[str, Any] = {}
        self._inline_work_panel_slots: dict[str, Any] = {}
        self._block_buttons: dict[str, Any] = {}
        self._work_remove_buttons: dict[str, Any] = {}
        self._pubdate_enrichment_retry_at = 0.0
        self._work_expand_serial = 0
        self._browse_page_model: BrowsePageModel | None = None
        self._queue_page_model: WorkListRenderModel | None = None
        self._evaluated_page_model: WorkListRenderModel | None = None
        self._works_page_model: WorkListRenderModel | None = None
        self._batch_summaries_cache: dict[tuple[Any, ...], list[Any]] = {}
        self._browse_visible_ids_cache: list[str] = []
        self._queue_eval_running = False
        self._queue_eval_cancel_requested = False
        self._queue_eval_batch_id = ""
        self._restore_cluster_schema_selection("queue")
        self._restore_cluster_schema_selection("evaluated")

    def build(self) -> None:
        with ui.column().classes("main-content gap-0 p-0") as self.root:
            with ui.splitter(value=self._layout_value("left_panel_width", 18)).classes("w-full h-full min-h-0") as left_splitter:
                left_splitter.on("update:model-value", self._save_left_width)
                with left_splitter.before:
                    self.left_container = ui.column().classes("w-full h-full panel-bg gap-2 p-2 overflow-hidden")
                with left_splitter.after:
                    with ui.splitter(value=100 - self._layout_value("right_panel_width", 24)).classes("w-full h-full min-h-0") as right_splitter:
                        right_splitter.on("update:model-value", self._save_right_width)
                        with right_splitter.before:
                            with ui.column().classes("w-full h-full min-h-0 overflow-hidden"):
                                self.top_container = ui.row().classes(
                                    "center-tab-strip w-full items-center gap-0 shrink-0 overflow-hidden"
                                )
                                self.center_container = ui.column().classes("w-full flex-grow min-h-0 min-w-0 overflow-hidden")
                                self.center_container.on(
                                    "wheel",
                                    self._handle_reader_font_wheel,
                                    throttle=0.05,
                                    js_handler="""
                                        e => {
                                            if (!e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
                                            const dy = Number(e.deltaY) || 0;
                                            if (!dy) return;
                                            e.preventDefault();
                                            e.stopPropagation();
                                            const unit = 100;
                                            e.currentTarget._ao3FontWheelRemainder =
                                                (e.currentTarget._ao3FontWheelRemainder || 0) + dy;
                                            const remainder = e.currentTarget._ao3FontWheelRemainder;
                                            const steps = Math.trunc(Math.abs(remainder) / unit);
                                            if (!steps) return;
                                            e.currentTarget._ao3FontWheelRemainder =
                                                remainder - Math.sign(remainder) * steps * unit;
                                            emit({step: remainder < 0 ? steps : -steps});
                                        }
                                    """,
                                )
                        with right_splitter.after:
                            with ui.column().classes("right-panel-shell w-full h-full min-h-0 panel-bg overflow-hidden gap-0"):
                                self.right_header_container = ui.row().classes(
                                    "right-panel-header-strip w-full items-center justify-end gap-1 shrink-0 overflow-hidden"
                                )
                                with ui.scroll_area().classes("right-panel-scroll w-full flex-grow min-h-0"):
                                    self.right_container = ui.column().classes(
                                        "right-panel-column w-full gap-3 p-3 overflow-x-hidden items-stretch"
                                    ).style("width: 100%; min-width: 100%; max-width: none;")
        self.refresh()
        ui.timer(0.2, self._prewarm_ao3_browser, once=True)

    async def _prewarm_ao3_browser(self) -> None:
        try:
            await run.io_bound(self.container.browse_service.prewarm)
        except Exception:
            return

    def _handle_reader_font_wheel(self, event) -> None:
        if self.page != "Read":
            return
        try:
            args = event.args
            if isinstance(args, (list, tuple)) and args:
                args = args[0]
            step = int(args.get("step") if isinstance(args, dict) else args)
        except (TypeError, ValueError, AttributeError):
            return
        if not step:
            return
        active = self._active_fandom()
        self.container.style_service.adjust_font_size(active.fandom_key, step)
        self._render_center()

    def refresh(self) -> None:
        self._render_left()
        self._render_center()
        self._render_top()
        self._render_right_header()
        self._render_right()

    @staticmethod
    def _current_client():
        try:
            return context.client
        except RuntimeError:
            return None

    @staticmethod
    def _notify(message: str, kind: str = "info", *, client: Any | None = None) -> None:
        try:
            if client is not None:
                with client:
                    ui.notify(message, type=kind)
            else:
                ui.notify(message, type=kind)
            return
        except RuntimeError:
            pass
        if client is not None:
            options = json.dumps({"message": str(message), "type": kind})
            client.run_javascript(f"Quasar.Notify.create({options})")

    def _layout_value(self, key: str, default: int) -> int:
        try:
            return max(8, min(48, int(self.container.preferences_service.get(key, default))))
        except (TypeError, ValueError):
            return default

    def _save_left_width(self, event) -> None:
        try:
            self.container.preferences_service.set("left_panel_width", int(round(float(event.args))))
        except (TypeError, ValueError):
            return

    def _save_right_width(self, event) -> None:
        try:
            self.container.preferences_service.set("right_panel_width", 100 - int(round(float(event.args))))
        except (TypeError, ValueError):
            return

    def _set_page(self, page: str) -> None:
        if page == self.page:
            return
        self.page = page
        self.container.preferences_service.set("active_page", page)
        self._render_center()
        self._render_top()
        self._render_right_header()
        self._render_right()
        self._render_left_footer()

    def _select_work(self, work_id: str, page: str | None = None) -> None:
        if page:
            self.selected_work_id = work_id
            self.container.preferences_service.set("selected_work_id", work_id)
            self._set_page(page)
        else:
            self._set_work_expansion(work_id, "toggle")

    def _set_work_expansion(self, work_id: str, desired: str = "toggle") -> None:
        desired = desired if desired in {"open", "close"} else "toggle"
        if desired == "close":
            if self.selected_work_id and self.selected_work_id != work_id:
                return
            self.selected_work_id = ""
        elif desired == "open":
            self.selected_work_id = work_id
        else:
            self.selected_work_id = "" if self.selected_work_id == work_id else work_id
        self._work_expand_serial += 1
        serial = self._work_expand_serial
        self.container.preferences_service.set("selected_work_id", self.selected_work_id)

        def render_right_if_current() -> None:
            if serial == self._work_expand_serial:
                self._render_right()

        ui.timer(0.38, render_right_if_current, once=True)

    def _render_top(self) -> None:
        if not self.top_container:
            return
        self.top_container.clear()
        mode = self.container.mode_service.current_mode()
        remote = self.container.identity_service.remote_identity()
        active = self._active_fandom()
        visible_ids = self._current_browse_visible_ids() if self.page == "Browse" else []
        with self.top_container:
            with ui.row().classes("center-toolbar-left items-center gap-1"):
                if self.page == "Browse":
                    purge = ui.button(icon="cleaning_services").props("round flat dense size=md").classes("top-action-button")
                    if not visible_ids:
                        purge.props("disable")
                    purge.style("color: #94a3b8 !important;")
                    purge.on("click.stop", lambda _=None, ids=visible_ids: self._purge_uncollected_cache(ids))
                    with purge:
                        rich_tooltip("Smart purge unprotected cached works", active.color)
                    ui.label("|").classes("action-separator")
                    collect_page = ui.button(icon="playlist_add").props("round flat dense size=md").classes("top-action-button")
                    if not visible_ids:
                        collect_page.props("disable")
                    collect_page.style(f"color: {normalized_label_color(active.color)} !important;")
                    collect_page.on("click.stop", lambda _=None, ids=visible_ids: self._show_save_page_set_dialog(ids))
                    with collect_page:
                        rich_tooltip("Save this page as a named evaluation queue", active.color)
                elif self.page == "Read":
                    reader = self._reader_top_context()
                    if reader:
                        ui.label(reader["author"]).classes("reader-top-muted text-xs truncate")
                        ui.label("|").classes("action-separator")
                        ui.label(reader["work_title"]).classes("reader-top-accent text-xs truncate").style(
                            f"color: {normalized_label_color(active.color)}; {glow_text(active.color, 2)}"
                        )
                        ui.label("|").classes("action-separator")
                        ui.label(reader["work_words"]).classes("reader-top-muted text-xs")
            with ui.row().classes("workspace-tab-rail workspace-tab-rail-centered items-center gap-0 min-w-0"):
                for label, icon in self._visible_workspace_tabs():
                    tab = ui.button(label, icon=icon, on_click=lambda _=None, p=label: self._set_page(p)).props("flat dense")
                    tab.classes("workspace-tab")
                    if label == self.page:
                        tab.classes("workspace-tab-active")
            with ui.row().classes("center-toolbar-right items-center justify-end gap-1 shrink-0 px-2"):
                if self.page == "Read":
                    reader = self._reader_top_context()
                    if reader:
                        ui.label(reader["chapter_title"]).classes("reader-top-chapter text-xs truncate").style(
                            f"color: {normalized_label_color(active.color)}; {glow_text(active.color, 2)}"
                        )
                        ui.label("|").classes("action-separator")
                        ui.label(reader["chapter_meta"]).classes("reader-top-muted text-xs")
                        ui.label("|").classes("action-separator")
                        ui.label(reader["chapter_words"]).classes("reader-top-muted text-xs")
                        ui.label("|").classes("action-separator")
                elif self.page in {"Browse", "Works"}:
                    ui.label(short_fandom_name(active.tag)).classes("reader-top-chapter text-xs truncate").style(
                        f"color: {normalized_label_color(active.color)}; {glow_text(active.color, 2)}"
                    )
                    ui.label("|").classes("action-separator")
                if self.page == "Queue":
                    run_color = "#fb7185" if self._queue_eval_running else normalized_label_color(active.color)
                    run_icon = "stop_circle" if self._queue_eval_running else "play_arrow"
                    run_btn = ui.button(icon=run_icon).props("round flat dense size=sm").classes("top-action-button")
                    run_btn.style(f"color: {run_color} !important;")
                    if not self._queue_eval_running and not self._queue_run_available():
                        run_btn.props("disable")
                    run_btn.on("click.stop", lambda _=None: self._toggle_queue_evaluation_run())
                    with run_btn:
                        rich_tooltip("Stop after current work" if self._queue_eval_running else "Evaluate selected queue", run_color)
                elif self.page == "Evaluated" and self._evaluated_slot_queue_available():
                    eval_color = normalized_label_color(active.color)
                    eval_btn = ui.button(icon="play_arrow").props("round flat dense size=sm").classes("top-action-button")
                    eval_btn.style(f"color: {eval_color} !important;")
                    eval_btn.on("click.stop", lambda _=None: self._queue_selected_evaluated_schema_slot(start=True))
                    with eval_btn:
                        rich_tooltip("Send selected schema slot to Queue and begin evaluation", active.color)
                mode_icon = ui.button(icon="public").props("round flat dense size=sm").classes("top-action-button")
                mode_color = normalized_label_color(active.color) if mode is RuntimeMode.SHARED else "#6b7280"
                mode_icon.style(f"color: {mode_color} !important;")
                mode_icon.on("click.stop", lambda _=None: self._toggle_runtime_mode())
                with mode_icon:
                    rich_tooltip(self.container.mode_service.status_badge(), mode_color)
                if remote.remote_role is RemoteRole.ADMIN:
                    ui.icon("admin_panel_settings", size="20px").style("color: #facc15;")

    def _visible_workspace_tabs(self) -> list[tuple[str, str]]:
        tabs = list(WORKSPACE_TABS)
        if self.container.mode_service.shared_widgets_visible():
            tabs.append(OPTIONAL_TABS[0])
        if self.container.mode_service.admin_widgets_visible():
            tabs.append(OPTIONAL_TABS[1])
        return tabs

    def _current_browse_visible_ids(self) -> list[str]:
        if self._browse_page_model:
            return list(self._browse_page_model.visible_ids)
        return list(self._browse_visible_ids_cache)

    def _current_browse_snapshot(self):
        if self._browse_page_model:
            return self._browse_page_model.snapshot
        state = self._browse_filter_state()
        current_url = self.container.browse_service.resolve_effective_fandom_filter_url(str(state.get("fandom") or DEFAULT_FANDOM), state)
        snapshot = self.container.snapshot_repo.latest_for_url(current_url)
        if not snapshot:
            return None
        visible_ids = self.container.work_library_service.visible_work_ids(snapshot.work_ids)
        if len(self.container.work_repo.list_by_ids(visible_ids)) != len(visible_ids):
            self.container.snapshot_repo.delete_stale_missing_works()
            return None
        return snapshot

    def _invalidate_browse_page_model(self) -> None:
        self._browse_page_model = None
        self._queue_page_model = None
        self._evaluated_page_model = None
        self._works_page_model = None
        self._batch_summaries_cache.clear()
        self._browse_visible_ids_cache = []

    def _browse_model_cache_key(self, snapshot: BrowseSnapshot, active: FandomProfile) -> tuple[Any, ...]:
        return (
            snapshot.id,
            snapshot.source_url,
            snapshot.captured_at,
            tuple(snapshot.work_ids),
            active.fandom_key,
        )

    def _browse_page_model_for_current_state(self) -> BrowsePageModel | None:
        state = self._browse_filter_state()
        current_url = self.container.browse_service.resolve_effective_fandom_filter_url(
            str(state.get("fandom") or DEFAULT_FANDOM),
            state,
        )
        snapshot = self.container.snapshot_repo.latest_for_url(current_url)
        if not snapshot:
            self._browse_visible_ids_cache = []
            return None

        active = self._active_fandom()
        cache_key = self._browse_model_cache_key(snapshot, active)
        if self._browse_page_model and self._browse_page_model.cache_key == cache_key:
            return self._browse_page_model

        snapshot_ids = [str(work_id) for work_id in snapshot.work_ids if str(work_id).strip()]
        all_works = self.container.work_repo.list_by_ids(snapshot_ids)
        works_by_id = {work.work_id: work for work in all_works}
        if len(works_by_id) != len(dict.fromkeys(snapshot_ids)):
            self.container.snapshot_repo.delete_stale_missing_works()
            self._browse_visible_ids_cache = []
            self._browse_page_model = None
            return None

        visible = self.container.work_library_service.visible_works([works_by_id[work_id] for work_id in snapshot_ids])
        visible_by_id = {work.work_id: work for work in visible}
        visible_ids = [work_id for work_id in snapshot_ids if work_id in visible_by_id]
        works = [visible_by_id[work_id] for work_id in visible_ids]
        schema = self.container.schema_service.active_schema()
        model = BrowsePageModel(
            cache_key=cache_key,
            snapshot=snapshot,
            state=dict(state),
            visible_ids=visible_ids,
            works=works,
            tags_by_work=self.container.work_library_service.tags_for_works(visible_ids),
            favorite_lookup=self._favorite_tag_map(active.fandom_key),
            tag_color_lookup=self._tag_color_map(active.fandom_key),
            queued_work_ids=self.container.queue_service.active_work_ids(),
            collected_ids=self.container.work_library_service.collected_ids(visible_ids),
            rarities_by_work=self.container.rarity_service.get_many(visible_ids),
            latest_evaluations=self.container.evaluation_service.latest_for_works(visible_ids, schema.schema_key),
            style_settings=self.container.style_service.effective_settings(active.fandom_key),
            schema=schema,
        )
        self._browse_page_model = model
        self._browse_visible_ids_cache = list(visible_ids)
        return model

    def _batch_summaries_for_mode(self, mode: str) -> list[Any]:
        active = self._active_fandom()
        selected_id = self.selected_evaluated_batch_id if mode == "evaluated" else self.selected_queue_batch_id
        key = (mode, active.fandom_key, selected_id)
        cached = self._batch_summaries_cache.get(key)
        if cached is not None:
            return cached
        if selected_id:
            current = self._evaluated_page_model if mode == "evaluated" else self._queue_page_model
            if current and current.summary and current.summary.batch.id == selected_id:
                if mode == "evaluated":
                    summaries = [current.summary] if current.summary.completed_count > 0 else []
                else:
                    summaries = [current.summary] if current.summary.active_count > 0 else []
                self._batch_summaries_cache[key] = summaries
                return summaries
            summary = self.container.queue_service.summary_for_batch(selected_id)
            if not summary:
                summaries: list[Any] = []
            elif mode == "evaluated":
                summaries = [summary] if summary.completed_count > 0 else []
            else:
                summaries = [summary] if summary.active_count > 0 else []
            self._batch_summaries_cache[key] = summaries
            return summaries
        summaries = (
            self.container.queue_service.list_evaluated_batches(active.fandom_key)
            if mode == "evaluated"
            else self.container.queue_service.list_queue_batches(active.fandom_key)
        )
        self._batch_summaries_cache[key] = summaries
        return summaries

    def _cluster_summaries_for_mode(self, mode: str) -> list[Any]:
        active = self._active_fandom()
        key = ("cluster-slots", mode, active.fandom_key)
        cached = self._batch_summaries_cache.get(key)
        if cached is not None:
            return cached
        summaries = self.container.queue_service.list_clusters_with_schema_slots(active.fandom_key, mode)
        self._batch_summaries_cache[key] = summaries
        return summaries

    def _selected_cluster_id(self, mode: str) -> str:
        return self.selected_evaluated_cluster_id if mode == "evaluated" else self.selected_queue_cluster_id

    def _selected_schema_key(self, mode: str) -> str:
        return self.selected_evaluated_schema_key if mode == "evaluated" else self.selected_queue_schema_key

    def _selected_batch_id(self, mode: str) -> str:
        return self.selected_evaluated_batch_id if mode == "evaluated" else self.selected_queue_batch_id

    def _selected_schema_slot(self, mode: str) -> Any | None:
        work_set_id = self._selected_cluster_id(mode)
        schema_key = self._selected_schema_key(mode)
        if not work_set_id or not schema_key:
            return None
        return self.container.queue_service.schema_slot_for_work_set(work_set_id, schema_key)

    def _restore_cluster_schema_selection(self, mode: str) -> None:
        batch_id = self.selected_evaluated_batch_id if mode == "evaluated" else self.selected_queue_batch_id
        cluster_id = self._selected_cluster_id(mode)
        schema_key = self._selected_schema_key(mode)
        if not batch_id or (cluster_id and schema_key):
            return
        summary = self.container.queue_service.summary_for_batch(batch_id)
        if not summary:
            self._set_schema_selection(mode, "", "", "")
            return
        self._set_schema_selection(mode, summary.work_set.id, summary.batch.schema_key, summary.batch.id)

    def _work_list_render_model(
        self,
        *,
        cache_key: tuple[Any, ...],
        works: list[Work],
        tags_by_work: dict[str, list[WorkTag]] | None = None,
        latest_evaluations: dict[str, Evaluation] | None = None,
        schema: EvaluationSchema | None = None,
        summary: Any | None = None,
    ) -> WorkListRenderModel:
        active = self._active_fandom()
        schema = schema or self.container.schema_service.active_schema()
        work_ids = [work.work_id for work in works]
        return WorkListRenderModel(
            cache_key=cache_key,
            works=works,
            tags_by_work=tags_by_work if tags_by_work is not None else self.container.work_library_service.tags_for_works(work_ids),
            favorite_lookup=self._favorite_tag_map(active.fandom_key),
            tag_color_lookup=self._tag_color_map(active.fandom_key),
            queued_work_ids=self.container.queue_service.active_work_ids(),
            collected_ids=self.container.work_library_service.collected_ids(work_ids),
            rarities_by_work=self.container.rarity_service.get_many(work_ids),
            latest_evaluations=latest_evaluations
            if latest_evaluations is not None
            else self.container.evaluation_service.latest_for_works(work_ids, schema.schema_key),
            style_settings=self.container.style_service.effective_settings(active.fandom_key),
            schema=schema,
            summary=summary,
        )

    def _cluster_page_model_for_mode(self, mode: str, batch_id: str) -> WorkListRenderModel | None:
        source = (
            self.container.queue_service.evaluated_works_for_batch(batch_id)
            if mode == "evaluated"
            else self.container.queue_service.pending_works_for_batch(batch_id)
        )
        if not source:
            return None
        work_ids = tuple(work.work_id for work in source.works)
        cache_key = (
            mode,
            source.batch.id,
            source.batch.updated_at,
            source.batch.status.value,
            source.work_set.updated_at,
            source.schema.schema_key,
            tuple(work_ids),
        )
        current = self._evaluated_page_model if mode == "evaluated" else self._queue_page_model
        if current and current.cache_key == cache_key:
            return current
        model = self._work_list_render_model(
            cache_key=cache_key,
            works=source.works,
            tags_by_work=source.tags_by_work,
            latest_evaluations=source.latest_evaluations,
            schema=source.schema,
            summary=source.summary,
        )
        if mode == "evaluated":
            self._evaluated_page_model = model
        else:
            self._queue_page_model = model
        return model

    def _works_page_model_for_current_state(self) -> WorkListRenderModel:
        active = self._active_fandom()
        search = str(self.container.preferences_service.get("work_search", "") or "")
        works = self.container.work_library_service.list_collected(100, search)
        schema = self.container.schema_service.active_schema()
        cache_key = (
            "works",
            active.fandom_key,
            search,
            schema.schema_key,
            tuple(work.work_id for work in works),
            tuple(work.last_scraped_at for work in works),
        )
        if self._works_page_model and self._works_page_model.cache_key == cache_key:
            return self._works_page_model
        self._works_page_model = self._work_list_render_model(cache_key=cache_key, works=works, schema=schema)
        return self._works_page_model

    def _current_work_render_model(self) -> Any | None:
        if self.page == "Browse":
            return self._browse_page_model or self._browse_page_model_for_current_state()
        if self.page == "Queue" and self.selected_queue_batch_id:
            return self._cluster_page_model_for_mode("queue", self.selected_queue_batch_id)
        if self.page == "Evaluated" and self.selected_evaluated_batch_id:
            return self._cluster_page_model_for_mode("evaluated", self.selected_evaluated_batch_id)
        if self.page == "Works":
            return self._works_page_model_for_current_state()
        return None

    def _change_mode(self, value: str) -> None:
        self.container.mode_service.set_mode(RuntimeMode(value))
        self.refresh()

    def _toggle_runtime_mode(self) -> None:
        current = self.container.mode_service.current_mode()
        target = RuntimeMode.SHARED if current is RuntimeMode.LOCAL else RuntimeMode.LOCAL
        self.container.mode_service.set_mode(target)
        self.refresh()

    def _reader_top_context(self) -> dict[str, str] | None:
        work_id = str(self.container.preferences_service.get("reader_work_id", "") or self.selected_work_id or "")
        if not work_id:
            return None
        result = self.container.reader_service.open_work(work_id, auto_download=False)
        if not result.work:
            return None
        work = result.work
        chapter_index = max(1, int(result.active_chapter_index or 1))
        chapter = result.chapters[chapter_index - 1] if result.chapters and chapter_index <= len(result.chapters) else None
        chapter_title = self._chapter_display_title(chapter.title, chapter_index) if chapter and chapter.title else "No downloaded chapter"
        return {
            "author": work.author_name or "Unknown author",
            "work_title": work.title or f"Work {work.work_id}",
            "work_words": f"{work.words:,} words" if work.words else "",
            "chapter_title": chapter_title,
            "chapter_meta": f"Ch {chapter_index}",
            "chapter_words": self._chapter_word_count_label(chapter.html if chapter else ""),
        }

    def _render_left(self) -> None:
        if not self.left_container:
            return
        self.left_container.clear()
        with self.left_container:
            with ui.column().classes("w-full flex-grow min-h-0 gap-2"):
                info_height = max(16, min(58, self.left_fandom_split))
                with ui.column().classes("w-full min-h-0 gap-2 pb-2 overflow-hidden").style(
                    f"height: {info_height}%; min-height: 110px;"
                ):
                    self._left_data_panel()
                split_handle = ui.element("div").classes("w-full h-3 shrink-0 cursor-row-resize flex items-center group")
                split_handle.style("touch-action: none;")
                with split_handle:
                    ui.element("div").classes("w-full h-px bg-gray-700 group-hover:bg-cyan-500 transition-colors")
                split_handle.on(
                    "mousedown",
                    self._save_fandom_split,
                    js_handler="""
                        e => {
                            e.preventDefault();
                            const handle = e.currentTarget;
                            const parent = handle.parentElement;
                            const top = handle.previousElementSibling;
                            const min = 16;
                            const max = 58;
                            const clamp = value => Math.max(min, Math.min(max, value));
                            const percentFromEvent = ev => {
                                const rect = parent.getBoundingClientRect();
                                return clamp(((ev.clientY - rect.top) / rect.height) * 100);
                            };
                            const move = ev => { top.style.height = percentFromEvent(ev) + '%'; };
                            const up = ev => {
                                document.removeEventListener('mousemove', move);
                                document.removeEventListener('mouseup', up);
                                document.body.style.cursor = '';
                                document.body.style.userSelect = '';
                                const percent = Math.round(percentFromEvent(ev));
                                top.style.height = percent + '%';
                                emit(percent);
                            };
                            document.body.style.cursor = 'row-resize';
                            document.body.style.userSelect = 'none';
                            document.addEventListener('mousemove', move);
                            document.addEventListener('mouseup', up);
                        }
                    """,
                )
                self._render_fandom_list()
            self.left_footer_container = ui.element("div").classes("w-full shrink-0")
            self._render_left_footer()

    def _save_fandom_split(self, event) -> None:
        try:
            percent = int(round(float(event.args)))
        except (TypeError, ValueError):
            return
        self.left_fandom_split = max(16, min(58, percent))
        self.container.preferences_service.set("left_fandom_split", self.left_fandom_split)

    def _left_data_panel(self) -> None:
        identity = self.container.identity_service.bootstrap()
        schema = self.container.schema_service.active_schema()
        model = self.container.local_model_service.config().get("model") or "not selected"
        browse_state = self._browse_filter_state()
        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("Local Data").classes("text-sm font-bold")
            ui.label(identity.display_name or identity.local_user_id[:8]).classes("text-xs text-gray-400 truncate")
            with ui.row().classes("w-full items-center justify-between mt-2"):
                ui.label("Works kept").classes("text-xs text-gray-500")
                ui.label(str(self.container.work_library_service.count())).classes("text-xs font-bold")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Browse cache").classes("text-xs text-gray-500")
                ui.label(str(self.container.work_library_service.cache_count())).classes("text-xs font-bold")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Evaluations").classes("text-xs text-gray-500")
                ui.label(str(self.container.evaluation_service.count())).classes("text-xs font-bold")
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Queued").classes("text-xs text-gray-500")
                ui.label(str(len(self.container.queue_service.list(QueueStatus.QUEUED)))).classes("text-xs font-bold")
            ui.separator().classes("my-2")
            ui.label(f"Fandom: {browse_state['fandom']}").classes("text-xs text-gray-400 truncate")
            ui.label(schema.name).classes("text-xs text-gray-400 truncate")
            ui.label(f"LM: {model}").classes("text-xs text-gray-500 truncate")
        snapshots = self.container.browse_service.recent_snapshots()
        if snapshots:
            with ui.element("div").classes("soft-panel w-full p-3"):
                ui.label("Recent").classes("text-sm font-bold")
                for snapshot in snapshots[:5]:
                    ui.label(f"{snapshot.context_key} ({len(snapshot.work_ids)})").classes("text-xs text-gray-500 truncate")

    def _render_left_footer(self) -> None:
        if not self.left_footer_container:
            return
        active = self.container.fandom_service.ensure_default()
        self.left_footer_container.clear()
        with self.left_footer_container, ui.row().classes("w-full items-center justify-between mt-auto pt-2 border-t border-gray-700"):
            with ui.row().classes("items-center gap-1 min-w-0"):
                refresh = ui.button(icon="refresh").props("flat round dense size=sm")
                refresh.style(f"color: {normalized_label_color(active.color)} !important; opacity: 0.82;")
                refresh.on("click.stop", lambda _=None: self._set_page("Browse"))
                with refresh:
                    rich_tooltip("Return to active fandom browse", active.color)
                ui.label(short_fandom_name(active.tag)).classes("text-xs text-gray-500 truncate")
            with ui.row().classes("items-center gap-1"):
                if self.page == "Queue":
                    queue_config = ui.button(icon="psychology").props("flat round dense size=sm")
                    queue_config.style(f"color: {normalized_label_color(active.color)} !important; opacity: 0.86;")
                    queue_config.on("click.stop", lambda _=None: self._show_queue_eval_config_dialog())
                    with queue_config:
                        rich_tooltip("Queue evaluation config", active.color)
                    ui.label("|").classes("action-separator")
                schema_btn = ui.button(icon="local_fire_department").props("flat round dense size=sm")
                schema_btn.style(
                    "color: #d6b274 !important; opacity: 0.84; "
                    "text-shadow: 0 0 1px rgba(0,0,0,1), 0 0 5px rgba(214,178,116,0.55);"
                )
                schema_btn.on("click.stop", lambda _=None: self._show_schema_studio_dialog())
                with schema_btn:
                    rich_tooltip("Evaluation schemas", "#d6b274")
                ui.label("|").classes("action-separator")
                settings_btn = ui.button(icon="settings").props("flat round dense size=sm")
                settings_btn.style("color: #94a3b8 !important; opacity: 0.82;")
                settings_btn.on("click.stop", lambda _=None: self._show_settings_dialog())
                with settings_btn:
                    rich_tooltip("Settings", active.color)

    def _render_fandom_list(self) -> None:
        active = self.container.fandom_service.ensure_default()
        profiles = self.container.fandom_service.list_profiles()
        with ui.column().classes("w-full flex-grow min-h-0 gap-2 pt-1"):
            with ui.row().classes("w-full items-center justify-between gap-1"):
                ui.label("Fandoms").classes("text-sm font-bold text-gray-200")
                add_btn = ui.button(icon="add").props("flat round dense color=cyan")
                add_btn.on("click.stop", lambda _=None: self._show_fandom_dialog(None))
                with add_btn:
                    rich_tooltip("Create fandom", active.color)
            with ui.scroll_area().classes("w-full flex-grow min-h-0"):
                with ui.column().classes("w-full gap-1"):
                    for profile in profiles:
                        self._fandom_row(profile, active.fandom_key == profile.fandom_key)

    def _fandom_row(self, profile: FandomProfile, selected: bool) -> None:
        r, g, b = rgb_from_hex(profile.color)
        classes = f"fandom-row w-full items-center gap-2 p-2 cursor-pointer {'fandom-row-selected' if selected else ''}"
        row = ui.row().classes(classes).style(f"--accent-r:{r}; --accent-g:{g}; --accent-b:{b};")
        row.on("click", lambda _=None, key=profile.fandom_key: self._select_fandom_profile(key))
        with row:
            self._fandom_avatar_button(profile, interactive=True)
            with ui.column().classes("gap-0 min-w-0 flex-grow"):
                with ui.row().classes("w-full items-center gap-1 min-w-0"):
                    ui.label(profile.display_name).classes("text-sm font-bold truncate min-w-0 flex-grow").style(
                        glow_text(profile.color, 4) if selected else ""
                    )
                    edit = ui.button(icon="edit").props("flat round dense size=sm")
                    edit.style(f"color: {normalized_label_color(profile.color)} !important;")
                    edit.on("click.stop", lambda _=None, p=profile: self._show_fandom_dialog(p))
                    with edit:
                        rich_tooltip("Edit fandom identity", profile.color)
                ui.label(profile.tag).classes("text-[11px] text-gray-500 truncate")

    def _select_fandom_profile(self, fandom_key_value: str) -> None:
        profile = self.container.fandom_service.select(fandom_key_value)
        state = dict(default_fandom_filter(profile.tag))
        state.update(profile.default_filter or {})
        state["fandom"] = profile.tag
        self.container.preferences_service.set("browse_filter_state", state)
        self.container.preferences_service.set("last_context_type", "fandom")
        self.container.preferences_service.set("last_context_key", profile.tag)
        self.page = "Browse"
        self.container.preferences_service.set("active_page", "Browse")
        self.refresh()

    def _fandom_avatar_button(self, profile: FandomProfile, *, interactive: bool = True) -> None:
        def content() -> None:
            self._avatar_image(profile.avatar_url, profile.display_name, profile.color, "34px", "200px")

        if not interactive:
            with ui.element("div").classes("p-0 m-0 relative w-[34px] h-[34px] shrink-0"):
                content()
            return
        avatar_btn = ui.button().props("flat round dense").classes("p-0 m-0 relative")
        avatar_btn.on("click.stop", lambda _=None, p=profile: self._open_fandom_avatar_dialog(p))
        with avatar_btn:
            content()

    def _character_avatar_button(
        self,
        character_id: str,
        name: str,
        avatar_url: str | None,
        color: str,
        rerender: Callable[[], None] | None = None,
        fandom_key_value: str | None = None,
    ) -> None:
        avatar_btn = ui.button().props("flat round dense").classes("p-0 m-0 relative")
        avatar_btn.on(
            "click.stop",
            lambda _=None, cid=character_id, n=name, c=color, r=rerender, fk=fandom_key_value: self._open_character_avatar_dialog(cid, n, c, r, fk),
        )
        with avatar_btn:
            self._avatar_image(avatar_url, name, color, "34px", "200px")

    def _avatar_image(
        self,
        avatar_url: str | None,
        label: str,
        color: str,
        small_size: str,
        big_size: str,
        *,
        expand_side: str = "right",
    ) -> None:
        src = self._avatar_src(avatar_url)
        tooltip_anchor = "center left" if expand_side == "left" else "center right"
        tooltip_self = "center right" if expand_side == "left" else "center left"
        tooltip_props = (
            f'anchor="{tooltip_anchor}" self="{tooltip_self}" '
            'transition-show="scale" transition-hide="scale" :delay="0" :hide-delay="0"'
        )
        if src:
            ui.image(src).classes("rounded-full object-cover").style(f"width:{small_size}; height:{small_size}; {self._styled_border_css(color)}")
            with ui.tooltip().classes("bg-transparent shadow-none pointer-events-none").props(tooltip_props).style(
                "padding: 16px; overflow: visible; width: 232px; height: 232px; box-sizing: border-box; will-change: transform;"
            ):
                ui.image(src).classes("rounded-full object-cover").style(f"width:{big_size}; height:{big_size}; {self._styled_border_css(color)}")
            return
        with ui.element("div").classes("rounded-full flex items-center justify-center").style(
            f"width:{small_size}; height:{small_size}; background: rgba({','.join(str(v) for v in rgb_from_hex(color))},0.20); {self._styled_border_css(color)}"
        ):
            ui.label((label or "?")[:1].upper()).classes("text-sm font-bold").style(f"color: {normalized_label_color(color)};")
        with ui.tooltip().classes("bg-transparent shadow-none pointer-events-none").props(tooltip_props).style(
            "padding: 16px; overflow: visible; width: 232px; height: 232px; box-sizing: border-box; will-change: transform;"
        ):
            with ui.element("div").classes("rounded-full flex items-center justify-center").style(
                f"width:{big_size}; height:{big_size}; background: rgba({','.join(str(v) for v in rgb_from_hex(color))},0.20); {self._styled_border_css(color)}"
            ):
                ui.label((label or "?")[:1].upper()).classes("text-5xl font-bold").style(f"color: {normalized_label_color(color)};")

    @staticmethod
    def _avatar_src(avatar_url: str | None) -> str:
        if not avatar_url:
            return ""
        separator = "&" if "?" in avatar_url else "?"
        return f"{avatar_url}{separator}t={int(time.time())}" if avatar_url.startswith("/") else avatar_url

    @staticmethod
    def _styled_border_css(color: str, width: str = "2px") -> str:
        r, g, b = rgb_from_hex(color)
        return f"border: {width} solid rgba({r},{g},{b},0.78); box-shadow: 0 0 10px rgba({r},{g},{b},0.26);"

    @staticmethod
    def _font_pill_label(full_name: str) -> str:
        words = full_name.split(" | ")[0].split()
        if "Monaspace" in full_name:
            return full_name.split(" | ")[0].replace("Monaspace ", "")
        if len(words) > 1:
            second = words[1].lower()
            if second in {"mono", "light", "hyperlegible", "quattro"}:
                return words[0]
            return " ".join(words[:2])
        return words[0] if words else full_name

    @staticmethod
    def _font_variation_css(font_value: str) -> str:
        if font_value == "'Newsreader', serif":
            return "position: relative; top: 1px;"
        if font_value == "'Fraunces', serif":
            return "position: relative; top: -0.5px;"
        if font_value == "'Kalam Light', cursive":
            return "position: relative; top: 1.7px;"
        if font_value == "'Coming Soon', cursive":
            return "position: relative; top: 0.3px;"
        if font_value == "'Shantell Sans', cursive":
            return "font-variation-settings: 'BNCE' 20, 'INFM' 70, 'SPAC' 0;"
        if font_value == "'Sono', monospace":
            return "font-variation-settings: 'MONO' 0;"
        if font_value == "'Recursive', monospace":
            return "font-variation-settings: 'MONO' 0, 'CASL' 1, 'CRSV' 1;"
        return ""

    @staticmethod
    def _font_typography_css(font_value: str, font_size: float) -> str:
        if "iA Writer Quattro" in font_value:
            return "font-weight: 360;"
        if "Cascadia Mono" in font_value:
            return "font-weight: 290;"
        if "Reddit Mono" in font_value:
            return "font-weight: 340;"
        if "Sono" in font_value:
            return "font-weight: 370; font-variation-settings: 'MONO' 0;"
        if "Atkinson Hyperlegible Mono" in font_value:
            return "font-weight: 300;"
        if "Recursive" in font_value:
            return "font-weight: 360; font-variation-settings: 'MONO' 0, 'slnt' 0, 'CASL' 1, 'CRSV' 1;"
        if "Martian Mono" in font_value:
            return "font-weight: 300; font-variation-settings: 'wdth' 100; font-feature-settings: 'calt' 1;"
        if "Source Code Pro" in font_value:
            return "font-weight: 400;"
        if "Loretta" in font_value:
            return "font-weight: 300;"
        if "Fraunces" in font_value:
            return f"font-weight: 275; font-variation-settings: 'opsz' {font_size}, 'SOFT' 70, 'WONK' 1;"
        if "Newsreader" in font_value:
            return f"font-weight: 300; font-variation-settings: 'opsz' {font_size};"
        if "Maple Mono" in font_value:
            return "font-weight: 300;"
        if "Merienda" in font_value:
            return "font-weight: 300;"
        if "M PLUS Code" in font_value:
            return "font-weight: 400; font-variation-settings: 'wdth' 100;"
        if "Monaspace" in font_value:
            return "font-weight: 300; font-feature-settings: 'calt' 1;"
        if "Shantell Sans" in font_value:
            return "font-weight: 350; font-variation-settings: 'BNCE' 20, 'INFM' 70, 'SPAC' 0;"
        if "Caveat" in font_value:
            return "font-weight: 400;"
        if "Gaegu" in font_value:
            return "font-weight: 400;"
        return ""

    @staticmethod
    def _font_color(font_value: str) -> str:
        return FONT_COLORS.get(font_value, "#94a3b8")

    @staticmethod
    def _rarity_border_style(tier: RarityTier, settings: dict[str, Any]) -> tuple[str, str]:
        thickness = float(settings.get("border_thickness") or 1.0)
        color = RARITY_COLORS.get(tier, "#30363d")
        if settings.get("gradient_border_enabled") and tier is not RarityTier.COMMON:
            mode = str(settings.get("gradient_border_mode") or "twin")
            if settings.get("rarity_map_enabled"):
                mode = str((settings.get("rarity_map") or {}).get(tier.value) or mode)
            classes = f"gradient-border gradient-border-{mode} gradient-border-{tier.value}"
            return classes, f"--gb-thickness: {thickness}px;"
        r, g, b = rgb_from_hex(color)
        alpha = 0.68 if tier is RarityTier.COMMON else 0.78
        glow = 0.16 if tier is RarityTier.COMMON else 0.28
        return "", f"border: {thickness}px solid rgba({r},{g},{b},{alpha}); box-shadow: 0 0 10px rgba({r},{g},{b},{glow});"

    def _rarity_border_for_work(self, work_id: str, settings: dict[str, Any]) -> tuple[str, str]:
        rarity = self.container.rarity_service.get(work_id)
        return self._rarity_border_for_rarity(rarity, settings)

    def _rarity_border_for_rarity(self, rarity: WorkRarity, settings: dict[str, Any]) -> tuple[str, str]:
        if rarity.manual_rarity is None and rarity.computed_rarity is None:
            return "", ""
        return self._rarity_border_style(rarity.effective_rarity, settings)

    @staticmethod
    def _reader_font_style(settings: dict[str, Any]) -> str:
        font = str(settings.get("preview_font_family") or "'Source Code Pro', monospace")
        size = float(settings.get("reader_font_size") or 16.5)
        return f"font-family: {font}; font-size: {size}px; {AO3StudioShell._font_typography_css(font, size)}"

    def _render_style_controls(
        self,
        *,
        settings: dict[str, Any],
        accent: str,
        save_handler: Callable[[dict[str, Any]], None],
        enabled_state: dict[str, bool] | None = None,
        show_thresholds: bool = False,
        show_save_button: bool = True,
    ) -> None:
        refs: dict[str, Any] = {}
        style_state = settings
        ar, ag, ab = rgb_from_hex(accent)

        def controls_enabled() -> bool:
            return enabled_state is None or bool(enabled_state.get("enabled"))

        def muted() -> str:
            return "" if controls_enabled() else "opacity: 0.42;"

        def set_font(font_value: str) -> None:
            style_state["preview_font_family"] = font_value
            render_font_pills()

        def set_mode(mode_value: str) -> None:
            style_state["gradient_border_mode"] = mode_value
            render_mode_pills()

        def render_font_pills() -> None:
            container = refs.get("fonts")
            if not container:
                return
            container.clear()
            current = str(style_state.get("preview_font_family") or "'Source Code Pro', monospace")
            with container:
                for _category, data in FONT_CATEGORIES.items():
                    for font_value, full_name in data["fonts"].items():
                        selected = font_value == current
                        color = self._font_color(font_value)
                        r, g, b = rgb_from_hex(color)
                        bg = "0.25" if selected else "0.08"
                        border = "0.50" if selected else "0.15"
                        label = self._font_pill_label(full_name)
                        pill = ui.button(label, on_click=lambda _=None, f=font_value: set_font(f)).props("dense flat rounded no-caps")
                        pill.classes("px-2 py-1")
                        pill.style(
                            f"background: rgba({r},{g},{b},{bg}) !important; border: 1px solid rgba({r},{g},{b},{border}); "
                            f"color: {color} !important; font-family: {font_value}; {self._font_variation_css(font_value)} "
                            f"text-shadow: {'0 0 6px ' + color if selected else 'none'}; {muted()}"
                        )
                        with pill:
                            ui.tooltip(full_name).classes("text-sm").style(
                                f"font-family: {font_value}; {self._font_variation_css(font_value)} "
                                f"color: {color}; background: linear-gradient(160deg, rgba({r},{g},{b},0.15), rgba({r},{g},{b},0.08)), #0d1117 !important; "
                                f"border: 1px solid rgba({r},{g},{b},0.30);"
                            )

        def render_mode_pills() -> None:
            container = refs.get("modes")
            if not container:
                return
            container.clear()
            current = str(style_state.get("gradient_border_mode") or "twin")
            with container:
                for mode_value, label in GRADIENT_MODE_LABELS:
                    selected = mode_value == current
                    pill = ui.button(label, on_click=lambda _=None, m=mode_value: set_mode(m)).props("dense flat rounded no-caps")
                    pill.style(
                        f"background: rgba({ar},{ag},{ab},{0.24 if selected else 0.07}) !important; "
                        f"border: 1px solid rgba({ar},{ag},{ab},{0.54 if selected else 0.18}); "
                        f"color: {normalized_label_color(accent)} !important; {muted()}"
                    )

        def open_rarity_map() -> None:
            with self.root:
                dialog = ui.dialog()
                dialog.on("hide", dialog.delete)
            draft = dict(style_state.get("rarity_map") or {})
            with dialog, ui.card().classes("w-[520px] max-w-[94vw] p-0 gap-0 overflow-hidden").style(
                wash_background(accent, 0.14) + f"border: 1px solid rgba({ar},{ag},{ab},0.26);"
            ):
                with ui.row().classes("w-full items-center justify-between p-3 border-b border-gray-700"):
                    ui.label("Rarity Map").classes("text-lg font-bold").style(glow_text(accent, 4))
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense color=white")
                with ui.column().classes("w-full gap-3 p-3"):
                    for tier in [RarityTier.UNCOMMON, RarityTier.RARE, RarityTier.EPIC, RarityTier.LEGENDARY, RarityTier.BEST]:
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label(RARITY_LABELS[tier]).classes("w-24 text-sm font-bold").style(f"color: {RARITY_COLORS[tier]};")
                            ui.select(
                                {mode: label for mode, label in GRADIENT_MODE_LABELS},
                                value=draft.get(tier.value, "twin"),
                            ).bind_value(draft, tier.value).props("dark outlined dense").classes("flex-grow")
                with ui.row().classes("w-full justify-end p-3 border-t border-gray-700"):
                    def save_map() -> None:
                        style_state["rarity_map"] = draft
                        dialog.close()

                    ui.button("Done", icon="check", on_click=save_map).style(
                        f"background-color: {dark_button_color(accent)} !important; color: white;"
                    )
            dialog.open()

        def open_thresholds() -> None:
            thresholds = self.container.style_service.rarity_thresholds()
            with self.root:
                dialog = ui.dialog()
                dialog.on("hide", dialog.delete)
            with dialog, ui.card().classes("w-[420px] max-w-[94vw] p-0 gap-0 overflow-hidden").style(
                wash_background(accent, 0.14) + f"border: 1px solid rgba({ar},{ag},{ab},0.26);"
            ):
                with ui.row().classes("w-full items-center justify-between p-3 border-b border-gray-700"):
                    ui.label("Rarity Thresholds").classes("text-lg font-bold").style(glow_text(accent, 4))
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense color=white")
                with ui.column().classes("w-full gap-3 p-3"):
                    for key, label in [("uncommon", "Uncommon"), ("rare", "Rare"), ("epic", "Epic"), ("legendary", "Legendary")]:
                        ui.number(label, value=thresholds[key], min=0, max=10, step=0.5).bind_value(thresholds, key).props(
                            "dark outlined dense"
                        ).classes("w-full")
                    ui.label("Best is manual-only. Automatic rarity tops out at Legendary.").classes("text-xs text-gray-500")
                with ui.row().classes("w-full justify-end p-3 border-t border-gray-700"):
                    def save_thresholds() -> None:
                        self.container.style_service.save_rarity_thresholds(thresholds)
                        dialog.close()
                        self._notify("Rarity thresholds saved.", "positive")

                    ui.button("Save", icon="save", on_click=save_thresholds).style(
                        f"background-color: {dark_button_color(accent)} !important; color: white;"
                    )
            dialog.open()

        if enabled_state is not None:
            with ui.row().classes("w-full items-center justify-between soft-panel p-3"):
                ui.label("Use fandom style override").classes("text-sm font-bold").style(glow_text(accent, 3))
                ui.switch(value=enabled_state["enabled"]).bind_value(enabled_state, "enabled").props("dense color=primary")

        with ui.column().classes("w-full gap-3").style(muted()):
            with ui.element("div").classes("soft-panel w-full p-3"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Font Family").classes("text-sm font-bold").style(glow_text(accent, 3))
                    if show_thresholds:
                        thresholds = ui.button(icon="tune").props("flat round dense")
                        thresholds.style(f"color: {normalized_label_color(accent)} !important;")
                        thresholds.on("click.stop", lambda _=None: open_thresholds())
                        with thresholds:
                            rich_tooltip("Rarity thresholds", accent)
                refs["fonts"] = ui.row().classes("w-full gap-2 flex-wrap mt-2")
                render_font_pills()
            with ui.element("div").classes("soft-panel w-full p-3"):
                ui.label("Font Size").classes("text-sm font-bold").style(glow_text(accent, 3))
                with ui.row().classes("w-full gap-2"):
                    ui.number("Current Font Size", value=style_state.get("reader_font_size", 16.5), min=8, max=48, step=0.5).bind_value(
                        style_state,
                        "reader_font_size",
                    ).props("dark outlined dense").classes("flex-grow")
                    ui.number("Mouse Wheel Font Step", value=style_state.get("font_wheel_step_px", 0.5), min=0.5, max=10, step=0.5).bind_value(
                        style_state,
                        "font_wheel_step_px",
                    ).props("dark outlined dense").classes("flex-grow")
            with ui.element("div").classes("soft-panel w-full p-3"):
                ui.label("Rarity Borders").classes("text-sm font-bold").style(glow_text(accent, 3))
                with ui.row().classes("w-full gap-2 items-center"):
                    ui.number("Rarity Border Thickness", value=style_state.get("border_thickness", 1.0), min=0, max=12, step=0.5).bind_value(
                        style_state,
                        "border_thickness",
                    ).props("dark outlined dense").classes("w-56")
                    ui.switch("Gradient Border", value=style_state.get("gradient_border_enabled", False)).bind_value(
                        style_state,
                        "gradient_border_enabled",
                    ).props("dense")
                    ui.switch("Rarity Map", value=style_state.get("rarity_map_enabled", False)).bind_value(
                        style_state,
                        "rarity_map_enabled",
                    ).props("dense")
                    map_btn = ui.button(icon="auto_awesome", on_click=open_rarity_map).props("flat round dense")
                    map_btn.style(f"color: {normalized_label_color(accent)} !important;")
                    with map_btn:
                        rich_tooltip("Configure rarity border modes", accent)
                refs["modes"] = ui.row().classes("w-full gap-2 flex-wrap mt-2")
                render_mode_pills()
            if show_save_button:
                with ui.row().classes("w-full justify-end"):
                    save = ui.button("Save", icon="save", on_click=lambda: save_handler(style_state)).props("dense")
                    save.style(f"background-color: {dark_button_color(accent)} !important; color: white;")

    def _show_fandom_dialog(self, profile: FandomProfile | None) -> None:
        active = profile or self.container.fandom_service.active_profile() or self.container.fandom_service.ensure_default()
        is_new = profile is None
        accent = active.color if not is_new else "#58a6ff"
        r, g, b = rgb_from_hex(accent)
        base_dialog_style = (
            wash_background(accent, 0.14)
            + f"width: 560px; max-width: 94vw; height: 85vh; max-height: calc(100vh - 24px); border: 1px solid rgba({r},{g},{b},0.24);"
        )
        fullscreen_dialog_style = (
            wash_background(accent, 0.14)
            + "width: 100vw !important; max-width: 100vw !important; height: 100vh !important; max-height: 100vh !important; "
            + f"border-radius: 0 !important; border: 1px solid rgba({r},{g},{b},0.24);"
        )
        draft = {
            "fandom_key": "" if is_new else active.fandom_key,
            "tag": "" if is_new else active.tag,
            "display_name": "" if is_new else active.display_name,
            "color": accent,
            "avatar_url": active.avatar_url or "",
            "notes": active.notes or "",
        }
        config_state = dict(default_fandom_filter(active.tag))
        config_state.update(active.default_filter or {})
        config_state["fandom"] = "" if is_new else active.tag
        style_override = self.container.style_service.fandom_override(active.fandom_key)
        style_state = dict(style_override.settings)
        style_enabled = {"enabled": bool(style_override.enabled)}
        character_draft = {"name": "", "full_name": "", "color": draft["color"], "avatar_url": "", "tag_urls": "", "notes": ""}
        initial_tab = str(self.container.preferences_service.get("fandom_dialog_tab", "Identity") or "Identity")
        if initial_tab not in {"Identity", "Style", "Config", "Characters"}:
            initial_tab = "Identity"
        refs: dict[str, Any] = {
            "avatar_slot": None,
            "character_panel": None,
            "config_container": None,
        }
        expanded_characters: set[str] = set()
        character_cleanup = {"mode": False, "armed": False, "selected": set()}

        def collapse_character_expansions() -> None:
            if expanded_characters:
                expanded_characters.clear()
                render_character_panel()

        def current_color() -> str:
            return str(draft.get("color") or accent or "#58a6ff")

        def handle_tab(event) -> None:
            value = str(getattr(event, "value", None) or getattr(event, "args", None) or "Identity")
            if value in {"Identity", "Style", "Config", "Characters"}:
                self.container.preferences_service.set("fandom_dialog_tab", value)
                collapse_character_expansions()

        def close_dialog() -> None:
            ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")
            dialog.close()

        def current_filter_state() -> dict[str, Any]:
            state = dict(config_state)
            state["fandom"] = str(draft["tag"]).strip() or state.get("fandom") or active.tag
            for key in ["words_from", "words_to"]:
                if state.get(key) in {"", 0.0}:
                    state[key] = None
            return state

        def save_fandom() -> None:
            nonlocal active, is_new, accent
            tag = str(draft["tag"]).strip()
            if not tag:
                self._notify("Fandom tag is required.", "warning")
                return
            key = str(draft["fandom_key"] or fandom_key(tag))
            saved = self.container.fandom_service.save_profile(
                FandomProfile(
                    fandom_key=key,
                    tag=tag,
                    display_name=str(draft["display_name"]).strip() or short_fandom_name(tag),
                    color=current_color(),
                    avatar_url=str(draft["avatar_url"]).strip() or None,
                    notes=str(draft["notes"]).strip() or None,
                    default_filter=current_filter_state(),
                    created_at=active.created_at if not is_new else "",
                    selected_at=active.selected_at if not is_new else None,
                )
            )
            self.container.fandom_service.select(saved.fandom_key)
            active = saved
            is_new = False
            accent = saved.color
            draft["fandom_key"] = saved.fandom_key
            draft["display_name"] = saved.display_name
            draft["avatar_url"] = saved.avatar_url or ""
            self.container.preferences_service.set("active_page", self.page)
            self._invalidate_browse_page_model()
            self._notify("Fandom saved.", "positive")
            render_avatar_slot()
            render_config_controls()
            render_character_panel()

        def save_fandom_style(state: dict[str, Any]) -> None:
            if is_new:
                self._notify("Save the fandom before enabling a style override.", "warning")
                return
            self.container.style_service.save_fandom_override(active.fandom_key, bool(style_enabled["enabled"]), state)
            self._invalidate_browse_page_model()
            self._notify("Fandom style saved.", "positive")

        def render_avatar_slot() -> None:
            slot = refs.get("avatar_slot")
            if not slot:
                return
            slot.clear()
            with slot:
                if is_new:
                    with ui.element("div").classes("p-0 m-0 relative"):
                        self._avatar_image(None, str(draft["display_name"] or "Fandom"), current_color(), "72px", "200px")
                        rich_tooltip("Save this fandom before adding a local avatar", current_color())
                    return
                avatar_btn = ui.button().props("flat round dense").classes("p-0 m-0 relative")
                avatar_btn.on("click.stop", lambda _=None, p=active: self._open_fandom_avatar_dialog(p))
                with avatar_btn:
                    self._avatar_image(str(draft["avatar_url"] or active.avatar_url or ""), str(draft["display_name"] or active.display_name), current_color(), "72px", "200px")

        def apply_current_filters() -> None:
            config_state.clear()
            config_state.update(self._browse_filter_state())
            render_config_controls()

        def clear_defaults() -> None:
            config_state.clear()
            config_state.update(default_fandom_filter(str(draft["tag"] or active.tag)))
            render_config_controls()

        def render_config_controls() -> None:
            container = refs.get("config_container")
            if not container:
                return
            container.clear()
            with container:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Default Browse Filters").classes("text-sm font-bold").style(glow_text(current_color(), 3))
                    json_btn = ui.button(icon="data_object").props("flat round dense")
                    json_btn.style(f"color: {normalized_label_color(current_color())} !important;")
                    json_btn.on("click.stop", lambda _=None: self._open_filter_json_dialog(config_state, current_color(), render_config_controls))
                    with json_btn:
                        rich_tooltip("Open JSON editor", current_color())
                ui.select(
                    {
                        "revised_at": "Date Updated",
                        "created_at": "Date Posted",
                        "kudos_count": "Kudos",
                        "hits": "Hits",
                        "word_count": "Word Count",
                        "comments_count": "Comments",
                        "bookmarks_count": "Bookmarks",
                    },
                    value=config_state.get("sort_column", "revised_at"),
                    label="Sort by",
                ).bind_value(config_state, "sort_column").props("dark outlined dense").classes("w-full")
                query = ui.input("Search within results", value=config_state.get("query", "")).bind_value(config_state, "query").props(
                    "dark outlined dense clearable"
                ).classes("w-full")
                query.on("keydown.enter", lambda _=None: save_fandom())
                with ui.row().classes("w-full gap-2"):
                    ui.input("Other tags to include", value=config_state.get("other_tag_names", "")).bind_value(
                        config_state,
                        "other_tag_names",
                    ).props("dark outlined dense clearable").classes("flex-grow")
                    ui.input("Other tags to exclude", value=config_state.get("excluded_tag_names", "")).bind_value(
                        config_state,
                        "excluded_tag_names",
                    ).props("dark outlined dense clearable").classes("flex-grow")
                with ui.row().classes("w-full gap-2"):
                    ui.select({"": "Any", "F": "Exclude crossovers", "T": "Only crossovers"}, value=config_state.get("crossover", ""), label="Crossovers").bind_value(
                        config_state,
                        "crossover",
                    ).props("dark outlined dense").classes("flex-grow")
                    ui.select({"": "Any", "T": "Complete only", "F": "Incomplete only"}, value=config_state.get("complete", ""), label="Completion").bind_value(
                        config_state,
                        "complete",
                    ).props("dark outlined dense").classes("flex-grow")
                with ui.row().classes("w-full gap-2"):
                    ui.number("Words from", value=config_state.get("words_from"), min=0).bind_value(
                        config_state,
                        "words_from",
                    ).props("dark outlined dense").classes("flex-grow")
                    ui.number("Words to", value=config_state.get("words_to"), min=0).bind_value(
                        config_state,
                        "words_to",
                    ).props("dark outlined dense").classes("flex-grow")
                with ui.row().classes("w-full gap-2"):
                    ui.input("Date from", value=config_state.get("date_from", "")).bind_value(config_state, "date_from").props(
                        "dark outlined dense clearable"
                    ).classes("flex-grow")
                    ui.input("Date to", value=config_state.get("date_to", "")).bind_value(config_state, "date_to").props(
                        "dark outlined dense clearable"
                    ).classes("flex-grow")
                ui.input("Language ID", value=config_state.get("language_id", "")).bind_value(config_state, "language_id").props(
                    "dark outlined dense clearable"
                ).classes("w-full")
                ui.input("Key work ID or URL", value=config_state.get("anchor_work_url", "")).bind_value(
                    config_state,
                    "anchor_work_url",
                ).props("dark outlined dense clearable").classes("w-full")
                with ui.row().classes("w-full gap-2"):
                    current_btn = ui.button("Use Current", icon="keyboard_return", on_click=apply_current_filters).props("dense flat")
                    current_btn.style(f"color: {normalized_label_color(current_color())} !important;")
                    clear_btn = ui.button("Clear", icon="backspace", on_click=clear_defaults).props("dense flat")
                    clear_btn.style("color: #94a3b8 !important;")

        def use_suggestion(suggestion, draft: dict[str, Any] | None = None) -> None:
            target = draft or character_draft
            source_label = suggestion.tag_url or suggestion.tag_text
            short_name, full_name = _character_names_from_ao3_label(source_label)
            target["name"] = short_name or suggestion.tag_text
            target["full_name"] = full_name or suggestion.tag_text
            target["tag_urls"] = _canonical_ao3_character_tag_url(source_label)
            render_character_panel()

        def save_character_from_draft(draft: dict[str, Any], character_id: str | None = None) -> None:
            if is_new:
                self._notify("Save the fandom before adding character identities.", "warning")
                return
            full_name = str(draft.get("full_name") or "").strip()
            name = str(draft.get("name") or "").strip()
            canonical_tag_url = _canonical_ao3_character_tag_url(
                str(draft.get("tag_urls") or "") or full_name or name
            )
            if not full_name:
                _, full_name = _character_names_from_ao3_label(canonical_tag_url or name)
            if not name:
                name, _ = _character_names_from_ao3_label(canonical_tag_url or full_name)
            result = self.container.fandom_service.save_character(
                fandom_key=active.fandom_key,
                character_id=character_id,
                name=name,
                full_name=full_name,
                color=str(draft.get("color") or draft["color"]),
                avatar_url=str(draft.get("avatar_url") or ""),
                tag_urls=[canonical_tag_url] if canonical_tag_url else [],
                notes=str(draft.get("notes") or ""),
            )
            self._notify(result.message, "positive" if result.ok else "warning")
            if result.ok and character_id is None:
                character_draft.update({"name": "", "full_name": "", "tag_urls": "", "notes": ""})
            render_character_panel()

        def delete_selected_characters() -> None:
            for character_id in list(character_cleanup["selected"]):
                self.container.fandom_service.delete_character(str(character_id))
            character_cleanup["selected"].clear()
            character_cleanup["armed"] = False
            character_cleanup["mode"] = False
            render_character_panel()

        async def refresh_catalog_from_dialog() -> None:
            if is_new:
                self._notify("Save the fandom before caching AO3 tags.", "warning")
                return
            await self._refresh_tag_catalog(active, rerender=render_character_panel)

        def render_character_panel() -> None:
            panel = refs.get("character_panel")
            if not panel:
                return
            panel.clear()
            with panel:
                if is_new:
                    ui.label("Save the fandom before adding character identities.").classes("text-sm text-gray-500")
                    return
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        count = self.container.fandom_service.tag_catalog_count(active.fandom_key)
                        ui.label(f"AO3 character tag suggestions cached: {count:,}").classes("text-xs text-gray-500")
                    with ui.row().classes("items-center gap-1"):
                        cleanup = ui.button(icon="cleaning_services").props("flat round dense")
                        cleanup.style(f"color: {'#ef4444' if character_cleanup['mode'] else normalized_label_color(current_color())} !important;")
                        cleanup.on("click.stop", lambda _=None: (character_cleanup.update({"mode": not character_cleanup["mode"], "armed": False, "selected": set()}), render_character_panel()))
                        with cleanup:
                            rich_tooltip("Cleanup mode", current_color())
                        trash = ui.button(icon="delete").props("flat round dense")
                        trash.style(f"color: {'#ef4444' if character_cleanup['armed'] else '#6b7280'} !important;")
                        trash.classes(remove="opacity-0 pointer-events-none" if character_cleanup["mode"] else "")
                        if not character_cleanup["mode"]:
                            trash.classes(add="opacity-0 pointer-events-none")
                        trash.on("click.stop", lambda _=None: delete_selected_characters() if character_cleanup["armed"] else (character_cleanup.update({"armed": True}), render_character_panel()))
                        with trash:
                            rich_tooltip("Delete selected character identities", "#ef4444")
                        refresh = ui.button(icon="cloud_sync").props("flat round dense")
                        refresh.style(f"color: {normalized_label_color(current_color())} !important;")
                        refresh.on("click.stop", lambda _=None: refresh_catalog_from_dialog())
                        with refresh:
                            rich_tooltip("Refresh AO3 tags for this fandom", current_color())
                characters = self.container.fandom_service.list_characters(active.fandom_key)
                if not characters:
                    ui.label("No character colors yet.").classes("text-sm text-gray-500")
                else:
                    with ui.row().classes("w-full gap-1 flex-wrap items-center reader-character-pill-row"):
                        for character in characters:
                            display_name, _ = _character_profile_display_names(character)
                            cleanup_selected = character.id in character_cleanup["selected"]
                            expanded = character.id in expanded_characters
                            color = "#ef4444" if cleanup_selected and character_cleanup["mode"] else character.color
                            selected = cleanup_selected if character_cleanup["mode"] else expanded
                            pill = ui.element("button").props("type=button").classes(
                                "work-tag-pill browse-tag-pill reader-character-pill character-profile-pill text-[11px]"
                            )
                            pill.style(self._filter_pill_style(color, selected))
                            pill.on(
                                "click",
                                lambda _=None, c=character: (
                                    character_cleanup["selected"].remove(c.id) if character_cleanup["mode"] and c.id in character_cleanup["selected"] else
                                    character_cleanup["selected"].add(c.id) if character_cleanup["mode"] else
                                    expanded_characters.remove(c.id) if c.id in expanded_characters else
                                    expanded_characters.add(c.id),
                                    render_character_panel(),
                                ),
                                js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
                            )
                            with pill:
                                self._avatar_image(character.avatar_url, display_name, character.color, "22px", "200px")
                                ui.label(display_name).classes("browse-tag-pill-label reader-character-pill-label")
                                rich_tooltip("Cleanup selected" if cleanup_selected and character_cleanup["mode"] else "Click to edit", color)
                    for character in characters:
                        if character.id not in expanded_characters:
                            continue
                        display_name, display_full_name = _character_profile_display_names(character)
                        cr, cg, cb = rgb_from_hex(character.color)
                        expanded_style = (
                            f"border: 1px solid rgba({cr},{cg},{cb},0.46); "
                            f"background: rgba({cr},{cg},{cb},0.11); "
                            f"box-shadow: 0 0 16px rgba({cr},{cg},{cb},0.12);"
                        )
                        draft = {
                            "name": display_name,
                            "full_name": display_full_name,
                            "color": character.color,
                            "avatar_url": character.avatar_url or "",
                            "tag_urls": _canonical_ao3_character_tag_url((character.tag_urls or [""])[0] or display_full_name or display_name),
                            "notes": character.notes or "",
                        }
                        with ui.element("div").classes("soft-panel w-full p-2 character-profile-expanded").style(expanded_style).on(
                            "click.stop",
                            lambda _=None: None,
                        ):
                            with ui.row().classes("w-full items-center gap-2"):
                                self._character_avatar_button(
                                    character.id,
                                    display_name,
                                    character.avatar_url,
                                    character.color,
                                    render_character_panel,
                                    active.fandom_key,
                                )
                                ui.input("Name", value=draft["name"]).bind_value(draft, "name").props(
                                    "dark outlined dense"
                                ).classes("w-32")
                                ui.input("Full Name", value=draft["full_name"]).bind_value(draft, "full_name").props(
                                    "dark outlined dense"
                                ).classes("flex-grow")
                                ui.color_input("Color", value=draft["color"]).bind_value(draft, "color").props("dark outlined dense").classes("w-32")
                            tag_input = ui.input("Canonical AO3 character tag URL", value=draft["tag_urls"]).bind_value(draft, "tag_urls").props(
                                "dark outlined dense"
                            ).classes("w-full")
                            ui.textarea("Notes", value=draft["notes"]).bind_value(draft, "notes").props("dark outlined dense rows=2").classes("w-full")
                            suggestions_row = ui.row().classes("w-full gap-1 flex-wrap")

                            def render_edit_suggestions(ch_draft=draft, row=suggestions_row, char_color=character.color) -> None:
                                row.clear()
                                query = str(ch_draft.get("tag_urls") or ch_draft.get("full_name") or ch_draft.get("name") or "")
                                suggestions = _canonical_character_suggestions(
                                    self.container.fandom_service.tag_suggestions(active.fandom_key, query, 24, category="character"),
                                    query,
                                )[:12]
                                with row:
                                    if not suggestions:
                                        ui.label("Refresh AO3 tag catalog for character-tag suggestions.").classes("text-[11px] text-gray-500")
                                        return
                                    for suggestion in suggestions:
                                        suggestion_label = _ao3_character_tag_label(suggestion.tag_url or suggestion.tag_text)
                                        pill = ui.button(
                                            suggestion_label,
                                            on_click=lambda _=None, s=suggestion, d=ch_draft: use_suggestion(s, d),
                                        ).props("dense rounded flat")
                                        pill.classes("max-w-full")
                                        pill.style(
                                            f"border: 1px solid rgba({','.join(str(v) for v in rgb_from_hex(char_color))},0.32); "
                                            f"color: {normalized_label_color(char_color)} !important; overflow: hidden; text-overflow: ellipsis;"
                                        )
                                        with pill:
                                            rich_tooltip("character", char_color)

                            tag_input.on("update:model-value", lambda _=None: render_edit_suggestions())
                            render_edit_suggestions()
                            with ui.row().classes("w-full justify-end"):
                                save_btn = ui.button(
                                    "Save",
                                    icon="save",
                                    on_click=lambda _=None, d=draft, cid=character.id: save_character_from_draft(d, cid),
                                ).props("dense")
                                save_btn.style(f"background-color: {dark_button_color(character.color)} !important; color: white;")
                ui.separator().classes("bg-gray-800")
                with ui.row().classes("w-full gap-2 items-end"):
                    name_input = ui.input("Name", value=character_draft["name"]).bind_value(character_draft, "name").props(
                        "dark outlined dense"
                    ).classes("w-36")
                    full_name_input = ui.input("Full Name", value=character_draft["full_name"]).bind_value(character_draft, "full_name").props(
                        "dark outlined dense"
                    ).classes("flex-grow")
                    ui.color_input("Color", value=character_draft["color"]).bind_value(character_draft, "color").props("dark outlined dense").classes("w-32")
                tag_input = ui.input("Canonical AO3 character tag URL", value=character_draft["tag_urls"]).bind_value(
                    character_draft,
                    "tag_urls",
                ).props("dark outlined dense").classes("w-full")
                suggestions_row = ui.row().classes("w-full gap-1 flex-wrap")

                def render_suggestions() -> None:
                    suggestions_row.clear()
                    query = str(character_draft["tag_urls"] or character_draft["full_name"] or character_draft["name"] or "")
                    suggestions = _canonical_character_suggestions(
                        self.container.fandom_service.tag_suggestions(active.fandom_key, query, 28, category="character"),
                        query,
                    )[:14]
                    with suggestions_row:
                        if not suggestions:
                            ui.label("Refresh AO3 tag catalog for live suggestions.").classes("text-[11px] text-gray-500")
                            return
                        for suggestion in suggestions:
                            suggestion_label = _ao3_character_tag_label(suggestion.tag_url or suggestion.tag_text)
                            pill = ui.button(
                                suggestion_label,
                                on_click=lambda _=None, s=suggestion: use_suggestion(s),
                            ).props("dense rounded flat")
                            pill.classes("max-w-full")
                            pill.style(
                                f"border: 1px solid rgba({','.join(str(v) for v in rgb_from_hex(current_color()))},0.32); "
                                f"color: {normalized_label_color(current_color())} !important; overflow: hidden; text-overflow: ellipsis;"
                            )
                            with pill:
                                rich_tooltip(suggestion.category.replace("_", " "), current_color())

                name_input.on("update:model-value", lambda _=None: render_suggestions())
                full_name_input.on("update:model-value", lambda _=None: render_suggestions())
                tag_input.on("update:model-value", lambda _=None: render_suggestions())
                render_suggestions()
                add_btn = ui.button("Add Character", icon="add", on_click=lambda: save_character_from_draft(character_draft))
                add_btn.style(f"background-color: {dark_button_color(current_color())} !important; color: white;")

        dialog = ui.dialog()
        dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("flex flex-col p-0 gap-0 overflow-hidden").style(base_dialog_style) as card:
            header_row = ui.row().classes("w-full items-center justify-between p-4 border-b border-gray-700 shrink-0").style(
                "background: rgba(22, 27, 34, 0.75); backdrop-filter: blur(8px);"
            )
            header_row.on("click", lambda _=None: collapse_character_expansions())
            with header_row:
                with ui.row().classes("items-center gap-2 min-w-0"):
                    ui.icon("collections_bookmark", size="sm").style(f"color: {normalized_label_color(accent)};")
                    ui.label("Edit Fandom:").classes("text-lg font-bold text-gray-300")
                    ui.label(active.display_name if not is_new else "New Fandom").classes("text-lg font-bold truncate min-w-0").style(
                        glow_text(accent, 4)
                    )
                    maximized = {"value": False}

                    def toggle_maximize() -> None:
                        maximized["value"] = not maximized["value"]
                        if maximized["value"]:
                            maximize_btn._props["icon"] = "fullscreen_exit"
                            card.style(replace=fullscreen_dialog_style)
                            dialog.props("maximized")
                            ui.run_javascript("if (!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(() => {}); }")
                        else:
                            maximize_btn._props["icon"] = "fullscreen"
                            card.style(replace=base_dialog_style)
                            dialog.props(remove="maximized")
                            ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")
                        maximize_btn.update()

                    maximize_btn = ui.button(icon="fullscreen", on_click=toggle_maximize).props("flat round dense size=sm")
                    maximize_btn.style(f"color: {normalized_label_color(accent)} !important; opacity: 0.78;")
                    with maximize_btn:
                        rich_tooltip("Toggle fullscreen", accent)

                ui.button(icon="close", on_click=close_dialog).props("flat round dense color=white")
            tabs = ui.tabs(value=initial_tab).classes("w-full text-gray-400 shrink-0").props("dense align=left")
            with tabs:
                identity_tab = ui.tab("Identity", icon="fingerprint")
                identity_tab.on("click", lambda _=None: self.container.preferences_service.set("fandom_dialog_tab", "Identity"))
                style_tab = ui.tab("Style", icon="palette")
                style_tab.on("click", lambda _=None: self.container.preferences_service.set("fandom_dialog_tab", "Style"))
                config_tab = ui.tab("Config", icon="tune")
                config_tab.on("click", lambda _=None: self.container.preferences_service.set("fandom_dialog_tab", "Config"))
                characters_tab = ui.tab("Characters", icon="group")
                characters_tab.on("click", lambda _=None: self.container.preferences_service.set("fandom_dialog_tab", "Characters"))
            tabs.on("update:model-value", handle_tab)
            ui.separator().classes("bg-gray-700")
            tab_lookup = {"Identity": identity_tab, "Style": style_tab, "Config": config_tab, "Characters": characters_tab}
            panels = ui.tab_panels(tabs, value=tab_lookup[initial_tab]).classes("w-full flex-grow p-0 text-white overflow-hidden").style(
                "background: transparent;"
            )
            with panels:
                with ui.tab_panel(identity_tab).classes("w-full h-full p-0"):
                    with ui.scroll_area().classes("w-full h-full px-4 py-4"):
                        with ui.column().classes("w-full gap-4"):
                            with ui.row().classes("w-full items-start gap-3"):
                                refs["avatar_slot"] = ui.element("div").classes("p-0 m-0 relative w-[76px] h-[76px] shrink-0")
                                render_avatar_slot()
                                with ui.column().classes("gap-2 flex-grow min-w-0"):
                                    ui.input("Fandom tag", value=draft["tag"]).bind_value(draft, "tag").props("dark outlined dense").classes("w-full")
                                    ui.input("Display name", value=draft["display_name"]).bind_value(draft, "display_name").props(
                                        "dark outlined dense"
                                    ).classes("w-full")
                            with ui.row().classes("w-full items-center gap-2"):
                                color_btn = ui.color_input("Theme color", value=draft["color"]).bind_value(draft, "color").props(
                                    "dark outlined dense"
                                ).classes("w-full")
                                with color_btn:
                                    rich_tooltip("Theme color", str(draft["color"]))
                            ui.separator().classes("bg-gray-800")
                            ui.label("Fandom Notes").classes("text-sm font-bold").style(glow_text(str(draft["color"]), 3))
                            ui.textarea(value=draft["notes"]).bind_value(draft, "notes").props("dark outlined rows=8").classes("w-full")
                with ui.tab_panel(style_tab).classes("w-full h-full p-0"):
                    with ui.scroll_area().classes("w-full h-full px-4 py-4"):
                        self._render_style_controls(
                            settings=style_state,
                            accent=current_color(),
                            save_handler=save_fandom_style,
                            enabled_state=style_enabled,
                            show_thresholds=False,
                        )
                with ui.tab_panel(config_tab).classes("w-full h-full p-0"):
                    with ui.scroll_area().classes("w-full h-full px-4 py-4"):
                        refs["config_container"] = ui.column().classes("w-full gap-3")
                        render_config_controls()
                with ui.tab_panel(characters_tab).classes("w-full h-full p-0"):
                    character_scroll = ui.scroll_area().classes("w-full h-full px-4 py-4")
                    character_scroll.on(
                        "click",
                        lambda _=None: collapse_character_expansions(),
                        js_handler=(
                            "(event) => { "
                            "if (event.target.closest('.character-profile-expanded, .character-profile-pill, "
                            ".q-field, .q-btn, button, input, textarea, [role=\"button\"]')) return; "
                            "emit(); "
                            "}"
                        ),
                    )
                    with character_scroll:
                        refs["character_panel"] = ui.column().classes("w-full gap-3")
                        render_character_panel()

            footer_row = ui.row().classes("w-full items-center justify-between p-3 border-t border-gray-700 shrink-0").style(
                "background: rgba(13, 17, 23, 0.78);"
            )
            footer_row.on(
                "click",
                lambda _=None: collapse_character_expansions(),
                js_handler=(
                    "(event) => { "
                    "if (event.target.closest('.q-btn, button, input, textarea, [role=\"button\"]')) return; "
                    "emit(); "
                    "}"
                ),
            )
            with footer_row:
                ui.label("Changes are local until saved.").classes("text-xs italic text-gray-500")
                footer_save = ui.button("Save", icon="save")
                footer_save.on("click.stop", lambda _=None: save_fandom())
                footer_save.style(
                    f"background-color: {dark_button_color(accent)} !important; color: white;"
                )
        dialog.open()

    def _open_filter_json_dialog(
        self,
        state: dict[str, Any],
        color: str,
        on_apply: Callable[[], None] | None = None,
    ) -> None:
        draft = {"json": json.dumps(state, ensure_ascii=False, indent=2)}
        with self.root or ui.column():
            dialog = ui.dialog()
            dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("w-[560px] max-w-[94vw] p-0 gap-0 overflow-hidden").style(wash_background(color, 0.16)):
            with ui.row().classes("w-full items-center justify-between p-3 border-b border-gray-700").style(
                "background: rgba(22, 27, 34, 0.75); backdrop-filter: blur(8px);"
            ):
                ui.label("Filter JSON").classes("text-base font-bold").style(glow_text(color, 4))
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=white")
            with ui.column().classes("w-full gap-3 p-3"):
                ui.textarea(value=draft["json"]).bind_value(draft, "json").props("dark outlined rows=16").classes("w-full font-mono text-xs")

            def apply_json() -> None:
                try:
                    parsed = json.loads(str(draft["json"] or "{}"))
                except json.JSONDecodeError as exc:
                    self._notify(f"Filter JSON is invalid: {exc}", "negative")
                    return
                if not isinstance(parsed, dict):
                    self._notify("Filter JSON must be an object.", "warning")
                    return
                state.clear()
                state.update(parsed)
                dialog.close()
                if on_apply:
                    on_apply()

            with ui.row().classes("w-full items-center justify-between p-3 border-t border-gray-700").style(
                "background: rgba(13, 17, 23, 0.78);"
            ):
                ui.label("Advanced local filter state.").classes("text-xs italic text-gray-500")
                ui.button("Apply", icon="check", on_click=apply_json).style(
                    f"background-color: {dark_button_color(color)} !important; color: white;"
                )
        dialog.open()

    async def _refresh_tag_catalog(
        self,
        profile: FandomProfile,
        rerender: Callable[[], None] | None = None,
    ) -> None:
        client = self._current_client()
        self._notify("Refreshing AO3 tag suggestions using local Firefox AO3 cookies...", "info", client=client)
        result = await run.io_bound(lambda: self.container.fandom_service.refresh_tag_catalog(profile))
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        try:
            if rerender:
                rerender()
            else:
                self.refresh()
        except RuntimeError:
            return

    def _open_fandom_avatar_dialog(self, profile: FandomProfile) -> None:
        dialog = ui.dialog()
        dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("w-96 p-4 gap-3").style(wash_background(profile.color, 0.14)):
            ui.label(f"Update Avatar for {profile.display_name}").classes("text-lg font-bold text-white")
            ui.label("Drop an image. AO3 Studio crops it to a round local avatar.").classes("text-xs text-gray-400 mb-2")
            ui.upload(
                label="Drop Image Here",
                auto_upload=True,
                max_files=1,
                on_upload=lambda event, p=profile, d=dialog: self._handle_fandom_avatar_upload(event, p, d),
            ).props('accept="image/*" flat bordered').classes("w-full")
        dialog.open()

    async def _handle_fandom_avatar_upload(
        self,
        event: events.UploadEventArguments,
        profile: FandomProfile,
        dialog,
    ) -> None:
        try:
            content = await event.file.read()
            result = images.process_fandom_avatar_upload(profile.fandom_key, content)
            profile.avatar_url = str(result["avatar_url"])
            profile.color = str(result["avatar_color"])
            self.container.fandom_service.save_profile(profile)
            self._notify("Avatar uploaded.", "positive")
            dialog.close()
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            self._notify(f"Upload failed: {exc}", "negative")

    def _open_character_avatar_dialog(
        self,
        character_id: str,
        name: str,
        color: str,
        rerender: Callable[[], None] | None = None,
        fandom_key_value: str | None = None,
    ) -> None:
        dialog = ui.dialog()
        dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("w-96 p-4 gap-3").style(wash_background(color, 0.14)):
            ui.label(f"Update Avatar for {name}").classes("text-lg font-bold text-white")
            ui.label("Drop an image. AO3 Studio crops it to a round local avatar.").classes("text-xs text-gray-400 mb-2")
            ui.upload(
                label="Drop Image Here",
                auto_upload=True,
                max_files=1,
                on_upload=lambda event, cid=character_id, d=dialog, r=rerender, fk=fandom_key_value: self._handle_character_avatar_upload(event, cid, d, r, fk),
            ).props('accept="image/*" flat bordered').classes("w-full")
        dialog.open()

    async def _handle_character_avatar_upload(
        self,
        event: events.UploadEventArguments,
        character_id: str,
        dialog,
        rerender: Callable[[], None] | None = None,
        fandom_key_value: str | None = None,
    ) -> None:
        active_key = str(fandom_key_value or self._active_fandom().fandom_key)
        characters = self.container.fandom_service.list_characters(active_key)
        character = next((item for item in characters if item.id == character_id), None)
        if not character:
            self._notify("Character not found.", "negative")
            return
        try:
            content = await event.file.read()
            result = images.process_character_avatar_upload(character.id, content)
            self.container.fandom_service.save_character(
                fandom_key=character.fandom_key,
                character_id=character.id,
                name=character.name,
                full_name=character.full_name or character.name,
                color=character.color,
                avatar_url=str(result["avatar_url"]),
                tag_urls=character.tag_urls,
                notes=character.notes or "",
            )
            self._notify("Character avatar uploaded.", "positive")
            dialog.close()
            if rerender:
                rerender()
            else:
                self._render_right()
        except Exception as exc:  # noqa: BLE001
            self._notify(f"Upload failed: {exc}", "negative")

    def _render_center(self) -> None:
        if not self.center_container:
            return
        self._pubdate_labels.clear()
        self._updatedate_labels.clear()
        self._inline_work_panel_slots.clear()
        self._block_buttons.clear()
        self._work_remove_buttons.clear()
        self.center_container.clear()
        with self.center_container:
            renderer = {
                "Browse": self._page_browse,
                "Works": self._page_works,
                "Read": self._page_read,
                "Queue": self._page_queue,
                "Evaluated": self._page_evaluated,
                "Analytics": self._page_analytics,
                "Shared": self._page_shared,
                "Admin": self._page_admin,
            }.get(self.page, self._page_browse)
            if self.page == "Read":
                renderer()
                return
            with ui.scroll_area().classes("center-work-scroll w-full h-full min-h-0"):
                body = ui.column().classes("w-full min-h-full gap-3 p-3 min-w-0")
                if self.page in {"Queue", "Evaluated"}:
                    body.on("click", lambda _=None, m="evaluated" if self.page == "Evaluated" else "queue": self._disarm_cluster_cleanup(m))
                with body:
                    renderer()
        self._restore_center_scroll_after_render()

    @staticmethod
    def _work_card_dom_id(work_id: str) -> str:
        return "ao3-work-card-" + re.sub(r"[^A-Za-z0-9_-]+", "_", str(work_id or "work"))

    @staticmethod
    def _work_card_click_js() -> str:
        return """
            (event) => {
                const card =
                    (event.target && event.target.closest ? event.target.closest('.work-card') : null) ||
                    (event.currentTarget && event.currentTarget.closest ? event.currentTarget.closest('.work-card') : null) ||
                    event.currentTarget;
                if (event.target && event.target.closest && event.target.closest('.inline-work-panel')) {
                    return;
                }
                const scroller = () =>
                    document.querySelector('.center-work-scroll .q-scrollarea__container') ||
                    document.querySelector('.center-work-scroll');
                const now = () =>
                    window.performance && typeof window.performance.now === 'function'
                        ? window.performance.now()
                        : Date.now();
                const frame = (callback) =>
                    typeof requestAnimationFrame === 'function'
                        ? requestAnimationFrame(callback)
                        : setTimeout(callback, 16);
                const moveScroll = (box, nextTop) => {
                    const target = Math.max(0, Number(nextTop) || 0);
                    const root = document.querySelector('.center-work-scroll');
                    const idMatch = String(root && root.id ? root.id : '').match(/\\d+/);
                    if (idMatch && typeof runMethod === 'function') {
                        try {
                            runMethod(Number(idMatch[0]), 'setScrollPosition', ['vertical', target, 0]);
                        } catch (_) {}
                    }
                    try {
                        box.scrollTo(0, target);
                    } catch (_) {}
                    try {
                        box.scrollTop = target;
                    } catch (_) {}
                    try {
                        if (Math.abs((Number(box.scrollTop) || 0) - target) > 0.5) {
                            box.scrollTo(0, target);
                        }
                    } catch (_) {}
                    try {
                        const delta = target - (Number(box.scrollTop) || 0);
                        if (Math.abs(delta) > 0.5) {
                            box.scrollBy(0, delta);
                        }
                    } catch (_) {}
                };
                const measurePanel = (panel) => Math.max(
                    panel && panel.querySelector('.inline-work-panel-inner')
                        ? panel.querySelector('.inline-work-panel-inner').scrollHeight || 0
                        : 0,
                    panel && panel.querySelector('.inline-work-panel-inner')
                        ? panel.querySelector('.inline-work-panel-inner').getBoundingClientRect().height || 0
                        : 0,
                    1
                ) + 10;
                const disconnectPanelObserver = (panel) => {
                    if (!panel || !panel.__ao3ResizeObserver) return;
                    try {
                        panel.__ao3ResizeObserver.disconnect();
                    } catch (_) {}
                    panel.__ao3ResizeObserver = null;
                };
                const clearPanelAnimation = (panel) => {
                    if (!panel) return;
                    if (panel.__ao3PanelAnimation) {
                        try {
                            panel.__ao3PanelAnimation.cancel();
                        } catch (_) {}
                        panel.__ao3PanelAnimation = null;
                    }
                    const inner = panel.querySelector('.inline-work-panel-inner');
                    if (inner && inner.__ao3InnerAnimation) {
                        try {
                            inner.__ao3InnerAnimation.cancel();
                        } catch (_) {}
                        inner.__ao3InnerAnimation = null;
                    }
                };
                const clearInnerReveal = (inner) => {
                    if (!inner) return;
                    inner.style.opacity = '';
                    inner.style.filter = '';
                    inner.style.clipPath = '';
                };
                const primeOpenInner = (inner, opacity = '1') => {
                    if (!inner) return;
                    if (inner.__ao3InnerAnimation) {
                        try {
                            inner.__ao3InnerAnimation.cancel();
                        } catch (_) {}
                        inner.__ao3InnerAnimation = null;
                    }
                    inner.style.opacity = opacity;
                    inner.style.filter = 'blur(0) saturate(1)';
                    inner.style.clipPath = 'inset(0 0 0 0)';
                };
                const nextPanelOpenToken = (panel) => {
                    if (!panel) return '';
                    const token = (Number(panel.dataset.ao3OpenToken) || 0) + 1;
                    panel.dataset.ao3OpenToken = String(token);
                    return String(token);
                };
                const setPanelHeight = (panel, value) => {
                    const height = Math.max(0, Math.ceil(Number(value) || 0));
                    panel.style.height = `${height}px`;
                    panel.dataset.ao3OpenHeight = String(height);
                };
                const animatePanelHeight = (panel, from, to, duration, easing, afterFinish) => {
                    if (!panel) return null;
                    if (panel.__ao3PanelAnimation) {
                        try {
                            panel.__ao3PanelAnimation.cancel();
                        } catch (_) {}
                        panel.__ao3PanelAnimation = null;
                    }
                    const start = Math.max(0, Math.ceil(Number(from) || 0));
                    const end = Math.max(0, Math.ceil(Number(to) || 0));
                    panel.style.height = `${start}px`;
                    panel.getBoundingClientRect();
                    if (typeof panel.animate !== 'function') {
                        setPanelHeight(panel, end);
                        if (afterFinish) afterFinish();
                        return null;
                    }
                    const animation = panel.animate(
                        [{ height: `${start}px` }, { height: `${end}px` }],
                        { duration, easing, fill: 'both' }
                    );
                    panel.__ao3PanelAnimation = animation;
                    animation.onfinish = () => {
                        panel.__ao3PanelAnimation = null;
                        setPanelHeight(panel, end);
                        if (afterFinish) afterFinish();
                    };
                    return animation;
                };
                const cancelBottomReveal = () => {
                    const motion = window.__ao3BottomRevealMotion;
                    if (!motion) return;
                    motion.cancelled = true;
                    if (motion.abort) {
                        try {
                            motion.abort.abort();
                        } catch (_) {}
                    }
                    window.__ao3BottomRevealMotion = null;
                };
                const startBottomReveal = (card, box, duration = 520) => {
                    if (!card || !box) return;
                    cancelBottomReveal();
                    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
                    const motion = {
                        card,
                        box,
                        until: now() + duration,
                        cancelled: false,
                        abort: controller,
                    };
                    window.__ao3BottomRevealMotion = motion;
                    const cancel = () => {
                        motion.cancelled = true;
                        if (window.__ao3BottomRevealMotion === motion) {
                            window.__ao3BottomRevealMotion = null;
                        }
                    };
                    const options = controller ? { signal: controller.signal, once: true, passive: true } : { once: true, passive: true };
                    try {
                        window.addEventListener('wheel', cancel, options);
                        window.addEventListener('touchstart', cancel, options);
                        window.addEventListener('pointerdown', cancel, options);
                        window.addEventListener('keydown', cancel, controller ? { signal: controller.signal, once: true } : { once: true });
                    } catch (_) {}
                    const tick = () => {
                        if (motion.cancelled || window.__ao3BottomRevealMotion !== motion) return;
                        const scrollRect = box.getBoundingClientRect();
                        const cardRect = card.getBoundingClientRect();
                        const overflow = cardRect.bottom - scrollRect.bottom + 18;
                        if (overflow > 0) {
                            const step = Math.min(Math.max(overflow * 0.38, 3), 24);
                            moveScroll(box, (Number(box.scrollTop) || 0) + step);
                        }
                        if (now() < motion.until || overflow > 1) {
                            frame(tick);
                        } else {
                            if (controller) {
                                try {
                                    controller.abort();
                                } catch (_) {}
                            }
                            if (window.__ao3BottomRevealMotion === motion) {
                                window.__ao3BottomRevealMotion = null;
                            }
                        }
                    };
                    frame(tick);
                };
                const watchOpenPanel = (card, panel, box) => {
                    if (!card || !panel) return;
                    const inner = panel.querySelector('.inline-work-panel-inner');
                    if (!inner || typeof ResizeObserver === 'undefined') return;
                    disconnectPanelObserver(panel);
                    let settleUntil = now() + 420;
                    let lastHeight = Math.max(Number(panel.dataset.ao3OpenHeight) || 0, panel.getBoundingClientRect().height || 0);
                    const adjust = () => {
                        if (!card.classList.contains('work-card-expanded') || card.dataset.ao3ClientCollapsed === '1') return;
                        const target = Math.max(measurePanel(panel), 1);
                        const current = Math.max(Number(panel.dataset.ao3OpenHeight) || 0, panel.getBoundingClientRect().height || 0);
                        if (Math.abs(target - current) > 1.5) {
                            const duration = Math.min(220, Math.max(110, Math.abs(target - current) * 1.6));
                            animatePanelHeight(panel, current, target, duration, 'cubic-bezier(0.16, 1, 0.3, 1)', () => {
                                lastHeight = target;
                            });
                            startBottomReveal(card, box, duration + 180);
                        } else if (Math.abs(lastHeight - current) > 0.5) {
                            setPanelHeight(panel, current);
                            lastHeight = current;
                        }
                    };
                    const observer = new ResizeObserver(() => {
                        frame(adjust);
                        settleUntil = Math.max(settleUntil, now() + 120);
                    });
                    observer.observe(inner);
                    panel.__ao3ResizeObserver = observer;
                    const settle = () => {
                        adjust();
                        if (now() < settleUntil) {
                            frame(settle);
                        } else {
                            startBottomReveal(card, box, 160);
                        }
                    };
                    frame(settle);
                };
                const animatePanelOpen = (card, box) => {
                    const panel = card ? card.querySelector('.inline-work-panel') : null;
                    if (!card || !panel) return;
                    const inner = panel.querySelector('.inline-work-panel-inner');
                    const startHeight = Math.max(panel.getBoundingClientRect().height || 0, 0);
                    clearPanelAnimation(panel);
                    disconnectPanelObserver(panel);
                    const openToken = nextPanelOpenToken(panel);
                    delete card.dataset.ao3ClientCollapsed;
                    setPanelHeight(panel, startHeight);
                    panel.style.overflow = 'hidden';
                    panel.dataset.ao3Opening = '1';
                    primeOpenInner(inner, startHeight > 12 ? '1' : '0.96');
                    card.classList.add('work-card-expanded');
                    frame(() => {
                        if (
                            panel.dataset.ao3OpenToken !== openToken ||
                            !card.classList.contains('work-card-expanded') ||
                            card.dataset.ao3ClientCollapsed === '1'
                        ) {
                            return;
                        }
                        const targetHeight = measurePanel(panel);
                        const scrollRect = box ? box.getBoundingClientRect() : null;
                        const cardRect = card.getBoundingClientRect();
                        if (box && scrollRect && cardRect.bottom + Math.max(0, targetHeight - startHeight) > scrollRect.bottom - 4) {
                            startBottomReveal(card, box, 620);
                        }
                        const panelAnimation = animatePanelHeight(
                            panel,
                            startHeight,
                            targetHeight,
                            365,
                            'cubic-bezier(0.16, 1, 0.3, 1)',
                            () => {
                                if (
                                    panel.dataset.ao3OpenToken === openToken &&
                                    card.classList.contains('work-card-expanded') &&
                                    card.dataset.ao3ClientCollapsed !== '1'
                                ) {
                                    delete panel.dataset.ao3Opening;
                                    panel.style.overflow = 'hidden';
                                    setPanelHeight(panel, measurePanel(panel));
                                    watchOpenPanel(card, panel, box);
                                }
                            }
                        );
                        if (inner && typeof inner.animate === 'function') {
                            const innerAnimation = inner.animate(
                                [
                                    { opacity: startHeight > 12 ? 1 : 0.96, filter: 'blur(0) saturate(1)', clipPath: 'inset(0 0 0 0)' },
                                    { opacity: 1, filter: 'blur(0) saturate(1)', clipPath: 'inset(0 0 0 0)' },
                                ],
                                {
                                    duration: 135,
                                    easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
                                    fill: 'both',
                                }
                            );
                            inner.__ao3InnerAnimation = innerAnimation;
                            innerAnimation.onfinish = () => {
                                inner.__ao3InnerAnimation = null;
                                if (
                                    panel.dataset.ao3OpenToken === openToken &&
                                    card.classList.contains('work-card-expanded') &&
                                    card.dataset.ao3ClientCollapsed !== '1'
                                ) {
                                    clearInnerReveal(inner);
                                }
                            };
                        } else if (inner) {
                            clearInnerReveal(inner);
                        }
                    });
                };
                const closeCard = (other) => {
                    if (!other || !other.classList.contains('work-card-expanded')) return;
                    const otherPanel = other.querySelector('.inline-work-panel');
                    if (otherPanel) {
                        const inner = otherPanel.querySelector('.inline-work-panel-inner');
                        const currentHeight = Math.max(otherPanel.getBoundingClientRect().height || 0, 1);
                        clearPanelAnimation(otherPanel);
                        disconnectPanelObserver(otherPanel);
                        nextPanelOpenToken(otherPanel);
                        setPanelHeight(otherPanel, currentHeight);
                        otherPanel.style.overflow = 'hidden';
                        delete otherPanel.dataset.ao3Opening;
                        if (inner) {
                            inner.style.opacity = '1';
                            inner.style.filter = 'blur(0) saturate(1)';
                            inner.style.clipPath = 'inset(0 0 0 0)';
                        }
                        otherPanel.getBoundingClientRect();
                        const panelAnimation = animatePanelHeight(
                            otherPanel,
                            currentHeight,
                            0,
                            265,
                            'cubic-bezier(0.4, 0, 0.2, 1)',
                            () => {
                                otherPanel.style.height = '';
                                otherPanel.style.overflow = '';
                                otherPanel.dataset.ao3OpenHeight = '';
                                if (inner) {
                                    inner.__ao3InnerAnimation = null;
                                    clearInnerReveal(inner);
                                }
                            }
                        );
                        if (inner && typeof inner.animate === 'function') {
                            const innerAnimation = inner.animate(
                                [
                                    { opacity: 1, filter: 'blur(0) saturate(1)', clipPath: 'inset(0 0 0 0)' },
                                    { opacity: 0, filter: 'blur(1.4px) saturate(0.94)', clipPath: 'inset(0 0 8% 0)' },
                                ],
                                {
                                    duration: 185,
                                    easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
                                    fill: 'both',
                                }
                            );
                            inner.__ao3InnerAnimation = innerAnimation;
                        } else if (inner) {
                            inner.__ao3InnerAnimation = null;
                            clearInnerReveal(inner);
                        }
                    }
                    other.dataset.ao3ClientCollapsed = '1';
                    other.classList.remove('work-card-expanded');
                };
                const maintain = () => {
                    const restore = window.__ao3CenterScrollRestore;
                    const box = scroller();
                    if (!restore || restore.cancelled) return;
                    if (!box) {
                        if (now() < (Number(restore.until) || 0)) {
                            frame(maintain);
                        }
                        return;
                    }
                    const anchor = restore.cardId ? document.getElementById(restore.cardId) : null;
                    if (anchor) {
                        const cardRect = anchor.getBoundingClientRect();
                        const delta = cardRect.top - (Number(restore.viewportTop) || 0);
                        if (Math.abs(delta) > 0.5) {
                            moveScroll(box, (Number(box.scrollTop) || 0) + delta);
                        }
                    }
                    if (now() < (Number(restore.until) || 0)) {
                        frame(maintain);
                    }
                };
                const box = scroller();
                if (card && box) {
                    const cardRect = card.getBoundingClientRect();
                    const expanded = card.classList.contains('work-card-expanded') && card.dataset.ao3ClientCollapsed !== '1';
                    if (expanded) {
                        const panel = card.querySelector('.inline-work-panel');
                        if (panel) {
                            panel.classList.remove('inline-work-panel-closing');
                        }
                        closeCard(card);
                        emit({desired: 'close'});
                        return;
                    }
                    delete card.dataset.ao3ClientCollapsed;
                    cancelBottomReveal();
                    const panel = card.querySelector('.inline-work-panel');
                    const needsHydration =
                        !panel ||
                        panel.classList.contains('inline-work-panel-unhydrated') ||
                        !panel.querySelector('.inline-work-panel-inner');
                    if (needsHydration) {
                        if (card.dataset.ao3Hydrating === '1') return;
                        const hydrateToken = String((Number(window.__ao3HydrateOpenToken) || 0) + 1);
                        window.__ao3HydrateOpenToken = hydrateToken;
                        card.dataset.ao3Hydrating = '1';
                        card.dataset.ao3HydrateToken = hydrateToken;
                        if (panel) {
                            panel.classList.add('inline-work-panel-pending');
                        }
                        emit({desired: 'open', hydrate: true, token: hydrateToken});
                        return;
                    }
                    const expandedAbove = [...document.querySelectorAll('.work-card-expanded')].some(other => {
                        if (other === card) return false;
                        return other.getBoundingClientRect().top < cardRect.top;
                    });
                    if (expandedAbove) {
                        window.__ao3CenterScrollRestore = {
                            cardId: card.id,
                            viewportTop: cardRect.top,
                            until: now() + 260,
                            cancelled: false,
                        };
                        const cancel = () => {
                            if (window.__ao3CenterScrollRestore) {
                                window.__ao3CenterScrollRestore.cancelled = true;
                            }
                        };
                        window.addEventListener('wheel', cancel, { once: true, passive: true });
                        window.addEventListener('touchstart', cancel, { once: true, passive: true });
                        window.addEventListener('pointerdown', cancel, { once: true, passive: true });
                        window.addEventListener('keydown', cancel, { once: true });
                        frame(maintain);
                    }
                    document.querySelectorAll('.work-card-expanded').forEach(other => {
                        if (other !== card) {
                            closeCard(other);
                        }
                    });
                    animatePanelOpen(card, box);
                }
                emit({desired: 'open'});
            }
        """

    def _animate_hydrated_work_panel(self, work_id: str, *, hydrate_token: str = "", client: Any | None = None) -> None:
        card_id = json.dumps(self._work_card_dom_id(work_id))
        expected_token = json.dumps(hydrate_token or "")
        script = f"""
                    (() => {{
                        const cardId = {card_id};
                        const expectedToken = {expected_token};
                        const now = () =>
                            window.performance && typeof window.performance.now === 'function'
                                ? window.performance.now()
                                : Date.now();
                        const frame = (callback) =>
                            typeof requestAnimationFrame === 'function'
                                ? requestAnimationFrame(callback)
                                : setTimeout(callback, 16);
                        const started = now();
                        const scroller = () =>
                            document.querySelector('.center-work-scroll .q-scrollarea__container') ||
                            document.querySelector('.center-work-scroll');
                        const moveScroll = (box, nextTop) => {{
                            const target = Math.max(0, Number(nextTop) || 0);
                            const root = document.querySelector('.center-work-scroll');
                            const idMatch = String(root && root.id ? root.id : '').match(/\\d+/);
                            if (idMatch && typeof runMethod === 'function') {{
                                try {{
                                    runMethod(Number(idMatch[0]), 'setScrollPosition', ['vertical', target, 0]);
                                }} catch (_) {{}}
                            }}
                            try {{ box.scrollTo(0, target); }} catch (_) {{}}
                            try {{ box.scrollTop = target; }} catch (_) {{}}
                            try {{
                                const delta = target - (Number(box.scrollTop) || 0);
                                if (Math.abs(delta) > 0.5) box.scrollBy(0, delta);
                            }} catch (_) {{}}
                        }};
                        const measurePanel = (panel) => Math.max(
                            panel && panel.querySelector('.inline-work-panel-inner')
                                ? panel.querySelector('.inline-work-panel-inner').scrollHeight || 0
                                : 0,
                            panel && panel.querySelector('.inline-work-panel-inner')
                                ? panel.querySelector('.inline-work-panel-inner').getBoundingClientRect().height || 0
                                : 0,
                            1
                        ) + 10;
                        const setPanelHeight = (panel, value) => {{
                            const height = Math.max(0, Math.ceil(Number(value) || 0));
                            panel.style.height = `${{height}}px`;
                            panel.dataset.ao3OpenHeight = String(height);
                        }};
                        const disconnectPanelObserver = (panel) => {{
                            if (!panel || !panel.__ao3ResizeObserver) return;
                            try {{ panel.__ao3ResizeObserver.disconnect(); }} catch (_) {{}}
                            panel.__ao3ResizeObserver = null;
                        }};
                        const cancelAnimation = (panel) => {{
                            if (panel && panel.__ao3PanelAnimation) {{
                                try {{ panel.__ao3PanelAnimation.cancel(); }} catch (_) {{}}
                                panel.__ao3PanelAnimation = null;
                            }}
                            const inner = panel ? panel.querySelector('.inline-work-panel-inner') : null;
                            if (inner && inner.__ao3InnerAnimation) {{
                                try {{ inner.__ao3InnerAnimation.cancel(); }} catch (_) {{}}
                                inner.__ao3InnerAnimation = null;
                            }}
                        }};
                        const clearInnerReveal = (inner) => {{
                            if (!inner) return;
                            inner.style.opacity = '';
                            inner.style.filter = '';
                            inner.style.clipPath = '';
                        }};
                        const primeOpenInner = (inner, opacity = '1') => {{
                            if (!inner) return;
                            if (inner.__ao3InnerAnimation) {{
                                try {{ inner.__ao3InnerAnimation.cancel(); }} catch (_) {{}}
                                inner.__ao3InnerAnimation = null;
                            }}
                            inner.style.opacity = opacity;
                            inner.style.filter = 'blur(0) saturate(1)';
                            inner.style.clipPath = 'inset(0 0 0 0)';
                        }};
                        const nextPanelOpenToken = (panel) => {{
                            if (!panel) return '';
                            const token = (Number(panel.dataset.ao3OpenToken) || 0) + 1;
                            panel.dataset.ao3OpenToken = String(token);
                            return String(token);
                        }};
                        const animatePanelHeight = (panel, from, to, duration, easing, afterFinish) => {{
                            const start = Math.max(0, Math.ceil(Number(from) || 0));
                            const end = Math.max(0, Math.ceil(Number(to) || 0));
                            panel.style.height = `${{start}}px`;
                            panel.getBoundingClientRect();
                            if (typeof panel.animate !== 'function') {{
                                setPanelHeight(panel, end);
                                if (afterFinish) afterFinish();
                                return null;
                            }}
                            const animation = panel.animate(
                                [{{ height: `${{start}}px` }}, {{ height: `${{end}}px` }}],
                                {{ duration, easing, fill: 'both' }}
                            );
                            panel.__ao3PanelAnimation = animation;
                            animation.onfinish = () => {{
                                panel.__ao3PanelAnimation = null;
                                setPanelHeight(panel, end);
                                if (afterFinish) afterFinish();
                            }};
                            return animation;
                        }};
                        const cancelBottomReveal = () => {{
                            const motion = window.__ao3BottomRevealMotion;
                            if (!motion) return;
                            motion.cancelled = true;
                            if (motion.abort) {{
                                try {{ motion.abort.abort(); }} catch (_) {{}}
                            }}
                            window.__ao3BottomRevealMotion = null;
                        }};
                        const startBottomReveal = (card, box, duration = 520) => {{
                            if (!card || !box) return;
                            cancelBottomReveal();
                            const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
                            const motion = {{
                                card,
                                box,
                                until: now() + duration,
                                cancelled: false,
                                abort: controller,
                            }};
                            window.__ao3BottomRevealMotion = motion;
                            const cancel = () => {{
                                motion.cancelled = true;
                                if (window.__ao3BottomRevealMotion === motion) {{
                                    window.__ao3BottomRevealMotion = null;
                                }}
                            }};
                            const options = controller ? {{ signal: controller.signal, once: true, passive: true }} : {{ once: true, passive: true }};
                            try {{
                                window.addEventListener('wheel', cancel, options);
                                window.addEventListener('touchstart', cancel, options);
                                window.addEventListener('pointerdown', cancel, options);
                                window.addEventListener('keydown', cancel, controller ? {{ signal: controller.signal, once: true }} : {{ once: true }});
                            }} catch (_) {{}}
                            const tick = () => {{
                                if (motion.cancelled || window.__ao3BottomRevealMotion !== motion) return;
                                const scrollRect = box.getBoundingClientRect();
                                const cardRect = card.getBoundingClientRect();
                                const overflow = cardRect.bottom - scrollRect.bottom + 18;
                                if (overflow > 0) {{
                                    const step = Math.min(Math.max(overflow * 0.38, 3), 24);
                                    moveScroll(box, (Number(box.scrollTop) || 0) + step);
                                }}
                                if (now() < motion.until || overflow > 1) {{
                                    frame(tick);
                                }} else {{
                                    if (controller) {{
                                        try {{ controller.abort(); }} catch (_) {{}}
                                    }}
                                    if (window.__ao3BottomRevealMotion === motion) {{
                                        window.__ao3BottomRevealMotion = null;
                                    }}
                                }}
                            }};
                            frame(tick);
                        }};
                        const watchOpenPanel = (card, panel, box) => {{
                            if (!card || !panel) return;
                            const inner = panel.querySelector('.inline-work-panel-inner');
                            if (!inner || typeof ResizeObserver === 'undefined') return;
                            disconnectPanelObserver(panel);
                            let settleUntil = now() + 420;
                            let lastHeight = Math.max(Number(panel.dataset.ao3OpenHeight) || 0, panel.getBoundingClientRect().height || 0);
                            const adjust = () => {{
                                if (!card.classList.contains('work-card-expanded') || card.dataset.ao3ClientCollapsed === '1') return;
                                const target = Math.max(measurePanel(panel), 1);
                                const current = Math.max(Number(panel.dataset.ao3OpenHeight) || 0, panel.getBoundingClientRect().height || 0);
                                if (Math.abs(target - current) > 1.5) {{
                                    const duration = Math.min(220, Math.max(110, Math.abs(target - current) * 1.6));
                                    animatePanelHeight(panel, current, target, duration, 'cubic-bezier(0.16, 1, 0.3, 1)', () => {{
                                        lastHeight = target;
                                    }});
                                    startBottomReveal(card, box, duration + 180);
                                }} else if (Math.abs(lastHeight - current) > 0.5) {{
                                    setPanelHeight(panel, current);
                                    lastHeight = current;
                                }}
                            }};
                            const observer = new ResizeObserver(() => {{
                                frame(adjust);
                                settleUntil = Math.max(settleUntil, now() + 120);
                            }});
                            observer.observe(inner);
                            panel.__ao3ResizeObserver = observer;
                            const settle = () => {{
                                adjust();
                                if (now() < settleUntil) {{
                                    frame(settle);
                                }} else {{
                                    startBottomReveal(card, box, 160);
                                }}
                            }};
                            frame(settle);
                        }};
                        const closeCard = (other) => {{
                            if (!other || !other.classList.contains('work-card-expanded')) return;
                            const otherPanel = other.querySelector('.inline-work-panel');
                            if (otherPanel) {{
                                const inner = otherPanel.querySelector('.inline-work-panel-inner');
                                const currentHeight = Math.max(otherPanel.getBoundingClientRect().height || 0, 1);
                                cancelAnimation(otherPanel);
                                disconnectPanelObserver(otherPanel);
                                nextPanelOpenToken(otherPanel);
                                setPanelHeight(otherPanel, currentHeight);
                                otherPanel.style.overflow = 'hidden';
                                delete otherPanel.dataset.ao3Opening;
                                otherPanel.classList.add('inline-work-panel-closing');
                                if (inner) {{
                                    inner.style.opacity = '1';
                                    inner.style.filter = 'blur(0) saturate(1)';
                                    inner.style.clipPath = 'inset(0 0 0 0)';
                                }}
                                otherPanel.getBoundingClientRect();
                                animatePanelHeight(
                                    otherPanel,
                                    currentHeight,
                                    0,
                                    265,
                                    'cubic-bezier(0.4, 0, 0.2, 1)',
                                    () => {{
                                        otherPanel.style.height = '';
                                        otherPanel.style.overflow = '';
                                        otherPanel.dataset.ao3OpenHeight = '';
                                        otherPanel.classList.remove('inline-work-panel-closing');
                                        if (inner) {{
                                            inner.__ao3InnerAnimation = null;
                                            clearInnerReveal(inner);
                                        }}
                                    }}
                                );
                                if (inner && typeof inner.animate === 'function') {{
                                    const innerAnimation = inner.animate(
                                        [
                                            {{ opacity: 1, filter: 'blur(0) saturate(1)', clipPath: 'inset(0 0 0 0)' }},
                                            {{ opacity: 0, filter: 'blur(1.4px) saturate(0.94)', clipPath: 'inset(0 0 8% 0)' }},
                                        ],
                                        {{
                                            duration: 185,
                                            easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
                                            fill: 'both',
                                        }}
                                    );
                                    inner.__ao3InnerAnimation = innerAnimation;
                                }} else if (inner) {{
                                    inner.__ao3InnerAnimation = null;
                                    clearInnerReveal(inner);
                                }}
                            }}
                            other.dataset.ao3ClientCollapsed = '1';
                            other.classList.remove('work-card-expanded');
                        }};
                        const maintain = () => {{
                            const restore = window.__ao3CenterScrollRestore;
                            const box = scroller();
                            if (!restore || restore.cancelled) return;
                            if (!box) {{
                                if (now() < (Number(restore.until) || 0)) {{
                                    frame(maintain);
                                }}
                                return;
                            }}
                            const anchor = restore.cardId ? document.getElementById(restore.cardId) : null;
                            if (anchor) {{
                                const cardRect = anchor.getBoundingClientRect();
                                const delta = cardRect.top - (Number(restore.viewportTop) || 0);
                                if (Math.abs(delta) > 0.5) {{
                                    moveScroll(box, (Number(box.scrollTop) || 0) + delta);
                                }}
                            }}
                            if (now() < (Number(restore.until) || 0)) {{
                                frame(maintain);
                            }}
                        }};
                        const tryOpen = () => {{
                            const card = document.getElementById(cardId);
                            const panel = card ? card.querySelector('.inline-work-panel') : null;
                            const inner = panel ? panel.querySelector('.inline-work-panel-inner') : null;
                            const box = scroller();
                            if (!card || !panel || !inner || !box) return false;
                            if (
                                expectedToken &&
                                (
                                    String(window.__ao3HydrateOpenToken || '') !== expectedToken ||
                                    String(card.dataset.ao3HydrateToken || '') !== expectedToken
                                )
                            ) {{
                                delete card.dataset.ao3Hydrating;
                                panel.classList.remove('inline-work-panel-pending');
                                return true;
                            }}
                            cancelAnimation(panel);
                            disconnectPanelObserver(panel);
                            const token = nextPanelOpenToken(panel);
                            const startHeight = Math.max(panel.getBoundingClientRect().height || 0, 0);
                            panel.classList.remove('inline-work-panel-unhydrated', 'inline-work-panel-pending');
                            panel.removeAttribute('inert');
                            panel.setAttribute('aria-hidden', 'false');
                            delete card.dataset.ao3Hydrating;
                            delete card.dataset.ao3HydrateToken;
                            delete card.dataset.ao3ClientCollapsed;
                            const cardRectBeforeClose = card.getBoundingClientRect();
                            const expandedAbove = [...document.querySelectorAll('.work-card-expanded')].some(other => {{
                                if (other === card) return false;
                                return other.getBoundingClientRect().top < cardRectBeforeClose.top;
                            }});
                            if (expandedAbove) {{
                                window.__ao3CenterScrollRestore = {{
                                    cardId: card.id,
                                    viewportTop: cardRectBeforeClose.top,
                                    until: now() + 260,
                                    cancelled: false,
                                }};
                                const cancelRestore = () => {{
                                    if (window.__ao3CenterScrollRestore) {{
                                        window.__ao3CenterScrollRestore.cancelled = true;
                                    }}
                                }};
                                window.addEventListener('wheel', cancelRestore, {{ once: true, passive: true }});
                                window.addEventListener('touchstart', cancelRestore, {{ once: true, passive: true }});
                                window.addEventListener('pointerdown', cancelRestore, {{ once: true, passive: true }});
                                window.addEventListener('keydown', cancelRestore, {{ once: true }});
                                frame(maintain);
                            }}
                            document.querySelectorAll('.work-card-expanded').forEach(other => {{
                                if (other !== card) {{
                                    closeCard(other);
                                }}
                            }});
                            card.classList.add('work-card-expanded');
                            setPanelHeight(panel, startHeight);
                            panel.style.overflow = 'hidden';
                            panel.dataset.ao3Opening = '1';
                            primeOpenInner(inner, startHeight > 12 ? '1' : '0.96');
                            frame(() => {{
                                if (
                                    panel.dataset.ao3OpenToken !== token ||
                                    !card.classList.contains('work-card-expanded') ||
                                    card.dataset.ao3ClientCollapsed === '1'
                                ) {{
                                    return;
                                }}
                                const targetHeight = measurePanel(panel);
                                const scrollRect = box.getBoundingClientRect();
                                const cardRect = card.getBoundingClientRect();
                                if (cardRect.bottom + Math.max(0, targetHeight - startHeight) > scrollRect.bottom - 4) {{
                                    startBottomReveal(card, box, 620);
                                }}
                                animatePanelHeight(
                                    panel,
                                    startHeight,
                                    targetHeight,
                                    365,
                                    'cubic-bezier(0.16, 1, 0.3, 1)',
                                    () => {{
                                        if (
                                            panel.dataset.ao3OpenToken === token &&
                                            card.classList.contains('work-card-expanded') &&
                                            card.dataset.ao3ClientCollapsed !== '1'
                                        ) {{
                                            delete panel.dataset.ao3Opening;
                                            setPanelHeight(panel, measurePanel(panel));
                                            watchOpenPanel(card, panel, box);
                                        }}
                                    }}
                                );
                                if (typeof inner.animate === 'function') {{
                                    const innerAnimation = inner.animate(
                                        [
                                            {{ opacity: startHeight > 12 ? 1 : 0.96, filter: 'blur(0) saturate(1)', clipPath: 'inset(0 0 0 0)' }},
                                            {{ opacity: 1, filter: 'blur(0) saturate(1)', clipPath: 'inset(0 0 0 0)' }},
                                        ],
                                        {{
                                            duration: 135,
                                            easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
                                            fill: 'both',
                                        }}
                                    );
                                    inner.__ao3InnerAnimation = innerAnimation;
                                    innerAnimation.onfinish = () => {{
                                        inner.__ao3InnerAnimation = null;
                                        if (
                                            panel.dataset.ao3OpenToken === token &&
                                            card.classList.contains('work-card-expanded') &&
                                            card.dataset.ao3ClientCollapsed !== '1'
                                        ) {{
                                            clearInnerReveal(inner);
                                        }}
                                    }};
                                }} else {{
                                    inner.__ao3InnerAnimation = null;
                                    clearInnerReveal(inner);
                                }}
                            }});
                            return true;
                        }};
                        const wait = () => {{
                            if (tryOpen()) return;
                            if (now() - started < 500) frame(wait);
                        }};
                        frame(() => frame(wait));
                    }})();
                    """

        try:
            if client is not None:
                with client:
                    ui.run_javascript(script)
            else:
                ui.run_javascript(script)
        except RuntimeError:
            if client is not None:
                try:
                    client.run_javascript(script)
                except RuntimeError:
                    return

    @staticmethod
    def _restore_center_scroll_after_render() -> None:
        try:
            ui.run_javascript(
                """
                (() => {
                    const restore = window.__ao3CenterScrollRestore;
                    if (!restore) return;
                    const now = () =>
                        window.performance && typeof window.performance.now === 'function'
                            ? window.performance.now()
                            : Date.now();
                    const frame = (callback) =>
                        typeof requestAnimationFrame === 'function'
                            ? requestAnimationFrame(callback)
                            : setTimeout(callback, 16);
                    const moveScroll = (box, nextTop) => {
                        const target = Math.max(0, Number(nextTop) || 0);
                        const root = document.querySelector('.center-work-scroll');
                        const idMatch = String(root && root.id ? root.id : '').match(/\\d+/);
                        if (idMatch && typeof runMethod === 'function') {
                            try {
                                runMethod(Number(idMatch[0]), 'setScrollPosition', ['vertical', target, 0]);
                            } catch (_) {}
                        }
                        try {
                            box.scrollTo(0, target);
                        } catch (_) {}
                        try {
                            box.scrollTop = target;
                        } catch (_) {}
                        try {
                            if (Math.abs((Number(box.scrollTop) || 0) - target) > 0.5) {
                                box.scrollTo(0, target);
                            }
                        } catch (_) {}
                        try {
                            const delta = target - (Number(box.scrollTop) || 0);
                            if (Math.abs(delta) > 0.5) {
                                box.scrollBy(0, delta);
                            }
                        } catch (_) {}
                    };
                    const run = () => {
                        if (restore.cancelled) {
                            window.__ao3CenterScrollRestore = null;
                            return;
                        }
                        const scroller =
                            document.querySelector('.center-work-scroll .q-scrollarea__container') ||
                            document.querySelector('.center-work-scroll');
                        if (!scroller) {
                            if (now() < (Number(restore.until) || 0)) {
                                frame(run);
                            }
                            return;
                        }
                        const card = restore.cardId ? document.getElementById(restore.cardId) : null;
                        if (card) {
                            const cardRect = card.getBoundingClientRect();
                            const delta = cardRect.top - (Number(restore.viewportTop) || 0);
                            if (Math.abs(delta) > 0.5) {
                                moveScroll(scroller, (Number(scroller.scrollTop) || 0) + delta);
                            }
                        }
                        if (now() < (Number(restore.until) || 0)) {
                            frame(run);
                        } else {
                            window.__ao3CenterScrollRestore = null;
                        }
                    };
                    frame(() => frame(run));
                })();
                """
            )
        except RuntimeError:
            return

    def _render_right_header(self) -> None:
        if not self.right_header_container:
            return
        self.right_header_container.clear()
        active = self._active_fandom()
        with self.right_header_container:
            if self.page == "Queue":
                header_hit = ui.row().classes("right-panel-header-hit w-full h-full items-center justify-end gap-1")
                header_hit.on("click", lambda _=None: self._disarm_cluster_cleanup("queue"))
                with header_hit:
                    self._render_cluster_cleanup_toolbar("queue", active.color)
            elif self.page == "Evaluated":
                header_hit = ui.row().classes("right-panel-header-hit w-full h-full items-center justify-end gap-1")
                header_hit.on("click", lambda _=None: self._disarm_cluster_cleanup("evaluated"))
                with header_hit:
                    self._render_cluster_cleanup_toolbar("evaluated", active.color)
            elif self.page == "Read":
                work_id = str(self.container.preferences_service.get("reader_work_id", "") or self.selected_work_id or "")
                result = self.container.reader_service.open_work(work_id, auto_download=False) if work_id else None
                if result and result.work:
                    work = result.work
                    chapters = result.chapters
                    chapter_index = max(1, int(result.active_chapter_index or 1))
                    chapter = chapters[chapter_index - 1] if chapters and chapter_index <= len(chapters) else None
                    characters = self.container.fandom_service.list_characters(active.fandom_key)
                    selected_id = self._reader_selected_character_id(
                        work.work_id,
                        chapter_index,
                        characters,
                        getattr(chapter, "html", "") if chapter else "",
                    )
                    selected_character = next((character for character in characters if character.id == selected_id), None)
                    sticky_enabled = self._reader_pov_sticky_enabled(work.work_id)
                    sticky_color = selected_character.color if selected_character and sticky_enabled else active.color
                    with ui.row().classes("right-panel-header-hit w-full h-full items-center justify-between gap-1"):
                        sticky = ui.button(icon="link" if sticky_enabled else "link_off").props("round flat dense size=sm")
                        sticky.classes("reader-pov-header-icon")
                        sticky.style(f"color: {normalized_label_color(sticky_color) if sticky_enabled else '#64748b'} !important;")
                        sticky.on(
                            "click.stop",
                            lambda _=None, w=work.work_id, ch=chapter_index, enabled=sticky_enabled: self._set_reader_pov_sticky(w, ch, not enabled),
                        )
                        with sticky:
                            rich_tooltip("POV persists between chapters" if sticky_enabled else "POV does not persist between chapters", sticky_color)
                        reset = ui.button(icon="restart_alt").props("round flat dense size=sm")
                        reset.classes("reader-pov-header-icon")
                        reset.style(f"color: {normalized_label_color(active.color)} !important;")
                        reset.on("click.stop", lambda _=None, w=work.work_id, ch=chapter_index: self._reset_reader_character_pool(w, ch))
                        with reset:
                            rich_tooltip("Reset character pool for this chapter", active.color)

    def _render_right(self) -> None:
        if not self.right_container:
            return
        if self.page in {"Queue", "Evaluated"}:
            self.right_container.classes(add="right-panel-batch-mode h-full min-h-full gap-0 p-0", remove="gap-3 p-3")
        else:
            self.right_container.classes(add="gap-3 p-3", remove="right-panel-batch-mode h-full min-h-full gap-0 p-0")
        self.right_container.clear()
        with self.right_container:
            if self.page == "Browse":
                self._render_browse_lookup_panel()
                return
            if self.page == "Works":
                self._render_works_side_panel()
                return
            if self.page == "Read":
                self._render_reader_side_panel()
                return
            if self.page == "Queue":
                self._render_batch_side_panel("queue")
                return
            if self.page == "Evaluated":
                self._render_batch_side_panel("evaluated")
                return
            if not self.selected_work_id:
                self._empty("article", "Select a work")
                return
            view = self.container.merge_service.work_view(self.selected_work_id)
            if not view:
                self._empty("article", "Selected work is not cached")
                return
            work = view.work
            ui.label(work.title or f"Work {work.work_id}").classes("text-lg font-bold")
            ui.label(work.author_name or "Unknown author").classes("text-sm text-gray-400")
            with ui.element("div").classes("soft-panel w-full p-3"):
                ui.label("Score Breakdown").classes("text-sm font-bold mb-2")
                if view.local_evaluation:
                    for key, value in view.local_evaluation.scores.items():
                        with ui.row().classes("w-full justify-between"):
                            ui.label(str(key)).classes("text-xs text-gray-500")
                            ui.label(str(value)).classes("text-xs font-bold")
                    if view.local_evaluation.model_name:
                        ui.label(f"Model: {view.local_evaluation.model_name}").classes("text-[11px] text-gray-500 mt-2")
                else:
                    ui.label("No local evaluation yet.").classes("text-xs text-gray-500")
            with ui.element("div").classes("soft-panel w-full p-3"):
                ui.label("Sync Info").classes("text-sm font-bold mb-2")
                if view.shared_overlay:
                    ui.label(f"Overlay: {view.shared_overlay.remote_schema_version}").classes("text-xs text-gray-400")
                    ui.label(f"Community count: {view.shared_overlay.evaluation_count or 0}").classes("text-xs text-gray-400")
                else:
                    ui.label("Local provenance only.").classes("text-xs text-gray-500")
            if view.local_evaluation and view.local_evaluation.notes_markdown:
                with ui.element("div").classes("soft-panel w-full p-3"):
                    ui.label("Notes").classes("text-sm font-bold")
                    ui.markdown(view.local_evaluation.notes_markdown).classes("text-sm")

    def _render_works_side_panel(self) -> None:
        active = self._active_fandom()
        state = {"search": self.container.preferences_service.get("work_search", "")}
        with ui.element("div").classes("soft-panel w-full p-2 right-panel-search").style("width: 100%; max-width: none; align-self: stretch;"):
            with ui.element("div").classes("right-panel-control-row right-panel-two-icon-grid"):
                search = ui.input(value=state["search"], placeholder="Search Works").bind_value(state, "search").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("right-panel-main-field min-w-0")
                search.on("keydown.enter", lambda _=None: self._search_works(state))
                apply_btn = ui.button(icon="search", on_click=lambda: self._search_works(state)).props("round flat dense")
                apply_btn.classes("right-panel-icon-button")
                apply_btn.style(f"color: {normalized_label_color(active.color)} !important;")
                with apply_btn:
                    rich_tooltip("Search pinned works and Work Sets", active.color)
                ui.element("div").classes("right-panel-icon-spacer")
        filter_state = self._cluster_filter_state("works")
        expanded = bool(self.container.preferences_service.get(f"works_ao3_filter_open:{active.fandom_key}", False))
        expansion = ui.expansion("AO3 Metadata Filters", icon="tune", value=expanded).classes("w-full filter-expansion soft-panel")
        expansion.on(
            "update:model-value",
            lambda event: self._set_works_metadata_open(self._event_bool(event)),
        )
        expansion.style(f"--filter-group-color: {active.color};")
        if expanded:
            with expansion:
                self._render_cluster_filter_panel(
                    filter_state,
                    active.color,
                    search_label="Search works",
                    apply_tooltip="Apply works metadata filters",
                )

    def _render_reader_side_panel(self) -> None:
        active = self._active_fandom()
        work_id = str(self.container.preferences_service.get("reader_work_id", "") or self.selected_work_id or "")
        if not work_id:
            self._empty("menu_book", "Select a work")
            return
        result = self.container.reader_service.open_work(work_id, auto_download=False)
        if not result.work:
            self._empty("menu_book", result.message or "Reader work is not cached")
            return
        work = result.work
        chapters = result.chapters
        chapter_index = max(1, int(result.active_chapter_index or 1))
        chapter = chapters[chapter_index - 1] if chapters and chapter_index <= len(chapters) else None
        accent = normalized_label_color(active.color)
        refresh_color = {"current": "#7ee787", "outdated": "#ef4444", "missing": "#94a3b8"}.get(result.freshness, "#94a3b8")
        with ui.element("div").classes("soft-panel w-full p-2 right-panel-search").style("width: 100%; max-width: none; align-self: stretch;"):
            with ui.element("div").classes("right-panel-control-row right-panel-reader-grid"):
                prev_btn = ui.button(icon="chevron_left").props("round flat dense size=sm")
                prev_btn.classes("reader-side-icon")
                prev_btn.style(f"color: {accent} !important;")
                if chapter_index <= 1:
                    prev_btn.props("disable")
                prev_btn.on("click.stop", lambda _=None, w=work.work_id, c=chapter_index - 1: self._set_reader_chapter(w, c))
                next_btn = ui.button(icon="chevron_right").props("round flat dense size=sm")
                next_btn.classes("reader-side-icon")
                next_btn.style(f"color: {accent} !important;")
                if not chapters or chapter_index >= len(chapters):
                    next_btn.props("disable")
                next_btn.on("click.stop", lambda _=None, w=work.work_id, c=chapter_index + 1: self._set_reader_chapter(w, c))
                if chapters:
                    ui.select(
                        {item.chapter_index: self._chapter_select_label(item.title, item.chapter_index) for item in chapters},
                        value=chapter_index,
                        on_change=lambda event, w=work.work_id: self._set_reader_chapter(w, int(event.value)),
                    ).props("dense dark outlined hide-bottom-space").classes("right-panel-main-field min-w-0")
                else:
                    ui.label("No chapters cached").classes("text-xs text-gray-500 right-panel-main-field min-w-0")
                refresh = ui.button(icon="refresh").props("round flat dense size=sm")
                refresh.classes("reader-side-icon")
                refresh.style(f"color: {refresh_color} !important;")
                refresh.on("click.stop", lambda _=None, w=work.work_id: self._start_reader_download(w, force=True))
                with refresh:
                    rich_tooltip("Refresh downloaded reader HTML", refresh_color)
        self._render_reader_character_pills(active, work, chapter, chapter_index)

    def _render_reader_character_pills(self, active: FandomProfile, work: Work, chapter: Any | None, chapter_index: int) -> None:
        characters = self.container.fandom_service.list_characters(active.fandom_key)
        if not characters:
            return
        work_tags = self.container.work_library_service.tags_for_work(work.work_id)
        chapter_html = getattr(chapter, "html", "") if chapter else ""
        selected_id = self._reader_selected_character_id(work.work_id, chapter_index, characters, chapter_html)
        committed = self._reader_character_view_committed(work.work_id, chapter_index)
        visible_characters = _reader_visible_characters_for_chapter(
            characters,
            work_tags,
            chapter_html,
            committed=committed,
        )
        if selected_id and selected_id not in {character.id for character in visible_characters}:
            selected_character = next((character for character in characters if character.id == selected_id), None)
            if selected_character:
                visible_characters.append(selected_character)
        with ui.row().classes("w-full gap-x-1 gap-y-1.5 flex-wrap items-center reader-character-pill-row px-2 -mt-1"):
            none_selected = self._reader_no_pov_enabled(work.work_id)
            no_pov = ui.element("button").props("type=button").classes(
                "work-tag-pill browse-tag-pill reader-character-pill reader-no-pov text-[11px]"
            )
            no_pov.style(self._filter_pill_style("#94a3b8", none_selected))
            no_pov.on(
                "click",
                lambda _=None, w=work.work_id, c=chapter_index: self._set_reader_character_selection("", w, c),
                js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
            )
            with no_pov:
                ui.label("No POV").classes("browse-tag-pill-label reader-character-pill-label")
                rich_tooltip("No POV tint", active.color)
            for character in visible_characters:
                display_name, _ = _character_profile_display_names(character)
                selected = character.id == selected_id
                pill = ui.element("button").props("type=button").classes(
                    "work-tag-pill browse-tag-pill reader-character-pill text-[11px]"
                )
                pill.style(self._filter_pill_style(character.color, selected))
                pill.on(
                    "click",
                    lambda _=None, c=character, w=work.work_id, ch=chapter_index: self._set_reader_character_selection(c.id, w, ch),
                    js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
                )
                with pill:
                    self._avatar_image(character.avatar_url, display_name, character.color, "22px", "200px", expand_side="left")
                    ui.label(display_name).classes("browse-tag-pill-label reader-character-pill-label")
                    rich_tooltip("Selected POV tint" if selected else "Select POV tint", character.color)

    @staticmethod
    def _reader_selected_character_key(work_id: str, chapter_index: int) -> str:
        return f"reader_selected_character:{work_id}:{max(1, int(chapter_index or 1))}"

    @staticmethod
    def _reader_pov_sticky_key(work_id: str) -> str:
        return f"reader_pov_sticky:{work_id}"

    @staticmethod
    def _reader_sticky_character_key(work_id: str) -> str:
        return f"reader_sticky_character:{work_id}"

    @staticmethod
    def _reader_pov_timeline_key(work_id: str) -> str:
        return f"reader_pov_timeline:{work_id}"

    @staticmethod
    def _reader_no_pov_key(work_id: str) -> str:
        return f"reader_no_pov:{work_id}"

    @staticmethod
    def _reader_character_pool_reset_key(work_id: str, chapter_index: int) -> str:
        return f"reader_character_pool_reset:{work_id}:{max(1, int(chapter_index or 1))}"

    def _reader_pov_sticky_enabled(self, work_id: str) -> bool:
        return bool(self.container.preferences_service.get(self._reader_pov_sticky_key(work_id), False))

    def _reader_character_pool_reset(self, work_id: str, chapter_index: int) -> bool:
        return bool(self.container.preferences_service.get(self._reader_character_pool_reset_key(work_id, chapter_index), False))

    def _reader_no_pov_enabled(self, work_id: str) -> bool:
        return bool(self.container.preferences_service.get(self._reader_no_pov_key(work_id), False))

    def _reader_character_view_committed(self, work_id: str, chapter_index: int) -> bool:
        if self._reader_character_list_committed(work_id, chapter_index):
            return True
        return self._reader_pov_sticky_enabled(work_id) and not self._reader_character_pool_reset(work_id, chapter_index)

    def _reader_pov_timeline(self, work_id: str) -> dict[int, str]:
        raw = self.container.preferences_service.get(self._reader_pov_timeline_key(work_id), {})
        if not isinstance(raw, dict):
            return {}
        timeline: dict[int, str] = {}
        for chapter, character_id in raw.items():
            try:
                chapter_index = max(1, int(chapter))
            except (TypeError, ValueError):
                continue
            value = str(character_id or "").strip()
            if value:
                timeline[chapter_index] = value
        return timeline

    def _save_reader_pov_timeline(self, work_id: str, timeline: dict[int, str]) -> None:
        payload = {str(chapter): character_id for chapter, character_id in sorted(timeline.items()) if character_id}
        self.container.preferences_service.set(self._reader_pov_timeline_key(work_id), payload)

    def _reader_timeline_character_id(self, work_id: str, chapter_index: int) -> str:
        timeline = self._reader_pov_timeline(work_id)
        previous_chapters = [chapter for chapter in timeline if chapter <= max(1, int(chapter_index or 1))]
        if previous_chapters:
            return timeline[max(previous_chapters)]
        legacy_id = str(self.container.preferences_service.get(self._reader_sticky_character_key(work_id), "") or "")
        return legacy_id

    def _reader_selected_character_id(
        self,
        work_id: str,
        chapter_index: int,
        characters: list[CharacterProfile] | None = None,
        chapter_html: str = "",
    ) -> str:
        if self._reader_no_pov_enabled(work_id):
            return ""
        key = self._reader_selected_character_key(work_id, chapter_index)
        selected_id = str(self.container.preferences_service.get(key, "") or "")
        character_by_id = {character.id: character for character in characters or []}
        if selected_id and characters is not None and selected_id not in character_by_id:
            self.container.preferences_service.set(key, "")
            return ""
        if selected_id:
            return selected_id
        if not self._reader_pov_sticky_enabled(work_id):
            return ""
        sticky_key = self._reader_sticky_character_key(work_id)
        sticky_id = self._reader_timeline_character_id(work_id, chapter_index)
        if not sticky_id:
            return ""
        if characters is not None and sticky_id not in character_by_id:
            return ""
        sticky_character = character_by_id.get(sticky_id)
        if sticky_character and not _chapter_mentions_character(chapter_html, sticky_character):
            return ""
        if not sticky_character and characters is not None:
            return ""
        return sticky_id

    def _reader_selected_character(
        self,
        work_id: str,
        chapter_index: int,
        characters: list[CharacterProfile],
        chapter_html: str = "",
    ) -> CharacterProfile | None:
        selected_id = self._reader_selected_character_id(work_id, chapter_index, characters, chapter_html)
        return next((character for character in characters if character.id == selected_id), None)

    def _set_reader_pov_sticky(self, work_id: str, chapter_index: int, enabled: bool) -> None:
        self.container.preferences_service.set(self._reader_pov_sticky_key(work_id), bool(enabled))
        if enabled:
            current_id = str(self.container.preferences_service.get(self._reader_selected_character_key(work_id, chapter_index), "") or "")
            if current_id:
                timeline = self._reader_pov_timeline(work_id)
                timeline[max(1, int(chapter_index or 1))] = current_id
                self._save_reader_pov_timeline(work_id, timeline)
                self.container.preferences_service.set(self._reader_sticky_character_key(work_id), current_id)
            self.container.preferences_service.set(self._reader_character_pool_reset_key(work_id, chapter_index), False)
        self._render_center()
        self._render_right_header()
        self._render_right()

    def _reset_reader_character_pool(self, work_id: str, chapter_index: int) -> None:
        self.container.preferences_service.set(self._reader_character_commit_key(work_id, chapter_index), False)
        self.container.preferences_service.set(self._reader_character_pool_reset_key(work_id, chapter_index), True)
        self._render_right_header()
        self._render_right()

    def _reader_character_commit_key(self, work_id: str, chapter_index: int) -> str:
        return f"reader_character_committed:{work_id}:{max(1, int(chapter_index or 1))}"

    def _reader_character_list_committed(self, work_id: str, chapter_index: int) -> bool:
        return bool(self.container.preferences_service.get(self._reader_character_commit_key(work_id, chapter_index), False))

    def _set_reader_character_selection(self, character_id: str, work_id: str = "", chapter_index: int = 1) -> None:
        key = self._reader_selected_character_key(work_id, chapter_index)
        no_pov_key = self._reader_no_pov_key(work_id)
        if not character_id:
            self.container.preferences_service.set(no_pov_key, not self._reader_no_pov_enabled(work_id))
        else:
            self.container.preferences_service.set(no_pov_key, False)
            self.container.preferences_service.set(key, str(character_id))
        if work_id:
            self.container.preferences_service.set(self._reader_character_commit_key(work_id, chapter_index), True)
            self.container.preferences_service.set(self._reader_character_pool_reset_key(work_id, chapter_index), False)
            if character_id and self._reader_pov_sticky_enabled(work_id):
                timeline = self._reader_pov_timeline(work_id)
                timeline[max(1, int(chapter_index or 1))] = str(character_id)
                self._save_reader_pov_timeline(work_id, timeline)
                self.container.preferences_service.set(self._reader_sticky_character_key(work_id), str(character_id))
        self._render_center()
        self._render_right_header()
        self._render_right()

    def _render_batch_side_panel(self, mode: str) -> None:
        active = self._active_fandom()
        evaluated = mode == "evaluated"
        clusters = self._cluster_summaries_for_mode(mode)
        selected_cluster_id = self._selected_cluster_id(mode)
        selected_schema_key = self._selected_schema_key(mode)
        selected_cluster = next((cluster for cluster in clusters if cluster.work_set.id == selected_cluster_id), None)
        if selected_cluster_id and not selected_cluster:
            self._set_schema_selection(mode, "", "", "")
            selected_cluster_id = ""
            selected_schema_key = ""
        selected_slot = None
        if selected_cluster and selected_schema_key:
            selected_slot = next((slot for slot in selected_cluster.slots if slot.schema.schema_key == selected_schema_key), None)
            if not selected_slot:
                self._set_schema_selection(mode, selected_cluster.work_set.id, "", "")
                selected_schema_key = ""

        host = ui.element("div").classes("right-panel-cleanup-host w-full h-full flex-grow")
        host.on("click", lambda _=None, m=mode: self._disarm_cluster_cleanup(m))
        with host:
            with ui.column().classes("right-panel-cleanup-content w-full h-full flex-grow gap-2"):
                with ui.row().classes("w-full gap-1 flex-wrap items-start cluster-pill-row"):
                    if selected_cluster:
                        self._render_cluster_pill(selected_cluster, mode)
                    elif not clusters:
                        ui.label("No evaluated clusters yet." if evaluated else "No named queues yet.").classes("text-xs text-gray-500")
                    else:
                        for cluster in clusters:
                            self._render_cluster_pill(cluster, mode)
                if not selected_cluster:
                    return

                schema_slots = (
                    [selected_slot]
                    if selected_slot and not self._cluster_cleanup_mode(mode)
                    else selected_cluster.slots
                )
                with ui.row().classes("w-full gap-1 flex-wrap items-start schema-slot-row"):
                    for slot in schema_slots:
                        if slot:
                            self._render_schema_slot_pill(slot, mode)
                if selected_slot:
                    self._render_selected_schema_status(selected_slot, mode)

                if not selected_slot or not selected_slot.batch:
                    return

                state = self._cluster_filter_state(mode)
                if evaluated:
                    if selected_slot.completed_count > 0:
                        self._render_evaluated_filter_panel(state, selected_slot.schema.schema_key, self._schema_slot_color(selected_slot, active.color))
                else:
                    self._render_cluster_filter_panel(state, active.color)

    def _render_cluster_pill(self, summary: Any, mode: str) -> None:
        active = self._active_fandom()
        selected_id = self._selected_cluster_id(mode)
        selected = summary.work_set.id == selected_id
        cleanup_selected = (
            self._cluster_cleanup_mode(mode)
            and not self._selected_cluster_id(mode)
            and summary.work_set.id in self._cleanup_selected_clusters(mode)
        )
        meta = self._cluster_meta(summary.work_set)
        color = "#ef4444" if cleanup_selected else self._cluster_color(summary.work_set, active.color)
        selected_class = "cluster-pill-selected" if selected else ""
        pill = ui.element("button").props("type=button").classes(
            f"work-tag-pill browse-tag-pill cluster-pill {selected_class} text-[11px]".strip()
        )
        pill.style(self._filter_pill_style(color, selected or cleanup_selected))
        pill.on(
            "click",
            lambda _=None, cid=summary.work_set.id, m=mode: self._handle_cluster_pill_click(m, cid),
            js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
        )
        pill.on(
            "contextmenu",
            lambda _=None, s=summary, m=mode: self._open_cluster_action_dialog(s, m),
            js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
        )
        with pill:
            ui.label(summary.work_set.name).classes("browse-tag-pill-label")
            tooltip_text = str(meta.get("description") or "Right-click to edit cluster").strip()
            rich_tooltip(tooltip_text, color)

    def _render_schema_slot_pill(self, slot: Any, mode: str) -> None:
        active = self._active_fandom()
        selected = (
            self._selected_cluster_id(mode) == slot.work_set.id
            and self._selected_schema_key(mode) == slot.schema.schema_key
        )
        cleanup_key = f"{slot.work_set.id}|{slot.schema.schema_key}"
        cleanup_selected = (
            self._cluster_cleanup_mode(mode)
            and self._selected_cluster_id(mode) == slot.work_set.id
            and cleanup_key in self._cleanup_selected_schemas(mode)
        )
        color = "#ef4444" if cleanup_selected else self._schema_slot_color(slot, active.color)
        pill = ui.button(slot.schema.name).props("dense rounded no-caps").classes("filter-favorite-pill schema-slot-pill")
        pill_style = self._filter_pill_style(color, selected or cleanup_selected)
        if slot.state == "empty":
            pill_style += " opacity: 0.72;"
        pill.style(pill_style)
        pill.on(
            "click",
            lambda _=None, s=slot, m=mode: self._handle_schema_slot_click(m, s),
            js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
        )
        with pill:
            rich_tooltip(self._schema_slot_tooltip(slot), color)

    def _render_selected_schema_status(self, slot: Any, mode: str) -> None:
        active = self._active_fandom()
        color = self._schema_slot_color(slot, active.color)
        count_text = (
            f"{slot.completed_count}/{slot.total_count} evaluated"
            if mode == "evaluated"
            else f"{slot.active_count} pending | {slot.completed_count} evaluated"
        )
        with ui.element("div").classes("w-full px-1 py-0 cluster-selected-status"):
            with ui.column().classes("w-full gap-0"):
                ui.label(slot.schema.name).classes("text-[11px] font-bold truncate").style(glow_text(color, 2))
                ui.label(count_text).classes("text-[11px] text-gray-500 truncate")

    @staticmethod
    def _cluster_meta(work_set: Any) -> dict[str, Any]:
        raw = work_set.filter_state.get("_cluster_meta") if isinstance(getattr(work_set, "filter_state", None), dict) else {}
        return dict(raw) if isinstance(raw, dict) else {}

    def _cluster_color(self, work_set: Any, fallback: str) -> str:
        color = self._normalize_hex(str(self._cluster_meta(work_set).get("color") or ""))
        return color or fallback

    def _schema_slot_color(self, slot: Any, fallback: str) -> str:
        if getattr(slot, "state", "empty") == "empty" or not getattr(slot, "completed_count", 0) and not getattr(slot, "active_count", 0):
            return "#6b7280"
        return self._schema_color(getattr(slot, "schema", None), fallback)

    def _schema_color(self, schema: Any | None, fallback: str) -> str:
        rules = getattr(schema, "aggregation_rules", {}) if schema else {}
        ui_rules = rules.get("_ui") if isinstance(rules, dict) else {}
        color = self._normalize_hex(str(ui_rules.get("color") or "")) if isinstance(ui_rules, dict) else ""
        return color or fallback

    def _schema_slot_tooltip(self, slot: Any) -> str:
        state = str(getattr(slot, "state", "empty") or "empty")
        if state == "empty":
            return "No completed evaluation for this schema yet."
        return (
            f"{getattr(slot, 'pending_count', 0)} pending | "
            f"{getattr(slot, 'completed_count', 0)} evaluated | "
            f"{getattr(slot, 'failed_count', 0)} failed"
        )

    def _render_cluster_cleanup_toolbar(self, mode: str, color: str) -> None:
        cleanup_mode = self._cluster_cleanup_mode(mode)
        armed = self._cluster_cleanup_armed(mode)
        if cleanup_mode:
            trash_color = "#ef4444" if armed else "#6b7280"
            trash = ui.button(icon="delete").props("round flat dense size=md").classes("top-action-button")
            trash.style(f"color: {trash_color} !important;")
            trash.on(
                "click.stop",
                lambda _=None, m=mode: self._handle_cluster_cleanup_trash(m),
                js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
            )
            with trash:
                rich_tooltip("Confirm cleanup" if armed else "Arm cleanup", "#ef4444")
        clean = ui.button(icon="cleaning_services").props("round flat dense size=md").classes("top-action-button")
        clean_color = normalized_label_color(color) if cleanup_mode else "#6b7280"
        clean.style(f"color: {clean_color} !important;")
        clean.on(
            "click.stop",
            lambda _=None, m=mode: self._toggle_cluster_cleanup_mode(m),
            js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
        )
        with clean:
            rich_tooltip(
                "Exit cleanup mode" if cleanup_mode else f"Cleanup {'evaluated' if mode == 'evaluated' else 'queue'} clusters or schema slots",
                color,
            )

    def _open_cluster_action_dialog(self, summary: Any, mode: str) -> None:
        active = self._active_fandom()
        meta = self._cluster_meta(summary.work_set)
        color = self._cluster_color(summary.work_set, active.color)
        draft = {
            "color": str(meta.get("color") or ""),
            "favorite": bool(meta.get("favorite")),
            "description": str(meta.get("description") or ""),
        }
        dialog = ui.dialog()
        dialog.on("hide", dialog.delete)

        def save(close: bool = True, notify: bool = True) -> None:
            result = self.container.queue_service.update_cluster_metadata(
                summary.work_set.id,
                color=str(draft.get("color") or ""),
                favorite=bool(draft.get("favorite")),
                description=str(draft.get("description") or ""),
            )
            if notify:
                self._notify(result.message, "positive" if result.ok else "negative")
            if result.ok:
                self._invalidate_browse_page_model()
            if close:
                dialog.close()
                self.refresh()

        def requeue(schema_key: str) -> None:
            save(close=False, notify=False)
            result = self.container.queue_service.requeue_work_set_under_schema(summary.work_set.id, schema_key)
            if result.ok and isinstance(result.payload, dict) and result.payload.get("batch"):
                self._set_batch_selection("queue", result.payload["batch"].id)
                self._set_page("Queue")
            self._invalidate_browse_page_model()
            self._notify(result.message, "positive" if result.ok else "negative")
            dialog.close()
            self.refresh()

        with dialog, ui.card().classes("tag-favorite-menu p-2 gap-2 min-w-[260px] max-w-[320px]"):
            with ui.row().classes("w-full items-start gap-2"):
                ui.label(summary.work_set.name).classes("text-sm font-bold flex-grow").style(glow_text(color, 3))
                close = ui.button(icon="close", on_click=dialog.close).props("flat round dense size=sm")
                close.style("color: #94a3b8 !important;")
            ui.color_input("Color", value=draft["color"] or color).bind_value(draft, "color").props("dense dark outlined").classes("w-full")
            ui.switch("Favorite", value=draft["favorite"]).bind_value(draft, "favorite").props("dense color=primary")
            ui.textarea("Description", value=draft["description"]).bind_value(draft, "description").props(
                "dense dark outlined rows=3"
            ).classes("w-full")
            if mode == "evaluated":
                ui.separator().classes("bg-gray-800")
                ui.label("Queue Under Schema").classes("text-xs font-bold uppercase text-gray-500")
                for schema, used in self.container.queue_service.schema_options_for_work_set(summary.work_set.id):
                    button = ui.button(schema.name, icon="lock" if used else "playlist_add").props("dense no-caps").classes("w-full")
                    button.style(
                        f"background-color: {dark_button_color(color) if not used else '#1f2937'} !important; "
                        f"color: {normalized_label_color(color) if not used else '#6b7280'} !important;"
                    )
                    if used:
                        button.props("disable")
                    else:
                        button.on("click.stop", lambda _=None, key=schema.schema_key: requeue(key))
            with ui.row().classes("w-full justify-end gap-2"):
                clear = ui.button(icon="format_color_reset").props("flat round dense")
                clear.style("color: #94a3b8 !important;")
                clear.on("click.stop", lambda _=None: draft.update({"color": ""}))
                with clear:
                    rich_tooltip("Use fandom color", active.color)
                save_btn = ui.button("Save", icon="save", on_click=lambda _=None: save()).props("dense no-caps")
                save_btn.style(f"background-color: {dark_button_color(color)} !important; color: white;")
        dialog.open()

    def _render_cluster_filter_panel(
        self,
        state: dict[str, Any],
        color: str,
        *,
        search_label: str = "Search cluster",
        apply_tooltip: str = "Apply local cluster filters",
    ) -> None:
        with ui.element("div").classes("soft-panel w-full p-3"):
            self._segmented_cluster_pills("", state, "sort_dir", [("desc", "Desc"), ("asc", "Asc")], color)
            with ui.row().classes("w-full items-center gap-1 flex-nowrap"):
                query = ui.input(search_label, value=state["query"]).bind_value(state, "query").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("flex-grow min-w-0")
                query.on("keydown.enter", lambda _=None: self._apply_cluster_filters(state, sort_mode="ao3"))
                apply_btn = ui.button(icon="refresh", on_click=lambda _=None: self._apply_cluster_filters(state, sort_mode="ao3")).props(
                    "round flat dense"
                )
                apply_btn.classes("right-panel-icon-button shrink-0")
                apply_btn.style(f"color: {normalized_label_color(color)} !important;")
                with apply_btn:
                    rich_tooltip(apply_tooltip, color)
            self._render_cluster_sort_pills(state, color)
            with ui.row().classes("w-full gap-1 filter-two-col-row"):
                ui.input("Words from", value=state["words_from"]).bind_value(state, "words_from").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("filter-half-field")
                ui.input("Words to", value=state["words_to"]).bind_value(state, "words_to").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("filter-half-field")

    def _render_evaluated_filter_panel(self, state: dict[str, Any], schema_key: str, color: str) -> None:
        schema = self.container.schema_repo.get(schema_key) or self.container.schema_service.active_schema()
        with ui.element("div").classes("soft-panel w-full p-3"):
            self._segmented_cluster_pills("", state, "score_dir", [("desc", "High"), ("asc", "Low")], color)
            options = {"": "Any score"}
            options.update({dimension.key: dimension.label for dimension in schema.dimensions})
            with ui.row().classes("w-full items-center gap-1 flex-nowrap"):
                ui.select(options, value=state.get("score_key") or "", label="Score").bind_value(state, "score_key").props(
                    "dense dark outlined hide-bottom-space"
                ).classes("flex-grow min-w-0")
                apply_btn = ui.button(icon="refresh", on_click=lambda _=None: self._apply_cluster_filters(state, sort_mode="score")).props(
                    "round flat dense"
                )
                apply_btn.classes("right-panel-icon-button shrink-0")
                apply_btn.style(f"color: {normalized_label_color(color)} !important;")
                with apply_btn:
                    rich_tooltip("Apply evaluated score filters", color)
            with ui.row().classes("w-full gap-1 filter-two-col-row"):
                ui.input("Min", value=state["score_min"]).bind_value(state, "score_min").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("filter-half-field")
                ui.input("Max", value=state["score_max"]).bind_value(state, "score_max").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("filter-half-field")

        expanded = bool(self.container.preferences_service.get(f"evaluated_ao3_filter_open:{self._active_fandom().fandom_key}", False))
        expansion = ui.expansion("AO3 Metadata Filters", icon="tune", value=expanded).classes("w-full filter-expansion soft-panel")
        expansion.on(
            "update:model-value",
            lambda event: self._set_evaluated_metadata_open(self._event_bool(event)),
        )
        expansion.style(f"--filter-group-color: {color};")
        if expanded:
            with expansion:
                self._render_cluster_filter_panel(state, color)

    def _render_cluster_sort_pills(self, state: dict[str, Any], color: str) -> None:
        with ui.row().classes("w-full gap-1 flex-wrap filter-sort-row mt-2"):
            for value, label in AO3_METADATA_SORT_PILLS:
                selected = str(state.get("sort_column") or "") == value
                pill = ui.button(label, on_click=lambda _=None, v=value: self._set_cluster_sort(state, v)).props("dense rounded")
                pill.style(self._filter_pill_style(color, selected))

    def _segmented_cluster_pills(self, label: str, state: dict[str, Any], key: str, options: list[tuple[str, str]], color: str) -> None:
        with ui.row().classes("w-full gap-1 flex-wrap items-center filter-segmented-row cluster-filter-segmented-row"):
            if label:
                ui.label(label).classes("text-xs text-gray-500 w-full")
            for value, text in options:
                selected = str(state.get(key) or "") == value
                pill = ui.button(text, on_click=lambda _=None, k=key, v=value: self._set_cluster_scalar(state, k, v)).props("dense rounded")
                pill.style(self._filter_pill_style(color, selected))

    def _render_browse_lookup_panel(self) -> None:
        state = self._browse_filter_state()
        metadata = self.filter_metadata or self.container.preferences_service.get("last_filter_metadata", None)
        active = self._active_fandom()
        with ui.element("div").classes("soft-panel w-full p-2"):
            with ui.element("div").classes("right-panel-search w-full"):
                with ui.element("div").classes("right-panel-control-row right-panel-three-icon-grid"):
                    search = ui.input("Search within results", value=state["query"]).bind_value(state, "query").props(
                        "outlined dense dark clearable hide-bottom-space"
                    ).classes("right-panel-main-field min-w-0")
                    search.on("keydown.enter", lambda: self._start_apply_fandom_filters(state))
                    refresh = ui.button(icon="refresh", on_click=lambda: self._start_apply_fandom_filters(state)).props("round flat dense")
                    refresh.classes("right-panel-icon-button")
                    refresh.style(f"color: {normalized_label_color(active.color)} !important;")
                    with refresh:
                        rich_tooltip("Apply search and filters", active.color)
                    save_defaults = ui.button(icon="save").props("round flat dense")
                    save_defaults.classes("right-panel-icon-button")
                    save_defaults.style(f"color: {normalized_label_color(active.color)} !important;")
                    save_defaults.on("click.stop", lambda _=None: self._save_current_filter_defaults(state))
                    with save_defaults:
                        rich_tooltip("Save current filters as this fandom's defaults", active.color)
                    open_btn = ui.button(icon="open_in_new", on_click=lambda: self._open_ao3_account_session(state)).props("round flat dense")
                    open_btn.classes("right-panel-icon-button")
                    open_btn.style(f"color: {normalized_label_color(active.color)} !important;")
                    with open_btn:
                        rich_tooltip("Open current AO3 page in your browser", active.color)
            self._render_sort_pills(metadata, state, active.color)
            with ui.row().classes("w-full gap-1 items-center filter-page-row"):
                prev_btn = ui.button(icon="chevron_left", on_click=lambda: self._turn_page(state, -1)).props("round flat dense")
                prev_btn.style(f"color: {normalized_label_color(active.color)} !important;")
                next_btn = ui.button(icon="chevron_right", on_click=lambda: self._turn_page(state, 1)).props("round flat dense")
                next_btn.style(f"color: {normalized_label_color(active.color)} !important;")
                page = ui.input("Page", value=str(state["page"])).bind_value(state, "page").props(
                    "outlined dense dark hide-bottom-space"
                ).classes("filter-page-input")
                page.on("keydown.enter", lambda: self._start_apply_fandom_filters(state))
                with page.add_slot("append"):
                    with ui.column().classes("filter-page-spinner gap-0"):
                        up = ui.button(icon="keyboard_arrow_up").props("flat dense round")
                        up.on("click.stop", lambda _=None, p=page: self._nudge_page_input(state, p, 1))
                        self._attach_page_spin_repeat(up)
                        down = ui.button(icon="keyboard_arrow_down").props("flat dense round")
                        down.on("click.stop", lambda _=None, p=page: self._nudge_page_input(state, p, -1))
                        self._attach_page_spin_repeat(down)
                self._render_browse_sort_direction_pills(state, active.color)
            self._render_favorite_filter_pills(metadata, state)
            self._render_filter_groups(metadata, state, "include")
            self._render_filter_groups(metadata, state, "exclude")
            self._render_more_filter_options(metadata, state, active.color)

    def _browse_filter_state(self) -> dict[str, Any]:
        active = self.container.fandom_service.ensure_default()
        stored = self.container.preferences_service.get("browse_filter_state", {})
        state: dict[str, Any] = default_fandom_filter(active.tag)
        state.update(active.default_filter or {})
        if isinstance(stored, dict):
            state.update(stored)
        state["fandom"] = self.container.browse_service.resolve_fandom(str(state.get("fandom") or active.tag)) or active.tag
        state["sort_column"] = normalize_ao3_sort_column(state.get("sort_column"))
        state["sort_direction"] = "asc" if str(state.get("sort_direction")) == "asc" else "desc"
        if not isinstance(state.get("selected"), dict):
            state["selected"] = {}
        if not isinstance(state.get("favorite_options"), list):
            state["favorite_options"] = []
        for legacy in state.get("favorite_groups", []) if isinstance(state.get("favorite_groups"), list) else []:
            if legacy and legacy not in state["favorite_options"]:
                state["favorite_options"].append(f"group:{legacy}")
        for key in ["words_from", "words_to"]:
            if state.get(key) is None:
                state[key] = ""
        return state

    def _active_fandom(self) -> FandomProfile:
        return self.container.fandom_service.ensure_default()

    def _persist_browse_state(self, state: dict[str, Any]) -> None:
        state["fandom"] = self.container.browse_service.resolve_fandom(str(state.get("fandom") or "")) or DEFAULT_FANDOM
        state["sort_column"] = normalize_ao3_sort_column(state.get("sort_column"))
        state["sort_direction"] = "asc" if str(state.get("sort_direction")) == "asc" else "desc"
        try:
            state["page"] = max(1, int(float(state.get("page") or 1)))
        except (TypeError, ValueError):
            state["page"] = 1
        for key in ["words_from", "words_to"]:
            state[key] = normalize_word_count_filter(state.get(key))
        for key in ["date_from", "date_to"]:
            state[key] = normalize_ao3_date_filter(state.get(key))
        active = self.container.fandom_service.active_profile()
        if not active or active.tag != state["fandom"]:
            existing = self.container.fandom_repo.get_by_tag(state["fandom"])
            if existing:
                self.container.fandom_service.select(existing.fandom_key)
            else:
                profile = FandomProfile(
                    fandom_key=fandom_key(state["fandom"]),
                    tag=state["fandom"],
                    display_name=short_fandom_name(state["fandom"]),
                    color="#58a6ff",
                    default_filter=default_fandom_filter(state["fandom"]),
                )
                self.container.fandom_service.save_profile(profile)
                self.container.fandom_service.select(profile.fandom_key)
        self.container.preferences_service.set("browse_filter_state", state)
        self.container.preferences_service.set("last_context_type", "fandom")
        self.container.preferences_service.set("last_context_key", state["fandom"])
        self._invalidate_browse_page_model()

    def _cluster_filter_state(self, mode: str) -> dict[str, Any]:
        active_key = self._active_fandom().fandom_key
        key = f"{mode}_cluster_filter_state:{active_key}"
        stored = self.container.preferences_service.get(key, {})
        state = {
            "query": "",
            "sort_column": "revised_at",
            "sort_dir": "desc",
            "words_from": "",
            "words_to": "",
            "score_key": "",
            "score_min": "",
            "score_max": "",
            "score_dir": "desc",
            "sort_mode": "",
        }
        stored_has_sort_mode = isinstance(stored, dict) and "sort_mode" in stored
        if isinstance(stored, dict):
            state.update(stored)
        state["sort_column"] = normalize_ao3_sort_column(state.get("sort_column"))
        state["sort_dir"] = "asc" if str(state.get("sort_dir")) == "asc" else "desc"
        state["score_dir"] = "asc" if str(state.get("score_dir")) == "asc" else "desc"
        state["sort_mode"] = str(state.get("sort_mode") or "").strip()
        if state["sort_mode"] not in {"ao3", "score"}:
            state["sort_mode"] = "score" if mode == "evaluated" and str(state.get("score_key") or "") and not stored_has_sort_mode else "ao3"
        for key_name in ["query", "words_from", "words_to", "score_key", "score_min", "score_max"]:
            state[key_name] = str(state.get(key_name) or "")
        return state

    def _persist_cluster_filter_state(self, mode: str, state: dict[str, Any]) -> None:
        active_key = self._active_fandom().fandom_key
        key = f"{mode}_cluster_filter_state:{active_key}"
        state["sort_column"] = normalize_ao3_sort_column(state.get("sort_column"))
        state["sort_mode"] = str(state.get("sort_mode") or "ao3") if mode == "evaluated" else "ao3"
        if state["sort_mode"] not in {"ao3", "score"}:
            state["sort_mode"] = "ao3"
        state["words_from"] = normalize_word_count_filter(state.get("words_from"))
        state["words_to"] = normalize_word_count_filter(state.get("words_to"))
        self.container.preferences_service.set(key, dict(state))

    def _apply_cluster_filters(self, state: dict[str, Any], sort_mode: str | None = None) -> None:
        mode = "evaluated" if self.page == "Evaluated" else "works" if self.page == "Works" else "queue"
        if sort_mode:
            state["sort_mode"] = sort_mode
        self._persist_cluster_filter_state(mode, state)
        self._render_center()
        self._render_right()

    def _set_cluster_sort(self, state: dict[str, Any], value: str) -> None:
        state["sort_column"] = normalize_ao3_sort_column(value)
        self._apply_cluster_filters(state, sort_mode="ao3")

    def _set_cluster_scalar(self, state: dict[str, Any], key: str, value: str) -> None:
        state[key] = value
        sort_mode = "score" if key == "score_dir" else "ao3" if key == "sort_dir" else None
        self._apply_cluster_filters(state, sort_mode=sort_mode)

    def _set_evaluated_metadata_open(self, value: bool) -> None:
        self.container.preferences_service.set(f"evaluated_ao3_filter_open:{self._active_fandom().fandom_key}", bool(value))
        if self.page == "Evaluated":
            self._render_right()

    def _set_works_metadata_open(self, value: bool) -> None:
        self.container.preferences_service.set(f"works_ao3_filter_open:{self._active_fandom().fandom_key}", bool(value))
        if self.page == "Works":
            self._render_right()

    def _cluster_cleanup_mode(self, mode: str) -> bool:
        return self.evaluated_cleanup_mode if mode == "evaluated" else self.queue_cleanup_mode

    def _cluster_cleanup_armed(self, mode: str) -> bool:
        return self.evaluated_cleanup_armed if mode == "evaluated" else self.queue_delete_armed

    def _set_cluster_cleanup_armed(self, mode: str, value: bool) -> None:
        if mode == "evaluated":
            self.evaluated_cleanup_armed = value
        else:
            self.queue_delete_armed = value

    def _cleanup_selected_clusters(self, mode: str) -> set[str]:
        return self.evaluated_cleanup_selected_clusters if mode == "evaluated" else self.queue_cleanup_selected_clusters

    def _cleanup_selected_schemas(self, mode: str) -> set[str]:
        return self.evaluated_cleanup_selected_schemas if mode == "evaluated" else self.queue_cleanup_selected_schemas

    def _clear_cluster_cleanup_selection(self, mode: str) -> None:
        self._cleanup_selected_clusters(mode).clear()
        self._cleanup_selected_schemas(mode).clear()

    def _set_schema_selection(self, mode: str, work_set_id: str, schema_key: str, batch_id: str = "") -> None:
        if mode == "evaluated":
            self.selected_evaluated_cluster_id = work_set_id
            self.selected_evaluated_schema_key = schema_key
            self.selected_evaluated_batch_id = batch_id
            self.evaluated_cleanup_armed = False
            self.container.preferences_service.set("selected_evaluated_cluster_id", work_set_id)
            self.container.preferences_service.set("selected_evaluated_schema_key", schema_key)
            self.container.preferences_service.set("selected_evaluated_batch_id", batch_id)
        else:
            self.selected_queue_cluster_id = work_set_id
            self.selected_queue_schema_key = schema_key
            self.selected_queue_batch_id = batch_id
            self.queue_delete_armed = False
            self.container.preferences_service.set("selected_queue_cluster_id", work_set_id)
            self.container.preferences_service.set("selected_queue_schema_key", schema_key)
            self.container.preferences_service.set("selected_queue_batch_id", batch_id)

    def _set_batch_selection(self, mode: str, batch_id: str) -> None:
        if not batch_id:
            self._set_schema_selection(mode, "", "", "")
            return
        summary = self.container.queue_service.summary_for_batch(batch_id)
        if summary:
            self._set_schema_selection(mode, summary.work_set.id, summary.batch.schema_key, summary.batch.id)
            return
        if mode == "evaluated":
            self.selected_evaluated_batch_id = batch_id
            self.container.preferences_service.set("selected_evaluated_batch_id", batch_id)
        else:
            self.selected_queue_batch_id = batch_id
            self.container.preferences_service.set("selected_queue_batch_id", batch_id)

    def _toggle_batch_selection(self, mode: str, batch_id: str) -> None:
        current = self.selected_evaluated_batch_id if mode == "evaluated" else self.selected_queue_batch_id
        self._set_batch_selection(mode, "" if current == batch_id else batch_id)
        self._render_center()
        self._render_right()

    def _handle_cluster_pill_click(self, mode: str, work_set_id: str) -> None:
        if self._cluster_cleanup_mode(mode) and not self._selected_cluster_id(mode):
            self._set_cluster_cleanup_armed(mode, False)
            selected_clusters = self._cleanup_selected_clusters(mode)
            if work_set_id in selected_clusters:
                selected_clusters.remove(work_set_id)
            else:
                selected_clusters.add(work_set_id)
            self._render_right_header()
            self._render_right()
            return
        current = self._selected_cluster_id(mode)
        if current == work_set_id:
            self._set_schema_selection(mode, "", "", "")
        else:
            self._set_schema_selection(mode, work_set_id, "", "")
        self._render_center()
        self._render_right()
        self._render_top()
        self._render_right_header()

    def _handle_schema_slot_click(self, mode: str, slot: Any) -> None:
        if self._cluster_cleanup_mode(mode) and self._selected_cluster_id(mode) == slot.work_set.id:
            self._set_cluster_cleanup_armed(mode, False)
            key = f"{slot.work_set.id}|{slot.schema.schema_key}"
            selected_schemas = self._cleanup_selected_schemas(mode)
            if key in selected_schemas:
                selected_schemas.remove(key)
            else:
                selected_schemas.add(key)
            self._render_right_header()
            self._render_right()
            return
        current_cluster = self._selected_cluster_id(mode)
        current_schema = self._selected_schema_key(mode)
        if current_cluster == slot.work_set.id and current_schema == slot.schema.schema_key:
            self._set_schema_selection(mode, slot.work_set.id, "", "")
        else:
            self._set_schema_selection(mode, slot.work_set.id, slot.schema.schema_key, slot.batch_id)
        self._render_center()
        self._render_right()
        self._render_top()
        self._render_right_header()

    def _requeue_work_set_under_schema(self, work_set_id: str, schema_key: str) -> None:
        result = self.container.queue_service.requeue_work_set_under_schema(work_set_id, schema_key)
        if result.ok and isinstance(result.payload, dict) and result.payload.get("batch"):
            self._set_batch_selection("queue", result.payload["batch"].id)
            self._set_page("Queue")
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _toggle_cluster_cleanup_mode(self, mode: str) -> None:
        if mode == "evaluated":
            self.evaluated_cleanup_mode = not self.evaluated_cleanup_mode
            self.evaluated_cleanup_armed = False
        else:
            self.queue_cleanup_mode = not self.queue_cleanup_mode
            self.queue_delete_armed = False
        self._clear_cluster_cleanup_selection(mode)
        self._render_right_header()
        self._render_right()

    def _disarm_cluster_cleanup(self, mode: str) -> None:
        if not self._cluster_cleanup_armed(mode):
            return
        self._set_cluster_cleanup_armed(mode, False)
        self._render_right_header()
        self._render_right()

    def _handle_cluster_cleanup_trash(self, mode: str) -> None:
        if not self._cluster_cleanup_mode(mode):
            return
        if self._selected_cluster_id(mode):
            selected = list(self._cleanup_selected_schemas(mode))
            if not selected:
                self._notify("Select schema pills to clean.", "warning")
                return
        else:
            selected = list(self._cleanup_selected_clusters(mode))
            if not selected:
                self._notify(f"Select {'evaluated' if mode == 'evaluated' else 'queue'} clusters to clean.", "warning")
                return
        if not self._cluster_cleanup_armed(mode):
            self._set_cluster_cleanup_armed(mode, True)
            self._render_right_header()
            self._render_right()
            return
        if self._selected_cluster_id(mode):
            messages: list[str] = []
            for key in selected:
                work_set_id, schema_key = key.split("|", 1)
                result = (
                    self.container.queue_service.clean_evaluated_schema_slot(work_set_id, schema_key)
                    if mode == "evaluated"
                    else self.container.queue_service.clean_queue_schema_slot(work_set_id, schema_key)
                )
                messages.append(result.message)
            current_key = f"{self._selected_cluster_id(mode)}|{self._selected_schema_key(mode)}"
            if current_key in selected:
                self._set_schema_selection(mode, self._selected_cluster_id(mode), self._selected_schema_key(mode), "")
            self._notify(messages[-1] if messages else "Schema cleanup complete.", "positive")
        else:
            result = (
                self.container.queue_service.clean_evaluated_clusters(selected)
                if mode == "evaluated"
                else self.container.queue_service.clean_queue_clusters(selected)
            )
            self._notify(result.message, "positive" if result.ok else "negative")
            if self._selected_cluster_id(mode) in selected:
                self._set_schema_selection(mode, "", "", "")
        if mode == "evaluated":
            self.evaluated_cleanup_mode = False
            self.evaluated_cleanup_armed = False
        else:
            self.queue_cleanup_mode = False
            self.queue_delete_armed = False
        self._clear_cluster_cleanup_selection(mode)
        self._invalidate_browse_page_model()
        self.refresh()

    def _evaluated_slot_queue_available(self) -> bool:
        if self.page != "Evaluated":
            return False
        slot = self._selected_schema_slot("evaluated")
        if not slot:
            return False
        return slot.state != "complete"

    def _queue_selected_evaluated_schema_slot(self, *, start: bool = False) -> None:
        slot = self._selected_schema_slot("evaluated")
        if not slot:
            self._notify("Select a schema slot first.", "warning")
            return
        result = self.container.queue_service.create_queue_for_schema_slot(slot.work_set.id, slot.schema.schema_key)
        if result.ok and isinstance(result.payload, dict) and result.payload.get("batch"):
            self._invalidate_browse_page_model()
            self._set_batch_selection("queue", result.payload["batch"].id)
            self._set_page("Queue")
            self._notify(result.message, "positive")
            if start:
                self._start_queue_evaluation_run()
            return
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _show_queue_eval_config_dialog(self, *, start_after_save: bool = False) -> None:
        active = self._active_fandom()
        accent = active.color
        r, g, b = rgb_from_hex(accent)
        config = self.container.queue_runner_service.config()
        draft = asdict(config)
        dialog_style = (
            wash_background(accent, 0.14)
            + f"width: 560px; max-width: 94vw; height: 85vh; max-height: calc(100vh - 24px); border: 1px solid rgba({r},{g},{b},0.24);"
        )
        with self.root:
            dialog = ui.dialog()
            dialog.on("hide", dialog.delete)

        def save() -> None:
            result = self.container.queue_runner_service.save_config(draft)
            self._notify(result.message, "positive" if result.ok else "negative")
            if result.ok:
                dialog.close()
                if start_after_save:
                    self._start_queue_evaluation_run()

        with dialog, ui.card().classes("flex flex-col p-0 gap-0 overflow-hidden").style(dialog_style):
            with ui.row().classes("w-full items-center justify-between p-4 border-b border-gray-700"):
                with ui.row().classes("items-center gap-2 min-w-0"):
                    ui.icon("psychology", size="22px").style(f"color: {normalized_label_color(accent)};")
                    ui.label("Queue Evaluation").classes("text-lg font-bold text-gray-300").style(glow_text(accent, 5))
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=white")
            with ui.scroll_area().classes("w-full flex-grow min-h-0"):
                with ui.column().classes("w-full gap-3 p-4"):
                    with ui.element("div").classes("soft-panel w-full p-3"):
                        ui.label("Prompt Contents").classes("text-lg font-bold").style(glow_text(accent, 3))
                        ui.switch("Include work metadata", value=draft["include_metadata"]).bind_value(
                            draft,
                            "include_metadata",
                        ).props("dense color=primary")
                        ui.switch("Include tags", value=draft["include_tags"]).bind_value(draft, "include_tags").props(
                            "dense color=primary"
                        )
                    with ui.element("div").classes("soft-panel w-full p-3"):
                        ui.label("Story Sample").classes("text-lg font-bold").style(glow_text(accent, 3))
                        with ui.row().classes("w-full gap-2"):
                            ui.number("Start chapter", value=draft["start_chapter"], min=1, step=1).bind_value(
                                draft,
                                "start_chapter",
                            ).props("outlined dense dark").classes("w-40")
                            ui.number("Chapter window", value=draft["chapter_window"], min=1, step=1).bind_value(
                                draft,
                                "chapter_window",
                            ).props("outlined dense dark").classes("w-40")
                        with ui.row().classes("w-full gap-2"):
                            ui.number("Target words", value=draft["target_words"], min=250, step=250).bind_value(
                                draft,
                                "target_words",
                            ).props("outlined dense dark").classes("w-40")
                            ui.number("Max words", value=draft["max_words"], min=250, step=250).bind_value(
                                draft,
                                "max_words",
                            ).props("outlined dense dark").classes("w-40")
                        ui.switch("Skip empty chapters forward", value=draft["skip_empty_chapters"]).bind_value(
                            draft,
                            "skip_empty_chapters",
                        ).props("dense color=primary")
            with ui.row().classes("w-full items-center justify-between p-3 border-t border-gray-700 shrink-0").style(
                "background: rgba(13, 17, 23, 0.78);"
            ):
                ui.label("Changes are local until saved.").classes("text-xs italic text-gray-500")
                label = "Save and Start" if start_after_save else "Save"
                ui.button(label, icon="play_arrow" if start_after_save else "save", on_click=save).style(
                    f"background-color: {dark_button_color(accent)} !important; color: white;"
                )
        dialog.open()

    def _filter_cluster_works(self, works: list[Work], model: WorkListRenderModel, mode: str) -> list[Work]:
        state = self._cluster_filter_state(mode)
        query = str(state.get("query") or "").strip().casefold()
        words_from = self._safe_int(normalize_word_count_filter(state.get("words_from")))
        words_to = self._safe_int(normalize_word_count_filter(state.get("words_to")))
        score_key = str(state.get("score_key") or "")
        score_min = self._safe_float(state.get("score_min"))
        score_max = self._safe_float(state.get("score_max"))

        def matches(work: Work) -> bool:
            tags = model.tags_by_work.get(work.work_id, [])
            if query:
                haystack = " ".join(
                    [
                        work.title or "",
                        work.author_name or "",
                        work.summary_text or "",
                        " ".join(tag.tag_text for tag in tags),
                    ]
                ).casefold()
                if query not in haystack:
                    return False
            if words_from is not None and (work.words or 0) < words_from:
                return False
            if words_to is not None and (work.words or 0) > words_to:
                return False
            if mode == "evaluated" and score_key:
                evaluation = model.latest_evaluations.get(work.work_id)
                raw_score = evaluation.scores.get(score_key) if evaluation else None
                try:
                    score = float(raw_score)
                except (TypeError, ValueError):
                    return False
                if score_min is not None and score < score_min:
                    return False
                if score_max is not None and score > score_max:
                    return False
            return True

        filtered = [work for work in works if matches(work)]
        sort_column = normalize_ao3_sort_column(state.get("sort_column"))
        sort_mode = str(state.get("sort_mode") or "ao3")
        reverse = str(state.get("sort_dir") or "desc") != "asc"
        if mode == "evaluated" and score_key and sort_mode == "score":
            reverse = str(state.get("score_dir") or "desc") != "asc"

            def score_key_fn(work: Work) -> tuple[float, str]:
                evaluation = model.latest_evaluations.get(work.work_id)
                try:
                    score = float(evaluation.scores.get(score_key) if evaluation else -1)
                except (TypeError, ValueError):
                    score = -1
                return (score, (work.title or "").casefold())

            return sorted(filtered, key=score_key_fn, reverse=reverse)

        return sorted(filtered, key=lambda work: self._work_sort_value(work, sort_column), reverse=reverse)

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            text = str(value or "").replace(",", "").strip()
            return int(text) if text else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            text = str(value or "").strip()
            return float(text) if text else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _work_sort_value(work: Work, sort_column: str) -> Any:
        if sort_column == "title_to_sort_on":
            return (work.title or "").casefold()
        if sort_column == "authors_to_sort_on":
            return (work.author_name or "").casefold()
        if sort_column == "created_at":
            return AO3StudioShell._work_sort_date(work.published_at or work.last_scraped_at)
        if sort_column == "hits":
            return work.hits or 0
        if sort_column == "kudos_count":
            return work.kudos or 0
        if sort_column == "bookmarks_count":
            return work.bookmarks or 0
        if sort_column == "comments_count":
            return work.comments or 0
        if sort_column == "word_count":
            return work.words or 0
        return AO3StudioShell._work_sort_date(work.last_ao3_updated_at or work.published_at or work.last_scraped_at)

    @staticmethod
    def _work_sort_date(value: str | None) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        cleaned = re.sub(r"\s+", " ", raw.replace(",", " ").strip())
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d %Y",
            "%B %d %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
        return cleaned

    def _store_filter_metadata(self, metadata: Any) -> None:
        if not metadata:
            return
        payload = asdict(metadata) if not isinstance(metadata, dict) else metadata
        self.filter_metadata = payload
        self.container.preferences_service.set("last_filter_metadata", payload)

    def _metadata_options(self, metadata: Any, key: str) -> list[dict[str, Any]]:
        if not metadata:
            return []
        options = metadata.get(key, []) if isinstance(metadata, dict) else getattr(metadata, key, [])
        return [asdict(option) if not isinstance(option, dict) else option for option in options]

    def _metadata_groups(self, metadata: Any, mode: str) -> list[dict[str, Any]]:
        if not metadata:
            return []
        groups = metadata.get("groups", []) if isinstance(metadata, dict) else getattr(metadata, "groups", [])
        rows = [asdict(group) if not isinstance(group, dict) else group for group in groups]
        hidden_keys = {"language", "languages"}
        return [
            group
            for group in rows
            if group.get("mode") == mode
            and str(group.get("key") or group.get("label") or "").strip().casefold() not in hidden_keys
        ]

    def _render_sort_pills(self, metadata: Any, state: dict[str, Any], color: str) -> None:
        current = normalize_ao3_sort_column(state.get("sort_column"))
        state["sort_column"] = current
        with ui.row().classes("w-full gap-1 flex-wrap filter-sort-row mt-2"):
            for value, label in AO3_METADATA_SORT_PILLS:
                selected = value == current
                pill = ui.button(label, on_click=lambda _=None, v=value: self._set_sort_column(state, v)).props("dense rounded")
                pill.style(self._filter_pill_style(color, selected))

    def _set_sort_column(self, state: dict[str, Any], value: str) -> None:
        state["sort_column"] = normalize_ao3_sort_column(value)
        self._persist_browse_state(state)
        self.refresh()

    def _render_browse_sort_direction_pills(self, state: dict[str, Any], color: str) -> None:
        with ui.row().classes("gap-1 flex-nowrap items-center filter-page-direction-row"):
            for value, label in [("desc", "Desc"), ("asc", "Asc")]:
                selected = str(state.get("sort_direction") or "desc") == value
                pill = ui.button(label, on_click=lambda _=None, v=value: self._set_browse_sort_direction(state, v)).props("dense rounded")
                pill.style(self._filter_pill_style(color, selected))

    def _set_browse_sort_direction(self, state: dict[str, Any], value: str) -> None:
        state["sort_direction"] = "asc" if value == "asc" else "desc"
        self._persist_browse_state(state)
        self.refresh()

    def _render_more_filter_options(self, metadata: Any, state: dict[str, Any], color: str) -> None:
        key = "more"
        expanded = self._filter_expanded(key, False)
        expansion = ui.expansion("More Options", icon="tune", value=expanded).classes("w-full filter-expansion")
        expansion.on(
            "update:model-value",
            lambda event, k=key: self._set_filter_expanded(k, self._event_bool(event), rerender_right=True),
        )
        expansion.style(f"--filter-group-color: {color};")
        if not expanded:
            return
        with expansion:
            self._render_other_tag_input("Other tags to include", state, "other_tag_names", color)
            self._render_other_tag_input("Other tags to exclude", state, "excluded_tag_names", TAG_TYPE_COLORS[TagType.WARNING])
            with ui.row().classes("w-full gap-1 filter-two-col-row"):
                ui.input("Words from", value=state["words_from"] or "").bind_value(state, "words_from").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("filter-half-field")
                ui.input("Words to", value=state["words_to"] or "").bind_value(state, "words_to").props(
                    "outlined dense dark clearable hide-bottom-space"
                ).classes("filter-half-field")
            with ui.row().classes("w-full gap-1 filter-two-col-row"):
                self._render_date_filter_input("Date from", state, "date_from", color)
                self._render_date_filter_input("Date to", state, "date_to", color)
            self._segmented_pills("Crossovers", state, "crossover", [("", "Any"), ("F", "No Xovers"), ("T", "Only Xovers")], color)
            self._segmented_pills("Completion", state, "complete", [("", "Any"), ("T", "Complete"), ("F", "Incomplete")], color)
            with ui.row().classes("w-full gap-1 flex-wrap filter-language-row"):
                ui.label("Language").classes("text-xs text-gray-500 w-full")
                for value, label in AO3_LANGUAGE_FILTERS:
                    selected = value == str(state.get("language_id") or "")
                    pill = ui.button(label, on_click=lambda _=None, v=value: self._set_filter_scalar(state, "language_id", v)).props(
                        "dense rounded"
                    )
                    pill.style(self._filter_pill_style(color, selected))

    @staticmethod
    def _comma_values(value: Any) -> list[str]:
        return [part.strip() for part in str(value or "").split(",") if part.strip()]

    @staticmethod
    def _set_comma_values(state: dict[str, Any], key: str, values: list[str]) -> None:
        state[key] = ", ".join(dict.fromkeys([value.strip() for value in values if value.strip()]))

    def _render_other_tag_input(self, label: str, state: dict[str, Any], key: str, color: str) -> None:
        active = self._active_fandom()
        values = self._comma_values(state.get(key))
        query_state = {"query": ""}
        autocomplete = self._tag_autocomplete(active.fandom_key)
        suggestion_ref: dict[str, Any] = {}

        def render_suggestions() -> None:
            row = suggestion_ref.get("row")
            if row is None:
                return
            row.clear()
            query = str(query_state.get("query") or "").strip()
            if len(query) < 2:
                return
            selected_values = {value.casefold() for value in self._comma_values(state.get(key))}
            suggestions = [
                item
                for item in self.container.fandom_service.tag_suggestions(active.fandom_key, query, 10)
                if item.tag_text and item.tag_text.casefold() not in selected_values
            ]
            with row:
                for item in suggestions[:8]:
                    tag_type = self._tag_type_from_catalog_category(item.category)
                    pill_color = TAG_TYPE_COLORS.get(tag_type, color)
                    r, g, b = rgb_from_hex(pill_color)
                    suggestion = ui.button(item.tag_text).props("flat dense rounded no-caps")
                    suggestion.classes("filter-suggestion-pill")
                    suggestion.style(
                        f"background: rgba({r},{g},{b},0.12) !important; "
                        f"border: 1px solid rgba({r},{g},{b},0.34); "
                        f"color: {normalized_label_color(pill_color)} !important;"
                    )
                    suggestion.on("click.stop", lambda _=None, text=item.tag_text: self._add_other_tag(state, key, text))

        def update_query(event: Any) -> None:
            query_state["query"] = str(event.value or "")
            render_suggestions()

        with ui.column().classes("w-full gap-0 filter-tag-input"):
            with ui.element("div").classes("filter-tag-box w-full").style(f"--filter-group-color: {color};"):
                with ui.row().classes("w-full items-center gap-1 flex-wrap"):
                    ui.label(label).classes("filter-tag-box-label")
                    ui.space()
                    if autocomplete:
                        ui.label(f"{len(autocomplete):,} catalog tags").classes("filter-tag-catalog-count")
                for value in values:
                    tag_type = self._tag_type_for_text(active.fandom_key, value)
                    favorite_lookup = self._favorite_tag_map(active.fandom_key)
                    tag_color_lookup = self._tag_color_map(active.fandom_key)
                    favorite_color = favorite_lookup.get((tag_type, value))
                    override_color = tag_color_lookup.get((tag_type, value))
                    pill_color = override_color or favorite_color or TAG_TYPE_COLORS.get(tag_type, color)
                    r, g, b = rgb_from_hex(pill_color)
                    with ui.element("div").classes("filter-selected-tag-chip").style(
                        f"background: rgba({r},{g},{b},{0.22 if favorite_color else 0.12}); "
                        f"border-color: rgba({r},{g},{b},{0.72 if favorite_color else 0.34}); "
                        f"color: {normalized_label_color(pill_color)};"
                    ):
                        star = ui.button(icon="star" if favorite_color else "star_border").props("flat dense round size=xs")
                        star.classes("filter-chip-star")
                        star.style(f"color: {'#facc15' if favorite_color else normalized_label_color(pill_color)} !important;")
                        star.on(
                            "click.stop",
                            lambda _=None, text=value: self._toggle_filter_tag_favorite(active, text),
                        )
                        ui.label(self._short_tag_label(value)).classes("filter-selected-tag-label")
                        close = ui.button(icon="close").props("flat dense round size=xs")
                        close.classes("filter-chip-close")
                        close.style(f"color: {normalized_label_color(pill_color)} !important;")
                        close.on("click.stop", lambda _=None, v=value: self._remove_other_tag(state, key, v))
                with ui.row().classes("w-full gap-1 items-center"):
                    tag_input = ui.input(
                        placeholder="Type to search fandom tags...",
                        value=query_state["query"],
                        autocomplete=[],
                        on_change=update_query,
                    ).props("borderless dense dark hide-bottom-space input-debounce=0").classes("filter-tag-entry")
                    tag_input.on("keydown.enter", lambda _=None: self._add_other_tag(state, key, str(query_state.get("query") or "")))
                    add = ui.button(icon="add").props("round flat dense")
                    add.style(f"color: {normalized_label_color(color)} !important;")
                    add.on("click.stop", lambda _=None: self._add_other_tag(state, key, str(query_state.get("query") or "")))
                suggestions_row = ui.row().classes("w-full gap-1 flex-wrap filter-suggestion-row")
                suggestion_ref["row"] = suggestions_row

    def _add_other_tag(self, state: dict[str, Any], key: str, value: str) -> None:
        clean = value.strip()
        if not clean:
            return
        values = self._comma_values(state.get(key))
        if clean not in values:
            values.append(clean)
        self._set_comma_values(state, key, values)
        self._persist_browse_state(state)
        self.refresh()

    def _remove_other_tag(self, state: dict[str, Any], key: str, value: str) -> None:
        self._set_comma_values(state, key, [item for item in self._comma_values(state.get(key)) if item != value])
        self._persist_browse_state(state)
        self.refresh()

    def _toggle_filter_tag_favorite(self, active: FandomProfile, tag_text: str) -> None:
        tag_type = self._tag_type_for_text(active.fandom_key, tag_text)
        favorite_lookup = self._favorite_tag_map(active.fandom_key)
        if (tag_type, tag_text) in favorite_lookup:
            result = self.container.work_library_service.unfavorite_tag(active.fandom_key, tag_type, tag_text)
        else:
            color = self._tag_color_map(active.fandom_key).get((tag_type, tag_text), TAG_TYPE_COLORS.get(tag_type, active.color))
            result = self.container.work_library_service.favorite_tag(active.fandom_key, tag_type, tag_text, color)
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _tag_type_for_text(self, fandom_key_value: str, tag_text: str) -> TagType:
        match = self._catalog_match(fandom_key_value, tag_text)
        return self._tag_type_from_catalog_category(match.category if match else "")

    def _catalog_match(self, fandom_key_value: str, tag_text: str) -> Any | None:
        query = str(tag_text or "").strip()
        if not query:
            return None
        for item in self.container.fandom_service.tag_suggestions(fandom_key_value, query, 32):
            if item.tag_text.casefold() == query.casefold():
                return item
        return None

    def _tag_autocomplete(self, fandom_key_value: str) -> list[str]:
        return [
            item.tag_text
            for item in self.container.fandom_service.tag_suggestions(fandom_key_value, "", 1200)
            if item.tag_text
        ]

    @staticmethod
    def _short_tag_label(value: str, limit: int = 60) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 3)].rstrip()}..."

    @staticmethod
    def _tag_type_from_catalog_category(category: str) -> TagType:
        category = str(category or "").casefold()
        if "relationship" in category:
            return TagType.RELATIONSHIP
        if "character" in category:
            return TagType.CHARACTER
        if "fandom" in category:
            return TagType.FANDOM
        if "warning" in category:
            return TagType.WARNING
        if "rating" in category:
            return TagType.RATING
        if "category" in category:
            return TagType.CATEGORY
        if "freeform" in category or "additional" in category:
            return TagType.FREEFORM
        return TagType.OTHER

    def _render_date_filter_input(self, label: str, state: dict[str, Any], key: str, color: str) -> None:
        with ui.input(label, value=state.get(key, "")).bind_value(state, key).props(
            "outlined dense dark clearable hide-bottom-space"
        ).classes("filter-half-field date-field-input") as date_input:
            date_input.on("keydown.enter", lambda _=None, k=key: self._normalize_date_filter(state, k))
            with date_input.add_slot("append"):
                calendar = ui.icon("edit_calendar", size="18px").classes("date-field-action cursor-pointer")
                calendar.style(f"color: {normalized_label_color(color)};")
                calendar.on(
                    "click.stop",
                    lambda _=None, k=key, d=date_input, c=color, label_text=label: self._open_filter_date_calendar(
                        state,
                        k,
                        d,
                        c,
                        label_text,
                    ),
                )
                with calendar:
                    rich_tooltip("Choose date", color)

    def _normalize_date_filter(self, state: dict[str, Any], key: str) -> None:
        state[key] = normalize_ao3_date_filter(state.get(key))
        self._persist_browse_state(state)
        self._remember_filter_date(key, state[key])

    def _set_date_from_picker(self, state: dict[str, Any], key: str, value: str, date_input: Any | None = None) -> None:
        normalized = normalize_ao3_date_filter(value)
        state[key] = normalized
        self._persist_browse_state(state)
        self._remember_filter_date(key, normalized)
        if date_input is not None:
            date_input.set_value(normalized)

    def _filter_date_memory_key(self, key: str) -> str:
        active = self._active_fandom()
        return f"filter_calendar_last_{active.fandom_key}_{key}"

    def _remember_filter_date(self, key: str, value: str) -> None:
        normalized = normalize_ao3_date_filter(value)
        if normalized:
            self.container.preferences_service.set(self._filter_date_memory_key(key), normalized)

    def _filter_date_seed(self, state: dict[str, Any], key: str) -> str:
        current = normalize_ao3_date_filter(state.get(key))
        if current:
            return current
        stored = normalize_ao3_date_filter(self.container.preferences_service.get(self._filter_date_memory_key(key), ""))
        if stored:
            return stored
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _filter_date_popover_style(color: str, *, min_width: int = 286) -> str:
        r, g, b = rgb_from_hex(color)
        return (
            f"--field-r:{r}; --field-g:{g}; --field-b:{b}; "
            f"--date-selected-bg: radial-gradient(circle at 35% 30%, rgba(255,255,255,0.22), rgba({r},{g},{b},0.36) 42%, rgba({r},{g},{b},0.16) 74%); "
            f"--q-primary: var(--date-selected-bg); --q-primary-rgb: {r},{g},{b}; "
            f"min-width: {min_width}px; "
            f"background: linear-gradient(145deg, rgba({r},{g},{b},0.18), rgba({r},{g},{b},0.07) 46%, rgba(13,17,23,0.96)), #0d1117; "
            f"border: 1px solid rgba({r},{g},{b},0.34); border-radius: 8px; "
            f"box-shadow: 0 18px 42px rgba(0,0,0,0.42), 0 0 20px rgba({r},{g},{b},0.14);"
        )

    def _open_filter_date_calendar(
        self,
        state: dict[str, Any],
        key: str,
        date_input: Any,
        color: str,
        label: str,
    ) -> None:
        dialog = ui.dialog()
        seed = self._filter_date_seed(state, key)

        def pick_date(event: Any) -> None:
            selected = str(getattr(event, "value", "") or getattr(event, "args", "") or seed)
            self._set_date_from_picker(state, key, selected, date_input)
            dialog.close()

        dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("date-popover p-2 gap-2").style(self._filter_date_popover_style(color)):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(label).classes("text-sm font-bold").style(glow_text(color, 2))
                close_date = ui.button(icon="close", on_click=dialog.close).props("flat round dense size=sm")
                close_date.style(f"color: {normalized_label_color(color)} !important;")
            ui.date(value=seed, on_change=pick_date).props("minimal no-parent-event")
        dialog.open()

    def _segmented_pills(self, label: str, state: dict[str, Any], key: str, options: list[tuple[str, str]], color: str) -> None:
        with ui.row().classes("w-full gap-1 flex-wrap items-center filter-segmented-row"):
            ui.label(label).classes("text-xs text-gray-500 w-full")
            for value, text in options:
                selected = str(state.get(key) or "") == value
                pill = ui.button(text, on_click=lambda _=None, k=key, v=value: self._set_filter_scalar(state, k, v)).props("dense rounded")
                pill.style(self._filter_pill_style(color, selected))

    def _set_filter_scalar(self, state: dict[str, Any], key: str, value: str) -> None:
        state[key] = value
        self._persist_browse_state(state)
        self.refresh()

    @staticmethod
    def _event_bool(event: Any) -> bool:
        value = getattr(event, "value", None)
        if value is None:
            value = getattr(event, "args", None)
        return bool(value)

    def _filter_expanded(self, key: str, default: bool) -> bool:
        active_key = self._active_fandom().fandom_key
        stored = self.container.preferences_service.get("browse_filter_expansions", {})
        if not isinstance(stored, dict):
            return default
        fandom_state = stored.get(active_key, {})
        if not isinstance(fandom_state, dict):
            return default
        return bool(fandom_state.get(key, default))

    def _set_filter_expanded(self, key: str, value: bool, *, rerender_right: bool = False) -> None:
        active_key = self._active_fandom().fandom_key
        stored = self.container.preferences_service.get("browse_filter_expansions", {})
        if not isinstance(stored, dict):
            stored = {}
        fandom_state = stored.get(active_key, {})
        if not isinstance(fandom_state, dict):
            fandom_state = {}
        fandom_state[key] = bool(value)
        stored[active_key] = fandom_state
        self.container.preferences_service.set("browse_filter_expansions", stored)
        if rerender_right and self.page == "Browse":
            self._render_right()

    @staticmethod
    def _filter_pill_style(color: str, selected: bool) -> str:
        r, g, b = rgb_from_hex(color)
        return (
            f"background: rgba({r},{g},{b},{0.30 if selected else 0.10}) !important; "
            f"color: {normalized_label_color(color)} !important; "
            f"border: 1px solid rgba({r},{g},{b},{0.70 if selected else 0.22}); "
            "min-height: 28px;"
        )

    @staticmethod
    def _filter_group_color(group: dict[str, Any]) -> str:
        key = str(group.get("key") or group.get("label") or "").casefold()
        label = str(group.get("label") or "").casefold()
        return FILTER_GROUP_COLORS.get(key) or FILTER_GROUP_COLORS.get(label) or "#58a6ff"

    @staticmethod
    def _filter_option_key(mode: str, name: str, value: str) -> str:
        return f"{mode}|{name}|{value}"

    @staticmethod
    def _filter_label(option: dict[str, Any]) -> str:
        label = str(option.get("label") or option.get("value") or "")
        count = option.get("count")
        return f"{label} ({count})" if count is not None else label

    def _render_favorite_filter_pills(self, metadata: Any, state: dict[str, Any]) -> None:
        favorites = set(state.get("favorite_options") or [])
        if not favorites:
            return
        rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for mode in ("include", "exclude"):
            for group in self._metadata_groups(metadata, mode):
                for raw_option in group.get("options", []):
                    option = raw_option if isinstance(raw_option, dict) else asdict(raw_option)
                    fav_key = self._filter_option_key(mode, str(option.get("name") or ""), str(option.get("value") or ""))
                    if fav_key in favorites:
                        rows.append((mode, group, option))
        if not rows:
            return
        with ui.row().classes("w-full gap-1 flex-wrap filter-favorite-strip"):
            for mode, _group, option in rows:
                color = self._active_fandom().color if mode == "include" else TAG_TYPE_COLORS[TagType.WARNING]
                option_name = str(option.get("name") or "")
                option_value = str(option.get("value") or "")
                selected = option_value in set(state.get("selected", {}).get(option_name, []))
                pill = ui.button(self._filter_label(option)).props("dense rounded no-caps")
                pill.classes("filter-favorite-pill")
                pill.style(self._filter_pill_style(color, selected))
                pill.on(
                    "click",
                    lambda _=None, n=option_name, v=option_value: self._toggle_filter_option(
                        state,
                        n,
                        v,
                        v not in set(state.get("selected", {}).get(n, [])),
                    ),
                    js_handler="(event) => { event.stopPropagation(); emit(); }",
                )
                with pill:
                    rich_tooltip(f"{'Include' if mode == 'include' else 'Exclude'} {self._filter_label(option)}", color)

    def _render_filter_groups(self, metadata: Any, state: dict[str, Any], mode: str) -> None:
        groups = self._metadata_groups(metadata, mode)
        title = "Include" if mode == "include" else "Exclude"
        icon = "add_circle" if mode == "include" else "remove_circle"
        favorites = set(state.get("favorite_options") or [])
        expanded = self._filter_expanded(mode, False)
        expansion = ui.expansion(title, icon=icon, value=expanded).classes("w-full filter-expansion")
        expansion.on(
            "update:model-value",
            lambda event, k=mode: self._set_filter_expanded(k, self._event_bool(event), rerender_right=True),
        )
        mode_color = self._active_fandom().color if mode == "include" else TAG_TYPE_COLORS[TagType.WARNING]
        expansion.style(f"--filter-group-color: {mode_color};")
        if not expanded:
            return
        with expansion:
            if not groups:
                ui.label("Open or refresh the active fandom to load AO3 criteria.").classes("text-xs text-gray-500")
                return
            ordered = sorted(groups, key=lambda group: str(group.get("label") or ""))
            for group in ordered:
                group_label = str(group.get("label") or group.get("key") or title)
                group_key = f"{mode}:{group_label}"
                expanded = self._filter_expanded(group_key, False)
                color = self._filter_group_color(group)
                nested = ui.expansion(group_label, icon="label", value=expanded).classes("w-full filter-expansion-nested")
                nested.on(
                    "update:model-value",
                    lambda event, k=group_key: self._set_filter_expanded(k, self._event_bool(event), rerender_right=True),
                )
                nested.style(f"--filter-group-color: {color};")
                if not expanded:
                    continue
                with nested:
                    for option in group.get("options", [])[:30]:
                        option = option if isinstance(option, dict) else asdict(option)
                        name = str(option.get("name") or "")
                        value = str(option.get("value") or "")
                        fav_key = self._filter_option_key(mode, name, value)
                        selected = value in set(state.get("selected", {}).get(name, []))
                        with ui.row().classes("filter-option-row w-full items-center gap-1"):
                            star = ui.button(icon="star" if fav_key in favorites else "star_border").props("flat round dense size=xs")
                            star.classes("filter-option-star")
                            star.style(f"color: {'#facc15' if fav_key in favorites else '#64748b'} !important;")
                            star.on("click.stop", lambda _=None, key=fav_key: self._toggle_favorite_filter_option(state, key))
                            checkbox = ui.checkbox(
                                self._filter_label(option),
                                value=selected,
                                on_change=lambda event, n=name, v=value: self._toggle_filter_option(
                                    state,
                                    n,
                                    v,
                                    bool(event.value),
                                ),
                            )
                            checkbox.classes("filter-option-checkbox text-xs leading-tight")

    def _toggle_favorite_filter_option(self, state: dict[str, Any], option_key: str) -> None:
        favorites = list(state.get("favorite_options") or [])
        if option_key in favorites:
            favorites.remove(option_key)
        else:
            favorites.append(option_key)
        state["favorite_options"] = favorites
        self._persist_browse_state(state)
        self.refresh()

    def _toggle_filter_option(self, state: dict[str, Any], name: str, value: str, checked: bool) -> None:
        selected = state.setdefault("selected", {})
        values = list(selected.get(name, []))
        if checked and value not in values:
            values.append(value)
        if not checked and value in values:
            values.remove(value)
        selected[name] = values
        self._persist_browse_state(state)
        self.refresh()

    async def _load_fandom(self, state: dict[str, Any], *, force_refresh: bool = False) -> None:
        client = self._current_client()
        state["page"] = 1
        self._persist_browse_state(state)
        result = await run.io_bound(
            lambda: self.container.browse_service.fetch_fandom(
                str(state.get("fandom") or DEFAULT_FANDOM),
                force_refresh=force_refresh,
            )
        )
        self._store_filter_metadata(result.filter_metadata)
        if result.ok and result.snapshot:
            purge_result = self.container.work_library_service.maybe_auto_purge_cache(result.snapshot.work_ids)
            if purge_result:
                self._notify(purge_result.message, "info", client=client)
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        self._invalidate_browse_page_model()
        self.refresh()

    def _start_apply_fandom_filters(self, state: dict[str, Any]) -> None:
        client = self._current_client()
        snapshot_state = json.loads(json.dumps(state))
        self._persist_browse_state(snapshot_state)
        url = self.container.browse_service.resolve_effective_fandom_filter_url(
            str(snapshot_state.get("fandom") or DEFAULT_FANDOM),
            snapshot_state,
        )
        self.refresh()
        if self._browse_fetch_inflight_url == url:
            return
        self._browse_fetch_serial += 1
        serial = self._browse_fetch_serial
        self._browse_fetch_inflight_url = url
        self._notify("Refreshing AO3 in the background.", "info", client=client)
        background_tasks.create(
            self._apply_fandom_filters_background(snapshot_state, client, serial, url),
            name="ao3-filter-refresh",
        )

    async def _apply_fandom_filters_background(
        self,
        state: dict[str, Any],
        client: Any | None,
        serial: int,
        url: str,
    ) -> None:
        result = await run.io_bound(
            lambda: self.container.browse_service.fetch_fandom(str(state.get("fandom") or DEFAULT_FANDOM), state, force_refresh=True)
        )
        if serial != self._browse_fetch_serial:
            return
        self._browse_fetch_inflight_url = "" if self._browse_fetch_inflight_url == url else self._browse_fetch_inflight_url
        self._store_filter_metadata(result.filter_metadata)
        if result.ok and result.snapshot:
            purge_result = self.container.work_library_service.maybe_auto_purge_cache(result.snapshot.work_ids)
            if purge_result:
                self._notify(purge_result.message, "info", client=client)
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        self._invalidate_browse_page_model()
        try:
            if client is not None:
                with client:
                    self.refresh()
            else:
                self.refresh()
        except RuntimeError:
            return

    def _turn_page(self, state: dict[str, Any], delta: int) -> None:
        try:
            current = int(float(state.get("page") or 1))
        except (TypeError, ValueError):
            current = 1
        state["page"] = max(1, current + delta)
        self._start_apply_fandom_filters(state)

    def _nudge_page_input(self, state: dict[str, Any], page_input: Any, delta: int) -> None:
        try:
            current = int(float(state.get("page") or 1))
        except (TypeError, ValueError):
            current = 1
        value = max(1, current + delta)
        state["page"] = str(value)
        page_input.set_value(str(value))

    @staticmethod
    def _attach_page_spin_repeat(button: Any) -> None:
        repeat_js = """
            (event) => {
                event.stopPropagation();
                const button = event.currentTarget;
                const stop = () => {
                    clearTimeout(button.__ao3SpinDelay);
                    clearInterval(button.__ao3SpinRepeat);
                    button.__ao3SpinDelay = null;
                    button.__ao3SpinRepeat = null;
                    window.removeEventListener('mouseup', stop);
                    window.removeEventListener('blur', stop);
                    button.removeEventListener('mouseleave', stop);
                };
                stop();
                button.__ao3SpinDelay = setTimeout(() => {
                    button.__ao3SpinRepeat = setInterval(() => button.click(), 72);
                }, 240);
                window.addEventListener('mouseup', stop);
                window.addEventListener('blur', stop);
                button.addEventListener('mouseleave', stop);
            }
        """
        button.on("mousedown", js_handler=repeat_js)

    async def _open_ao3_account_session(self, state: dict[str, Any]) -> None:
        client = self._current_client()
        self._persist_browse_state(state)
        url = self.container.browse_service.resolve_effective_fandom_filter_url(str(state.get("fandom") or DEFAULT_FANDOM), state)
        ui.run_javascript(f"window.open({json.dumps(url)}, '_blank', 'noopener')")
        self._notify("Opened AO3 in your current browser. AO3 Studio reads local Firefox AO3 cookies on retry.", "info", client=client)

    def _current_browse_url(self, state: dict[str, Any] | None = None) -> str:
        browse_state = state or self._browse_filter_state()
        return self.container.browse_service.resolve_effective_fandom_filter_url(str(browse_state.get("fandom") or DEFAULT_FANDOM), browse_state)

    def _show_save_page_set_dialog(self, work_ids: list[str]) -> None:
        state = self._browse_filter_state()
        snapshot = self._current_browse_snapshot()
        if not snapshot or not work_ids:
            self._notify("Refresh this AO3 page before saving it as a queue.", "warning")
            return
        active = self._active_fandom()
        schema = self.container.schema_service.active_schema()
        page_number = int(snapshot.page_number or state.get("page") or 1)
        default_name = f"{short_fandom_name(active.tag)} p{page_number} {normalize_ao3_sort_column(state.get('sort_column')).replace('_', ' ')}"
        draft = {"name": default_name}
        dialog = ui.dialog()
        dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("w-[420px] max-w-[94vw] p-0 gap-0 overflow-hidden").style(wash_background(active.color, 0.16)):
            with ui.row().classes("w-full items-center justify-between p-3 border-b border-gray-700"):
                ui.label("Save Page as Queue").classes("text-base font-bold").style(glow_text(active.color, 4))
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=white")
            with ui.column().classes("w-full gap-3 p-3"):
                ui.input("Queue name", value=draft["name"]).bind_value(draft, "name").props("outlined dense dark").classes("w-full")
                ui.label(f"{schema.name} | page {page_number} | {len(work_ids)} works | {short_fandom_name(active.tag)}").classes(
                    "text-xs text-gray-500"
                )
            with ui.row().classes("w-full justify-end gap-2 p-3 border-t border-gray-700"):
                ui.button("Save", icon="playlist_add", on_click=lambda: save()).style(
                    f"background-color: {dark_button_color(active.color)} !important; color: white;"
                )

        def save() -> None:
            result = self.container.queue_service.save_page_as_evaluation_queue(
                fandom_key=active.fandom_key,
                name=str(draft["name"] or ""),
                filter_state=state,
                source_url=snapshot.source_url,
                work_ids=work_ids,
                page_number=page_number,
                schema_key=schema.schema_key,
            )
            if result.ok and isinstance(result.payload, dict) and result.payload.get("batch"):
                self._set_batch_selection("queue", result.payload["batch"].id)
            self._notify(result.message, "positive" if result.ok else "negative")
            dialog.close()
            self.refresh()

        dialog.open()

    def _collect_page(self, work_ids: list[str]) -> None:
        active = self._active_fandom()
        result = self.container.work_library_service.collect_many(work_ids, active.fandom_key)
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _collect_work(self, work_id: str, button: Any | None = None) -> None:
        active = self._active_fandom()
        if self.container.work_library_service.is_collected(work_id):
            self._notify("Already in Works.", "info")
            self._style_work_action(button, normalized_label_color(active.color), icon="bookmark")
            return
        result = self.container.work_library_service.collect(work_id, active.fandom_key)
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        if result.ok:
            self._style_work_action(button, normalized_label_color(active.color), icon="bookmark")

    def _block_work(self, work_id: str, button: Any | None = None) -> None:
        active = self._active_fandom()
        result = self.container.work_library_service.block_work(work_id, active.fandom_key)
        self._notify(result.message, "positive" if result.ok else "negative")
        self.block_armed_work_id = ""
        self._style_work_action(button, "#6b7280")
        if result.ok:
            self._invalidate_browse_page_model()
            self.refresh()

    def _block_author_for_work(self, work_id: str) -> None:
        active = self._active_fandom()
        result = self.container.work_library_service.block_author_for_work(work_id, active.fandom_key)
        self._notify(result.message, "positive" if result.ok else "negative")
        if result.ok:
            self._invalidate_browse_page_model()
            self.refresh()

    def _handle_block_icon(self, work_id: str, button: Any | None = None) -> None:
        if self.block_armed_work_id == work_id:
            self._block_work(work_id, button)
            return
        self._disarm_block_icon()
        self.block_armed_work_id = work_id
        self._block_buttons[work_id] = button
        self._style_work_action(button, "#ef4444")

    def _handle_work_card_body_click(self, work_id: str, event: Any | None = None) -> None:
        if self.work_remove_armed_id:
            self._disarm_work_remove_icon()
            return
        if self.block_armed_work_id:
            self._disarm_block_icon()
            return
        desired = "toggle"
        hydrate = False
        hydrate_token = ""
        args = getattr(event, "args", None)
        if isinstance(args, dict):
            desired = str(args.get("desired") or "toggle")
            hydrate = bool(args.get("hydrate"))
            hydrate_token = str(args.get("token") or "")
        elif isinstance(args, (list, tuple)) and args and isinstance(args[0], dict):
            desired = str(args[0].get("desired") or "toggle")
            hydrate = bool(args[0].get("hydrate"))
            hydrate_token = str(args[0].get("token") or "")
        if hydrate and desired == "open":
            self._hydrate_work_panel(work_id, hydrate_token=hydrate_token)
            return
        self._set_work_expansion(work_id, desired)

    def _hydrate_browse_work_panel(self, work_id: str, *, hydrate_token: str = "") -> None:
        self._hydrate_work_panel(work_id, hydrate_token=hydrate_token)

    def _hydrate_work_panel(self, work_id: str, *, hydrate_token: str = "") -> None:
        client = self._current_client()
        active = self._active_fandom()
        model = self._current_work_render_model()
        work = next((item for item in model.works if item.work_id == work_id), None) if model else None
        work = work or self.container.work_library_service.get(work_id)
        panel_slot = self._inline_work_panel_slots.get(work_id)
        if not work or panel_slot is None:
            self._set_work_expansion(work_id, "open")
            return
        self.selected_work_id = work_id
        self._work_expand_serial += 1
        self.container.preferences_service.set("selected_work_id", self.selected_work_id)
        panel_slot.clear()
        with panel_slot:
            self._inline_work_panel_contents(
                work,
                active,
                schema=model.schema if model else None,
                latest=model.latest_evaluations.get(work_id) if model else None,
                latest_loaded=model is not None,
                rarity=model.rarities_by_work.get(work_id) if model else None,
            )
        self._render_right()
        self._animate_hydrated_work_panel(work_id, hydrate_token=hydrate_token, client=client)

    def _disarm_block_icon(self) -> None:
        if not self.block_armed_work_id:
            return
        button = self._block_buttons.get(self.block_armed_work_id)
        self._style_work_action(button, "#6b7280")
        self.block_armed_work_id = ""

    @staticmethod
    def _style_work_action(button: Any | None, color: str, *, icon: str | None = None) -> None:
        if button is None:
            return
        try:
            if icon:
                button._props["icon"] = icon
            button.style(replace=f"color: {color} !important;")
            button.update()
        except RuntimeError:
            return

    def _handle_work_remove_icon(self, work_id: str, button: Any | None = None) -> None:
        if self.page != "Works":
            return
        if self.work_remove_armed_id == work_id:
            self.container.work_library_service.uncollect(work_id)
            self._invalidate_browse_page_model()
            self.work_remove_armed_id = ""
            self._notify("Removed from Works.", "positive")
            self.refresh()
            return
        self._disarm_work_remove_icon()
        self.work_remove_armed_id = work_id
        self._work_remove_buttons[work_id] = button
        self._style_work_action(button, "#ef4444", icon="bookmark_remove")

    def _disarm_work_remove_icon(self) -> None:
        if not self.work_remove_armed_id:
            return
        button = self._work_remove_buttons.get(self.work_remove_armed_id)
        self._style_work_action(button, normalized_label_color(self._active_fandom().color), icon="bookmark")
        self.work_remove_armed_id = ""

    def _open_reader(self, work_id: str) -> None:
        self.selected_work_id = work_id
        self.container.preferences_service.set("selected_work_id", work_id)
        self.container.preferences_service.set("reader_work_id", work_id)
        self._set_page("Read")

    def _purge_uncollected_cache(self, keep_work_ids: list[str] | None = None) -> None:
        result = self.container.work_library_service.purge_uncollected_cache(keep_work_ids)
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive")
        self.refresh()

    def _unblock_work(self, work_id: str) -> None:
        self.container.work_library_service.unblock_work(work_id)
        self._invalidate_browse_page_model()
        self._notify("Work unblocked.", "positive")
        self.refresh()

    def _unblock_author(self, author_key: str) -> None:
        self.container.work_library_service.unblock_author(author_key)
        self._invalidate_browse_page_model()
        self._notify("Author unblocked.", "positive")
        self.refresh()

    def _save_current_filter_defaults(self, state: dict[str, Any]) -> None:
        active = self._active_fandom()
        self._persist_browse_state(state)
        result = self.container.fandom_service.save_filter_preferences(active.fandom_key, state)
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _page_title(self, title: str, subtitle: str = "") -> None:
        with ui.row().classes("w-full items-start justify-between gap-3"):
            with ui.column().classes("gap-0"):
                ui.label(title).classes("text-2xl font-bold")
                if subtitle:
                    ui.label(subtitle).classes("text-sm text-gray-500")

    def _page_browse(self) -> None:
        model = self._browse_page_model_for_current_state()
        if not model:
            self._empty("travel_explore", "Refresh this AO3 filter to load the current page")
            return

        anchor_id = _work_id_from_any(str(model.state.get("anchor_work_url") or ""))
        if anchor_id:
            anchor_text = "key work on this page" if anchor_id in model.visible_ids else "key work not on this page"
            ui.label(anchor_text).classes("text-[11px] text-gray-500 px-1 -mb-1")
        self._render_work_list(model.works, "", browse_actions=True, browse_model=model)

    async def _fetch_browse(self, state: dict[str, Any]) -> None:
        client = self._current_client()
        self.container.preferences_service.set("last_browse_url", state["url"])
        self.container.preferences_service.set("last_context_type", state["context_type"])
        self.container.preferences_service.set("last_context_key", state["context_key"])
        result = await run.io_bound(
            lambda: self.container.browse_service.fetch_browse_url(
                state["url"],
                state["context_type"],
                state["context_key"],
            )
        )
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        self._invalidate_browse_page_model()
        self.refresh()

    def _start_pubdate_enrichment(self, works: list[Work]) -> None:
        if time.monotonic() < self._pubdate_enrichment_retry_at:
            return
        candidates = [
            work
            for work in works
            if work.ao3_url
            and self._needs_date_enrichment(work)
            and work.work_id not in self._pubdate_enrichment_ids
            and not work.is_deleted_or_missing
        ]
        if not candidates:
            return
        batch = candidates
        for work in batch:
            self._pubdate_enrichment_ids.add(work.work_id)
        client = self._current_client()
        background_tasks.create(self._pubdate_enrichment_background(batch, client), name="ao3-pubdate-enrichment")

    def _needs_date_enrichment(self, work: Work) -> bool:
        pub_display = self._display_ao3_date(work.published_at)
        up_display = self._display_ao3_date(work.last_ao3_updated_at)
        return not pub_display or not up_display or bool(pub_display and up_display == pub_display)

    async def _pubdate_enrichment_background(self, works: list[Work], client: Any | None) -> None:
        def enrich() -> tuple[dict[str, dict[str, str]], int]:
            updated: dict[str, dict[str, str]] = {}
            failed = 0
            for work in works:
                result = self.container.work_fetch_service.fetch_work(work.ao3_url)
                if result.ok and result.work:
                    pub_text = self._display_ao3_date(result.work.published_at)
                    up_text = self._display_ao3_date(result.work.last_ao3_updated_at)
                    if pub_text or up_text:
                        updated[work.work_id] = {"published": pub_text, "updated": up_text}
                elif not result.ok:
                    failed += 1
            return updated, failed

        updated, failed = await run.io_bound(enrich)
        for work in works:
            self._pubdate_enrichment_ids.discard(work.work_id)
        if failed and not updated:
            self._pubdate_enrichment_retry_at = time.monotonic() + 90
            return
        if updated:
            try:
                if client is not None:
                    with client:
                        for work_id, date_texts in updated.items():
                            pub_label = self._pubdate_labels.get(work_id)
                            if pub_label is not None and date_texts.get("published"):
                                pub_label.set_text(f"Pub: {date_texts['published']}")
                            up_label = self._updatedate_labels.get(work_id)
                            up_text = date_texts.get("updated") or ""
                            pub_text = date_texts.get("published") or ""
                            if up_label is not None and up_text and up_text != pub_text:
                                up_label.set_text(f"Up: {up_text}")
            except RuntimeError:
                return

    async def _use_suggestion(self, state: dict[str, Any], value: str) -> None:
        state["context_key"] = value
        self.container.preferences_service.set("last_context_key", value)
        await self._fetch_browse(state)

    def _page_work_detail(self) -> None:
        self._page_title("Work Detail", "Refresh metadata, queue work, and save manual or LM Studio evaluations.")
        if not self.selected_work_id:
            self._empty("article", "Select a cached work from Browse or Works")
            return
        work = self.container.work_library_service.get(self.selected_work_id)
        if not work:
            self._empty("article", "Selected work is not cached")
            return
        self._work_header(work)
        self._evaluation_panel(work)

    def _work_header(self, work: Work) -> None:
        with ui.element("div").classes("work-card w-full p-3"):
            with ui.row().classes("w-full items-start justify-between gap-3"):
                with ui.column().classes("gap-1 min-w-0"):
                    ui.link(work.title or f"Work {work.work_id}", work.ao3_url, new_tab=True).classes("text-xl font-bold text-blue-200")
                    ui.label(work.author_name or "Unknown author").classes("text-sm text-gray-400")
                    if work.summary_text:
                        ui.label(work.summary_text).classes("text-sm text-gray-300")
                with ui.column().classes("items-end gap-1"):
                    ui.label(f"{work.words or 0:,} words").classes("text-xs text-gray-400")
                    ui.label(f"{work.kudos or 0:,} kudos").classes("text-xs text-gray-400")
                    ui.button("Refresh Work", icon="refresh", on_click=lambda: self._refresh_work(work)).props("dense")
                    ui.button("Queue", icon="playlist_add", on_click=lambda: self._queue_work(work.work_id)).props("dense")
            tags = self.container.work_library_service.tags_for_work(work.work_id)
            if tags:
                with ui.row().classes("gap-1 flex-wrap mt-2"):
                    for tag in tags[:30]:
                        ui.label(tag.tag_text).classes("text-[11px] px-2 py-1 rounded-full").style(
                            "background: rgba(88,166,255,0.12); border: 1px solid rgba(88,166,255,0.22);"
                        )

    async def _refresh_work(self, work: Work) -> None:
        client = self._current_client()
        result = await run.io_bound(lambda: self.container.work_fetch_service.fetch_work(work.ao3_url))
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        self.refresh()

    def _queue_work(self, work_id: str, button: Any | None = None) -> None:
        if self.container.queue_service.is_active_for_work(work_id):
            self._notify("Already queued for evaluation.", "info")
            self._style_work_action(button, normalized_label_color(self._active_fandom().color))
            return
        active = self._active_fandom()
        self.container.queue_service.enqueue(work_id, reason="Manual queue", fandom_key_value=active.fandom_key)
        self._invalidate_browse_page_model()
        self._notify("Queued for evaluation.", "positive")
        self._style_work_action(button, normalized_label_color(active.color))

    def _evaluation_panel(self, work: Work) -> None:
        schema = self.container.schema_service.active_schema()
        latest = self.container.evaluation_service.latest_for_work(work.work_id, schema.schema_key)
        score_state = {dimension.key: latest.scores.get(dimension.key, schema.score_range.minimum) if latest else schema.score_range.minimum for dimension in schema.dimensions}
        note_state = {"notes": latest.notes_markdown if latest and latest.notes_markdown else ""}
        with ui.element("div").classes("soft-panel w-full p-3"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(f"Evaluation: {schema.name}").classes("text-lg font-bold")
                with ui.row().classes("gap-2"):
                    ui.button("Evaluate with LM Studio", icon="psychology", on_click=lambda: self._lmstudio_eval(work, schema)).props("color=secondary")
                    ui.button("Save Manual", icon="save", on_click=lambda: self._save_manual_eval(work, schema, score_state, note_state)).props("color=primary")
            with ui.row().classes("w-full gap-3 flex-wrap mt-3"):
                for dimension in schema.dimensions:
                    ui.number(
                        dimension.label,
                        value=score_state[dimension.key],
                        min=schema.score_range.minimum,
                        max=schema.score_range.maximum,
                        step=schema.score_range.step,
                    ).bind_value(score_state, dimension.key).props("outlined dense dark").classes("w-48")
            ui.textarea("Notes", value=note_state["notes"]).bind_value(note_state, "notes").props("outlined dense dark").classes(
                "w-full mt-3"
            )
        evaluations = self.container.evaluation_service.list_for_work(work.work_id)
        if evaluations:
            ui.label("Evaluation History").classes("text-sm font-bold")
            for evaluation in evaluations[:8]:
                with ui.element("div").classes("soft-panel w-full p-2"):
                    with ui.row().classes("w-full justify-between"):
                        ui.label(f"{evaluation.schema_key} {evaluation.schema_version}").classes("text-sm font-bold")
                        ui.label(evaluation.updated_at).classes("text-xs text-gray-500")
                    ui.label(_score_summary(evaluation.scores)).classes("text-xs text-gray-400")

    async def _lmstudio_eval(self, work: Work, schema: EvaluationSchema) -> None:
        client = self._current_client()
        result = await run.io_bound(lambda: self.container.evaluation_service.evaluate_with_lm_studio(work.work_id, schema.schema_key))
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        if result.errors:
            self._notify("; ".join(result.errors[:2]), "warning", client=client)
        self.refresh()

    def _save_manual_eval(self, work: Work, schema: EvaluationSchema, scores: dict[str, Any], note_state: dict[str, Any]) -> None:
        clean_scores = {key: int(value) for key, value in scores.items()}
        result = self.container.evaluation_service.save_manual(
            work_id=work.work_id,
            schema_key=schema.schema_key,
            scores=clean_scores,
            notes_markdown=str(note_state.get("notes") or ""),
            status=EvaluationStatus.COMPLETE,
        )
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _page_read(self) -> None:
        work_id = str(self.container.preferences_service.get("reader_work_id", "") or self.selected_work_id or "")
        if not work_id:
            with ui.column().classes("reader-stage w-full h-full min-h-0"):
                self._empty("menu_book", "Select a work title from Browse, Works, or Queue")
            return
        result = self.container.reader_service.open_work(work_id, auto_download=False)
        if not result.work:
            with ui.column().classes("reader-stage w-full h-full min-h-0"):
                self._empty("menu_book", result.message or "Reader work is not cached")
            return
        work = result.work
        active = self._active_fandom()
        chapter_index = max(1, int(result.active_chapter_index or 1))
        chapters = result.chapters
        chapter = chapters[chapter_index - 1] if chapters and chapter_index <= len(chapters) else None
        if not chapters and not self._reader_download_inflight:
            self._start_reader_download(work.work_id, rerender=False)
        style_settings = self.container.style_service.effective_settings(active.fandom_key)
        border_classes, border_style = self._rarity_border_for_work(work.work_id, style_settings)
        with ui.column().classes("reader-stage w-full h-full gap-0 min-h-0"):
            with ui.element("div").classes("reader-panels-container w-full flex-grow min-h-0"):
                with ui.column().classes("reader-panel flex-1 h-full gap-2 min-w-0"):
                    reader_classes = f"reader-border-container flex-grow w-full rounded-lg overflow-hidden flex flex-col {border_classes}".strip()
                    with ui.element("div").classes(reader_classes).style(border_style):
                        self._attach_rarity_context_menu(work.work_id, active.color)
                        with ui.scroll_area().classes("reader-panel-scroll w-full h-full flex-grow"):
                            if chapter:
                                characters = self.container.fandom_service.list_characters(active.fandom_key)
                                selected_character = self._reader_selected_character(
                                    work.work_id,
                                    chapter_index,
                                    characters,
                                    chapter.html,
                                )
                                rendered = _reader_highlight_characters(chapter.html, characters)
                                rendered = _reader_apply_pov_paragraph_colors(
                                    rendered,
                                    selected_character.color if selected_character else None,
                                )
                                prose_style = html.escape(self._reader_font_style(style_settings), quote=True)
                                ui.html(
                                    f'<div class="reader-html-root"><div class="reader-prose" style="{prose_style}">{rendered}</div></div>',
                                    sanitize=False,
                                ).classes("w-full h-full")
                            elif self._reader_download_inflight == work.work_id:
                                self._empty("hourglass_empty", "Downloading AO3 reader HTML")
                            else:
                                self._empty("menu_book", result.message or "No reader content downloaded yet")

    def _set_reader_chapter(self, work_id: str, chapter_index: int) -> None:
        self.container.reader_service.set_position(work_id, max(1, chapter_index), 0.0)
        self.container.preferences_service.set("reader_work_id", work_id)
        self.refresh()

    def _start_reader_download(self, work_id: str, *, force: bool = False, rerender: bool = True) -> None:
        if self._reader_download_inflight and not force:
            return
        client = self._current_client()
        self._reader_download_inflight = work_id
        self.container.preferences_service.set("reader_work_id", work_id)
        self._notify("Downloading AO3 reader HTML.", "info", client=client)
        background_tasks.create(self._reader_download_background(work_id, client), name="ao3-reader-download")
        if rerender:
            self.refresh()

    async def _reader_download_background(self, work_id: str, client: Any | None) -> None:
        result = await run.io_bound(lambda: self.container.reader_service.refresh_work(work_id))
        self._reader_download_inflight = ""
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        try:
            if client is not None:
                with client:
                    self.refresh()
            else:
                self.refresh()
        except RuntimeError:
            return

    def _page_queue(self) -> None:
        if not self.selected_queue_cluster_id:
            clusters = self._cluster_summaries_for_mode("queue")
            if not clusters:
                self._empty("playlist_add_check", "Save a Browse page as a queue")
                return
            self._empty("playlist_add_check", "Select a queue cluster from the right panel")
            return
        if not self.selected_queue_schema_key:
            self._empty("rule", "Select a schema under this queue cluster")
            return
        if not self.selected_queue_batch_id:
            self._empty("playlist_add_check", "No queued works for this schema")
            return
        model = self._cluster_page_model_for_mode("queue", self.selected_queue_batch_id)
        if not model:
            self._empty("playlist_add_check", "Queue cluster is unavailable")
            return
        works = self._filter_cluster_works(model.works, model, "queue")
        if not works:
            self._empty("check_circle", "No pending works match these filters")
            return
        ui.label(model.summary.work_set.name if model.summary else "Queue").classes("text-sm font-bold text-gray-300")
        self._render_work_list(works, "", render_model=model, lazy_panels=True)

    def _page_evaluated(self) -> None:
        if not self.selected_evaluated_cluster_id:
            clusters = self._cluster_summaries_for_mode("evaluated")
            if not clusters:
                self._empty("fact_check", "Completed evaluations will appear here")
                return
            self._empty("fact_check", "Select an evaluated cluster from the right panel")
            return
        if not self.selected_evaluated_schema_key:
            self._empty("rule", "Select a schema under this evaluated cluster")
            return
        if not self.selected_evaluated_batch_id:
            self._empty("playlist_add", "This schema has not been evaluated for this cluster yet")
            return
        model = self._cluster_page_model_for_mode("evaluated", self.selected_evaluated_batch_id)
        if not model:
            self._empty("fact_check", "Evaluated cluster is unavailable")
            return
        works = self._filter_cluster_works(model.works, model, "evaluated")
        if not works:
            self._empty("fact_check", "No evaluated works match these filters")
            return
        name = model.summary.work_set.name if model.summary else "Evaluated"
        ui.label(f"{name} | {model.schema.name}").classes("text-sm font-bold text-gray-300")
        self._render_work_list(works, "", render_model=model, lazy_panels=True)

    def _queue_run_available(self) -> bool:
        if not self.selected_queue_batch_id:
            return False
        summary = self.container.queue_service.summary_for_batch(self.selected_queue_batch_id)
        return bool(summary and summary.active_count > 0)

    def _queue_run_work_order(self) -> list[str]:
        if not self.selected_queue_batch_id:
            return []
        model = self._cluster_page_model_for_mode("queue", self.selected_queue_batch_id)
        if not model:
            return []
        state = self._cluster_filter_state("queue")
        sort_column = normalize_ao3_sort_column(state.get("sort_column"))
        reverse = str(state.get("sort_dir") or "desc") != "asc"
        works = sorted(model.works, key=lambda work: self._work_sort_value(work, sort_column), reverse=reverse)
        return [work.work_id for work in works]

    def _toggle_queue_evaluation_run(self) -> None:
        if self._queue_eval_running:
            self._queue_eval_cancel_requested = True
            self._notify("Queue evaluation will stop after the current work.", "info")
            self._render_top()
            return
        self._start_queue_evaluation_run()

    def _start_queue_evaluation_run(self) -> None:
        if not self.selected_queue_batch_id:
            self._notify("Select a queue cluster first.", "warning")
            return
        if not self.container.queue_runner_service.config_exists():
            self._show_queue_eval_config_dialog(start_after_save=True)
            return
        if not self._queue_run_available():
            self._notify("No pending works remain in this queue.", "info")
            return
        batch_id = self.selected_queue_batch_id
        work_order = self._queue_run_work_order()
        client = self._current_client()
        self._queue_eval_running = True
        self._queue_eval_cancel_requested = False
        self._queue_eval_batch_id = batch_id
        self._notify("Queue evaluation started.", "info", client=client)
        background_tasks.create(self._queue_evaluation_background(batch_id, work_order, client), name="ao3-queue-evaluation")
        self._render_top()

    async def _queue_evaluation_background(self, batch_id: str, work_order: list[str], client: Any | None) -> None:
        result = await run.io_bound(
            lambda: self.container.queue_runner_service.run_batch(
                batch_id,
                work_order=work_order,
                should_cancel=lambda: self._queue_eval_cancel_requested,
            )
        )
        self._queue_eval_running = False
        self._queue_eval_cancel_requested = False
        self._queue_eval_batch_id = ""
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        try:
            if client is not None:
                with client:
                    self.refresh()
            else:
                self.refresh()
        except RuntimeError:
            return

    def _set_queue_status(self, item_id: str, status: QueueStatus) -> None:
        self.container.queue_service.update_status(item_id, status)
        self._invalidate_browse_page_model()
        self.refresh()

    def _page_works(self) -> None:
        model = self._works_page_model_for_current_state()
        works = self._filter_cluster_works(model.works, model, "works")
        if not works:
            self._empty("library_books", "No works match these filters")
            return
        self._render_work_list(works, "", render_model=model, lazy_panels=True)

    def _work_set_expanded(self, set_id: str) -> bool:
        expanded = self.container.preferences_service.get("expanded_work_sets", [])
        return set_id in expanded if isinstance(expanded, list) else False

    def _toggle_work_set(self, set_id: str) -> None:
        expanded = self.container.preferences_service.get("expanded_work_sets", [])
        if not isinstance(expanded, list):
            expanded = []
        if set_id in expanded:
            expanded.remove(set_id)
        else:
            expanded.append(set_id)
        self.container.preferences_service.set("expanded_work_sets", expanded)
        self.refresh()

    async def _refresh_work_set(self, set_id: str) -> None:
        client = self._current_client()

        def refresh() -> ServiceResult:
            work_set = self.container.work_set_repo.get(set_id)
            if not work_set:
                return ServiceResult(False, "Work Set was not found.")
            profile = self.container.fandom_repo.get(work_set.fandom_key)
            if not profile:
                return ServiceResult(False, "Work Set fandom was not found.")
            pages = self.container.work_library_service.work_set_pages(set_id)
            if not pages:
                page = max(1, int(float(work_set.filter_state.get("page") or 1)))
                pages_to_refresh = [(page, "")]
            else:
                pages_to_refresh = [(page.page_number, page.source_url) for page in pages]
            refreshed = 0
            for page_number, _url in pages_to_refresh:
                state = dict(work_set.filter_state)
                state["page"] = page_number
                result = self.container.browse_service.fetch_fandom(profile.tag, state, force_refresh=True)
                if not result.ok or not result.snapshot:
                    return ServiceResult(False, result.message)
                self.container.work_set_repo.record_page(
                    set_id,
                    page_number,
                    result.snapshot.source_url,
                    result.snapshot.work_ids,
                    result.snapshot.captured_at,
                )
                refreshed += 1
            return ServiceResult(True, f"Refreshed {refreshed} page{'s' if refreshed != 1 else ''}.")

        result = await run.io_bound(refresh)
        self._notify(result.message, "positive" if result.ok else "negative", client=client)
        self.refresh()

    def _rename_work_set_dialog(self, set_id: str, current_name: str) -> None:
        active = self._active_fandom()
        draft = {"name": current_name}
        dialog = ui.dialog()
        dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("w-[380px] max-w-[94vw] p-0 gap-0 overflow-hidden").style(wash_background(active.color, 0.16)):
            with ui.row().classes("w-full items-center justify-between p-3 border-b border-gray-700"):
                ui.label("Rename Work Set").classes("text-base font-bold").style(glow_text(active.color, 4))
                ui.button(icon="close", on_click=dialog.close).props("flat round dense color=white")
            with ui.column().classes("w-full p-3"):
                ui.input("Name", value=draft["name"]).bind_value(draft, "name").props("outlined dense dark").classes("w-full")
            with ui.row().classes("w-full justify-end gap-2 p-3 border-t border-gray-700"):
                ui.button("Save", icon="save", on_click=lambda: save()).style(
                    f"background-color: {dark_button_color(active.color)} !important; color: white;"
                )

        def save() -> None:
            result = self.container.work_library_service.rename_work_set(set_id, str(draft["name"] or ""))
            self._notify(result.message, "positive" if result.ok else "negative")
            dialog.close()
            self.refresh()

        dialog.open()

    def _delete_work_set(self, set_id: str) -> None:
        result = self.container.work_library_service.delete_work_set(set_id)
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _search_works(self, state: dict[str, Any]) -> None:
        self.container.preferences_service.set("work_search", state.get("search", ""))
        self._render_center()
        self._render_right()

    def _clear_work_search(self, state: dict[str, Any]) -> None:
        state["search"] = ""
        self.container.preferences_service.set("work_search", "")
        self._render_center()
        self._render_right()

    def _render_work_list(
        self,
        works: list[Work],
        title: str,
        *,
        browse_actions: bool = False,
        browse_model: BrowsePageModel | None = None,
        render_model: WorkListRenderModel | None = None,
        lazy_panels: bool = False,
    ) -> None:
        active = self._active_fandom()
        lookup_model = browse_model or render_model
        favorite_lookup = lookup_model.favorite_lookup if lookup_model else self._favorite_tag_map(active.fandom_key)
        tag_color_lookup = lookup_model.tag_color_lookup if lookup_model else self._tag_color_map(active.fandom_key)
        style_settings = lookup_model.style_settings if lookup_model else self.container.style_service.effective_settings(active.fandom_key)
        if title:
            ui.label(title).classes("text-sm font-bold text-gray-300")
        if not works:
            self._empty("library_books", "Search AO3 from the right panel")
            return
        queued_work_ids = lookup_model.queued_work_ids if lookup_model else self.container.queue_service.active_work_ids()
        for work in works:
            expanded = work.work_id == self.selected_work_id
            rarity = (
                lookup_model.rarities_by_work.get(work.work_id)
                if lookup_model
                else self.container.rarity_service.get(work.work_id)
            )
            if rarity is None:
                rarity = WorkRarity(work_id=work.work_id, local_user_id="")
            border_classes, border_style = self._rarity_border_for_rarity(rarity, style_settings)
            has_assigned_rarity = rarity.manual_rarity is not None or rarity.computed_rarity is not None
            is_collected = work.work_id in lookup_model.collected_ids if lookup_model else self.container.work_library_service.is_collected(work.work_id)
            is_queued = work.work_id in queued_work_ids
            card_id = self._work_card_dom_id(work.work_id)
            expanded_class = "work-card-expanded" if expanded else ""
            card_classes = f"work-card work-card-clickable relative w-full p-3 {expanded_class} {border_classes}".strip()
            card = ui.element("div").classes(card_classes).style(border_style)
            card.props(f"id={card_id}")
            card.on(
                "click",
                lambda event, w=work.work_id: self._handle_work_card_body_click(w, event),
                js_handler=self._work_card_click_js(),
            )
            with card:
                self._attach_rarity_context_menu(work.work_id, active.color)
                with ui.row().classes("work-card-actions items-center gap-0"):
                    has_left_action = False
                    if browse_actions and not is_collected:
                        collect = ui.button(icon="bookmark_add").props("round flat dense size=md").classes("work-action-button")
                        collect.style("color: #6b7280 !important;")
                        collect.on(
                            "click",
                            lambda _=None, w=work.work_id, b=collect: self._collect_work(w, b),
                            js_handler="(event) => { event.stopPropagation(); emit(); }",
                        )
                        with collect:
                            rich_tooltip("Add to Works", active.color)
                        has_left_action = True
                    elif is_collected:
                        if self.page == "Works":
                            armed_remove = self.work_remove_armed_id == work.work_id
                            kept_button = ui.button(icon="bookmark_remove" if armed_remove else "bookmark").props(
                                "round flat dense size=md"
                            ).classes("work-action-button")
                            kept_button.style(f"color: {'#ef4444' if armed_remove else normalized_label_color(active.color)} !important;")
                            self._work_remove_buttons[work.work_id] = kept_button
                            kept_button.on(
                                "click",
                                lambda _=None, w=work.work_id, b=kept_button: self._handle_work_remove_icon(w, b),
                                js_handler="(event) => { event.stopPropagation(); emit(); }",
                            )
                            with kept_button:
                                rich_tooltip("Click twice to remove from Works", "#ef4444" if armed_remove else active.color)
                        else:
                            kept = ui.icon("bookmark", size="22px").classes("px-2").style(f"color: {normalized_label_color(active.color)};")
                            with kept:
                                rich_tooltip("Already in Works", active.color)
                        has_left_action = True
                    if has_left_action:
                        ui.label("|").classes("action-separator")
                    queue = ui.button(icon="playlist_add").props("round flat dense size=md").classes("work-action-button")
                    queue.style(f"color: {normalized_label_color(active.color) if is_queued else '#6b7280'} !important;")
                    queue.on(
                        "click",
                        lambda _=None, w=work.work_id, b=queue: self._queue_work(w, b),
                        js_handler="(event) => { event.stopPropagation(); emit(); }",
                    )
                    with queue:
                        rich_tooltip("Already queued" if is_queued else "Queue for evaluation", active.color)
                    if browse_actions and not has_assigned_rarity:
                        ui.label("|").classes("action-separator")
                        armed = self.block_armed_work_id == work.work_id
                        block = ui.button(icon="visibility_off").props("round flat dense size=md").classes("work-action-button")
                        block.style(f"color: {'#ef4444' if armed else '#6b7280'} !important;")
                        self._block_buttons[work.work_id] = block
                        block.on(
                            "click",
                            lambda _=None, w=work.work_id, b=block: self._handle_block_icon(w, b),
                            js_handler="(event) => { event.stopPropagation(); emit(); }",
                        )
                        with block:
                            rich_tooltip("Click once to arm, click again to block this work ID", "#ef4444" if armed else "#94a3b8")
                with ui.column().classes("work-card-body gap-1 min-w-0"):
                    title_label = ui.label(work.title or f"Work {work.work_id}").classes("text-base font-bold work-title reader-title-link")
                    title_label.on("click.stop", lambda _=None, w=work.work_id: self._open_reader(w))
                    with title_label:
                        rich_tooltip("Read in AO3 Studio", active.color)
                    if lookup_model:
                        tags = lookup_model.tags_by_work.get(work.work_id, [])
                    else:
                        tags = self.container.work_library_service.tags_for_work(work.work_id)
                    self._render_work_meta_row(work, tags)
                    if work.summary_text:
                        ui.label(work.summary_text[:520]).classes("text-sm text-gray-400 work-summary")
                    if tags:
                        self._render_work_tags(
                            tags,
                            active,
                            favorite_lookup,
                            tag_color_lookup,
                            limit=28,
                            lightweight=browse_actions or lazy_panels,
                        )
                if (browse_actions or lazy_panels) and not expanded:
                    self._inline_work_panel_placeholder(work.work_id)
                else:
                    self._inline_work_panel(
                        work,
                        active,
                        schema=lookup_model.schema if lookup_model else None,
                        latest=(
                            lookup_model.latest_evaluations.get(work.work_id)
                            if lookup_model
                            else None
                        ),
                        latest_loaded=lookup_model is not None,
                        rarity=rarity,
                    )
        self._start_pubdate_enrichment(works)

    def _attach_rarity_context_menu(self, work_id: str, accent: str) -> None:
        with ui.context_menu().classes("tag-favorite-menu"):
            with ui.column().classes("gap-1 p-2 min-w-[190px]"):
                ui.label("Rarity").classes("text-xs font-bold uppercase text-gray-500")
                for tier in [RarityTier.COMMON, RarityTier.UNCOMMON, RarityTier.RARE, RarityTier.EPIC, RarityTier.LEGENDARY, RarityTier.BEST]:
                    label = RARITY_LABELS[tier]
                    color = RARITY_COLORS[tier]
                    item = ui.menu_item(label, on_click=lambda _=None, w=work_id, t=tier: self._set_manual_rarity(w, t))
                    item.style(f"color: {color};")
                ui.separator().classes("bg-gray-800")
                ui.menu_item("Clear manual rarity", on_click=lambda _=None, w=work_id: self._clear_manual_rarity(w)).style(
                    f"color: {normalized_label_color(accent)};"
                )

    def _set_manual_rarity(self, work_id: str, tier: RarityTier) -> None:
        self.container.rarity_service.set_manual(work_id, tier)
        self._invalidate_browse_page_model()
        self._notify(f"Marked {RARITY_LABELS[tier]}.", "positive")
        self.refresh()

    def _clear_manual_rarity(self, work_id: str) -> None:
        self.container.rarity_service.set_manual(work_id, None)
        self._invalidate_browse_page_model()
        self._notify("Manual rarity cleared.", "positive")
        self.refresh()

    def _favorite_tag_map(self, fandom_key_value: str) -> dict[tuple[TagType, str], str]:
        return {
            (favorite.tag_type, favorite.tag_text): favorite.color
            for favorite in self.container.work_library_service.favorite_tags_for_fandom(fandom_key_value)
        }

    def _tag_color_map(self, fandom_key_value: str) -> dict[tuple[TagType, str], str]:
        return {
            (tag_color.tag_type, tag_color.tag_text): tag_color.color
            for tag_color in self.container.work_library_service.tag_colors_for_fandom(fandom_key_value)
        }

    def _render_work_tags(
        self,
        tags: list[WorkTag],
        active: FandomProfile,
        favorites: dict[tuple[TagType, str], str],
        tag_colors: dict[tuple[TagType, str], str],
        *,
        limit: int = 28,
        lightweight: bool = False,
    ) -> None:
        remaining = max(0, limit)
        for tag_type in TAG_TYPE_ORDER:
            if tag_type in {TagType.CATEGORY, TagType.FANDOM}:
                continue
            group = [tag for tag in tags if tag.tag_type is tag_type]
            if tag_type is TagType.WARNING:
                group = [tag for tag in group if not self._is_no_archive_warning(tag.tag_text)]
            if not group or remaining <= 0:
                continue
            visible_group = group[:remaining]
            with ui.row().classes("gap-1 flex-wrap mt-1 items-center"):
                ui.label(tag_type.value.title()).classes("tag-type-label")
                for tag in visible_group:
                    if lightweight:
                        self._render_lightweight_tag_pill(tag, active, favorites, tag_colors)
                    else:
                        self._render_tag_pill(tag, active, favorites, tag_colors)
            remaining -= len(visible_group)

    @staticmethod
    def _is_no_archive_warning(tag_text: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(tag_text or "").strip()).casefold()
        return normalized in {"no archive warnings apply", "no archive warnings apply."}

    @staticmethod
    def _is_complete_work(work: Work) -> bool:
        current = work.chapters_current
        total_text = str(work.chapters_total_text or "").strip()
        if total_text and total_text != "?":
            try:
                total = int(total_text)
            except ValueError:
                return False
            return bool(total and current and current >= total)
        return False

    @staticmethod
    def _chapter_label(work: Work) -> str:
        current = work.chapters_current
        total = str(work.chapters_total_text or "").strip() or "?"
        if current or total != "?":
            return f"Ch: {current or '?'}{('/' + total) if total else '/?'}"
        return ""

    @staticmethod
    def _relationship_designation(tags: list[WorkTag]) -> str:
        values = [tag.tag_text for tag in tags if tag.tag_type is TagType.CATEGORY and tag.tag_text]
        preferred = ["F/F", "F/M", "M/F", "M/M", "Multi", "Gen", "Other"]
        ordered = [value for value in preferred if value in values]
        ordered.extend(value for value in values if value not in ordered)
        return ", ".join(ordered)

    @staticmethod
    def _display_ao3_date(value: str | None) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        cleaned = re.sub(r"\s+", " ", raw.replace(",", " ").strip())
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d %Y",
            "%B %d %Y",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(cleaned, fmt)
                return f"{parsed.day} {parsed.strftime('%b')} {parsed.year}"
            except ValueError:
                continue
        return cleaned

    def _work_meta_parts(self, work: Work, tags: list[WorkTag], *, reserve_pub_slot: bool = False) -> list[dict[str, Any]]:
        chapter = self._chapter_label(work)
        pub_display = self._display_ao3_date(work.published_at)
        up_display = self._display_ao3_date(work.last_ao3_updated_at)
        if pub_display and up_display == pub_display:
            up_display = ""
        needs_enrichment = self._needs_date_enrichment(work)
        parts: list[dict[str, Any]] = [
            {"kind": "author", "text": work.author_name or "Unknown author", "color": "#6b7280", "work_id": work.work_id},
            {"kind": "category", "text": self._relationship_designation(tags)},
            {"kind": "text", "text": f"{work.words:,} words" if work.words else "", "color": "#6b7280"},
            {"kind": "text", "text": chapter, "color": "#7ee787" if chapter and self._is_complete_work(work) else "#6b7280"},
            {
                "kind": "text",
                "text": f"Pub: {pub_display}" if pub_display else "Pub: ..." if reserve_pub_slot and up_display else "",
                "color": "#6b7280",
                "class": "work-meta-date work-meta-pubdate",
                "work_id": work.work_id,
            },
            {
                "kind": "text",
                "text": f"Up: {up_display}" if up_display else "Up: ..." if reserve_pub_slot and needs_enrichment and pub_display else "",
                "color": "#6b7280",
                "class": "work-meta-date work-meta-updatedate",
                "work_id": work.work_id,
            },
        ]
        return [part for part in parts if part.get("text")]

    def _work_meta_plain(self, work: Work, tags: list[WorkTag]) -> str:
        return " | ".join(str(part["text"]) for part in self._work_meta_parts(work, tags))

    def _render_work_meta_row(self, work: Work, tags: list[WorkTag]) -> None:
        parts = self._work_meta_parts(work, tags, reserve_pub_slot=True)
        with ui.row().classes("work-meta-line items-center gap-1 text-xs flex-wrap"):
            for index, part in enumerate(parts):
                if index:
                    ui.label("|").classes("action-separator")
                if part["kind"] == "category":
                    self._render_category_designation(str(part["text"]))
                elif part["kind"] == "author":
                    label = ui.label(str(part["text"])).classes("work-meta-segment cursor-context-menu").style(f"color: {part['color']};")
                    label.on("contextmenu", lambda _=None: None, js_handler="(event) => { event.stopPropagation(); emit(); }")
                    with label:
                        with ui.context_menu().classes("tag-favorite-menu"):
                            ui.menu_item(
                                "Block author",
                                on_click=lambda _=None, w=str(part["work_id"]): self._block_author_for_work(w),
                            ).style("color: #fb7185;")
                else:
                    classes = " ".join(["work-meta-segment", str(part.get("class") or "")]).strip()
                    label = ui.label(str(part["text"])).classes(classes).style(f"color: {part['color']};")
                    if part.get("class") and "work-meta-pubdate" in str(part["class"]):
                        self._pubdate_labels[str(part["work_id"])] = label
                    if part.get("class") and "work-meta-updatedate" in str(part["class"]):
                        self._updatedate_labels[str(part["work_id"])] = label

    def _render_category_designation(self, text: str) -> None:
        with ui.row().classes("category-designation items-center gap-0"):
            for token in re.split(r"(,\s*)", text):
                if not token:
                    continue
                compact = token.strip()
                if "/" in compact and all(part in {"F", "M"} for part in compact.split("/") if part):
                    for char in token:
                        if char == "F":
                            color = TAG_TYPE_COLORS[TagType.RELATIONSHIP]
                        elif char == "M":
                            color = TAG_TYPE_COLORS[TagType.FANDOM]
                        else:
                            color = "#6b7280"
                        ui.label(char).classes("category-designation-char").style(f"color: {color};")
                else:
                    ui.label(token).classes("category-designation-char").style("color: #6b7280;")

    @staticmethod
    def _chapter_display_title(title: str, chapter_index: int) -> str:
        text = re.sub(r"\s+", " ", str(title or "").strip())
        if not text:
            return f"Chapter {chapter_index}"
        patterns = [
            rf"^chapter\s*{chapter_index}\s*[:.\-\u2013\u2014]\s*(.+)$",
            rf"^{chapter_index}\s*[:.\-\u2013\u2014]\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if match and match.group(1).strip():
                return match.group(1).strip()
        return text

    def _chapter_select_label(self, title: str, chapter_index: int) -> str:
        display = self._chapter_display_title(title, chapter_index)
        if display.casefold() == f"chapter {chapter_index}".casefold():
            return display
        return f"Ch {chapter_index} - {display}"

    @staticmethod
    def _chapter_word_count_label(chapter_html: str) -> str:
        if not chapter_html:
            return "0 words"
        text = BeautifulSoup(chapter_html, "lxml").get_text(" ")
        count = len(re.findall(r"\b[\w'-]+\b", text))
        return f"{count:,} words"

    @staticmethod
    def _normalize_hex(value: str) -> str:
        clean = str(value or "").strip()
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", clean):
            return f"#{clean.lstrip('#').lower()}"
        if re.fullmatch(r"#?[0-9a-fA-F]{3}", clean):
            raw = clean.lstrip("#").lower()
            return "#" + "".join(char * 2 for char in raw)
        return ""

    @staticmethod
    def _tag_pill_style(hex_color: str, favored: bool) -> str:
        r, g, b = rgb_from_hex(hex_color)
        border_alpha = "0.72" if favored else "0.34"
        bg_alpha = "0.20" if favored else "0.10"
        return (
            f"background: rgba({r},{g},{b},{bg_alpha}) !important; "
            f"border: 1px solid rgba({r},{g},{b},{border_alpha}); "
            f"color: {normalized_label_color(hex_color)} !important;"
        )

    def _tag_colors_for_tag(
        self,
        tag: WorkTag,
        favorites: dict[tuple[TagType, str], str],
        tag_colors: dict[tuple[TagType, str], str],
    ) -> tuple[str | None, str | None, str]:
        favorite_color = favorites.get((tag.tag_type, tag.tag_text))
        override_color = tag_colors.get((tag.tag_type, tag.tag_text))
        color = override_color or favorite_color or TAG_TYPE_COLORS.get(tag.tag_type, TAG_TYPE_COLORS[TagType.OTHER])
        return favorite_color, override_color, color

    def _render_lightweight_tag_pill(
        self,
        tag: WorkTag,
        active: FandomProfile,
        favorites: dict[tuple[TagType, str], str],
        tag_colors: dict[tuple[TagType, str], str],
    ) -> None:
        favorite_color, override_color, color = self._tag_colors_for_tag(tag, favorites, tag_colors)
        pill = ui.element("button").props("type=button").classes("work-tag-pill browse-tag-pill text-[11px]")
        pill.style(self._tag_pill_style(color, bool(favorite_color)))
        pill.on(
            "click",
            lambda _=None, t=tag, fc=favorite_color, oc=override_color, c=color: self._open_tag_action_dialog(active, t, fc, oc, c),
            js_handler="(event) => { event.preventDefault(); event.stopPropagation(); emit(); }",
        )
        with pill:
            ui.label(tag.tag_text).classes("browse-tag-pill-label")

    def _render_tag_pill(
        self,
        tag: WorkTag,
        active: FandomProfile,
        favorites: dict[tuple[TagType, str], str],
        tag_colors: dict[tuple[TagType, str], str],
    ) -> None:
        favorite_color, override_color, color = self._tag_colors_for_tag(tag, favorites, tag_colors)
        pill = ui.button(tag.tag_text).props("flat dense rounded no-caps").classes("work-tag-pill text-[11px]")
        pill.style(self._tag_pill_style(color, bool(favorite_color)))
        pill.on("click.stop", lambda _=None: None)
        with pill:
            with ui.menu().props("auto-close=false").classes("tag-favorite-menu"):
                draft = {"color": override_color or color}
                saved = {"color": override_color or favorite_color or color, "dirty": False}
                block_state = {"armed": False, "button": None}

                def disarm_block_tag() -> None:
                    if not block_state["armed"]:
                        return
                    block_state["armed"] = False
                    self._style_work_action(block_state.get("button"), "#6b7280")

                def handle_block_tag() -> None:
                    if not block_state["armed"]:
                        block_state["armed"] = True
                        self._style_work_action(block_state.get("button"), "#ef4444")
                        return
                    result = self.container.work_library_service.block_tag(active.fandom_key, tag.tag_type, tag.tag_text)
                    self._invalidate_browse_page_model()
                    self._notify(result.message, "positive" if result.ok else "negative")
                    if result.ok and self.page == "Browse":
                        self._start_apply_fandom_filters(self._browse_filter_state())
                    else:
                        self.refresh()

                def auto_save_color(value: str) -> None:
                    clean = self._normalize_hex(value)
                    if not clean or clean == saved["color"]:
                        return
                    self.container.work_library_service.set_tag_color(active.fandom_key, tag.tag_type, tag.tag_text, clean)
                    self._invalidate_browse_page_model()
                    saved["color"] = clean
                    saved["dirty"] = True
                    draft["color"] = clean
                    try:
                        pill.style(replace=self._tag_pill_style(clean, True))
                        pill.update()
                    except RuntimeError:
                        return

                def finalize_color_picker() -> None:
                    auto_save_color(str(draft.get("color") or ""))
                    if saved["dirty"]:
                        saved["dirty"] = False
                        self.refresh()

                with ui.column().classes("gap-2 p-2 min-w-[220px]").on("click", lambda _=None: disarm_block_tag()):
                    with ui.row().classes("w-full items-start gap-2"):
                        ui.label(tag.tag_text).classes("text-sm font-bold flex-grow")
                        block_btn = ui.button(icon="block").props("flat round dense size=sm")
                        block_btn.style("color: #6b7280 !important;")
                        block_btn.on("click.stop", lambda _=None: handle_block_tag())
                        block_state["button"] = block_btn
                        with block_btn:
                            rich_tooltip("Block tag", "#ef4444")
                    ui.label(tag.tag_type.value.title()).classes("text-xs text-gray-500")
                    color_control = ui.color_input("Color", value=draft["color"], on_change=lambda e: auto_save_color(str(e.value or "")))
                    color_control.bind_value(draft, "color").props("dense dark outlined").classes("w-full")
                    color_control.picker.on("hide", lambda _=None: finalize_color_picker())
                    with ui.row().classes("w-full gap-2 justify-end"):
                        if favorite_color:
                            ui.button(
                                icon="star",
                                on_click=lambda _=None, t=tag: self._unfavorite_tag(active, t),
                            ).props("flat round dense").style("color: #ef4444 !important;")
                        ui.button(
                            "Favorite",
                            icon="star",
                            on_click=lambda _=None, t=tag, d=draft: self._favorite_tag(active, t, str(d["color"] or color)),
                        ).props("dense").style(f"background-color: {dark_button_color(color)} !important; color: white;")

    def _open_tag_action_dialog(
        self,
        active: FandomProfile,
        tag: WorkTag,
        favorite_color: str | None,
        override_color: str | None,
        color: str,
    ) -> None:
        dialog = ui.dialog()
        draft = {"color": override_color or color}
        saved = {"color": override_color or favorite_color or color, "dirty": False}
        block_state = {"armed": False, "button": None}

        def disarm_block_tag() -> None:
            if not block_state["armed"]:
                return
            block_state["armed"] = False
            self._style_work_action(block_state.get("button"), "#6b7280")

        def handle_block_tag() -> None:
            if not block_state["armed"]:
                block_state["armed"] = True
                self._style_work_action(block_state.get("button"), "#ef4444")
                return
            result = self.container.work_library_service.block_tag(active.fandom_key, tag.tag_type, tag.tag_text)
            self._invalidate_browse_page_model()
            self._notify(result.message, "positive" if result.ok else "negative")
            dialog.close()
            if result.ok and self.page == "Browse":
                self._start_apply_fandom_filters(self._browse_filter_state())
            else:
                self.refresh()

        def auto_save_color(value: str) -> None:
            clean = self._normalize_hex(value)
            if not clean or clean == saved["color"]:
                return
            result = self.container.work_library_service.set_tag_color(active.fandom_key, tag.tag_type, tag.tag_text, clean)
            if not result.ok:
                self._notify(result.message, "negative")
                return
            self._invalidate_browse_page_model()
            saved["color"] = clean
            saved["dirty"] = True
            draft["color"] = clean

        def finalize_dialog() -> None:
            if saved["dirty"]:
                saved["dirty"] = False
                self.refresh()

        dialog.on("hide", lambda _=None: (finalize_dialog(), dialog.delete()))
        with dialog, ui.card().classes("tag-favorite-menu p-2 gap-2 min-w-[240px]").on("click", lambda _=None: disarm_block_tag()):
            with ui.row().classes("w-full items-start gap-2"):
                ui.label(tag.tag_text).classes("text-sm font-bold flex-grow")
                block_btn = ui.button(icon="block").props("flat round dense size=sm")
                block_btn.style("color: #6b7280 !important;")
                block_btn.on("click.stop", lambda _=None: handle_block_tag())
                block_state["button"] = block_btn
                with block_btn:
                    rich_tooltip("Block tag", "#ef4444")
            ui.label(tag.tag_type.value.title()).classes("text-xs text-gray-500")
            color_control = ui.color_input("Color", value=draft["color"], on_change=lambda e: auto_save_color(str(e.value or "")))
            color_control.bind_value(draft, "color").props("dense dark outlined").classes("w-full")
            color_control.picker.on("hide", lambda _=None: auto_save_color(str(draft.get("color") or "")))
            with ui.row().classes("w-full gap-2 justify-end"):
                if favorite_color:
                    ui.button(
                        icon="star",
                        on_click=lambda _=None, t=tag: (dialog.close(), self._unfavorite_tag(active, t)),
                    ).props("flat round dense").style("color: #ef4444 !important;")
                ui.button(
                    "Favorite",
                    icon="star",
                    on_click=lambda _=None, t=tag, d=draft: (dialog.close(), self._favorite_tag(active, t, str(d["color"] or color))),
                ).props("dense").style(f"background-color: {dark_button_color(color)} !important; color: white;")
        dialog.open()

    def _favorite_tag(self, active: FandomProfile, tag: WorkTag, color: str) -> None:
        result = self.container.work_library_service.favorite_tag(active.fandom_key, tag.tag_type, tag.tag_text, color)
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _unfavorite_tag(self, active: FandomProfile, tag: WorkTag) -> None:
        result = self.container.work_library_service.unfavorite_tag(active.fandom_key, tag.tag_type, tag.tag_text)
        self._invalidate_browse_page_model()
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _inline_work_panel_placeholder(self, work_id: str) -> None:
        panel = ui.element("div").classes("inline-work-panel inline-work-panel-unhydrated w-full").props("aria-hidden=true inert")
        self._inline_work_panel_slots[work_id] = panel

    def _inline_work_panel_contents(
        self,
        work: Work,
        active: FandomProfile,
        *,
        schema: EvaluationSchema | None = None,
        latest: Evaluation | None = None,
        latest_loaded: bool = False,
        rarity: WorkRarity | None = None,
    ) -> None:
        schema = schema or self.container.schema_service.active_schema()
        if not latest_loaded:
            latest = self.container.evaluation_service.latest_for_work(work.work_id, schema.schema_key)
        score_state = {
            dimension.key: latest.scores.get(dimension.key, schema.score_range.minimum) if latest else schema.score_range.minimum
            for dimension in schema.dimensions
        }
        note_state = {"notes": latest.notes_markdown if latest and latest.notes_markdown else ""}
        r, g, b = rgb_from_hex(active.color)
        rarity = rarity or self.container.rarity_service.get(work.work_id)
        note_color = (
            RARITY_COLORS.get(rarity.effective_rarity, active.color)
            if rarity.manual_rarity is not None or rarity.computed_rarity is not None
            else active.color
        )
        nr, ng, nb = rgb_from_hex(note_color)
        with ui.element("div").classes("inline-work-panel-inner"):
            with ui.element("div").classes("w-full mt-2 pt-1"):
                with ui.row().classes("w-full items-center justify-between gap-2"):
                    with ui.row().classes("items-center gap-2 min-w-0"):
                        ui.icon("psychology", size="20px").style(f"color: {normalized_label_color(active.color)};")
                        ui.label(schema.name).classes("text-sm font-bold truncate").style(glow_text(active.color, 3))
                        if latest:
                            ui.label(f"last saved {latest.updated_at}").classes("text-[11px] text-gray-500")
                    with ui.row().classes("items-center gap-1"):
                        lm = ui.button(icon="auto_awesome", on_click=lambda _=None, w=work, s=schema: self._lmstudio_eval(w, s)).props(
                            "round flat dense"
                        )
                        lm.style(f"color: {normalized_label_color(active.color)} !important;")
                        with lm:
                            rich_tooltip("Evaluate with LM Studio", active.color)
                        save = ui.button(
                            icon="save",
                            on_click=lambda _=None: self._save_manual_eval(work, schema, score_state, note_state),
                        ).props("round flat dense")
                        save.style(f"color: {normalized_label_color(active.color)} !important;")
                        with save:
                            rich_tooltip("Save manual evaluation", active.color)
                        refresh = ui.button(icon="refresh", on_click=lambda _=None, w=work: self._refresh_work(w)).props("round flat dense")
                        refresh.style(f"color: {normalized_label_color(active.color)} !important;")
                        with refresh:
                            rich_tooltip("Refresh this work", active.color)
                with ui.row().classes("w-full gap-2 flex-wrap mt-2"):
                    for dimension in schema.dimensions:
                        with ui.element("div").classes("score-pill px-2 py-2").style(
                            f"border: 1px solid rgba({r},{g},{b},0.24); background: rgba({r},{g},{b},0.075);"
                        ):
                            ui.number(
                                dimension.label,
                                value=score_state[dimension.key],
                                min=schema.score_range.minimum,
                                max=schema.score_range.maximum,
                                step=schema.score_range.step,
                            ).bind_value(score_state, dimension.key).props("outlined dense dark hide-bottom-space").classes("w-36")
                ui.textarea("Notes and evidence", value=note_state["notes"]).bind_value(note_state, "notes").props(
                    "borderless dense dark autogrow"
                ).classes("w-full mt-2 evaluation-notes-field").style(f"--note-r:{nr}; --note-g:{ng}; --note-b:{nb};")
                evaluations = self.container.evaluation_service.list_for_work(work.work_id)
                if evaluations:
                    with ui.row().classes("w-full gap-1 flex-wrap mt-2"):
                        for evaluation in evaluations[:5]:
                            ui.label(_score_summary(evaluation.scores)).classes("text-[11px] px-2 py-1 rounded-full").style(
                                f"background: rgba({r},{g},{b},0.10); border: 1px solid rgba({r},{g},{b},0.20);"
                            )

    def _inline_work_panel(
        self,
        work: Work,
        active: FandomProfile,
        *,
        schema: EvaluationSchema | None = None,
        latest: Evaluation | None = None,
        latest_loaded: bool = False,
        rarity: WorkRarity | None = None,
    ) -> None:
        with ui.element("div").classes("inline-work-panel w-full").on("click.stop", lambda _=None: None) as panel:
            self._inline_work_panel_slots[work.work_id] = panel
            self._inline_work_panel_contents(
                work,
                active,
                schema=schema,
                latest=latest,
                latest_loaded=latest_loaded,
                rarity=rarity,
            )

    def _page_schemas(self) -> None:
        self._page_title("Schemas", "Mutable local schemas, locked shared-compatible schemas, and evaluator prompts.")
        schemas = self.container.schema_service.list_schemas()
        active = self.container.schema_service.active_schema()
        for schema in schemas:
            with ui.element("div").classes("soft-panel w-full p-3"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.column().classes("gap-0"):
                        ui.label(f"{schema.name} v{schema.version}").classes("text-base font-bold")
                        ui.label(schema.description).classes("text-xs text-gray-500")
                    ui.label("ACTIVE" if schema.schema_key == active.schema_key else "local").classes("text-[11px] text-gray-400")
                ui.label(f"Dimensions: {', '.join(d.label for d in schema.dimensions)}").classes("text-xs text-gray-400 mt-2")
        self._schema_editor(active)

    def _schema_editor(self, source: EvaluationSchema) -> None:
        state = {
            "schema_key": source.schema_key if not source.is_official_shared_compatible else f"{source.schema_key}_copy",
            "name": source.name,
            "version": source.version,
            "description": source.description,
            "prompt_template": source.prompt_template,
            "parameters": [asdict(dimension) for dimension in source.dimensions],
            "groups": [
                dict(group)
                for group in source.aggregation_rules.get("parameter_groups", [])
                if isinstance(group, dict)
            ],
            "active": source.is_active,
            "shared": source.is_official_shared_compatible,
        }

        def render_parameters(container) -> None:
            container.clear()
            with container:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Individual Parameters").classes("text-sm font-bold text-gray-300")
                    add = ui.button(icon="add").props("flat round dense color=cyan")
                    add.on("click.stop", lambda _=None: add_parameter())
                    with add:
                        rich_tooltip("Add evaluation parameter")
                if not state["parameters"]:
                    ui.label("No parameters yet. Add at least one 1-10 criterion.").classes("text-xs text-gray-500")
                for index, parameter in enumerate(state["parameters"]):
                    with ui.element("div").classes("soft-panel w-full p-2"):
                        with ui.row().classes("w-full items-start gap-2"):
                            ui.icon("drag_indicator", size="20px").classes("text-gray-500 mt-2")
                            with ui.column().classes("flex-grow min-w-0 gap-2"):
                                with ui.row().classes("w-full gap-2"):
                                    ui.input("Label", value=parameter.get("label", "")).bind_value(parameter, "label").props(
                                        "dark dense outlined"
                                    ).classes("flex-grow")
                                    ui.input("Key", value=parameter.get("key", "")).bind_value(parameter, "key").props(
                                        "dark dense outlined"
                                    ).classes("w-44")
                                ui.input("Description", value=parameter.get("description", "")).bind_value(parameter, "description").props(
                                    "dark dense outlined"
                                ).classes("w-full")
                                with ui.row().classes("items-center gap-3"):
                                    ui.toggle(
                                        {"positive": "Positive", "negative": "Negative"},
                                        value=str(_score_polarity(parameter.get("polarity")).value),
                                        on_change=lambda event, p=parameter: p.update({"polarity": str(event.value)}),
                                    ).props('dark rounded toggle-color="transparent"')
                                    ui.toggle(
                                        IMPACT_OPTIONS,
                                        value=_impact_value(parameter.get("weight")),
                                        on_change=lambda event, p=parameter: p.update({"weight": float(event.value)}),
                                    ).props('dark rounded toggle-color="transparent"')
                            delete = ui.button(icon="delete").props("flat round dense")
                            delete.style("color: #ef4444 !important;")
                            delete.on("click.stop", lambda _=None, i=index: delete_parameter(i))

        def render_groups(container) -> None:
            container.clear()
            with container:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Parameter Groups").classes("text-sm font-bold text-gray-300")
                    add = ui.button(icon="add").props("flat round dense color=cyan")
                    add.on("click.stop", lambda _=None: add_group())
                    with add:
                        rich_tooltip("Add parameter group")
                if not state["groups"]:
                    ui.label("Groups are optional. They organize the LM Studio prompt and analytics rollups.").classes("text-xs text-gray-500")
                parameter_keys = [str(item.get("key") or _slug(str(item.get("label") or ""))) for item in state["parameters"]]
                for index, group in enumerate(state["groups"]):
                    members = group.setdefault("parameter_keys", [])
                    with ui.element("div").classes("soft-panel w-full p-2"):
                        with ui.row().classes("w-full items-start gap-2"):
                            ui.icon("folder_special", size="20px").style("color: #facc15;")
                            with ui.column().classes("flex-grow min-w-0 gap-2"):
                                ui.input("Group name", value=group.get("name", "")).bind_value(group, "name").props(
                                    "dark dense outlined"
                                ).classes("w-full")
                                ui.input("Prompt guidance", value=group.get("description", "")).bind_value(group, "description").props(
                                    "dark dense outlined"
                                ).classes("w-full")
                                with ui.row().classes("w-full gap-1 flex-wrap"):
                                    for parameter in state["parameters"]:
                                        key = str(parameter.get("key") or _slug(str(parameter.get("label") or "")))
                                        label = str(parameter.get("label") or key)
                                        selected = key in members
                                        pill = ui.button(label, on_click=lambda _=None, g=group, k=key: toggle_group_member(g, k)).props(
                                            "dense rounded"
                                        )
                                        pill.style(self._filter_pill_style("#facc15", selected))
                                missing = [key for key in members if key not in parameter_keys]
                                if missing:
                                    ui.label(f"Missing parameters: {', '.join(missing)}").classes("text-[11px] text-red-300")
                            delete = ui.button(icon="delete").props("flat round dense")
                            delete.style("color: #ef4444 !important;")
                            delete.on("click.stop", lambda _=None, i=index: delete_group(i))

        def add_parameter() -> None:
            label = f"Criterion {len(state['parameters']) + 1}"
            state["parameters"].append({"key": _slug(label), "label": label, "description": "", "weight": 1.0, "polarity": "positive"})
            render_parameters(parameters_container)
            render_groups(groups_container)

        def delete_parameter(index: int) -> None:
            if 0 <= index < len(state["parameters"]):
                removed = str(state["parameters"][index].get("key") or "")
                del state["parameters"][index]
                for group in state["groups"]:
                    group["parameter_keys"] = [key for key in group.get("parameter_keys", []) if key != removed]
            render_parameters(parameters_container)
            render_groups(groups_container)

        def add_group() -> None:
            state["groups"].append({"name": f"Group {len(state['groups']) + 1}", "description": "", "parameter_keys": []})
            render_groups(groups_container)

        def delete_group(index: int) -> None:
            if 0 <= index < len(state["groups"]):
                del state["groups"][index]
            render_groups(groups_container)

        def toggle_group_member(group: dict[str, Any], key: str) -> None:
            members = list(group.get("parameter_keys", []))
            if key in members:
                members.remove(key)
            else:
                members.append(key)
            group["parameter_keys"] = members
            render_groups(groups_container)

        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("Evaluation Schema Builder").classes("text-lg font-bold")
            with ui.row().classes("w-full gap-2"):
                ui.input("Schema key", value=state["schema_key"]).bind_value(state, "schema_key").props("outlined dense dark").classes("flex-grow")
                ui.input("Version", value=state["version"]).bind_value(state, "version").props("outlined dense dark").classes("w-36")
            ui.input("Name", value=state["name"]).bind_value(state, "name").props("outlined dense dark").classes("w-full")
            ui.textarea("Description", value=state["description"]).bind_value(state, "description").props(
                "outlined dense dark autogrow"
            ).classes("w-full")
            ui.textarea("Evaluator/System Prompt", value=state["prompt_template"]).bind_value(state, "prompt_template").props(
                "outlined dense dark autogrow"
            ).classes("w-full")
            parameters_container = ui.column().classes("w-full gap-2")
            groups_container = ui.column().classes("w-full gap-2")
            with ui.row().classes("items-center gap-3"):
                ui.checkbox("Set active", value=state["active"]).bind_value(state, "active")
                ui.checkbox("Official shared-compatible locked schema", value=state["shared"]).bind_value(state, "shared")
                ui.button("Save Schema", icon="save", on_click=lambda: self._save_schema(state)).style(
                    f"background-color: {dark_button_color('#58a6ff')} !important; color: white;"
                )
        render_parameters(parameters_container)
        render_groups(groups_container)

    def _save_schema(self, state: dict[str, Any]) -> None:
        try:
            dimensions = []
            for row in state.get("parameters", []):
                label = str(row.get("label") or "").strip()
                key = str(row.get("key") or _slug(label)).strip()
                if not label or not key:
                    continue
                dimensions.append(
                    ScoreDimension(
                        key=_slug(key),
                        label=label,
                        description=str(row.get("description") or ""),
                        weight=float(row.get("weight") or 1.0),
                        polarity=_score_polarity(row.get("polarity")),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self._notify(f"Schema parameters are invalid: {exc}", "negative")
            return
        if not dimensions:
            self._notify("Add at least one evaluation parameter.", "warning")
            return
        schema = EvaluationSchema(
            schema_key=_slug(str(state["schema_key"]).strip() or str(state["name"])),
            name=str(state["name"]).strip(),
            version=str(state["version"]).strip(),
            label=str(state["name"]).strip(),
            description=str(state["description"]).strip(),
            dimensions=dimensions,
            score_range=ScoreRange(1, 10, 1),
            prompt_template=str(state["prompt_template"]),
            aggregation_rules={"parameter_groups": list(state.get("groups", []))},
            shared_compatibility={"official": bool(state["shared"])},
            is_active=bool(state["active"]),
            is_official_shared_compatible=bool(state["shared"]),
        )
        result = self.container.schema_service.save_schema(schema)
        self._notify(result.message, "positive" if result.ok else "negative")
        self.refresh()

    def _page_analytics(self) -> None:
        self._page_title("Local Analytics", "Local-only counts and personal evaluation coverage.")
        with ui.row().classes("w-full gap-3 flex-wrap"):
            self._metric("Works cached", self.container.work_library_service.count(), "#58a6ff")
            self._metric("Evaluations", self.container.evaluation_service.count(), "#7ee787")
            self._metric("Queued", len(self.container.queue_service.list(QueueStatus.QUEUED)), "#facc15")
            self._metric("Schemas", len(self.container.schema_service.list_schemas()), "#f778ba")

    def _metric(self, label: str, value: Any, color: str) -> None:
        with ui.element("div").classes("soft-panel p-4 w-48"):
            ui.label(str(value)).classes("text-3xl font-bold").style(f"color: {color};")
            ui.label(label).classes("text-xs text-gray-500")

    def _page_shared(self) -> None:
        self._page_title("Shared Overlay", "Stubbed remote overlay that never replaces local truth.")
        if not self.container.mode_service.shared_widgets_visible():
            self._empty("groups", "Enable Shared Mode to view overlays")
            return
        if self.selected_work_id:
            ui.button("Fetch overlay for selected work", icon="cloud_download", on_click=self._fetch_overlay).props("color=primary")
        overlays = self.container.shared_overlay_service.list_recent()
        if not overlays:
            self._empty("groups", "No shared overlays cached")
            return
        for overlay in overlays:
            with ui.element("div").classes("soft-panel w-full p-3"):
                ui.label(f"Work {overlay.work_id} | {overlay.remote_schema_version}").classes("text-sm font-bold")
                ui.label(f"{overlay.evaluation_count or 0} remote evaluations").classes("text-xs text-gray-500")

    def _fetch_overlay(self) -> None:
        result = self.container.sync_service.fetch_overlay(self.selected_work_id)
        self._notify(result.message, "positive" if result.ok else "warning")
        self.refresh()

    def _schema_studio_state(self) -> dict[str, Any]:
        stored = self.container.preferences_service.get("schema_studio_state", {})
        if isinstance(stored, dict) and stored.get("parameters") and stored.get("groups") and stored.get("schemas"):
            for parameter in stored.get("parameters", []):
                parameter["polarity"] = str(_score_polarity(parameter.get("polarity")).value)
                parameter["weight"] = float(parameter.get("weight") or 1.0)
                parameter.pop("required", None)
            for schema in stored.get("schemas", []):
                schema["color"] = self._normalize_hex(str(schema.get("color") or "")) if schema.get("color") else ""
            return stored

        schemas = self.container.schema_service.list_schemas()
        active = self.container.schema_service.active_schema()
        parameters: list[dict[str, Any]] = []
        seen_parameters: set[str] = set()
        for schema in schemas or [active]:
            for dimension in schema.dimensions:
                parameter_id = _slug(dimension.key or dimension.label)
                if parameter_id in seen_parameters:
                    continue
                seen_parameters.add(parameter_id)
                parameters.append(
                    {
                        "id": parameter_id,
                        "name": dimension.label,
                        "description": dimension.description,
                        "weight": dimension.weight,
                        "polarity": str(_score_polarity(getattr(dimension, "polarity", ScorePolarity.POSITIVE)).value),
                    }
                )
        if not parameters:
            parameters = [
                {"id": "story_fit", "name": "Story Fit", "description": "How well the work matches your tastes.", "weight": 1.0, "polarity": "positive"},
                {"id": "craft", "name": "Craft", "description": "Prose, pacing, structure, and clarity.", "weight": 1.0, "polarity": "positive"},
                {"id": "emotional_pull", "name": "Emotional Pull", "description": "How strongly it makes you want to continue.", "weight": 1.0, "polarity": "positive"},
            ]

        groups: list[dict[str, Any]] = []
        seen_groups: set[str] = set()
        for schema in schemas or [active]:
            for index, group in enumerate(schema.aggregation_rules.get("parameter_groups", []) or []):
                if not isinstance(group, dict):
                    continue
                group_id = str(group.get("id") or _slug(str(group.get("name") or f"group_{index + 1}")))
                if group_id in seen_groups:
                    continue
                parameter_ids = list(group.get("parameter_ids") or group.get("parameter_keys") or [])
                groups.append(
                    {
                        "id": group_id,
                        "name": str(group.get("name") or f"Group {len(groups) + 1}"),
                        "description": str(group.get("description") or ""),
                        "parameter_ids": [_slug(str(item)) for item in parameter_ids],
                    }
                )
                seen_groups.add(group_id)
        if not groups:
            groups = [
                {
                    "id": "general",
                    "name": "General",
                    "description": "Default scoring group.",
                    "parameter_ids": [str(item["id"]) for item in parameters],
                }
            ]

        schema_rows: list[dict[str, Any]] = []
        all_group_ids = [str(group["id"]) for group in groups]
        for schema in schemas or [active]:
            configured_groups = schema.aggregation_rules.get("schema_group_ids")
            ui_rules = schema.aggregation_rules.get("_ui") if isinstance(schema.aggregation_rules, dict) else {}
            schema_rows.append(
                {
                    "id": schema.schema_key or _slug(schema.name),
                    "name": schema.name,
                    "description": schema.description,
                    "prompt": schema.prompt_template,
                    "group_ids": list(configured_groups) if isinstance(configured_groups, list) else all_group_ids,
                    "active": schema.is_active,
                    "version": schema.version,
                    "shared": schema.is_official_shared_compatible,
                    "color": self._normalize_hex(str(ui_rules.get("color") or "")) if isinstance(ui_rules, dict) else "",
                }
            )
        if not schema_rows:
            schema_rows = [
                {
                    "id": "local_default_v1",
                    "name": "Local Default",
                    "description": "A starter 1-10 evaluator for story fit and quality.",
                    "prompt": "Evaluate this AO3 work for a private reading database. Score each dimension from 1 to 10.",
                    "group_ids": all_group_ids,
                    "active": True,
                    "version": "1.0.0",
                    "shared": False,
                    "color": "",
                }
            ]
        if not any(schema.get("active") for schema in schema_rows):
            schema_rows[0]["active"] = True

        state = {"mode": "parameters", "parameters": parameters, "groups": groups, "schemas": schema_rows}
        self.container.preferences_service.set("schema_studio_state", state)
        return state

    def _save_schema_studio_state(self, state: dict[str, Any]) -> ServiceResult:
        parameters = {str(item.get("id")): item for item in state.get("parameters", [])}
        groups = {str(item.get("id")): item for item in state.get("groups", [])}
        schemas = list(state.get("schemas", []))
        if schemas and not any(schema.get("active") for schema in schemas):
            schemas[0]["active"] = True
        for schema_row in schemas:
            selected_group_ids = [str(item) for item in schema_row.get("group_ids", [])]
            selected_groups = [groups[group_id] for group_id in selected_group_ids if group_id in groups]
            if not selected_groups:
                selected_groups = list(groups.values())
            parameter_ids: list[str] = []
            for group in selected_groups:
                for parameter_id in group.get("parameter_ids", []):
                    parameter_id = str(parameter_id)
                    if parameter_id in parameters and parameter_id not in parameter_ids:
                        parameter_ids.append(parameter_id)
            if not parameter_ids:
                parameter_ids = list(parameters)
            dimensions = [
                ScoreDimension(
                    key=_slug(str(parameter.get("id") or parameter.get("name"))),
                    label=str(parameter.get("name") or "Untitled Parameter").strip(),
                    description=str(parameter.get("description") or ""),
                    weight=float(parameter.get("weight") or 1.0),
                    polarity=_score_polarity(parameter.get("polarity")),
                )
                for parameter_id in parameter_ids
                if (parameter := parameters.get(parameter_id))
            ]
            if not dimensions:
                continue
            raw_color = str(schema_row.get("color") or "").strip()
            clean_color = self._normalize_hex(raw_color)
            if raw_color and not clean_color:
                return ServiceResult(False, f"{schema_row.get('name') or 'Schema'} color must be a hex color.")
            aggregation_rules = {
                "schema_group_ids": selected_group_ids,
                "parameter_groups": [
                    {
                        "id": str(group.get("id")),
                        "name": str(group.get("name") or "Untitled Group"),
                        "description": str(group.get("description") or ""),
                        "parameter_ids": [str(item) for item in group.get("parameter_ids", [])],
                        "parameter_keys": [_slug(str(item)) for item in group.get("parameter_ids", [])],
                    }
                    for group in selected_groups
                ],
            }
            if clean_color:
                aggregation_rules["_ui"] = {"color": clean_color}
                schema_row["color"] = clean_color
            schema = EvaluationSchema(
                schema_key=_slug(str(schema_row.get("id") or schema_row.get("name") or "local_schema")),
                name=str(schema_row.get("name") or "Untitled Schema").strip(),
                version=str(schema_row.get("version") or "1.0.0"),
                label=str(schema_row.get("name") or "Untitled Schema").strip(),
                description=str(schema_row.get("description") or ""),
                dimensions=dimensions,
                score_range=ScoreRange(1, 10, 1),
                prompt_template=str(schema_row.get("prompt") or ""),
                aggregation_rules=aggregation_rules,
                shared_compatibility={"official": bool(schema_row.get("shared"))},
                is_active=bool(schema_row.get("active")),
                is_official_shared_compatible=bool(schema_row.get("shared")),
                created_at=utc_now_iso(),
            )
            result = self.container.schema_service.save_schema(schema)
            if not result.ok:
                return result
        self.container.preferences_service.set("schema_studio_state", state)
        return ServiceResult(True, "Evaluation schema studio saved.")

    def _show_schema_studio_dialog(self) -> None:
        state = self._schema_studio_state()
        amber = "#d6b274"
        teal = "#5eead4"
        violet = "#c4b5fd"
        r, g, b = rgb_from_hex(amber)
        mode = {"value": str(state.get("mode") or "parameters")}
        search = {"text": ""}
        expanded_parameters: set[str] = set()
        expanded_groups: set[str] = set()
        expanded_schemas: set[str] = set()
        expanded_group_parameters: set[str] = set()
        expanded_schema_groups: set[str] = set()
        group_member_search: dict[str, str] = {}
        schema_group_search: dict[str, str] = {}
        purge_state: dict[str, Any] = {
            "mode": False,
            "armed": False,
            "parameters": set(),
            "groups": set(),
            "schemas": set(),
        }
        purge_refs: dict[str, Any] = {"trash": None, "clean": None}
        activation_state: dict[str, bool] = {"mode": False}
        activation_refs: dict[str, Any] = {"button": None}

        def save_state() -> None:
            state["mode"] = mode["value"]
            self.container.preferences_service.set("schema_studio_state", state)

        def make_id(prefix: str) -> str:
            existing = {
                str(item.get("id"))
                for item in [*state.get("parameters", []), *state.get("groups", []), *state.get("schemas", [])]
            }
            stamp = int(time.time() * 1000)
            index = 0
            while True:
                candidate = f"{prefix}_{stamp + index}"
                if candidate not in existing:
                    return candidate
                index += 1

        def pill_style(color: str, selected: bool = False) -> str:
            if selected and purge_state.get("mode"):
                return (
                    "background: rgba(239,68,68,0.40); "
                    "border: 1px solid rgba(239,68,68,0.82); "
                    "padding: 4px 12px; transition: all 0.16s ease;"
                )
            pr, pg, pb = rgb_from_hex(color)
            return (
                f"background: rgba({pr},{pg},{pb},{0.24 if selected else 0.15}); "
                f"border: 1px solid rgba({pr},{pg},{pb},{0.58 if selected else 0.35}); "
                "padding: 4px 12px; transition: all 0.16s ease;"
            )

        def pill_text_style(color: str) -> str:
            return (
                f"color: {color}; white-space: normal; overflow-wrap: anywhere; "
                "text-shadow: 0 0 1px rgba(0,0,0,1), 0 1px 2px rgba(0,0,0,0.9), 0 0 5px rgba(0,0,0,0.7);"
            )

        def filtered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            query = search["text"].strip().lower()
            if not query:
                return items
            return [
                item
                for item in items
                if query in str(item.get("name") or "").lower()
                or query in str(item.get("description") or "").lower()
                or query in str(item.get("prompt") or "").lower()
            ]

        def parameter_lookup() -> dict[str, dict[str, Any]]:
            return {str(item.get("id")): item for item in state.get("parameters", [])}

        def group_lookup() -> dict[str, dict[str, Any]]:
            return {str(item.get("id")): item for item in state.get("groups", [])}

        def parameter_display_color(parameter: dict[str, Any]) -> str:
            return "#fca5a5" if _score_polarity(parameter.get("polarity")) is ScorePolarity.NEGATIVE else amber

        def set_parameter_polarity(parameter: dict[str, Any], value: str) -> None:
            parameter["polarity"] = str(_score_polarity(value).value)
            render_active()

        def set_parameter_weight(parameter: dict[str, Any], value: str) -> None:
            parameter["weight"] = float(_impact_value(value))
            render_active()

        def parameter_tooltip(parameter: dict[str, Any]) -> str:
            polarity = _score_polarity(parameter.get("polarity"))
            framing = "Negative: high raw scores hurt quality." if polarity is ScorePolarity.NEGATIVE else "Positive: high raw scores help quality."
            return f"{framing} Impact: {_impact_label(parameter.get('weight'))}. {parameter.get('description') or ''}".strip()

        def schema_display_color(schema: dict[str, Any]) -> str:
            return self._normalize_hex(str(schema.get("color") or "")) or violet

        def active_schema_ids() -> set[str]:
            active = {str(item.get("id")) for item in state.get("schemas", []) if item.get("active")}
            if not active and state.get("schemas"):
                active.add(str(state["schemas"][0].get("id")))
                state["schemas"][0]["active"] = True
            return active

        def active_purge_key() -> str:
            return mode["value"] if mode["value"] in {"parameters", "groups", "schemas"} else "parameters"

        def active_purge_selection() -> set[str]:
            return purge_state[active_purge_key()]

        def update_purge_controls() -> None:
            trash_btn = purge_refs.get("trash")
            clean_btn = purge_refs.get("clean")
            if clean_btn is not None:
                clean_btn.style(
                    "color: #ffffff !important;" if purge_state["mode"] else "color: #6b7280 !important; opacity: 0.86;"
                )
            if trash_btn is None:
                return
            if purge_state["mode"]:
                trash_btn.classes(remove="opacity-0 pointer-events-none")
            else:
                trash_btn.classes(add="opacity-0 pointer-events-none")
            trash_btn.style("color: #ef4444 !important;" if purge_state["armed"] else "color: #6b7280 !important;")

        def update_activation_controls() -> None:
            button = activation_refs.get("button")
            if button is None:
                return
            if mode["value"] == "schemas":
                button.classes(remove="opacity-0 pointer-events-none")
            else:
                button.classes(add="opacity-0 pointer-events-none")
                activation_state["mode"] = False
            button.style(
                f"color: {'#facc15' if activation_state['mode'] else violet} !important; "
                "background: transparent !important;"
            )

        def disarm_purge() -> None:
            if purge_state["armed"]:
                purge_state["armed"] = False
                update_purge_controls()

        def toggle_purge_mode() -> None:
            purge_state["mode"] = not purge_state["mode"]
            purge_state["armed"] = False
            if purge_state["mode"]:
                activation_state["mode"] = False
            for bucket in ("parameters", "groups", "schemas"):
                purge_state[bucket].clear()
            update_purge_controls()
            update_activation_controls()
            render_active()

        def toggle_activation_mode() -> None:
            activation_state["mode"] = not activation_state["mode"]
            if activation_state["mode"]:
                purge_state["mode"] = False
                purge_state["armed"] = False
                for bucket in ("parameters", "groups", "schemas"):
                    purge_state[bucket].clear()
            update_purge_controls()
            update_activation_controls()
            render_active()

        def toggle_purge_selection(item_id: str) -> None:
            disarm_purge()
            selected = active_purge_selection()
            if item_id in selected:
                selected.remove(item_id)
            else:
                selected.add(item_id)
            render_active()

        def handle_item_click(bucket: set[str], item_id: str) -> None:
            if mode["value"] == "schemas" and activation_state["mode"]:
                set_active_schema(item_id)
                return
            if purge_state["mode"]:
                toggle_purge_selection(item_id)
                return
            disarm_purge()
            toggle_expanded(bucket, item_id)

        with self.root:
            dialog = ui.dialog()
            dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("schema-studio-dialog w-[900px] h-[85vh] flex flex-col p-0 gap-0 overflow-hidden").style(
            f"background: linear-gradient(160deg, rgba({r},{g},{b},0.18) 0%, rgba({r},{g},{b},0.10) 50%, rgba({r},{g},{b},0.04) 100%), #0d1117 !important;"
            f"border: 1px solid rgba({r},{g},{b},0.20);"
        ) as card:
            with ui.row().classes("w-full items-center justify-between p-4 border-b border-gray-700 shrink-0").style(
                "background: rgba(22, 27, 34, 0.75); backdrop-filter: blur(8px);"
            ):
                with ui.row().classes("items-center gap-2 min-w-0"):
                    ui.icon("local_fire_department", size="sm").style(
                        f"color: {amber}; text-shadow: 0 0 4px rgba(0,0,0,0.7), 0 0 6px {amber};"
                    )
                    ui.label("Evaluation Schema Studio").classes("text-lg font-bold").style(
                        f"color: {amber}; text-shadow: 0 0 4px rgba(0,0,0,0.7), 0 0 6px {amber};"
                    )
                    maximized = {"value": False}

                    def toggle_maximize() -> None:
                        maximized["value"] = not maximized["value"]
                        if maximized["value"]:
                            maximize_btn.props("icon=fullscreen_exit")
                            card.classes(
                                "w-[100vw] h-[100vh] max-w-[100vw] max-h-[100vh] !rounded-none",
                                remove="w-[900px] h-[85vh]",
                            )
                            dialog.props("maximized")
                            ui.run_javascript(
                                "if (!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(() => {}); }"
                            )
                        else:
                            maximize_btn.props("icon=fullscreen")
                            card.classes("w-[900px] h-[85vh]", remove="w-[100vw] h-[100vh] max-w-[100vw] max-h-[100vh] !rounded-none")
                            dialog.props(remove="maximized")
                            ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")

                    maximize_btn = ui.button(icon="fullscreen", on_click=toggle_maximize).props("flat round dense size=sm").style(
                        f"color: {amber}; opacity: 0.78;"
                    )
                    with maximize_btn:
                        rich_tooltip("Toggle fullscreen", amber)

                with ui.row().classes("items-center gap-1"):
                    def close_dialog() -> None:
                        ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")
                        dialog.close()

                    ui.button(icon="close", on_click=close_dialog).props("flat round dense color=white")

            ui.add_css(
                f"""
                .schema-tab-toggle .q-btn {{
                    background-image: none !important;
                    border: 1px solid transparent;
                    transition: all 0.2s ease;
                }}
                .schema-tab-toggle .q-btn[aria-pressed="false"] {{
                    opacity: 0.58;
                }}
                .schema-tab-toggle .q-btn[aria-pressed="true"] {{
                    background-color: rgba({r},{g},{b},0.25) !important;
                    border: 1px solid rgba({r},{g},{b},0.50) !important;
                    opacity: 1;
                }}
                .schema-tab-toggle .q-btn .q-btn__content,
                .schema-tab-toggle .q-btn span {{
                    color: {amber} !important;
                    text-shadow: 0 0 1px rgba(0,0,0,1), 0 1px 2px rgba(0,0,0,0.9), 0 0 6px {amber};
                }}
                """
            )

            with ui.column().classes("w-full px-4 pt-3 pb-1 gap-2 shrink-0"):
                with ui.row().classes("w-full items-center relative h-8"):
                    with ui.row().classes("absolute left-0 items-center gap-2 z-10"):
                        activation_refs["button"] = ui.button(icon="radio_button_checked").props("flat dense round size=sm").style(
                            f"color: {violet} !important; background: transparent !important;"
                        ).classes("transition-opacity duration-200 opacity-0 pointer-events-none")
                        activation_refs["button"].on("click.stop", lambda _=None: toggle_activation_mode())
                        with activation_refs["button"]:
                            rich_tooltip("Activation mode", violet)
                    with ui.row().classes("absolute inset-0 items-center justify-center pointer-events-none schema-tab-toggle z-0"):
                        mode_toggle = ui.toggle(
                            {"parameters": "Parameters", "groups": "Parameter Groups", "schemas": "Schemas"},
                            value=mode["value"],
                            on_change=lambda event: change_mode(str(event.value)),
                        ).props('dark rounded toggle-color="transparent"').classes("pointer-events-auto")
                    with ui.row().classes("absolute right-0 items-center gap-2 z-10"):
                        purge_refs["trash"] = ui.button(icon="delete").props("flat dense round size=sm").style(
                            "color: #6b7280 !important; background: transparent !important;"
                        ).classes("transition-opacity duration-200 opacity-0 pointer-events-none")
                        purge_refs["trash"].on("click.stop", lambda _=None: handle_trash_click())
                        with purge_refs["trash"]:
                            rich_tooltip("Purge selected", "#ef4444")
                        purge_refs["clean"] = ui.button(icon="cleaning_services").props("flat dense round size=sm").style(
                            "color: #6b7280 !important; opacity: 0.86; background: transparent !important;"
                        )
                        purge_refs["clean"].on("click.stop", lambda _=None: toggle_purge_mode())
                        with purge_refs["clean"]:
                            rich_tooltip("Purge mode", amber)
                search_input = ui.input(placeholder="Search...").props("dark dense outlined rounded").classes("w-full").style(
                    f"--q-primary: {amber};"
                )
                search_input.on("click", lambda _=None: disarm_purge())
                search_input.on("update:model-value", lambda event: update_search(str(event.args or "")))

            with ui.scroll_area().classes("w-full flex-grow px-4 pb-2").on("click", lambda _=None: collapse_all()):
                content = ui.column().classes("w-full gap-2 mt-1").on("click.stop", lambda _=None: None)

            with ui.row().classes("w-full items-center justify-between p-3 border-t border-gray-700 bg-[#161b22] gap-2 shrink-0"):
                ui.button("Param", icon="add", on_click=lambda: add_parameter()).props("outline dense").style(
                    f"color: {amber} !important; border-color: {amber} !important;"
                ).classes("schema-footer-btn")
                ui.button("Group", icon="create_new_folder", on_click=lambda: add_group()).props("outline dense").style(
                    f"color: {teal} !important; border-color: {teal} !important;"
                ).classes("schema-footer-btn")
                ui.button("Schema", icon="rule", on_click=lambda: add_schema()).props("outline dense").style(
                    f"color: {violet} !important; border-color: {violet} !important;"
                ).classes("schema-footer-btn")
                ui.space()
                ui.button("Save", icon="save", on_click=lambda: save_all()).props("dense").style(
                    "background-color: #7a6849 !important; color: white; text-shadow: 1px 1px 3px rgba(0,0,0,1);"
                ).classes("schema-footer-save")

            def change_mode(value: str) -> None:
                mode["value"] = value if value in {"parameters", "groups", "schemas"} else "parameters"
                state["mode"] = mode["value"]
                for bucket in ("parameters", "groups", "schemas"):
                    purge_state[bucket].clear()
                disarm_purge()
                update_purge_controls()
                update_activation_controls()
                save_state()
                render_active()

            def update_search(value: str) -> None:
                search["text"] = value
                disarm_purge()
                render_active()

            def toggle_expanded(bucket: set[str], item_id: str) -> None:
                if item_id in bucket:
                    bucket.remove(item_id)
                else:
                    bucket.add(item_id)
                render_active()

            def add_item() -> None:
                {"parameters": add_parameter, "groups": add_group, "schemas": add_schema}[mode["value"]]()

            def add_parameter() -> None:
                item_id = make_id("param")
                state.setdefault("parameters", []).append(
                    {"id": item_id, "name": f"Parameter {len(state.get('parameters', [])) + 1}", "description": "", "weight": 1.0, "polarity": "positive"}
                )
                expanded_parameters.add(item_id)
                mode["value"] = "parameters"
                mode_toggle.set_value("parameters")
                render_active()

            def add_group() -> None:
                item_id = make_id("group")
                state.setdefault("groups", []).append(
                    {"id": item_id, "name": f"Group {len(state.get('groups', [])) + 1}", "description": "", "parameter_ids": []}
                )
                expanded_groups.add(item_id)
                mode["value"] = "groups"
                mode_toggle.set_value("groups")
                render_active()

            def add_schema() -> None:
                item_id = make_id("schema")
                state.setdefault("schemas", []).append(
                    {
                        "id": item_id,
                        "name": f"Schema {len(state.get('schemas', [])) + 1}",
                        "description": "",
                        "prompt": "",
                        "group_ids": [],
                        "active": not any(item.get("active") for item in state.get("schemas", [])),
                        "version": "1.0.0",
                        "shared": False,
                        "color": "",
                    }
                )
                expanded_schemas.add(item_id)
                mode["value"] = "schemas"
                mode_toggle.set_value("schemas")
                render_active()

            def delete_parameter(item_id: str, *, rerender: bool = True) -> None:
                state["parameters"] = [item for item in state.get("parameters", []) if item.get("id") != item_id]
                for group in state.get("groups", []):
                    group["parameter_ids"] = [pid for pid in group.get("parameter_ids", []) if pid != item_id]
                expanded_parameters.discard(item_id)
                for sub_id in list(expanded_group_parameters):
                    if sub_id.endswith(f":{item_id}"):
                        expanded_group_parameters.discard(sub_id)
                purge_state["parameters"].discard(item_id)
                if rerender:
                    render_active()

            def delete_group(item_id: str, *, rerender: bool = True) -> None:
                state["groups"] = [item for item in state.get("groups", []) if item.get("id") != item_id]
                for schema in state.get("schemas", []):
                    schema["group_ids"] = [gid for gid in schema.get("group_ids", []) if gid != item_id]
                expanded_groups.discard(item_id)
                for sub_id in list(expanded_schema_groups):
                    if sub_id.endswith(f":{item_id}"):
                        expanded_schema_groups.discard(sub_id)
                purge_state["groups"].discard(item_id)
                if rerender:
                    render_active()

            def delete_schema(item_id: str, *, rerender: bool = True) -> None:
                state["schemas"] = [item for item in state.get("schemas", []) if item.get("id") != item_id]
                if state.get("schemas") and not any(item.get("active") for item in state["schemas"]):
                    state["schemas"][0]["active"] = True
                expanded_schemas.discard(item_id)
                purge_state["schemas"].discard(item_id)
                if rerender:
                    render_active()

            def collapse_all() -> None:
                changed = bool(
                    expanded_parameters
                    or expanded_groups
                    or expanded_schemas
                    or expanded_group_parameters
                    or expanded_schema_groups
                    or purge_state["armed"]
                )
                expanded_parameters.clear()
                expanded_groups.clear()
                expanded_schemas.clear()
                expanded_group_parameters.clear()
                expanded_schema_groups.clear()
                purge_state["armed"] = False
                update_purge_controls()
                if changed:
                    render_active()

            def handle_trash_click() -> None:
                selected = set(active_purge_selection())
                if not selected:
                    return
                if not purge_state["armed"]:
                    purge_state["armed"] = True
                    update_purge_controls()
                    return
                if active_purge_key() == "parameters":
                    for item_id in selected:
                        delete_parameter(item_id, rerender=False)
                elif active_purge_key() == "groups":
                    for item_id in selected:
                        delete_group(item_id, rerender=False)
                else:
                    for item_id in selected:
                        delete_schema(item_id, rerender=False)
                active_purge_selection().clear()
                purge_state["armed"] = False
                purge_state["mode"] = False
                update_purge_controls()
                render_active()

            def toggle_group_parameter(group: dict[str, Any], parameter_id: str) -> None:
                ids = list(group.get("parameter_ids", []))
                if parameter_id in ids:
                    ids.remove(parameter_id)
                else:
                    ids.append(parameter_id)
                group["parameter_ids"] = ids
                render_active()

            def toggle_schema_group(schema: dict[str, Any], group_id: str) -> None:
                ids = list(schema.get("group_ids", []))
                if group_id in ids:
                    ids.remove(group_id)
                else:
                    ids.append(group_id)
                schema["group_ids"] = ids
                render_active()

            def set_active_schema(schema_id: str) -> None:
                for schema in state.get("schemas", []):
                    schema["active"] = schema.get("id") == schema_id
                result = self._save_schema_studio_state(state)
                if result.ok:
                    service_result = self.container.schema_service.set_active_schema(_slug(schema_id))
                    self._invalidate_browse_page_model()
                    self._notify(service_result.message, "positive" if service_result.ok else "negative")
                else:
                    self._notify(result.message, "negative")
                render_active()

            def add_group_parameter(group: dict[str, Any], parameter_id: str) -> None:
                ids = list(group.get("parameter_ids", []))
                if parameter_id not in ids:
                    ids.append(parameter_id)
                group["parameter_ids"] = ids
                render_active()

            def remove_group_parameter(group: dict[str, Any], parameter_id: str) -> None:
                group["parameter_ids"] = [pid for pid in group.get("parameter_ids", []) if pid != parameter_id]
                expanded_group_parameters.discard(f"{group.get('id')}:{parameter_id}")
                render_active()

            def set_group_member_search(group_id: str, value: str) -> None:
                group_member_search[group_id] = value
                render_active()

            def add_schema_group(schema: dict[str, Any], group_id: str) -> None:
                ids = list(schema.get("group_ids", []))
                if group_id not in ids:
                    ids.append(group_id)
                schema["group_ids"] = ids
                render_active()

            def remove_schema_group(schema: dict[str, Any], group_id: str) -> None:
                schema["group_ids"] = [gid for gid in schema.get("group_ids", []) if gid != group_id]
                expanded_schema_groups.discard(f"{schema.get('id')}:{group_id}")
                render_active()

            def set_schema_group_search(schema_id: str, value: str) -> None:
                schema_group_search[schema_id] = value
                render_active()

            def render_header_pill(icon: str, name: str, color: str, tooltip: str, on_click: Callable[[], None], selected: bool = False) -> None:
                display_color = "#fca5a5" if selected and purge_state["mode"] else color
                with ui.row().classes("items-center gap-1 rounded-full cursor-pointer select-none schema-pill").style(pill_style(color, selected)).on(
                    "click.stop", lambda _=None: on_click()
                ):
                    ui.icon(icon, size="14px").style(f"color: {display_color};")
                    ui.label(name or "Untitled").classes("text-xs font-medium").style(pill_text_style(display_color))
                    if tooltip:
                        rich_tooltip(tooltip, display_color)

            def render_parameters() -> None:
                content.clear()
                items = filtered(state.get("parameters", []))
                with content:
                    if not items:
                        ui.label("No parameters yet.").classes("text-gray-500 italic p-4")
                    with ui.row().classes("w-full flex-wrap gap-2 items-start"):
                        for item in items:
                            item_id = str(item.get("id"))
                            selected = item_id in purge_state["parameters"]
                            color = parameter_display_color(item)
                            if item_id in expanded_parameters:
                                with ui.element("div").classes("schema-expanded-pill w-full p-3").style(
                                    pill_style(color, selected if purge_state["mode"] else True)
                                ):
                                    with ui.row().classes("w-full items-center gap-2 cursor-pointer").on(
                                        "click.stop", lambda _=None, pid=item_id: handle_item_click(expanded_parameters, pid)
                                    ):
                                        ui.icon("tune", size="18px").style(f"color: {color};")
                                        ui.label(str(item.get("name") or "Untitled Parameter")).classes("text-sm font-bold flex-grow").style(
                                            pill_text_style("#fca5a5" if selected and purge_state["mode"] else color)
                                        )
                                        ui.label(_impact_label(item.get("weight"))).classes("text-[11px] text-gray-400")
                                        ui.button(icon="expand_less").props("flat round dense size=sm").on(
                                            "click.stop", lambda _=None, pid=item_id: toggle_expanded(expanded_parameters, pid)
                                        ).style(f"color: {color} !important;")
                                    with ui.row().classes("w-full items-center gap-2"):
                                        ui.input("Parameter", value=item.get("name", "")).bind_value(item, "name").props(
                                            "dark dense borderless"
                                        ).classes("flex-grow directive-name-input").on("click.stop", lambda _=None: None)
                                    with ui.row().classes("w-full items-center gap-3 flex-wrap").on("click.stop", lambda _=None: None):
                                        ui.label("Framing").classes("text-xs text-gray-500")
                                        ui.toggle(
                                            {"positive": "Positive", "negative": "Negative"},
                                            value=str(_score_polarity(item.get("polarity")).value),
                                            on_change=lambda event, p=item: set_parameter_polarity(p, str(event.value)),
                                        ).props('dark rounded toggle-color="transparent"').classes("schema-tab-toggle")
                                        ui.label("Impact").classes("text-xs text-gray-500")
                                        ui.toggle(
                                            IMPACT_OPTIONS,
                                            value=_impact_value(item.get("weight")),
                                            on_change=lambda event, p=item: set_parameter_weight(p, str(event.value)),
                                        ).props('dark rounded toggle-color="transparent"').classes("schema-tab-toggle")
                                    ui.textarea(
                                        "Scoring guidance",
                                        value=item.get("description", ""),
                                    ).bind_value(item, "description").props("dark dense outlined rows=3").classes("w-full directive-textarea").on(
                                        "click.stop", lambda _=None: None
                                    )
                            else:
                                render_header_pill(
                                    "tune",
                                    str(item.get("name") or "Untitled Parameter"),
                                    color,
                                    parameter_tooltip(item) or "Click to expand",
                                    lambda pid=item_id: handle_item_click(expanded_parameters, pid),
                                    selected,
                                )

            def render_groups() -> None:
                content.clear()
                params = parameter_lookup()
                items = filtered(state.get("groups", []))

                def render_member_parameter(group: dict[str, Any], param: dict[str, Any]) -> None:
                    group_id = str(group.get("id"))
                    pid = str(param.get("id"))
                    sub_id = f"{group_id}:{pid}"
                    color = parameter_display_color(param)
                    if sub_id in expanded_group_parameters:
                        with ui.column().classes("w-full mt-1 mb-2 p-2 rounded gap-2").style(
                            f"background: #0d1117; border: 1px solid rgba({','.join(str(v) for v in rgb_from_hex(color))},0.40);"
                        ).on("click.stop", lambda _=None: None):
                            with ui.row().classes("w-full items-center gap-2"):
                                ui.icon("tune", size="14px").style(f"color: {color};")
                                ui.input("Parameter", value=param.get("name", "")).bind_value(param, "name").props(
                                    "dark dense borderless"
                                ).classes("flex-grow directive-name-input")
                                ui.button(icon="expand_less").props("flat dense round size=sm").style(
                                    f"color: {color} !important;"
                                ).on("click.stop", lambda _=None, sid=sub_id: (expanded_group_parameters.discard(sid), render_active()))
                                ui.button(icon="close").props("flat dense round size=sm").style("color: #8b949e !important;").on(
                                    "click.stop", lambda _=None, g=group, p=pid: remove_group_parameter(g, p)
                                )
                            with ui.row().classes("w-full items-center gap-3 flex-wrap"):
                                ui.toggle(
                                    {"positive": "Positive", "negative": "Negative"},
                                    value=str(_score_polarity(param.get("polarity")).value),
                                    on_change=lambda event, p=param: set_parameter_polarity(p, str(event.value)),
                                ).props('dark rounded toggle-color="transparent"').classes("schema-tab-toggle")
                                ui.toggle(
                                    IMPACT_OPTIONS,
                                    value=_impact_value(param.get("weight")),
                                    on_change=lambda event, p=param: set_parameter_weight(p, str(event.value)),
                                ).props('dark rounded toggle-color="transparent"').classes("schema-tab-toggle")
                            ui.textarea("Scoring guidance", value=param.get("description", "")).bind_value(
                                param, "description"
                            ).props("dark dense outlined rows=3").classes("w-full directive-textarea")
                        return

                    with ui.row().classes("items-center gap-1 rounded-full cursor-pointer select-none").style(
                        pill_style(color)
                    ).on("click.stop", lambda _=None, sid=sub_id: (expanded_group_parameters.add(sid), render_active())):
                        ui.icon("tune", size="12px").style(f"color: {color};")
                        ui.label(str(param.get("name") or "Untitled")).classes("text-xs").style(pill_text_style(color))
                        ui.icon("close", size="12px").classes("cursor-pointer").style("color: #8b949e;").on(
                            "click.stop", lambda _=None, g=group, p=pid: remove_group_parameter(g, p)
                        )

                with content:
                    if not items:
                        ui.label("No parameter groups yet.").classes("text-gray-500 italic p-4")
                    with ui.row().classes("w-full flex-wrap gap-2 items-start"):
                        for group in items:
                            group_id = str(group.get("id"))
                            names = [params.get(pid, {}).get("name", pid) for pid in group.get("parameter_ids", [])]
                            tooltip = ", ".join(names) if names else "Empty group"
                            selected = group_id in purge_state["groups"]
                            if group_id in expanded_groups:
                                with ui.element("div").classes("schema-expanded-pill w-full p-3").style(
                                    pill_style(teal, selected if purge_state["mode"] else True)
                                ):
                                    with ui.row().classes("w-full items-center gap-2 cursor-pointer").on(
                                        "click.stop", lambda _=None, gid=group_id: handle_item_click(expanded_groups, gid)
                                    ):
                                        ui.icon("folder", size="18px").style(f"color: {teal};")
                                        ui.label(str(group.get("name") or "Untitled Group")).classes("text-sm font-bold flex-grow").style(
                                            pill_text_style("#fca5a5" if selected and purge_state["mode"] else teal)
                                        )
                                        ui.button(icon="expand_less").props("flat round dense size=sm").on(
                                            "click.stop", lambda _=None, gid=group_id: toggle_expanded(expanded_groups, gid)
                                        ).style(f"color: {teal} !important;")
                                    ui.input("Group", value=group.get("name", "")).bind_value(group, "name").props(
                                        "dark dense borderless"
                                    ).classes("w-full directive-name-input").on("click.stop", lambda _=None: None)
                                    ui.textarea("Group guidance", value=group.get("description", "")).bind_value(
                                        group, "description"
                                    ).props("dark dense outlined rows=2").classes("w-full directive-textarea").on("click.stop", lambda _=None: None)
                                    ui.label("Parameters").classes("text-xs text-gray-500 mt-1")
                                    current_ids = [str(pid) for pid in group.get("parameter_ids", []) if str(pid) in params]
                                    if current_ids:
                                        with ui.row().classes("w-full flex-wrap gap-1 items-start"):
                                            for pid in current_ids:
                                                render_member_parameter(group, params[pid])
                                    else:
                                        ui.label("No parameters in this group yet.").classes("text-xs text-gray-500")

                                    query = group_member_search.get(group_id, "")
                                    ui.input("Search parameters to add...", value=query).props("dark dense outlined rounded").classes("w-full mt-1").style(
                                        f"--q-primary: {teal};"
                                    ).on("click.stop", lambda _=None: None).on(
                                        "update:model-value", lambda event, gid=group_id: set_group_member_search(gid, str(event.args or ""))
                                    )
                                    if query.strip():
                                        available = [
                                            parameter
                                            for parameter in state.get("parameters", [])
                                            if str(parameter.get("id")) not in current_ids
                                            and (
                                                query.lower() in str(parameter.get("name") or "").lower()
                                                or query.lower() in str(parameter.get("description") or "").lower()
                                            )
                                        ]
                                        with ui.row().classes("w-full flex-wrap gap-1"):
                                            if not available:
                                                ui.label("No matching parameters").classes("text-xs text-gray-500 p-1")
                                            for parameter in available:
                                                pid = str(parameter.get("id"))
                                                color = parameter_display_color(parameter)
                                                with ui.row().classes("items-center gap-1 rounded-full cursor-pointer").style(
                                                    pill_style("#6b7280")
                                                ).on("click.stop", lambda _=None, g=group, p=pid: add_group_parameter(g, p)):
                                                    ui.icon("add", size="12px").style(f"color: {color};")
                                                    ui.label(str(parameter.get("name") or "Untitled")).classes("text-xs").style(pill_text_style("#d1d5db"))
                            else:
                                render_header_pill(
                                    "folder",
                                    str(group.get("name") or "Untitled Group"),
                                    teal,
                                    tooltip,
                                    lambda gid=group_id: handle_item_click(expanded_groups, gid),
                                    selected,
                                )

            def show_schema_editor_dialog(schema: dict[str, Any]) -> None:
                edit_search = {"text": ""}
                base_style = (
                    f"background: linear-gradient(160deg, rgba({rgb_from_hex(violet)[0]},{rgb_from_hex(violet)[1]},{rgb_from_hex(violet)[2]},0.18) 0%, "
                    f"rgba({rgb_from_hex(violet)[0]},{rgb_from_hex(violet)[1]},{rgb_from_hex(violet)[2]},0.08) 100%), #0d1117 !important;"
                    f"width: 980px; max-width: 96vw; height: 88vh; max-height: calc(100vh - 18px); border: 1px solid rgba({rgb_from_hex(violet)[0]},{rgb_from_hex(violet)[1]},{rgb_from_hex(violet)[2]},0.24);"
                )
                fullscreen_style = (
                    base_style
                    + "width: 100vw !important; max-width: 100vw !important; height: 100vh !important; max-height: 100vh !important; border-radius: 0 !important;"
                )
                with self.root:
                    edit_dialog = ui.dialog()
                    edit_dialog.on("hide", edit_dialog.delete)
                with edit_dialog, ui.card().classes("flex flex-col p-0 gap-0 overflow-hidden").style(base_style) as edit_card:
                    with ui.row().classes("w-full items-center justify-between p-4 border-b border-gray-700 shrink-0").style(
                        "background: rgba(22, 27, 34, 0.75); backdrop-filter: blur(8px);"
                    ):
                        with ui.row().classes("items-center gap-2 min-w-0"):
                            ui.icon("rule", size="sm").style(f"color: {violet};")
                            ui.label(str(schema.get("name") or "Schema Editor")).classes("text-lg font-bold").style(glow_text(violet, 5))
                            maximized = {"value": False}

                            def toggle_fullscreen() -> None:
                                maximized["value"] = not maximized["value"]
                                if maximized["value"]:
                                    maximize_btn.props("icon=fullscreen_exit")
                                    edit_card.style(replace=fullscreen_style)
                                    edit_dialog.props("maximized")
                                    ui.run_javascript(
                                        "if (!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(() => {}); }"
                                    )
                                else:
                                    maximize_btn.props("icon=fullscreen")
                                    edit_card.style(replace=base_style)
                                    edit_dialog.props(remove="maximized")
                                    ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")

                            maximize_btn = ui.button(icon="fullscreen", on_click=toggle_fullscreen).props("flat round dense size=sm").style(
                                f"color: {violet}; opacity: 0.78;"
                            )
                            with maximize_btn:
                                rich_tooltip("Toggle fullscreen", violet)

                        def close_edit() -> None:
                            ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")
                            edit_dialog.close()
                            render_active()

                        ui.button(icon="close", on_click=close_edit).props("flat round dense color=white")

                    with ui.scroll_area().classes("schema-editor-scroll w-full flex-grow px-4 py-3"):
                        with ui.column().classes("schema-editor-body w-full min-h-full gap-3").style("width: 100%; min-height: 100%;"):
                            ui.input("Schema name", value=schema.get("name", "")).bind_value(schema, "name").props("dark dense outlined").classes("w-full")
                            with ui.row().classes("w-full items-center gap-2"):
                                ui.color_input("Schema pill color", value=schema.get("color") or schema_display_color(schema)).bind_value(
                                    schema,
                                    "color",
                                ).props("dense dark outlined").classes("flex-grow min-w-0")
                                clear_color = ui.button(icon="format_color_reset").props("flat round dense size=sm")
                                clear_color.style("color: #94a3b8 !important;")
                                clear_color.on("click.stop", lambda _=None, s=schema: (s.update({"color": ""}), render_active()))
                                with clear_color:
                                    rich_tooltip("Use fandom/schema fallback color", violet)
                            ui.textarea("Description", value=schema.get("description", "")).bind_value(
                                schema, "description"
                            ).props("dark dense outlined rows=3").classes("w-full")
                            ui.textarea("Evaluator / system prompt", value=schema.get("prompt", "")).bind_value(
                                schema, "prompt"
                            ).props("dark dense outlined rows=16").classes("schema-prompt-editor w-full")
                            ui.label("Included parameter groups").classes("text-sm font-bold text-gray-300")
                            groups_container = ui.column().classes("w-full gap-2")

                            def render_edit_groups() -> None:
                                groups_container.clear()
                                groups = group_lookup()
                                selected_ids = [str(gid) for gid in schema.get("group_ids", []) if str(gid) in groups]
                                query = edit_search["text"].strip().lower()
                                with groups_container:
                                    if selected_ids:
                                        with ui.row().classes("w-full flex-wrap gap-1"):
                                            for gid in selected_ids:
                                                group = groups[gid]
                                                with ui.row().classes("items-center gap-1 rounded-full").style(pill_style(teal)):
                                                    ui.icon("folder", size="12px").style(f"color: {teal};")
                                                    ui.label(str(group.get("name") or "Untitled Group")).classes("text-xs").style(pill_text_style(teal))
                                                    ui.icon("close", size="12px").classes("cursor-pointer").style("color: #8b949e;").on(
                                                        "click.stop", lambda _=None, s=schema, g=gid: (remove_schema_group(s, g), render_edit_groups())
                                                    )
                                    else:
                                        ui.label("No groups selected.").classes("text-xs text-gray-500")
                                    ui.input("Search groups to add...", value=edit_search["text"]).props("dark dense outlined rounded").classes("w-full").style(
                                        f"--q-primary: {violet};"
                                    ).on(
                                        "update:model-value",
                                        lambda event: (edit_search.update({"text": str(event.args or "")}), render_edit_groups()),
                                    )
                                    if query:
                                        matches = [
                                            group
                                            for group in state.get("groups", [])
                                            if str(group.get("id")) not in selected_ids
                                            and (
                                                query in str(group.get("name") or "").lower()
                                                or query in str(group.get("description") or "").lower()
                                            )
                                        ]
                                        with ui.row().classes("w-full flex-wrap gap-1"):
                                            if not matches:
                                                ui.label("No matching groups").classes("text-xs text-gray-500 p-1")
                                            for group in matches:
                                                gid = str(group.get("id"))
                                                with ui.row().classes("items-center gap-1 rounded-full cursor-pointer").style(pill_style("#6b7280")).on(
                                                    "click.stop", lambda _=None, s=schema, g=gid: (add_schema_group(s, g), render_edit_groups())
                                                ):
                                                    ui.icon("add", size="12px").style(f"color: {teal};")
                                                    ui.label(str(group.get("name") or "Untitled Group")).classes("text-xs").style(pill_text_style("#d1d5db"))

                            render_edit_groups()

                    with ui.row().classes("w-full p-3 border-t border-gray-700 bg-[#161b22] gap-2 shrink-0 justify-end"):
                        ui.button("Done", icon="check", on_click=close_edit).style(
                            f"background-color: {dark_button_color(violet)} !important; color: white;"
                        )

                edit_dialog.open()

            def render_schemas() -> None:
                content.clear()
                groups = group_lookup()
                active_ids = active_schema_ids()
                items = filtered(state.get("schemas", []))

                def render_schema_group(schema: dict[str, Any], group: dict[str, Any]) -> None:
                    schema_id = str(schema.get("id"))
                    gid = str(group.get("id"))
                    sub_id = f"{schema_id}:{gid}"
                    if sub_id in expanded_schema_groups:
                        with ui.column().classes("w-full mt-1 mb-2 p-2 rounded gap-2").style(
                            "background: #0d1117; border: 1px solid rgba(94,234,212,0.40);"
                        ).on("click.stop", lambda _=None: None):
                            with ui.row().classes("w-full items-center gap-2"):
                                ui.icon("folder", size="14px").style(f"color: {teal};")
                                ui.input("Group", value=group.get("name", "")).bind_value(group, "name").props(
                                    "dark dense borderless"
                                ).classes("flex-grow directive-name-input")
                                ui.button(icon="expand_less").props("flat dense round size=sm").style(
                                    f"color: {teal} !important;"
                                ).on("click.stop", lambda _=None, sid=sub_id: (expanded_schema_groups.discard(sid), render_active()))
                                ui.button(icon="close").props("flat dense round size=sm").style("color: #8b949e !important;").on(
                                    "click.stop", lambda _=None, s=schema, g=gid: remove_schema_group(s, g)
                                )
                            ui.textarea("Group guidance", value=group.get("description", "")).bind_value(
                                group, "description"
                            ).props("dark dense outlined rows=2").classes("w-full directive-textarea")
                            member_names = [
                                parameter_lookup().get(str(pid), {}).get("name", str(pid))
                                for pid in group.get("parameter_ids", [])
                                if str(pid) in parameter_lookup()
                            ]
                            ui.label(", ".join(member_names) if member_names else "No parameters in this group.").classes(
                                "text-xs text-gray-500"
                            )
                        return

                    with ui.row().classes("items-center gap-1 rounded-full cursor-pointer select-none").style(pill_style(teal)).on(
                        "click.stop", lambda _=None, sid=sub_id: (expanded_schema_groups.add(sid), render_active())
                    ):
                        ui.icon("folder", size="12px").style(f"color: {teal};")
                        ui.label(str(group.get("name") or "Untitled Group")).classes("text-xs").style(pill_text_style(teal))
                        ui.icon("close", size="12px").classes("cursor-pointer").style("color: #8b949e;").on(
                            "click.stop", lambda _=None, s=schema, g=gid: remove_schema_group(s, g)
                        )

                with content:
                    if not items:
                        ui.label("No schemas yet.").classes("text-gray-500 italic p-4")
                    with ui.row().classes("w-full flex-wrap gap-2 items-start"):
                        for schema in items:
                            schema_id = str(schema.get("id"))
                            schema_color = schema_display_color(schema)
                            group_names = [groups.get(gid, {}).get("name", gid) for gid in schema.get("group_ids", [])]
                            tooltip = ", ".join(group_names) if group_names else "No groups selected"
                            selected = schema_id in purge_state["schemas"]
                            if schema_id in expanded_schemas:
                                with ui.element("div").classes("schema-expanded-pill w-full p-3").style(
                                    pill_style(schema_color, selected if purge_state["mode"] else True)
                                ):
                                    with ui.row().classes("w-full items-center gap-2 cursor-pointer").on(
                                        "click.stop", lambda _=None, sid=schema_id: handle_item_click(expanded_schemas, sid)
                                    ):
                                        ui.icon("rule", size="18px").style(f"color: {schema_color};")
                                        ui.label(str(schema.get("name") or "Untitled Schema")).classes("text-sm font-bold flex-grow").style(
                                            pill_text_style("#fca5a5" if selected and purge_state["mode"] else schema_color)
                                        )
                                        ui.button(icon="open_in_full").props("flat round dense size=sm").on(
                                            "click.stop", lambda _=None, s=schema: show_schema_editor_dialog(s)
                                        ).style(f"color: {schema_color} !important;")
                                        ui.button(icon="expand_less").props("flat round dense size=sm").on(
                                            "click.stop", lambda _=None, sid=schema_id: toggle_expanded(expanded_schemas, sid)
                                        ).style(f"color: {schema_color} !important;")
                                    with ui.row().classes("w-full items-center gap-2").on("click.stop", lambda _=None: None):
                                        ui.input("Schema", value=schema.get("name", "")).bind_value(schema, "name").props(
                                            "dark dense borderless"
                                        ).classes("flex-grow directive-name-input")
                                        ui.color_input("Color", value=schema.get("color") or schema_color).bind_value(schema, "color").props(
                                            "dark dense outlined"
                                        ).classes("w-36")
                                        ui.button("Open editor", icon="open_in_full").props("flat dense").style(
                                            f"color: {schema_color} !important;"
                                        ).on("click.stop", lambda _=None, s=schema: show_schema_editor_dialog(s))
                                    ui.label("Parameter groups").classes("text-xs text-gray-500 mt-1")
                                    selected_ids = [str(gid) for gid in schema.get("group_ids", []) if str(gid) in groups]
                                    if selected_ids:
                                        with ui.row().classes("w-full flex-wrap gap-1 items-start"):
                                            for gid in selected_ids:
                                                render_schema_group(schema, groups[gid])
                                    else:
                                        ui.label("No groups selected for this schema.").classes("text-xs text-gray-500")
                                    query = schema_group_search.get(schema_id, "")
                                    ui.input("Search groups to add...", value=query).props("dark dense outlined rounded").classes("w-full mt-1").style(
                                        f"--q-primary: {violet};"
                                    ).on("click.stop", lambda _=None: None).on(
                                        "update:model-value", lambda event, sid=schema_id: set_schema_group_search(sid, str(event.args or ""))
                                    )
                                    if query.strip():
                                        matches = [
                                            group
                                            for group in state.get("groups", [])
                                            if str(group.get("id")) not in selected_ids
                                            and (
                                                query.lower() in str(group.get("name") or "").lower()
                                                or query.lower() in str(group.get("description") or "").lower()
                                            )
                                        ]
                                        with ui.row().classes("w-full flex-wrap gap-1"):
                                            if not matches:
                                                ui.label("No matching groups").classes("text-xs text-gray-500 p-1")
                                            for group in matches:
                                                gid = str(group.get("id"))
                                                with ui.row().classes("items-center gap-1 rounded-full cursor-pointer").style(
                                                    pill_style("#6b7280")
                                                ).on("click.stop", lambda _=None, s=schema, g=gid: add_schema_group(s, g)):
                                                    ui.icon("add", size="12px").style(f"color: {teal};")
                                                    ui.label(str(group.get("name") or "Untitled Group")).classes("text-xs").style(
                                                        pill_text_style("#d1d5db")
                                                    )
                            else:
                                name = str(schema.get("name") or "Untitled Schema")
                                if schema_id in active_ids:
                                    name = f"{name}  ACTIVE"
                                render_header_pill(
                                    "rule",
                                    name,
                                    schema_color,
                                    tooltip,
                                    lambda sid=schema_id: handle_item_click(expanded_schemas, sid),
                                    selected,
                                )

            def render_active() -> None:
                save_state()
                update_activation_controls()
                if mode["value"] == "groups":
                    render_groups()
                elif mode["value"] == "schemas":
                    render_schemas()
                else:
                    render_parameters()

            def save_all() -> None:
                save_state()
                result = self._save_schema_studio_state(state)
                self._notify(result.message, "positive" if result.ok else "negative")
                if result.ok:
                    self.refresh()

            render_active()
        dialog.open()

    def _show_settings_dialog(self) -> None:
        active = self._active_fandom()
        accent = active.color
        r, g, b = rgb_from_hex(accent)
        identity = self.container.identity_service.bootstrap()
        model_config = self.container.local_model_service.config()
        cache_policy = self.container.work_library_service.browse_cache_policy()
        style_state = self.container.style_service.global_settings()
        settings_state = {
            "display_name": identity.display_name or "",
            "overlay": self.container.mode_service.overlay_visibility().value,
            "lm_base_url": model_config["base_url"],
            "lm_model": model_config["model"],
            "lm_timeout": model_config["timeout_seconds"],
            "lm_temperature": model_config["temperature"],
            "lm_context_length": model_config.get("context_length", 0),
            "lm_models": [],
            "lm_models_message": "",
            "remote_api_base_url": self.container.identity_service.remote_identity().api_base_url,
            "auto_purge_enabled": cache_policy["auto_purge_enabled"],
            "max_cached_works": cache_policy["max_cached_works"],
        }
        footer_refs: dict[str, Any] = {}
        current_tab = {"value": "Style"}
        blocked_refs: dict[str, Any] = {}
        base_dialog_style = (
            wash_background(accent, 0.14)
            + f"width: 560px; max-width: 94vw; height: 85vh; max-height: calc(100vh - 24px); border: 1px solid rgba({r},{g},{b},0.24);"
        )
        fullscreen_dialog_style = (
            wash_background(accent, 0.14)
            + "width: 100vw !important; max-width: 100vw !important; height: 100vh !important; max-height: 100vh !important; "
            + f"border-radius: 0 !important; border: 1px solid rgba({r},{g},{b},0.24);"
        )
        with self.root:
            dialog = ui.dialog()
            dialog.on("hide", dialog.delete)
        with dialog, ui.card().classes("flex flex-col p-0 gap-0 overflow-hidden").style(base_dialog_style) as card:
            def save_style() -> None:
                self.container.style_service.save_global_settings(style_state)
                self._invalidate_browse_page_model()
                self._notify("Global reader style saved.", "positive")
                self.refresh()

            def save_settings() -> None:
                self.container.identity_service.update_display_name(str(settings_state["display_name"]))
                self.container.mode_service.set_overlay_visibility(OverlayVisibility(str(settings_state["overlay"])))
                remote = self.container.identity_service.remote_identity()
                remote.api_base_url = str(settings_state["remote_api_base_url"]).strip()
                remote.auth_state = AuthState.NOT_CONFIGURED
                self.container.identity_service.save_remote_identity(remote)
                result = self.container.local_model_service.save_config(
                    base_url=str(settings_state["lm_base_url"]),
                    model=str(settings_state["lm_model"]),
                    timeout_seconds=int(settings_state["lm_timeout"] or 180),
                    temperature=float(settings_state["lm_temperature"] or 0.2),
                    context_length=settings_state.get("lm_context_length", 0),
                )
                self.container.work_library_service.save_browse_cache_policy(
                    {
                        "auto_purge_enabled": bool(settings_state.get("auto_purge_enabled")),
                        "max_cached_works": settings_state.get("max_cached_works"),
                    }
                )
                self._notify(result.message if result.ok else f"Saved settings, but LM Studio config failed: {result.message}", "positive" if result.ok else "warning")
                self.refresh()

            def render_footer() -> None:
                footer = footer_refs.get("container")
                if not footer:
                    return
                footer.clear()
                with footer:
                    if current_tab["value"] == "Blocked":
                        with ui.row().classes("items-center gap-1"):
                            toggle_restore = blocked_refs.get("toggle_restore")
                            restore_selected = blocked_refs.get("restore_selected")
                            selected_count = int(blocked_refs.get("selected_count", lambda: 0)())
                            restore_active = bool(blocked_refs.get("restore_active", lambda: False)())
                            restore_armed = bool(blocked_refs.get("restore_armed", lambda: False)())
                            restore = ui.button(icon="restore").props("round flat dense size=md")
                            restore.style(f"color: {'#ffffff' if restore_active else '#6b7280'} !important;")
                            if callable(toggle_restore):
                                restore.on("click.stop", lambda _=None: toggle_restore())
                            with restore:
                                rich_tooltip("Restore", accent)
                            if restore_active:
                                unlock = ui.button(icon="lock_open").props("round flat dense size=md")
                                unlock.style(f"color: {'#7ee787' if restore_armed else '#6b7280'} !important;")
                                if selected_count == 0:
                                    unlock.props("disable")
                                if callable(restore_selected):
                                    unlock.on("click.stop", lambda _=None: restore_selected())
                                with unlock:
                                    rich_tooltip("Restore", "#7ee787")
                        ui.space()
                        if blocked_refs.get("mode", lambda: "Tags")() == "Tags":
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("public", size="18px").style(f"color: {normalized_label_color(accent)};")
                                show_all = ui.switch(value=bool(blocked_refs.get("show_all", lambda: False)())).props("dense")
                                toggle_show_all = blocked_refs.get("toggle_show_all")
                                if callable(toggle_show_all):
                                    show_all.on("update:model-value", lambda _=None: toggle_show_all())
                                with show_all:
                                    rich_tooltip("Show blocked tags from all fandoms", accent)
                    else:
                        ui.label("Changes are local until saved.").classes("text-xs italic text-gray-500")
                        save = ui.button("Save", icon="save", on_click=save_style if current_tab["value"] == "Style" else save_settings)
                        save.style(f"background-color: {dark_button_color(accent)} !important; color: white;")

            def disarm_blocked() -> None:
                disarm = blocked_refs.get("disarm")
                if callable(disarm):
                    disarm()

            def handle_tab(event: Any) -> None:
                value = str(getattr(event, "value", None) or getattr(event, "args", None) or "")
                current_tab["value"] = value or current_tab["value"]
                disarm_blocked()
                render_footer()

            blocked_refs["render_footer"] = render_footer

            with ui.row().classes("w-full items-center justify-between p-4 border-b border-gray-700").on("click", lambda _=None: disarm_blocked()):
                with ui.row().classes("items-center gap-2 min-w-0"):
                    ui.icon("settings", size="22px").style(f"color: {normalized_label_color(accent)};")
                    ui.label("AO3 Studio Settings").classes("text-lg font-bold text-gray-300").style(glow_text(accent, 5))
                    fullscreen = {"value": False}

                    def toggle_fullscreen() -> None:
                        fullscreen["value"] = not fullscreen["value"]
                        if fullscreen["value"]:
                            maximize_btn.props("icon=fullscreen_exit")
                            card.style(replace=fullscreen_dialog_style)
                            dialog.props("maximized")
                            ui.run_javascript(
                                "if (!document.fullscreenElement) { document.documentElement.requestFullscreen().catch(() => {}); }"
                            )
                        else:
                            maximize_btn.props("icon=fullscreen")
                            card.style(replace=base_dialog_style)
                            dialog.props(remove="maximized")
                            ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")

                    maximize_btn = ui.button(icon="fullscreen", on_click=toggle_fullscreen).props("flat round dense size=sm")
                    with maximize_btn:
                        rich_tooltip("Toggle fullscreen", accent)

                with ui.row().classes("items-center gap-1"):
                    def close_dialog() -> None:
                        ui.run_javascript("if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); }")
                        dialog.close()

                    ui.button(icon="close", on_click=close_dialog).props("flat round dense color=white")
            with ui.tabs(value="Style").classes("w-full text-gray-400 shrink-0") as tabs:
                style_tab = ui.tab("Style", icon="palette")
                settings_tab = ui.tab("Settings", icon="tune")
                api_tab = ui.tab("API", icon="api")
                blocked_tab = ui.tab("Blocked", icon="block")
            tabs.on("update:model-value", handle_tab)
            with ui.tab_panels(tabs, value=style_tab).classes("w-full flex-grow p-0 text-white overflow-hidden").style(
                "background: transparent;"
            ):
                with ui.tab_panel(style_tab).classes("w-full h-full p-0"):
                    with ui.scroll_area().classes("w-full h-full"):
                        with ui.column().classes("w-full gap-3 p-4"):
                            self._render_style_controls(
                                settings=style_state,
                                accent=accent,
                                save_handler=lambda _state: save_style(),
                                show_thresholds=True,
                                show_save_button=False,
                            )
                with ui.tab_panel(settings_tab).classes("w-full h-full p-0"):
                    with ui.scroll_area().classes("w-full h-full"):
                        with ui.column().classes("w-full gap-3 p-4"):
                            self._page_settings(settings_state, accent)
                with ui.tab_panel(api_tab).classes("w-full h-full p-0"):
                    with ui.scroll_area().classes("w-full h-full"):
                        with ui.column().classes("w-full gap-3 p-4"):
                            self._page_api_settings(settings_state, accent)
                with ui.tab_panel(blocked_tab).classes("w-full h-full p-0"):
                    self._page_blocked_settings(accent, blocked_refs)
            footer_refs["container"] = ui.row().classes("w-full items-center justify-between p-3 border-t border-gray-700 shrink-0").style(
                "background: rgba(13, 17, 23, 0.78);"
            )
            footer_refs["container"].on("click", lambda _=None: disarm_blocked())
            render_footer()
        dialog.open()

    def _page_settings(self, state: dict[str, Any], accent: str) -> None:
        with ui.element("div").classes("soft-panel w-full p-3"):
            identity = self.container.identity_service.bootstrap()
            ui.label("Local Identity").classes("text-lg font-bold").style(glow_text(accent, 3))
            ui.label(identity.local_user_id).classes("text-xs text-gray-500")
            ui.input("Display name", value=state["display_name"]).bind_value(state, "display_name").props("outlined dense dark").classes("w-full")
        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("Shared Overlay").classes("text-lg font-bold").style(glow_text(accent, 3))
            ui.select({item.value: item.value for item in OverlayVisibility}, value=state["overlay"]).bind_value(state, "overlay").props(
                "outlined dense dark"
            ).classes("w-full")
            ui.input("Future remote API base URL", value=state["remote_api_base_url"]).bind_value(state, "remote_api_base_url").props(
                "outlined dense dark"
            ).classes("w-full")
        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("Browse Cache").classes("text-lg font-bold").style(glow_text(accent, 3))
            ui.switch("Auto smart purge after successful AO3 refresh", value=state["auto_purge_enabled"]).bind_value(
                state,
                "auto_purge_enabled",
            )
            ui.number("Max cached works", value=state["max_cached_works"], min=1, step=1).bind_value(
                state,
                "max_cached_works",
            ).props("outlined dense dark").classes("w-48")

    def _page_api_settings(self, state: dict[str, Any], accent: str) -> None:
        refs: dict[str, Any] = {}

        def render_models() -> None:
            box = refs.get("models")
            if not box:
                return
            box.clear()
            models = state.get("lm_models") or []
            message = str(state.get("lm_models_message") or "")
            with box:
                if message:
                    ui.label(message).classes("text-xs text-gray-500")
                if not models:
                    ui.label("No models loaded yet.").classes("text-xs text-gray-500")
                    return
                for item in models:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or item.get("id") or item.get("display_name") or "")
                    if not key:
                        continue
                    display = str(item.get("display_name") or key)
                    loaded = bool(item.get("loaded_instances"))
                    selected = key == str(state.get("lm_model") or "")
                    pill = ui.button(display, icon="memory" if loaded else "radio_button_unchecked").props("dense rounded no-caps")
                    pill.classes("filter-favorite-pill")
                    pill.style(self._filter_pill_style("#7ee787" if loaded else accent, selected))
                    pill.on("click.stop", lambda _=None, model_key=key: state.update({"lm_model": model_key}))
                    with pill:
                        rich_tooltip("Loaded" if loaded else "Available", "#7ee787" if loaded else accent)

        async def refresh_models() -> None:
            result = await run.io_bound(self.container.local_model_service.available_model_details)
            if result.ok:
                state["lm_models"] = result.payload or []
                state["lm_models_message"] = f"{len(state['lm_models'])} model{'s' if len(state['lm_models']) != 1 else ''} available"
            else:
                state["lm_models"] = []
                state["lm_models_message"] = result.message
            render_models()

        async def load_model() -> None:
            save_result = self.container.local_model_service.save_config(
                base_url=str(state["lm_base_url"]),
                model=str(state["lm_model"]),
                timeout_seconds=float(state["lm_timeout"]),
                temperature=float(state["lm_temperature"]),
                context_length=state.get("lm_context_length", 0),
            )
            if not save_result.ok:
                self._notify(save_result.message, "negative")
                return
            result = await run.io_bound(self.container.local_model_service.load_selected_model)
            self._notify(result.message, "positive" if result.ok else "negative")
            await refresh_models()

        async def unload_model() -> None:
            result = await run.io_bound(self.container.local_model_service.unload_selected_model)
            self._notify(result.message, "positive" if result.ok else "negative")
            await refresh_models()

        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("LM Studio Local API").classes("text-lg font-bold").style(glow_text(accent, 3))
            ui.input("Base URL", value=state["lm_base_url"]).bind_value(state, "lm_base_url").props("outlined dense dark").classes("w-full")
            ui.input("Selected model", value=state["lm_model"]).bind_value(state, "lm_model").props("outlined dense dark").classes("w-full")
            with ui.row().classes("w-full gap-2"):
                ui.number("Timeout seconds", value=state["lm_timeout"], min=5, max=1200).bind_value(state, "lm_timeout").props(
                    "outlined dense dark"
                ).classes("w-40")
                ui.number("Temperature", value=state["lm_temperature"], min=0, max=2, step=0.05).bind_value(
                    state,
                    "lm_temperature",
                ).props("outlined dense dark").classes("w-36")
                ui.number("Context length", value=state["lm_context_length"], min=0, step=1024).bind_value(
                    state,
                    "lm_context_length",
                ).props("outlined dense dark").classes("w-40")
            with ui.row().classes("w-full items-center gap-2"):
                refresh = ui.button("Refresh Models", icon="list", on_click=refresh_models).props("flat dense no-caps")
                refresh.style(f"color: {normalized_label_color(accent)} !important;")
                ui.button("Load", icon="download", on_click=load_model).props("dense no-caps").style(
                    f"background-color: {dark_button_color(accent)} !important; color: white;"
                )
                ui.button("Unload", icon="eject", on_click=unload_model).props("flat dense no-caps").style("color: #94a3b8;")
        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("Available Models").classes("text-lg font-bold").style(glow_text(accent, 3))
            refs["models"] = ui.row().classes("w-full gap-1 flex-wrap")
            render_models()
        ui.timer(0.1, lambda: background_tasks.create(refresh_models(), name="ao3-lmstudio-model-list"), once=True)

    def _page_blocked_settings(self, accent: str, refs: dict[str, Any] | None = None) -> None:
        state: dict[str, Any] = {
            "cleanup": False,
            "armed": False,
            "mode": str(self.container.preferences_service.get("blocked_tab_mode", "Tags") or "Tags"),
            "show_all": bool(self.container.preferences_service.get("blocked_show_all_fandoms", False)),
            "authors": set(),
            "works": set(),
            "tags": set(),
            "locked_authors": set(),
            "expanded": set(self.container.preferences_service.get("blocked_expanded_authors", []) or []),
            "expanded_works": set(),
        }
        if state["mode"] not in {"Tags", "Works", "Authors"}:
            state["mode"] = "Tags"
        content = ui.column().classes("w-full h-full min-h-0 gap-0")

        def selected_count() -> int:
            return len(state["authors"]) + len(state["works"]) + len(state["tags"])

        def persist_expanded() -> None:
            self.container.preferences_service.set("blocked_expanded_authors", sorted(state["expanded"]))

        def disarm() -> None:
            changed = bool(state["armed"] or state["expanded"] or state["expanded_works"])
            state["armed"] = False
            state["expanded"].clear()
            state["expanded_works"].clear()
            if changed:
                persist_expanded()
                render()
                if refs and callable(refs.get("render_footer")):
                    refs["render_footer"]()

        if refs is not None:
            refs["disarm"] = disarm

        def toggle_cleanup() -> None:
            state["cleanup"] = not state["cleanup"]
            state["armed"] = False
            state["authors"].clear()
            state["works"].clear()
            state["tags"].clear()
            render()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def set_mode(value: str) -> None:
            state["mode"] = value
            state["armed"] = False
            state["authors"].clear()
            state["works"].clear()
            state["tags"].clear()
            self.container.preferences_service.set("blocked_tab_mode", value)
            render()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def toggle_show_all() -> None:
            state["show_all"] = not bool(state["show_all"])
            self.container.preferences_service.set("blocked_show_all_fandoms", bool(state["show_all"]))
            render()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def toggle_author(author_key: str) -> None:
            state["armed"] = False
            if state["cleanup"]:
                if author_key in state["authors"]:
                    state["authors"].remove(author_key)
                else:
                    state["authors"].add(author_key)
            else:
                if author_key in state["expanded"]:
                    state["expanded"].remove(author_key)
                else:
                    state["expanded"].add(author_key)
                persist_expanded()
            render()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def toggle_work(work_id: str) -> None:
            state["armed"] = False
            if state["cleanup"]:
                if work_id in state["works"]:
                    state["works"].remove(work_id)
                else:
                    state["works"].add(work_id)
            else:
                if work_id in state["expanded_works"]:
                    state["expanded_works"].remove(work_id)
                else:
                    state["expanded_works"].add(work_id)
            render()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def toggle_tag(tag_key: tuple[str, str]) -> None:
            state["armed"] = False
            if state["cleanup"]:
                if tag_key in state["tags"]:
                    state["tags"].remove(tag_key)
                else:
                    state["tags"].add(tag_key)
            render()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def restore_selected() -> None:
            if selected_count() == 0:
                return
            if not state["armed"]:
                state["armed"] = True
                render()
                if refs and callable(refs.get("render_footer")):
                    refs["render_footer"]()
                return
            if state["authors"] & state["locked_authors"]:
                confirm_author_restore()
                return
            perform_restore()

        def perform_restore() -> None:
            author_count = self.container.work_library_service.unblock_many_authors(list(state["authors"]))
            work_count = self.container.work_library_service.unblock_many_works(list(state["works"]))
            tag_count = self.container.work_library_service.unblock_many_tags(list(state["tags"]))
            state["cleanup"] = False
            state["armed"] = False
            state["authors"].clear()
            state["works"].clear()
            state["tags"].clear()
            self._notify(
                f"Restored {author_count} author{'s' if author_count != 1 else ''}, "
                f"{work_count} work{'s' if work_count != 1 else ''}, and {tag_count} tag{'s' if tag_count != 1 else ''}.",
                "positive",
            )
            render()
            self._render_center()
            if refs and callable(refs.get("render_footer")):
                refs["render_footer"]()

        def confirm_author_restore() -> None:
            with self.root:
                dialog = ui.dialog()
                dialog.on("hide", dialog.delete)
            with dialog, ui.card().classes("p-0 overflow-hidden").style(
                f"{wash_background(accent, 0.18)} width: 420px; max-width: 92vw; border: 1px solid rgba(251,113,133,0.35);"
            ):
                with ui.column().classes("w-full gap-3 p-4"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("warning", size="20px").style("color: #fbbf24;")
                        ui.label("Explicitly blocked works exist").classes("text-sm font-bold").style("color: #fbbf24;")
                    ui.label(
                        "This author has explicitly blocked works in the Works tab. Unblocking the author will not restore those work blocks."
                    ).classes("text-sm text-gray-300")
                    with ui.row().classes("w-full items-center justify-end gap-2"):
                        ui.button("Cancel", on_click=dialog.close).props("flat dense no-caps").style("color: #9ca3af;")

                        def confirm() -> None:
                            dialog.close()
                            perform_restore()

                        ui.button("Unblock author", icon="lock_open", on_click=confirm).props("dense no-caps").style(
                            "background-color: #2d6a4f !important; color: white;"
                        )
            dialog.open()

        def short_title(work: Work | None, fallback: str) -> str:
            value = (work.title if work and work.title else fallback).strip()
            return value[:60] + ("..." if len(value) > 60 else "")

        def work_hover_names(works: list[Work]) -> str:
            names = [short_title(work, work.work_id) for work in works[:14]]
            return "\n".join(names) if names else "No cached works yet"

        def work_author(work: Work | None) -> str:
            return (work.author_name if work and work.author_name else "Unknown author").strip()

        if refs is not None:
            refs["toggle_restore"] = toggle_cleanup
            refs["restore_selected"] = restore_selected
            refs["selected_count"] = selected_count
            refs["restore_active"] = lambda: bool(state["cleanup"])
            refs["restore_armed"] = lambda: bool(state["armed"])
            refs["mode"] = lambda: str(state["mode"])
            refs["show_all"] = lambda: bool(state["show_all"])
            refs["toggle_show_all"] = toggle_show_all

        def pill_style(color: str, selected: bool = False) -> str:
            r, g, b = rgb_from_hex(color)
            if selected:
                return f"background: rgba({r},{g},{b},0.32); border: 1px solid rgba({r},{g},{b},0.82); color: {normalized_label_color(color)};"
            return f"background: rgba({r},{g},{b},0.12); border: 1px solid rgba({r},{g},{b},0.34); color: {normalized_label_color(color)};"

        def render() -> None:
            content.clear()
            with content:
                with ui.row().classes("w-full items-center justify-center gap-1 shrink-0 px-4 py-2").on("click", lambda _=None: disarm()):
                    for label in ["Tags", "Works", "Authors"]:
                        selected = state["mode"] == label
                        pill = ui.button(label).props("dense rounded no-caps")
                        pill.classes("filter-favorite-pill")
                        color = accent if label == "Tags" else TAG_TYPE_COLORS[TagType.FANDOM] if label == "Works" else "#fb7185"
                        pill.style(self._filter_pill_style(color, selected))
                        pill.on(
                            "click",
                            lambda _=None, v=label: set_mode(v),
                            js_handler="(event) => { event.stopPropagation(); emit(); }",
                        )

                with ui.scroll_area().classes("w-full flex-grow min-h-0").on("click", lambda _=None: disarm()):
                    with ui.column().classes("w-full gap-2 px-4 pb-4 pt-0 min-h-full").on("click", lambda _=None: disarm()):
                        if state["mode"] == "Tags":
                            fandom_filter = None if state["show_all"] else self._active_fandom().fandom_key
                            tags = self.container.work_library_service.list_blocked_tags(240, fandom_filter)
                            if not tags:
                                self._empty("sell", "No blocked tags")
                                return
                            with ui.row().classes("w-full gap-1 flex-wrap"):
                                for blocked_tag in tags:
                                    selected = (blocked_tag.tag_type.value, blocked_tag.tag_text) in state["tags"]
                                    color = TAG_TYPE_COLORS.get(blocked_tag.tag_type, TAG_TYPE_COLORS[TagType.OTHER])
                                    r, g, b = rgb_from_hex(color)
                                    pill = ui.button(blocked_tag.tag_text).props("flat dense rounded no-caps")
                                    pill.classes("work-tag-pill blocked-tag-restore-pill")
                                    pill.style(
                                        f"background: rgba({r},{g},{b},{0.28 if selected else 0.10}) !important; "
                                        f"border: 1px solid rgba({r},{g},{b},{0.78 if selected else 0.34}); "
                                        f"color: {normalized_label_color(color)} !important;"
                                    )
                                    pill.on(
                                        "click",
                                        lambda _=None, key=(blocked_tag.tag_type.value, blocked_tag.tag_text): toggle_tag(key),
                                        js_handler="(event) => { event.stopPropagation(); emit(); }",
                                    )
                                    with pill:
                                        rich_tooltip(blocked_tag.tag_type.value.title(), color)
                            return

                        active_fandom_key = self._active_fandom().fandom_key
                        if state["mode"] == "Authors":
                            groups = self.container.work_library_service.blocked_author_groups(120, active_fandom_key)
                            state["locked_authors"] = {group.author.author_key for group in groups if group.explicit_work_ids}
                            if not groups:
                                self._empty("person_off", "No blocked authors")
                                return
                            with ui.row().classes("w-full gap-1 flex-wrap items-start"):
                                for group in groups:
                                    author_key = group.author.author_key
                                    selected = author_key in state["authors"]
                                    expanded = author_key in state["expanded"]
                                    restore_locked = bool(group.explicit_work_ids)
                                    color = "#fb7185"
                                    if expanded and not state["cleanup"]:
                                        with ui.column().classes("blocked-expanded-card w-full px-2 pt-1 pb-2 gap-0 rounded").style(
                                            f"background: #161b22; border: 1px solid #30363d; --ss-drop-color: {normalized_label_color(color)};"
                                        ).on("click.stop", lambda _=None, key=author_key: toggle_author(key)):
                                            with ui.row().classes("w-full items-center gap-2"):
                                                ui.icon("person_off", size="xs").style(
                                                    f"color: {normalized_label_color(color)}; text-shadow: 0 0 2px rgba(0,0,0,0.7), 0 0 4px {normalized_label_color(color)}; opacity: 0.8;"
                                                )
                                                ui.label(group.author.display_name or group.author.author_key).classes(
                                                    "flex-grow blocked-expanded-title"
                                                ).style(f"color: {normalized_label_color(color)};")
                                                if restore_locked:
                                                    warning = ui.icon("warning", size="16px").style("color: #fbbf24;")
                                                    with warning:
                                                        rich_tooltip("Explicit work blocks remain in Works tab", "#fbbf24")
                                                ui.icon("expand_less", size="18px").style(f"color: {normalized_label_color(color)};")
                                            if not group.works:
                                                ui.label("No cached works by this author yet.").classes("blocked-expanded-text")
                                            for work in group.works[:60]:
                                                explicit = work.work_id in group.explicit_work_ids
                                                with ui.element("div").classes("blocked-expanded-work w-full mt-2"):
                                                    with ui.row().classes("w-full items-center gap-2"):
                                                        ui.icon("block" if explicit else "person_off", size="xs").style(
                                                            f"color: {normalized_label_color('#ef4444' if explicit else '#94a3b8')}; opacity: 0.8;"
                                                        )
                                                        title_label = ui.label(short_title(work, work.work_id)).classes(
                                                            "blocked-expanded-title flex-grow cursor-context-menu"
                                                        )
                                                        title_label.on(
                                                            "contextmenu",
                                                            lambda _=None: None,
                                                            js_handler="(event) => { event.stopPropagation(); emit(); }",
                                                        )
                                                        with title_label:
                                                            with ui.context_menu().classes("tag-favorite-menu"):
                                                                ui.menu_item(
                                                                    "Block work",
                                                                    on_click=lambda _=None, w=work.work_id: self._block_work(w),
                                                                ).style("color: #58a6ff;")
                                                    if work.summary_text:
                                                        ui.label(work.summary_text[:260]).classes("blocked-expanded-text")
                                        continue
                                    pill = ui.element("div").classes("blocked-pill")
                                    pill.style(pill_style("#6b7280" if restore_locked and state["cleanup"] else color, selected))
                                    pill.on(
                                        "click",
                                        lambda _=None, key=author_key: toggle_author(key),
                                        js_handler="(event) => { event.stopPropagation(); emit(); }",
                                    )
                                    with pill:
                                        with ui.row().classes("w-full items-center gap-2"):
                                            ui.icon("person_off", size="18px")
                                            pill_label = ui.label(
                                                f"{group.author.display_name or group.author.author_key} ({len(group.works)})"
                                            ).classes("text-[11px] truncate")
                                            with pill_label:
                                                tooltip = work_hover_names(group.works)
                                                if restore_locked:
                                                    tooltip = f"Explicit work blocks remain in Works tab\n{tooltip}"
                                                rich_tooltip(tooltip, color)
                            return

                        standalone = self.container.work_library_service.standalone_blocked_work_views(160, active_fandom_key)
                        if not standalone:
                            self._empty("block", "No blocked works")
                            return
                        with ui.row().classes("w-full gap-1 flex-wrap items-start"):
                            for view in standalone:
                                work = view.work
                                selected = view.block.work_id in state["works"]
                                expanded_work = view.block.work_id in state["expanded_works"]
                                if expanded_work and not state["cleanup"]:
                                    with ui.column().classes("blocked-expanded-card w-full px-2 pt-1 pb-2 gap-0 rounded").style(
                                        "background: #161b22; border: 1px solid #30363d; --ss-drop-color: #58a6ff;"
                                    ).on("click.stop", lambda _=None, w=view.block.work_id: toggle_work(w)):
                                        with ui.row().classes("w-full items-center gap-2 min-w-0"):
                                            ui.icon("block", size="xs").style(
                                                "color: #58a6ff; text-shadow: 0 0 2px rgba(0,0,0,0.7), 0 0 4px #58a6ff; opacity: 0.8;"
                                            )
                                            ui.label(short_title(work, view.block.work_id)).classes("blocked-expanded-title min-w-0")
                                            ui.label("|").classes("action-separator")
                                            author_label = ui.label(work_author(work)).classes(
                                                "blocked-expanded-title flex-grow min-w-0 cursor-context-menu"
                                            ).style("color: #6b7280;")
                                            author_label.on(
                                                "contextmenu",
                                                lambda _=None: None,
                                                js_handler="(event) => { event.stopPropagation(); emit(); }",
                                            )
                                            with author_label:
                                                with ui.context_menu().classes("tag-favorite-menu"):
                                                    ui.menu_item(
                                                        "Block author",
                                                        on_click=lambda _=None, w=view.block.work_id: self._block_author_for_work(w),
                                                    ).style("color: #fb7185;")
                                            ui.icon("expand_less", size="18px").style("color: #58a6ff;")
                                        ui.label((work.summary_text if work and work.summary_text else "No cached summary.")[:320]).classes(
                                            "blocked-expanded-text"
                                        )
                                    continue
                                pill = ui.element("div").classes("blocked-pill blocked-work-pill")
                                pill.style(pill_style("#58a6ff", selected))
                                pill.on(
                                    "click",
                                    lambda _=None, w=view.block.work_id: toggle_work(w),
                                    js_handler="(event) => { event.stopPropagation(); emit(); }",
                                )
                                with pill:
                                    with ui.row().classes("w-full items-center gap-2"):
                                        ui.icon("block", size="18px")
                                        pill_label = ui.label(short_title(work, view.block.work_id)).classes("text-[11px] truncate")
                                        with pill_label:
                                            rich_tooltip(work_author(work), "#58a6ff")

        render()

    def _save_identity(self, state: dict[str, Any]) -> None:
        self.container.identity_service.update_display_name(str(state["display_name"]))
        self._notify("Identity saved.", "positive")
        self.refresh()

    def _save_shared_settings(self, state: dict[str, Any]) -> None:
        self.container.mode_service.set_overlay_visibility(OverlayVisibility(str(state["overlay"])))
        remote = self.container.identity_service.remote_identity()
        remote.api_base_url = str(state["remote_api_base_url"]).strip()
        remote.auth_state = AuthState.NOT_CONFIGURED
        self.container.identity_service.save_remote_identity(remote)
        self._notify("Shared settings saved.", "positive")
        self.refresh()

    def _save_cache_policy(self, state: dict[str, Any]) -> None:
        self.container.work_library_service.save_browse_cache_policy(
            {
                "auto_purge_enabled": bool(state.get("auto_purge_enabled")),
                "max_cached_works": state.get("max_cached_works"),
            }
        )
        self._notify("Browse cache policy saved.", "positive")
        self.refresh()

    def _save_lmstudio(self, state: dict[str, Any]) -> None:
        result = self.container.local_model_service.save_config(
            base_url=str(state["lm_base_url"]),
            model=str(state["lm_model"]),
            timeout_seconds=float(state["lm_timeout"]),
            temperature=float(state["lm_temperature"]),
            context_length=state.get("lm_context_length", 0),
        )
        self._notify(result.message, "positive")

    async def _list_lmstudio_models(self) -> None:
        client = self._current_client()
        result = await run.io_bound(self.container.local_model_service.available_models)
        if result.ok:
            models = result.payload or []
            self._notify(f"Models: {', '.join(models[:6]) if models else 'none returned'}", "positive", client=client)
        else:
            self._notify(result.message, "warning", client=client)

    def _page_admin(self) -> None:
        self._page_title("Remote Admin", "Hidden unless Shared Mode has an authenticated remote admin identity.")
        result = self.container.admin_service.admin_status()
        if not result.ok:
            self._empty("admin_panel_settings", result.message)
            return
        with ui.element("div").classes("soft-panel w-full p-3"):
            ui.label("Admin actions are remote-only and server-enforced later.").classes("text-sm text-gray-400")
            for label in [
                "User lookup",
                "Delete remote evaluations from user",
                "Ban or disable user",
                "Inspect divergence flags",
                "Inspect schema adoption",
                "Inspect suspicious submission bursts",
                "Reindex remote aggregates",
            ]:
                ui.button(label, icon="block").props("disable flat").classes("w-full justify-start")

    def _empty(self, icon: str, text: str) -> None:
        with ui.column().classes("w-full min-h-[34vh] items-center justify-center gap-2 text-gray-500"):
            ui.icon(icon, size="36px")
            ui.label(text).classes("text-sm")


def _score_summary(scores: dict[str, Any]) -> str:
    return " | ".join(f"{key}: {value}" for key, value in scores.items())


def _canonical_ao3_character_tag_url(value: str | None) -> str:
    label = _ao3_character_tag_label(value)
    if not label:
        return ""
    return f"https://archiveofourown.org/tags/{quote(label, safe='')}/works"


def _ao3_character_tag_label(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = parsed.path if parsed.scheme or parsed.netloc else raw
    match = re.search(r"/tags/([^/]+)(?:/works)?/?$", path)
    if match:
        return " ".join(unquote(match.group(1)).split())
    return " ".join(unquote(raw).split())


def _character_names_from_ao3_label(value: str | None) -> tuple[str, str]:
    label = _ao3_character_tag_label(value)
    label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
    label = " ".join(label.split())
    if not label:
        return "", ""
    nickname_match = re.search(r"[\"\u201c\u201d]([^\"\u201c\u201d]+)[\"\u201c\u201d]", label)
    full_name = re.sub(r"\s*[\"\u201c\u201d][^\"\u201c\u201d]+[\"\u201c\u201d]\s*", " ", label).strip()
    full_name = " ".join(full_name.split()) or label
    if nickname_match:
        short_name = " ".join(nickname_match.group(1).split())
    else:
        short_name = re.split(r"\s+", full_name, maxsplit=1)[0].strip()
    return short_name, full_name


def _character_profile_display_names(character: Any) -> tuple[str, str]:
    stored_name = str(getattr(character, "name", "") or "").strip()
    stored_full_name = str(getattr(character, "full_name", "") or "").strip()
    tag_urls = list(getattr(character, "tag_urls", []) or [])
    source_label = (tag_urls[0] if tag_urls else "") or stored_full_name or stored_name
    derived_name, derived_full_name = _character_names_from_ao3_label(source_label)
    display_full_name = stored_full_name or stored_name
    display_name = stored_name or derived_name
    if derived_full_name and (not display_full_name or display_full_name == stored_name):
        display_full_name = derived_full_name
    if derived_name and (
        not display_name
        or display_name == display_full_name
        or len(display_name.split()) > 1
        or "\"" in display_name
        or "\u201c" in display_name
        or "\u201d" in display_name
    ):
        display_name = derived_name
    return display_name or display_full_name, display_full_name or display_name


def _canonical_character_suggestions(suggestions: list[Any], query: str = "") -> list[Any]:
    candidates: list[tuple[Any, str, str, bool, int]] = []
    query_key = _character_match_key(query)
    for index, suggestion in enumerate(suggestions):
        raw_label = _ao3_character_tag_label(
            str(getattr(suggestion, "tag_url", "") or getattr(suggestion, "tag_text", ""))
        )
        if not raw_label or re.search(r"\([^)]*\)\s*$", raw_label):
            continue
        short_name, full_name = _character_names_from_ao3_label(raw_label)
        if len(short_name) < 2 or len(full_name) < 2:
            continue
        has_quoted_name = bool(re.search(r"[\"\u201c\u201d][^\"\u201c\u201d]+[\"\u201c\u201d]", raw_label))
        candidates.append((suggestion, short_name, full_name, has_quoted_name, index))

    quoted_short_names = {short.casefold() for _, short, _, has_quoted, _ in candidates if has_quoted}
    filtered = [
        candidate
        for candidate in candidates
        if candidate[3] or candidate[1].casefold() not in quoted_short_names
    ]

    def rank(candidate: tuple[Any, str, str, bool, int]) -> tuple[int, int, int, int]:
        suggestion, short_name, full_name, has_quoted_name, index = candidate
        label = _ao3_character_tag_label(str(getattr(suggestion, "tag_text", "") or ""))
        haystack = f"{short_name} {full_name} {label}".casefold()
        starts_query = int(bool(query_key) and (short_name.casefold().startswith(query_key) or full_name.casefold().startswith(query_key)))
        contains_query = int(bool(query_key) and query_key in haystack)
        return (-starts_query, -contains_query, -int(has_quoted_name), index)

    return [candidate[0] for candidate in sorted(filtered, key=rank)]


def _character_label_variants(value: str | None) -> set[str]:
    label = _ao3_character_tag_label(value)
    if not label:
        return set()
    variants = {label}
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
    if stripped:
        variants.add(stripped)
    return variants


def _character_match_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _character_aliases(character: Any) -> set[str]:
    labels: set[str] = set()
    labels.update(_character_label_variants(getattr(character, "name", "")))
    labels.update(_character_label_variants(getattr(character, "full_name", "")))
    for tag_url in getattr(character, "tag_urls", []) or []:
        labels.update(_character_label_variants(tag_url))
    aliases: set[str] = set()
    for label in labels:
        clean = " ".join(str(label or "").split())
        if len(clean) >= 3:
            aliases.add(clean)
        first = re.split(r"\s+", clean, maxsplit=1)[0].strip()
        if len(first) >= 3:
            aliases.add(first)
        for nickname in re.findall(r"[\"“”]([^\"“”]+)[\"“”]", clean):
            nickname = " ".join(nickname.split())
            if len(nickname) >= 3:
                aliases.add(nickname)
    return aliases


def _character_work_tag_keys(tag: WorkTag) -> set[str]:
    if tag.tag_type is not TagType.CHARACTER:
        return set()
    keys: set[str] = set()
    canonical_url = _canonical_ao3_character_tag_url(tag.tag_url or tag.tag_text)
    if canonical_url:
        keys.add(f"url:{canonical_url.casefold()}")
    for label in _character_label_variants(tag.tag_text):
        key = _character_match_key(label)
        if key:
            keys.add(f"label:{key}")
    for label in _character_label_variants(tag.tag_url):
        key = _character_match_key(label)
        if key:
            keys.add(f"label:{key}")
    return keys


def _character_profile_match_keys(character: Any) -> set[str]:
    keys: set[str] = set()
    for tag_url in getattr(character, "tag_urls", []) or []:
        canonical_url = _canonical_ao3_character_tag_url(tag_url)
        if canonical_url:
            keys.add(f"url:{canonical_url.casefold()}")
    for alias in _character_aliases(character):
        key = _character_match_key(alias)
        if key:
            keys.add(f"label:{key}")
    return keys


def _character_matches_work_tags(character: Any, work_tags: list[WorkTag]) -> bool:
    character_keys = _character_profile_match_keys(character)
    if not character_keys:
        return False
    for tag in work_tags:
        if character_keys.intersection(_character_work_tag_keys(tag)):
            return True
    return False


def _chapter_mentions_character(chapter_html: str, character: Any) -> bool:
    text = BeautifulSoup(chapter_html or "", "lxml").get_text(" ", strip=True)
    if not text:
        return False
    for alias in sorted(_character_aliases(character), key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?:['\u2019]s)?(?![A-Za-z0-9_])", text, re.IGNORECASE):
            return True
    return False


def _reader_visible_characters_for_chapter(
    characters: list[CharacterProfile],
    work_tags: list[WorkTag],
    chapter_html: str,
    *,
    committed: bool,
) -> list[CharacterProfile]:
    work_tagged_ids = {character.id for character in characters if _character_matches_work_tags(character, work_tags)}
    mentioned_ids = {character.id for character in characters if _chapter_mentions_character(chapter_html, character)}
    visible_ids = mentioned_ids if committed else work_tagged_ids | mentioned_ids
    return [character for character in characters if character.id in visible_ids]


def _reader_highlight_characters(fragment: str, characters: list[Any]) -> str:
    names: dict[str, str] = {}
    for character in characters:
        color = str(getattr(character, "color", "") or "#58a6ff")
        for alias in _character_aliases(character):
            if len(alias) >= 3:
                names.setdefault(alias, color)
    if not names:
        return fragment
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r")(?:['\u2019]s)?\b",
        re.IGNORECASE,
    )
    lookup = {name.lower(): color for name, color in names.items()}
    soup = BeautifulSoup(fragment, "lxml")
    for node in list(soup.find_all(string=True)):
        if not isinstance(node, NavigableString) or node.parent and node.parent.name in {"script", "style"}:
            continue
        text = str(node)
        if not pattern.search(text):
            continue
        parts: list[str] = []
        last = 0
        for match in pattern.finditer(text):
            parts.append(html.escape(text[last : match.start()]))
            base = match.group(1)
            matched = match.group(0)
            color = lookup.get(base.lower(), "#58a6ff")
            style = glow_text(color, 6)
            parts.append(f'<span style="{html.escape(style, quote=True)}">{html.escape(matched)}</span>')
            last = match.end()
        parts.append(html.escape(text[last:]))
        replacement = BeautifulSoup("".join(parts), "html.parser")
        node.replace_with(*list((replacement.body or replacement).contents))
    body = soup.body or soup
    return str(body.decode_contents())


def _reader_apply_pov_paragraph_colors(fragment: str, pov_color: str | None) -> str:
    if not fragment:
        return fragment
    if pov_color and pov_color != "#e0e0e0":
        color_a = _scriptstudio_lighten_color(pov_color, 0.45)
        color_b = _scriptstudio_lighten_color(pov_color, 0.65)
    else:
        color_a = "#c9d1d9"
        color_b = "#dde3ea"
    soup = BeautifulSoup(fragment, "lxml")
    body = soup.body or soup
    blocks: list[Any] = []
    for node in body.find_all(["p", "blockquote", "div"]):
        if node.name == "div" and node.find(["p", "blockquote", "div"]):
            continue
        if node.get_text(" ", strip=True):
            blocks.append(node)
    for index, node in enumerate(blocks):
        color = color_a if index % 2 == 0 else color_b
        existing = str(node.get("style") or "").strip()
        separator = "" if not existing or existing.endswith(";") else "; "
        node["style"] = f"{existing}{separator}color: {color};"
    return str(body.decode_contents())


def _scriptstudio_lighten_color(hex_color: str, amount: float = 0.3) -> str:
    value = str(hex_color or "").strip().lstrip("#")
    if len(value) != 6:
        return str(hex_color or "")
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return str(hex_color or "")
    r = int(r + (255 - r) * amount)
    g = int(g + (255 - g) * amount)
    b = int(b + (255 - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


IMPACT_OPTIONS = {"0.5": "Low", "1.0": "Normal", "1.5": "High", "2.0": "Critical"}


def _score_polarity(value: Any) -> ScorePolarity:
    try:
        return ScorePolarity(str(value or ScorePolarity.POSITIVE))
    except ValueError:
        return ScorePolarity.POSITIVE


def _impact_value(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 1.0
    closest = min((float(key) for key in IMPACT_OPTIONS), key=lambda option: abs(option - parsed))
    return f"{closest:.1f}"


def _impact_label(value: Any) -> str:
    impact = _impact_value(value)
    return f"{IMPACT_OPTIONS[impact]} ({impact}x)"


def _work_id_from_any(value: str) -> str:
    import re

    match = re.search(r"/works/(\d+)|^(\d+)$", value.strip())
    if not match:
        return ""
    return str(match.group(1) or match.group(2) or "")


def _slug(value: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return slug or "criterion"
