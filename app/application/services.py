from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable
from urllib.parse import parse_qs, parse_qsl, quote, unquote, unquote_plus, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.application.dto import (
    BrowseResult,
    EvaluationResult,
    MergedWorkView,
    ReaderResult,
    RemoteResult,
    ServiceResult,
    WorkFetchResult,
)
from app.domain.entities import (
    BlockedAuthor,
    BlockedAuthorGroup,
    BlockedTag,
    BlockedWork,
    BlockedWorkView,
    BrowseSnapshot,
    CharacterProfile,
    Evaluation,
    EvaluationBatch,
    EvaluationQueueItem,
    EvaluationSchema,
    FandomDirectorySource,
    FandomProfile,
    FandomSuggestion,
    FandomStyleOverride,
    FavoriteTag,
    ReaderAsset,
    ReaderChapter,
    ReadingState,
    RemoteIdentity,
    SharedOverlay,
    SyncState,
    TagColorOverride,
    Work,
    WorkEvaluationSample,
    WorkRarity,
    WorkSet,
    WorkTag,
)
from app.domain.enums import (
    EvaluationBatchStatus,
    EvaluationStatus,
    OverlayVisibility,
    QueueStatus,
    RarityTier,
    ReadingStatus,
    RemoteResultStatus,
    RuntimeMode,
    TagType,
)
from app.domain.policies import MergePolicy, ModePolicy, SchemaPolicy
from app.domain.ports import (
    BlockedAuthorRepository,
    BlockedTagRepository,
    BlockedWorkRepository,
    BrowseSnapshotRepository,
    CharacterProfileRepository,
    EvaluationBatchRepository,
    EvaluationQueueRepository,
    EvaluationRepository,
    EvaluationSchemaRepository,
    FandomRepository,
    FandomStyleRepository,
    FandomTagCatalogRepository,
    FavoriteTagRepository,
    IdentityRepository,
    ModelEvaluationProvider,
    RarityRepository,
    ReaderAssetRepository,
    ReadingStateRepository,
    SettingsRepository,
    SharedOverlayRepository,
    SyncRepository,
    TagColorRepository,
    TagRepository,
    WorkCollectionRepository,
    WorkRepository,
    WorkSetRepository,
)
from app.infrastructure.ao3.models import ParsedBrowsePage, ParsedReaderDocument, ParsedWorkDetail

AO3_BASE_URL = "https://archiveofourown.org"
DEFAULT_FANDOM = "Life is Strange (Video Games 2015 2017 2024 2026)"
DEFAULT_FANDOM_DIRECTORY_SOURCES = (
    ("Movies", "Movies", f"{AO3_BASE_URL}/media/Movies/fandoms", "#f59e0b", True),
    ("TV Shows", "TV Shows", f"{AO3_BASE_URL}/media/TV%20Shows/fandoms", "#58a6ff", True),
    ("Video Games", "Video Games", f"{AO3_BASE_URL}/media/Video%20Games/fandoms", "#7ee787", True),
    ("Anime *a* Manga", "Anime & Manga", f"{AO3_BASE_URL}/media/Anime%20*a*%20Manga/fandoms", "#c084fc", True),
    ("Books *a* Literature", "Books & Literature", f"{AO3_BASE_URL}/media/Books%20*a*%20Literature/fandoms", "#d6b274", True),
    (
        "Cartoons *a* Comics *a* Graphic Novels",
        "Cartoons & Comics & Graphic Novels",
        f"{AO3_BASE_URL}/media/Cartoons%20*a*%20Comics%20*a*%20Graphic%20Novels/fandoms",
        "#fb7185",
        True,
    ),
)
AO3_SORT_COLUMN_ALIASES = {
    "creator": "authors_to_sort_on",
    "author": "authors_to_sort_on",
    "authors": "authors_to_sort_on",
    "authors_to_sort_on": "authors_to_sort_on",
    "title": "title_to_sort_on",
    "title_to_sort_on": "title_to_sort_on",
    "date posted": "created_at",
    "posted": "created_at",
    "created_at": "created_at",
    "date updated": "revised_at",
    "updated": "revised_at",
    "revised_at": "revised_at",
    "word count": "word_count",
    "words": "word_count",
    "word_count": "word_count",
    "hits": "hits",
    "kudos": "kudos_count",
    "kudos_count": "kudos_count",
    "comments": "comments_count",
    "comments_count": "comments_count",
    "bookmarks": "bookmarks_count",
    "bookmarks_count": "bookmarks_count",
}
STYLE_SETTINGS_KEY = "reader_style_global"
RARITY_THRESHOLDS_KEY = "rarity_thresholds_global"
BROWSE_CACHE_POLICY_KEY = "browse_cache_policy"
QUEUE_EVAL_CONFIG_KEY = "queue_evaluation_config"
DEFAULT_BROWSE_CACHE_POLICY = {
    "auto_purge_enabled": False,
    "max_cached_works": 120,
}
DEFAULT_QUEUE_EVAL_CONFIG = {
    "include_metadata": True,
    "include_tags": True,
    "start_chapter": 1,
    "chapter_window": 3,
    "target_words": 5000,
    "max_words": 6500,
    "skip_empty_chapters": True,
}
GRADIENT_BORDER_MODES = {
    "single",
    "twin",
    "duotone",
    "tritone",
    "clash",
    "traffic",
    "glitch",
    "wildcard",
    "ignition",
    "reverse",
    "sonar",
    "overload",
    "nebula",
    "abyss",
}
DEFAULT_RARITY_THRESHOLDS = {
    "uncommon": 5.0,
    "rare": 6.5,
    "epic": 7.5,
    "legendary": 8.5,
}
DEFAULT_READER_STYLE = {
    "preview_font_family": "'Source Code Pro', monospace",
    "reader_font_size": 16.5,
    "font_wheel_step_px": 0.5,
    "border_thickness": 1.0,
    "gradient_border_enabled": False,
    "gradient_border_mode": "twin",
    "rarity_map_enabled": False,
    "rarity_map": {
        "uncommon": "twin",
        "rare": "twin",
        "epic": "twin",
        "legendary": "twin",
        "best": "twin",
    },
}
STYLE_OVERRIDE_SECTIONS_KEY = "_override_sections"
STYLE_FONT_KEYS = ("preview_font_family", "reader_font_size", "font_wheel_step_px")
STYLE_RARITY_KEYS = (
    "border_thickness",
    "gradient_border_enabled",
    "gradient_border_mode",
    "rarity_map_enabled",
    "rarity_map",
)
DEFAULT_CHARACTER_READER_STYLE = {
    "font_family": DEFAULT_READER_STYLE["preview_font_family"],
    "custom_font_enabled": False,
    "font_size": DEFAULT_READER_STYLE["reader_font_size"],
    "font_size_enabled": False,
}


def utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_author_key(author_name: str | None = None, author_url: str | None = None) -> str:
    raw_url = str(author_url or "").strip()
    if raw_url:
        parsed = urlparse(raw_url)
        path = parsed.path.strip("/")
        if path:
            return path.casefold()
        return raw_url.casefold()
    return re.sub(r"\s+", " ", str(author_name or "").strip()).casefold()


def normalize_word_count_filter(value: Any) -> str:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return ""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmM]?)", raw)
    if not match:
        return raw
    number = float(match.group(1))
    suffix = match.group(2).casefold()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return str(max(0, int(round(number))))


def normalize_ao3_date_filter(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    raw = re.sub(r"(\d)([A-Za-z])", r"\1 \2", raw)
    raw = re.sub(r"([A-Za-z])(\d)", r"\1 \2", raw)
    raw = re.sub(r"\s+", " ", raw)
    slash = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if slash:
        month, day, year = [int(part) for part in slash.groups()]
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return str(value or "").strip()
    compact = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if compact:
        year, month, day = [int(part) for part in compact.groups()]
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return str(value or "").strip()
    month_names = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    parts = raw.replace(",", "").split(" ")
    if len(parts) == 3:
        try:
            if parts[0].casefold() in month_names:
                month = month_names[parts[0].casefold()]
                day = int(parts[1])
                year = int(parts[2])
                return date(year, month, day).isoformat()
            if parts[1].casefold() in month_names:
                day = int(parts[0])
                month = month_names[parts[1].casefold()]
                year = int(parts[2])
                return date(year, month, day).isoformat()
        except ValueError:
            return str(value or "").strip()
    return str(value or "").strip()


def filter_signature(filter_state: dict[str, Any]) -> str:
    normalized = json.dumps(filter_state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return stable_hash(normalized)[:24]


def fandom_key(tag: str) -> str:
    return stable_hash(tag.strip().lower())[:16]


def short_fandom_name(tag: str) -> str:
    value = tag.strip()
    return value.split(" (", 1)[0] if " (" in value else value


def normalize_ao3_sort_column(value: Any) -> str:
    raw = str(value or "revised_at").strip()
    return AO3_SORT_COLUMN_ALIASES.get(raw.casefold(), raw or "revised_at")


def default_fandom_filter(tag: str) -> dict[str, Any]:
    return {
        "fandom": tag,
        "sort_column": "revised_at",
        "sort_direction": "desc",
        "query": "",
        "page": 1,
        "other_tag_names": "",
        "excluded_tag_names": "",
        "crossover": "",
        "complete": "",
        "words_from": None,
        "words_to": None,
        "date_from": "",
        "date_to": "",
        "language_id": "",
        "anchor_work_url": "",
        "selected": {},
        "favorite_options": [],
    }


def _float_between(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return max(minimum, min(maximum, numeric))


def _normalized_rarity_map(value: Any, default_mode: str = "twin") -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    rarity_map: dict[str, str] = {}
    for tier in (RarityTier.UNCOMMON, RarityTier.RARE, RarityTier.EPIC, RarityTier.LEGENDARY, RarityTier.BEST):
        mode = str(raw.get(tier.value) or default_mode or "twin")
        rarity_map[tier.value] = mode if mode in GRADIENT_BORDER_MODES else "twin"
    return rarity_map


def normalize_style_override_sections(value: Any, fallback_enabled: bool = False) -> dict[str, bool]:
    raw = value if isinstance(value, dict) else {}
    return {
        "font": bool(raw.get("font", fallback_enabled)),
        "rarity": bool(raw.get("rarity", fallback_enabled)),
    }


def normalize_reader_style(settings: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(DEFAULT_READER_STYLE)
    if fallback:
        base.update(fallback)
        base["rarity_map"] = _normalized_rarity_map(fallback.get("rarity_map"), str(fallback.get("gradient_border_mode", "twin")))
    raw = dict(settings or {})
    merged = dict(base)
    merged.update(raw)
    mode = str(merged.get("gradient_border_mode") or "twin")
    if mode not in GRADIENT_BORDER_MODES:
        mode = "twin"
    normalized = {
        "preview_font_family": str(merged.get("preview_font_family") or DEFAULT_READER_STYLE["preview_font_family"]),
        "reader_font_size": _float_between(merged.get("reader_font_size"), 16.5, 8.0, 48.0),
        "font_wheel_step_px": _float_between(merged.get("font_wheel_step_px"), 0.5, 0.5, 10.0),
        "border_thickness": _float_between(merged.get("border_thickness"), 1.0, 0.0, 12.0),
        "gradient_border_enabled": bool(merged.get("gradient_border_enabled")),
        "gradient_border_mode": mode,
        "rarity_map_enabled": bool(merged.get("rarity_map_enabled")),
        "rarity_map": _normalized_rarity_map(merged.get("rarity_map"), mode),
    }
    if isinstance(raw.get(STYLE_OVERRIDE_SECTIONS_KEY), dict):
        normalized[STYLE_OVERRIDE_SECTIONS_KEY] = normalize_style_override_sections(raw.get(STYLE_OVERRIDE_SECTIONS_KEY))
    return normalized


def normalize_character_reader_style(settings: dict[str, Any] | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(DEFAULT_CHARACTER_READER_STYLE)
    if fallback:
        base.update(
            {
                "font_family": str(fallback.get("font_family") or fallback.get("preview_font_family") or base["font_family"]),
                "font_size": _float_between(fallback.get("font_size") or fallback.get("reader_font_size"), base["font_size"], 8.0, 48.0),
                "custom_font_enabled": bool(fallback.get("custom_font_enabled", base["custom_font_enabled"])),
                "font_size_enabled": bool(fallback.get("font_size_enabled", base["font_size_enabled"])),
            }
        )
    raw = dict(settings or {})
    font_family = str(raw.get("font_family") or raw.get("preview_font_family") or base["font_family"])
    return {
        "font_family": font_family,
        "custom_font_enabled": bool(raw.get("custom_font_enabled", raw.get("font_enabled", base["custom_font_enabled"]))),
        "font_size": _float_between(raw.get("font_size") or raw.get("reader_font_size"), float(base["font_size"]), 8.0, 48.0),
        "font_size_enabled": bool(raw.get("font_size_enabled", base["font_size_enabled"])),
    }


def normalize_rarity_thresholds(thresholds: dict[str, Any] | None) -> dict[str, float]:
    raw = thresholds if isinstance(thresholds, dict) else {}
    normalized = {
        "uncommon": _float_between(raw.get("uncommon"), DEFAULT_RARITY_THRESHOLDS["uncommon"], 0.0, 10.0),
        "rare": _float_between(raw.get("rare"), DEFAULT_RARITY_THRESHOLDS["rare"], 0.0, 10.0),
        "epic": _float_between(raw.get("epic"), DEFAULT_RARITY_THRESHOLDS["epic"], 0.0, 10.0),
        "legendary": _float_between(raw.get("legendary"), DEFAULT_RARITY_THRESHOLDS["legendary"], 0.0, 10.0),
    }
    last = 0.0
    for key in ("uncommon", "rare", "epic", "legendary"):
        normalized[key] = max(last, normalized[key])
        last = normalized[key]
    return normalized


def evaluation_quality_score(evaluation: Evaluation) -> float | None:
    if not isinstance(evaluation.subscores, dict):
        return None
    quality = evaluation.subscores.get("ao3_studio_quality")
    if isinstance(quality, dict):
        value = quality.get("quality_score")
    else:
        value = quality
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class IdentityService:
    def __init__(self, identities: IdentityRepository) -> None:
        self.identities = identities

    def bootstrap(self):
        identity = self.identities.get_or_create_local()
        identity.last_seen_at = utc_now_iso()
        self.identities.save_local(identity)
        return identity

    def remote_identity(self) -> RemoteIdentity:
        return self.identities.get_remote()

    def save_remote_identity(self, identity: RemoteIdentity) -> None:
        self.identities.save_remote(identity)

    def update_display_name(self, display_name: str) -> None:
        identity = self.identities.get_or_create_local()
        identity.display_name = display_name.strip() or None
        identity.last_seen_at = utc_now_iso()
        self.identities.save_local(identity)


class ModeService:
    def __init__(self, settings: SettingsRepository, identities: IdentityRepository) -> None:
        self.settings = settings
        self.identities = identities

    def current_mode(self) -> RuntimeMode:
        return self.settings.get_mode()

    def set_mode(self, mode: RuntimeMode) -> None:
        self.settings.set_mode(mode)

    def status_badge(self) -> str:
        return ModePolicy.status_badge(self.current_mode())

    def shared_widgets_visible(self) -> bool:
        return ModePolicy.shared_widgets_visible(self.current_mode())

    def admin_widgets_visible(self) -> bool:
        return ModePolicy.admin_widgets_visible(self.current_mode(), self.identities.get_remote())

    def overlay_visibility(self) -> OverlayVisibility:
        return self.settings.get_overlay_visibility()

    def set_overlay_visibility(self, visibility: OverlayVisibility) -> None:
        self.settings.set_overlay_visibility(visibility)


class PreferencesService:
    def __init__(self, settings: SettingsRepository) -> None:
        self.settings = settings

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.settings.set(key, value)


class FandomService:
    def __init__(
        self,
        fandoms: FandomRepository,
        characters: CharacterProfileRepository,
        tag_catalog: FandomTagCatalogRepository,
        settings: SettingsRepository,
        ao3_client: Any,
    ) -> None:
        self.fandoms = fandoms
        self.characters = characters
        self.tag_catalog = tag_catalog
        self.settings = settings
        self.ao3_client = ao3_client

    def ensure_default(self) -> FandomProfile:
        active = self.active_profile()
        if active:
            return active
        existing = self.fandoms.get_by_tag(DEFAULT_FANDOM)
        if existing:
            self.fandoms.select(existing.fandom_key)
            self.settings.set("active_fandom_key", existing.fandom_key)
            return existing
        now = utc_now_iso()
        profile = FandomProfile(
            fandom_key=fandom_key(DEFAULT_FANDOM),
            tag=DEFAULT_FANDOM,
            display_name="Life is Strange",
            color="#58a6ff",
            default_filter=default_fandom_filter(DEFAULT_FANDOM),
            created_at=now,
            updated_at=now,
            selected_at=now,
        )
        self.fandoms.save(profile)
        self.settings.set("active_fandom_key", profile.fandom_key)
        return profile

    def active_profile(self) -> FandomProfile | None:
        key = str(self.settings.get("active_fandom_key", "") or "")
        if key:
            profile = self.fandoms.get(key)
            if profile:
                return profile
        profiles = self.fandoms.list()
        return profiles[0] if profiles else None

    def select(self, fandom_key: str) -> FandomProfile:
        profile = self.fandoms.get(fandom_key)
        if not profile:
            raise ValueError("Fandom profile not found.")
        self.fandoms.select(fandom_key)
        self.settings.set("active_fandom_key", fandom_key)
        return profile

    def list_profiles(self) -> list[FandomProfile]:
        self.ensure_default()
        return self.fandoms.list()

    def save_profile(self, profile: FandomProfile) -> FandomProfile:
        now = utc_now_iso()
        if not profile.fandom_key:
            profile.fandom_key = fandom_key(profile.tag)
        if not profile.display_name:
            profile.display_name = short_fandom_name(profile.tag)
        if not profile.default_filter:
            profile.default_filter = default_fandom_filter(profile.tag)
        profile.created_at = profile.created_at or now
        profile.updated_at = now
        self.fandoms.save(profile)
        if not self.settings.get("active_fandom_key"):
            self.settings.set("active_fandom_key", profile.fandom_key)
        return profile

    def suggest_fandoms(self, query: str, limit: int = 12) -> list[FandomSuggestion]:
        clean_query = " ".join(str(query or "").split())
        if not clean_query:
            return []
        self.ensure_fandom_directory_sources()
        return self.fandoms.suggest_directory_fandoms(clean_query, limit)

    def ensure_fandom_directory_sources(self) -> list[FandomDirectorySource]:
        existing = {source.media_key: source for source in self.fandoms.list_directory_sources()}
        for media_key, label, url, color, enabled in DEFAULT_FANDOM_DIRECTORY_SOURCES:
            if media_key in existing:
                continue
            source = FandomDirectorySource(
                media_key=media_key,
                label=label,
                url=url,
                color=color,
                enabled=enabled,
            )
            self.fandoms.upsert_directory_source(source)
        return self.fandoms.list_directory_sources()

    def refresh_fandom_directory_sources(self) -> ServiceResult:
        self.ensure_fandom_directory_sources()
        if not hasattr(self.ao3_client, "fetch_media_categories"):
            return ServiceResult(False, "AO3 media categories are not available.")
        try:
            remote_sources = list(self.ao3_client.fetch_media_categories())
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(False, f"AO3 media categories failed: {exc}")
        current = {source.media_key: source for source in self.fandoms.list_directory_sources()}
        default_by_key = {
            media_key: FandomDirectorySource(media_key, label, url, color, enabled)
            for media_key, label, url, color, enabled in DEFAULT_FANDOM_DIRECTORY_SOURCES
        }
        added = 0
        for remote in remote_sources:
            existing = current.get(remote.media_key)
            fallback = default_by_key.get(remote.media_key)
            source = FandomDirectorySource(
                media_key=remote.media_key,
                label=fallback.label if fallback else remote.label,
                url=remote.url,
                color=(existing.color if existing else fallback.color if fallback else remote.color or "#58a6ff"),
                enabled=bool(existing.enabled if existing else fallback.enabled if fallback else False),
                cached_at=existing.cached_at if existing else None,
            )
            if not existing:
                added += 1
            self.fandoms.upsert_directory_source(source)
        sources = self.fandoms.list_directory_sources()
        return ServiceResult(True, f"Found {len(sources)} AO3 fandom categories.", payload=sources, )

    def update_fandom_directory_source(
        self,
        media_key: str,
        *,
        enabled: bool | None = None,
        color: str | None = None,
    ) -> ServiceResult:
        sources = {source.media_key: source for source in self.ensure_fandom_directory_sources()}
        source = sources.get(str(media_key or ""))
        if not source:
            return ServiceResult(False, "Fandom category not found.")
        clean_color = source.color
        if color is not None:
            clean_color = self._normalize_hex_color(color)
            if color and not clean_color:
                return ServiceResult(False, "Fandom category color must be a hex color.")
            clean_color = clean_color or source.color or "#58a6ff"
        updated = FandomDirectorySource(
            media_key=source.media_key,
            label=source.label,
            url=source.url,
            color=clean_color,
            enabled=source.enabled if enabled is None else bool(enabled),
            cached_at=source.cached_at,
            updated_at=source.updated_at,
            cached_count=source.cached_count,
        )
        self.fandoms.upsert_directory_source(updated)
        return ServiceResult(True, "Fandom category updated.", payload=updated)

    def cache_fandom_directory_sources(self, media_keys: list[str] | None = None) -> ServiceResult:
        sources = self.ensure_fandom_directory_sources()
        wanted = {str(key) for key in media_keys or [] if str(key).strip()}
        selected = [source for source in sources if source.media_key in wanted] if wanted else [source for source in sources if source.enabled]
        if not selected:
            return ServiceResult(False, "Select at least one fandom category to cache.")
        if not hasattr(self.ao3_client, "fetch_media_fandoms"):
            return ServiceResult(False, "AO3 media fandom fetch is not available.")
        added = 0
        total = 0
        failed: list[str] = []
        for source in selected:
            try:
                suggestions = list(
                    self.ao3_client.fetch_media_fandoms(source.media_key, source.label, source.url, source.color or "#58a6ff")
                )
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{source.label}: {exc}")
                continue
            self.fandoms.upsert_directory_source(source)
            added += self.fandoms.cache_directory_fandoms(source.media_key, suggestions)
            total += len(suggestions)
        if failed:
            message = f"Cached {total:,} fandom tags; {added:,} new. Failed: {'; '.join(failed[:2])}"
            return ServiceResult(False, message, payload={"added": added, "total": total, "failed": failed})
        return ServiceResult(True, f"Cached {total:,} fandom tags; {added:,} new.", payload={"added": added, "total": total})

    def delete_fandom_directory_cache(self, media_key: str) -> ServiceResult:
        sources = {source.media_key: source for source in self.ensure_fandom_directory_sources()}
        source = sources.get(str(media_key or ""))
        if not source:
            return ServiceResult(False, "Fandom category not found.")
        deleted = self.fandoms.delete_directory_cache(source.media_key)
        return ServiceResult(True, f"Deleted {deleted:,} cached {source.label} fandom tags.", payload={"deleted": deleted})

    def create_from_suggestion(self, suggestion: FandomSuggestion) -> FandomProfile:
        tag = str(suggestion.tag or suggestion.label or "").strip()
        if not tag:
            raise ValueError("Fandom tag is required.")
        existing = self.fandoms.get_by_tag(tag)
        if existing:
            self.select(existing.fandom_key)
            return existing
        now = utc_now_iso()
        profile = FandomProfile(
            fandom_key=fandom_key(tag),
            tag=tag,
            display_name=short_fandom_name(str(suggestion.label or tag)),
            color="#58a6ff",
            default_filter=default_fandom_filter(tag),
            created_at=now,
            updated_at=now,
            selected_at=now,
        )
        self.fandoms.save(profile)
        self.select(profile.fandom_key)
        return profile

    @staticmethod
    def _normalize_hex_color(value: str | None) -> str:
        clean = str(value or "").strip()
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", clean):
            return f"#{clean.lstrip('#').lower()}"
        if re.fullmatch(r"#?[0-9a-fA-F]{3}", clean):
            raw = clean.lstrip("#").lower()
            return "#" + "".join(char * 2 for char in raw)
        return ""

    def export_fandom_backup(self, fandom_key: str) -> tuple[str, bytes]:
        return self.fandoms.export_backup_zip(fandom_key)

    def import_fandom_backup(self, zip_bytes: bytes) -> FandomProfile:
        profile = self.fandoms.import_backup_zip(zip_bytes)
        self.select(profile.fandom_key)
        return profile

    def delete_fandoms_after_backup(self, fandom_keys: list[str]) -> ServiceResult:
        selected = [key for key in dict.fromkeys(str(item) for item in fandom_keys) if key.strip()]
        if not selected:
            return ServiceResult(False, "Select one or more fandoms first.")
        deleted = self.fandoms.delete_clean(selected)
        active_key = str(self.settings.get("active_fandom_key", "") or "")
        if active_key in selected or not self.active_profile():
            profiles = self.fandoms.list()
            if profiles:
                self.select(profiles[0].fandom_key)
            else:
                self.settings.set("active_fandom_key", "")
                self.ensure_default()
        return ServiceResult(True, f"Deleted {deleted} fandom{'s' if deleted != 1 else ''}.")

    def save_filter_preferences(self, fandom_key: str, filter_state: dict[str, Any]) -> ServiceResult:
        profile = self.fandoms.get(fandom_key)
        if not profile:
            return ServiceResult(False, "Fandom profile not found.")
        profile.default_filter = filter_state
        profile.updated_at = utc_now_iso()
        self.fandoms.save(profile)
        return ServiceResult(True, "Fandom filter preferences saved.")

    def list_characters(self, fandom_key: str) -> list[CharacterProfile]:
        return self.characters.list_for_fandom(fandom_key)

    def save_character(
        self,
        *,
        fandom_key: str,
        name: str,
        color: str,
        full_name: str = "",
        avatar_url: str = "",
        tag_urls: list[str] | None = None,
        notes: str = "",
        reader_style: dict[str, Any] | None = None,
        character_id: str | None = None,
    ) -> ServiceResult:
        if not name.strip():
            return ServiceResult(False, "Character name is required.")
        now = utc_now_iso()
        self.characters.save(
            CharacterProfile(
                id=character_id or str(uuid.uuid4()),
                fandom_key=fandom_key,
                name=name.strip(),
                full_name=full_name.strip() or name.strip(),
                color=color.strip() or "#58a6ff",
                avatar_url=avatar_url.strip() or None,
                tag_urls=[url.strip() for url in (tag_urls or []) if url.strip()],
                notes=notes.strip() or None,
                reader_style=normalize_character_reader_style(reader_style),
                created_at=now,
                updated_at=now,
            )
        )
        return ServiceResult(True, "Character saved.")

    def delete_character(self, character_id: str) -> None:
        self.characters.delete(character_id)

    def tag_suggestions(self, fandom_key: str, query: str = "", limit: int = 16, category: str | None = None):
        return self.tag_catalog.suggest(fandom_key, query, limit, category)

    def tag_catalog_count(self, fandom_key: str) -> int:
        return self.tag_catalog.count(fandom_key)

    def refresh_tag_catalog(self, profile: FandomProfile) -> ServiceResult:
        urls = [f"{AO3_BASE_URL}/tags/{quote(profile.tag, safe='')}"]
        relationship_index = f"{AO3_BASE_URL}/fandoms/{quote(profile.tag, safe='')}"
        urls.append(relationship_index)
        items = []
        for url in urls:
            try:
                items.extend(self.ao3_client.fetch_fandom_tag_catalog(url, profile.fandom_key))
            except Exception as exc:  # noqa: BLE001
                if not items:
                    return ServiceResult(False, f"AO3 tag catalog refresh failed: {exc}")
        unique: dict[tuple[str, str], Any] = {}
        for item in items:
            unique[(item.tag_text.lower(), item.category)] = item
        self.tag_catalog.replace_for_fandom(profile.fandom_key, list(unique.values()))
        return ServiceResult(True, f"Saved {len(unique)} AO3 tag suggestions for {profile.display_name}.")


class StyleService:
    def __init__(
        self,
        settings: SettingsRepository,
        fandom_styles: FandomStyleRepository,
    ) -> None:
        self.settings = settings
        self.fandom_styles = fandom_styles

    def global_settings(self) -> dict[str, Any]:
        return normalize_reader_style(self.settings.get(STYLE_SETTINGS_KEY, DEFAULT_READER_STYLE))

    def save_global_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_reader_style(settings)
        self.settings.set(STYLE_SETTINGS_KEY, normalized)
        return normalized

    def override_sections(self, override: FandomStyleOverride | None) -> dict[str, bool]:
        if not override:
            return normalize_style_override_sections(None, False)
        return normalize_style_override_sections(
            (override.settings or {}).get(STYLE_OVERRIDE_SECTIONS_KEY),
            bool(override.enabled),
        )

    def fandom_override(self, fandom_key: str) -> FandomStyleOverride:
        existing = self.fandom_styles.get(fandom_key)
        if existing:
            existing.settings = normalize_reader_style(existing.settings, self.global_settings())
            existing.settings[STYLE_OVERRIDE_SECTIONS_KEY] = self.override_sections(existing)
            existing.enabled = any(existing.settings[STYLE_OVERRIDE_SECTIONS_KEY].values())
            return existing
        return FandomStyleOverride(
            fandom_key=fandom_key,
            enabled=False,
            settings={
                **self.global_settings(),
                STYLE_OVERRIDE_SECTIONS_KEY: normalize_style_override_sections(None, False),
            },
            updated_at=utc_now_iso(),
        )

    def save_fandom_override(self, fandom_key: str, enabled: bool, settings: dict[str, Any]) -> FandomStyleOverride:
        sections = normalize_style_override_sections(settings.get(STYLE_OVERRIDE_SECTIONS_KEY), enabled)
        normalized = normalize_reader_style(settings, self.global_settings())
        normalized[STYLE_OVERRIDE_SECTIONS_KEY] = sections
        override = FandomStyleOverride(
            fandom_key=fandom_key,
            enabled=any(sections.values()),
            settings=normalized,
            updated_at=utc_now_iso(),
        )
        self.fandom_styles.save(override)
        return override

    def effective_settings(self, fandom_key: str | None = None) -> dict[str, Any]:
        global_settings = self.global_settings()
        if not fandom_key:
            return global_settings
        override = self.fandom_styles.get(fandom_key)
        sections = self.override_sections(override)
        if not override or not any(sections.values()):
            return global_settings
        override_settings = normalize_reader_style(override.settings, global_settings)
        effective = dict(global_settings)
        if sections.get("font"):
            for key in STYLE_FONT_KEYS:
                effective[key] = override_settings[key]
        if sections.get("rarity"):
            for key in STYLE_RARITY_KEYS:
                effective[key] = override_settings[key]
        return normalize_reader_style(effective)

    def rarity_thresholds(self) -> dict[str, float]:
        return normalize_rarity_thresholds(self.settings.get(RARITY_THRESHOLDS_KEY, DEFAULT_RARITY_THRESHOLDS))

    def save_rarity_thresholds(self, thresholds: dict[str, Any]) -> dict[str, float]:
        normalized = normalize_rarity_thresholds(thresholds)
        self.settings.set(RARITY_THRESHOLDS_KEY, normalized)
        return normalized

    def adjust_font_size(self, fandom_key: str | None, direction: int) -> dict[str, Any]:
        effective = self.effective_settings(fandom_key)
        step = _float_between(effective.get("font_wheel_step_px"), 0.5, 0.5, 10.0)
        next_size = _float_between(effective.get("reader_font_size", 16.5), 16.5, 8.0, 48.0) + (step * direction)
        effective["reader_font_size"] = _float_between(next_size, 16.5, 8.0, 48.0)
        if fandom_key:
            override = self.fandom_styles.get(fandom_key)
            sections = self.override_sections(override)
            if override and sections.get("font"):
                saved = dict(override.settings or {})
                saved.update(
                    {
                        "preview_font_family": effective["preview_font_family"],
                        "reader_font_size": effective["reader_font_size"],
                        "font_wheel_step_px": effective["font_wheel_step_px"],
                        STYLE_OVERRIDE_SECTIONS_KEY: sections,
                    }
                )
                self.save_fandom_override(fandom_key, any(sections.values()), saved)
                return effective
        self.save_global_settings(effective)
        return effective


class RarityService:
    def __init__(
        self,
        rarities: RarityRepository,
        identities: IdentityRepository,
        style_service: StyleService,
    ) -> None:
        self.rarities = rarities
        self.identities = identities
        self.style_service = style_service

    def tier_for_quality(self, score: float | None) -> RarityTier:
        if score is None:
            return RarityTier.COMMON
        score = _float_between(score, 0.0, 0.0, 10.0)
        thresholds = self.style_service.rarity_thresholds()
        if score >= thresholds["legendary"]:
            return RarityTier.LEGENDARY
        if score >= thresholds["epic"]:
            return RarityTier.EPIC
        if score >= thresholds["rare"]:
            return RarityTier.RARE
        if score >= thresholds["uncommon"]:
            return RarityTier.UNCOMMON
        return RarityTier.COMMON

    def get(self, work_id: str) -> WorkRarity:
        identity = self.identities.get_or_create_local()
        return self.rarities.get(work_id, identity.local_user_id) or WorkRarity(
            work_id=work_id,
            local_user_id=identity.local_user_id,
        )

    def get_many(self, work_ids: list[str]) -> dict[str, WorkRarity]:
        identity = self.identities.get_or_create_local()
        existing = self.rarities.list_for_works(work_ids, identity.local_user_id)
        return {
            str(work_id): existing.get(str(work_id))
            or WorkRarity(work_id=str(work_id), local_user_id=identity.local_user_id)
            for work_id in work_ids
            if str(work_id).strip()
        }

    def effective_tier(self, work_id: str) -> RarityTier:
        return self.get(work_id).effective_rarity

    def has_assigned_rarity(self, work_id: str) -> bool:
        rarity = self.get(work_id)
        return rarity.manual_rarity is not None or rarity.computed_rarity is not None

    def set_manual(self, work_id: str, rarity: RarityTier | str | None) -> WorkRarity:
        identity = self.identities.get_or_create_local()
        if rarity is None:
            rarity_value = None
        elif isinstance(rarity, RarityTier):
            rarity_value = rarity.value
        else:
            rarity_value = str(rarity)
        self.rarities.set_manual(work_id, identity.local_user_id, rarity_value, utc_now_iso() if rarity_value else None)
        return self.get(work_id)

    def refresh_from_evaluation(self, evaluation: Evaluation) -> WorkRarity | None:
        score = evaluation_quality_score(evaluation)
        if score is None:
            return None
        existing = self.rarities.get(evaluation.work_id, evaluation.local_user_id) or WorkRarity(
            work_id=evaluation.work_id,
            local_user_id=evaluation.local_user_id,
        )
        existing.computed_quality_score = score
        existing.computed_rarity = self.tier_for_quality(score)
        existing.computed_schema_key = evaluation.schema_key
        existing.computed_schema_version = evaluation.schema_version
        existing.computed_evaluation_id = evaluation.id
        existing.computed_at = utc_now_iso()
        self.rarities.upsert(existing)
        return existing


class SchemaService:
    def __init__(self, schemas: EvaluationSchemaRepository) -> None:
        self.schemas = schemas

    def ensure_default_schema(self) -> EvaluationSchema:
        active = self.schemas.active()
        if active:
            return active
        now = utc_now_iso()
        schema = EvaluationSchema(
            schema_key="local_default_v1",
            name="Local Default",
            version="1.0.0",
            label="Local Default",
            description="A starter 1-10 evaluator for story fit and quality.",
            dimensions=[
                {"key": "story_fit", "label": "Story Fit", "description": "How well the work matches your tastes.", "weight": 1.0, "polarity": "positive"},
                {"key": "craft", "label": "Craft", "description": "Prose, pacing, structure, and clarity.", "weight": 1.0, "polarity": "positive"},
                {"key": "emotional_pull", "label": "Emotional Pull", "description": "How strongly it makes you want to continue.", "weight": 1.0, "polarity": "positive"},
            ],
            prompt_template=(
                "Evaluate this AO3 work for a private reading database. Score each dimension from 1 to 10. "
                "Use the work metadata, summary, author, tags, and any available notes. Be concise and practical."
            ),
            is_active=True,
            created_at=now,
        )
        schema.dimensions = [
            dimension if not isinstance(dimension, dict) else _dimension_from_dict(dimension)
            for dimension in schema.dimensions
        ]
        self.schemas.save(schema)
        return schema

    def list_schemas(self) -> list[EvaluationSchema]:
        self.ensure_default_schema()
        return self.schemas.list()

    def active_schema(self) -> EvaluationSchema:
        active = self.schemas.active()
        return active or self.ensure_default_schema()

    def set_active_schema(self, schema_key: str) -> ServiceResult:
        schema = self.schemas.get(schema_key)
        if not schema:
            return ServiceResult(False, "Schema not found.")
        schema.is_active = True
        self.schemas.save(schema)
        return ServiceResult(True, f"Active schema set to {schema.name}.")

    def save_schema(self, schema: EvaluationSchema) -> ServiceResult:
        existing = self.schemas.get(schema.schema_key)
        if existing and SchemaPolicy.is_locked(existing):
            return ServiceResult(False, "Shared-compatible schemas are locked. Create a new local schema version instead.")
        self.schemas.save(schema)
        return ServiceResult(True, "Schema saved.")

    def validate_scores(self, schema: EvaluationSchema, scores: dict[str, Any]):
        return SchemaPolicy.validate_scores(schema, scores)


class EvaluationService:
    def __init__(
        self,
        evaluations: EvaluationRepository,
        schemas: EvaluationSchemaRepository,
        identities: IdentityRepository,
        works: WorkRepository,
        tags: TagRepository,
        model_provider: ModelEvaluationProvider | None = None,
        rarity_service: RarityService | None = None,
    ) -> None:
        self.evaluations = evaluations
        self.schemas = schemas
        self.identities = identities
        self.works = works
        self.tags = tags
        self.model_provider = model_provider
        self.rarity_service = rarity_service

    def save_manual(
        self,
        *,
        work_id: str,
        schema_key: str,
        scores: dict[str, Any],
        notes_markdown: str = "",
        evidence: dict[str, Any] | None = None,
        status: EvaluationStatus = EvaluationStatus.COMPLETE,
    ) -> EvaluationResult:
        identity = self.identities.get_or_create_local()
        schema = self.schemas.get(schema_key)
        if not schema:
            return EvaluationResult(False, "Schema not found.", errors=["Schema not found."])
        validation = SchemaPolicy.validate_scores(schema, scores)
        if not validation.valid:
            return EvaluationResult(False, "Scores need attention.", errors=validation.errors)
        now = utc_now_iso()
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            work_id=work_id,
            local_user_id=identity.local_user_id,
            schema_key=schema.schema_key,
            schema_version=schema.version,
            scores=scores,
            subscores={"ao3_studio_quality": SchemaPolicy.score_breakdown(schema, scores)},
            notes_markdown=notes_markdown,
            evidence=evidence,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.evaluations.save(evaluation)
        if self.rarity_service:
            self.rarity_service.refresh_from_evaluation(evaluation)
        return EvaluationResult(True, "Evaluation saved.", evaluation=evaluation)

    def evaluate_with_lm_studio(self, work_id: str, schema_key: str | None = None) -> EvaluationResult:
        if not self.model_provider:
            return EvaluationResult(False, "LM Studio provider is not configured.", errors=["No model provider."])
        work = self.works.get(work_id)
        if not work:
            return EvaluationResult(False, "Work not found.", errors=["Work not found."])
        schema = self.schemas.get(schema_key or "") if schema_key else self.schemas.active()
        if not schema:
            return EvaluationResult(False, "Schema not found.", errors=["Schema not found."])
        try:
            result = self.model_provider.evaluate_work(
                work=work,
                tags=self.tags.list_for_work(work.work_id),
                schema=schema,
                prompt_template=schema.prompt_template,
            )
        except Exception as exc:  # noqa: BLE001 - surface local model errors to the UI
            return EvaluationResult(
                False,
                f"LM Studio evaluation failed: {exc}",
                errors=[str(exc)],
                payload={"fatal": self._model_exception_is_fatal(exc)},
            )
        scores = result.get("scores", {})
        validation = SchemaPolicy.validate_scores(schema, scores)
        if not validation.valid:
            return EvaluationResult(False, "LM Studio returned invalid scores.", errors=validation.errors)
        identity = self.identities.get_or_create_local()
        now = utc_now_iso()
        subscores = result.get("subscores") if isinstance(result.get("subscores"), dict) else {}
        subscores["ao3_studio_quality"] = SchemaPolicy.score_breakdown(schema, scores)
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            work_id=work_id,
            local_user_id=identity.local_user_id,
            schema_key=schema.schema_key,
            schema_version=schema.version,
            scores=scores,
            subscores=subscores,
            notes_markdown=result.get("notes_markdown") or result.get("notes") or "",
            evidence=result.get("evidence"),
            model_name=str(result.get("model_name") or ""),
            model_prompt_hash=stable_hash(schema.prompt_template),
            status=EvaluationStatus.COMPLETE,
            created_at=now,
            updated_at=now,
        )
        self.evaluations.save(evaluation)
        if self.rarity_service:
            self.rarity_service.refresh_from_evaluation(evaluation)
        return EvaluationResult(True, "LM Studio evaluation saved.", evaluation=evaluation)

    def evaluate_sample_with_lm_studio(
        self,
        work_id: str,
        schema_key: str,
        sample: WorkEvaluationSample,
    ) -> EvaluationResult:
        if not self.model_provider:
            return EvaluationResult(False, "LM Studio provider is not configured.", errors=["No model provider."], payload={"fatal": True})
        work = self.works.get(work_id)
        if not work:
            return EvaluationResult(False, "Work not found.", errors=["Work not found."])
        schema = self.schemas.get(schema_key)
        if not schema:
            return EvaluationResult(False, "Schema not found.", errors=["Schema not found."], payload={"fatal": True})
        try:
            result = self.model_provider.evaluate_sampled_work(
                work=work,
                tags=self.tags.list_for_work(work.work_id),
                schema=schema,
                prompt_template=schema.prompt_template,
                sample=sample,
            )
        except Exception as exc:  # noqa: BLE001 - surface local model errors to the queue runner
            return EvaluationResult(
                False,
                f"LM Studio evaluation failed: {exc}",
                errors=[str(exc)],
                payload={"fatal": self._model_exception_is_fatal(exc)},
            )
        scores = result.get("scores", {})
        validation = SchemaPolicy.validate_scores(schema, scores)
        if not validation.valid:
            return EvaluationResult(False, "LM Studio returned invalid scores.", errors=validation.errors)
        identity = self.identities.get_or_create_local()
        now = utc_now_iso()
        subscores = result.get("subscores") if isinstance(result.get("subscores"), dict) else {}
        subscores["ao3_studio_quality"] = SchemaPolicy.score_breakdown(schema, scores)
        prompt_hash_payload = {
            "prompt_template": schema.prompt_template,
            "schema_key": schema.schema_key,
            "schema_version": schema.version,
            "sample": sample.chapter_scope,
        }
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            work_id=work_id,
            local_user_id=identity.local_user_id,
            schema_key=schema.schema_key,
            schema_version=schema.version,
            scores=scores,
            subscores=subscores,
            notes_markdown=result.get("notes_markdown") or result.get("notes") or "",
            evidence=result.get("evidence"),
            model_name=str(result.get("model_name") or ""),
            model_prompt_hash=stable_hash(json.dumps(prompt_hash_payload, sort_keys=True)),
            chapter_scope=sample.chapter_scope,
            status=EvaluationStatus.COMPLETE,
            created_at=now,
            updated_at=now,
        )
        self.evaluations.save(evaluation)
        if self.rarity_service:
            self.rarity_service.refresh_from_evaluation(evaluation)
        return EvaluationResult(True, "LM Studio evaluation saved.", evaluation=evaluation)

    @staticmethod
    def _model_exception_is_fatal(exc: Exception) -> bool:
        module = type(exc).__module__
        if module.startswith("httpx"):
            return True
        if isinstance(exc, ValueError) and "LM Studio model" in str(exc):
            return True
        return False

    def list_for_work(self, work_id: str) -> list[Evaluation]:
        return self.evaluations.list_for_work(work_id)

    def latest_for_work(self, work_id: str, schema_key: str | None = None) -> Evaluation | None:
        identity = self.identities.get_or_create_local()
        return self.evaluations.latest_for_work(work_id, identity.local_user_id, schema_key)

    def latest_for_works(self, work_ids: list[str], schema_key: str | None = None) -> dict[str, Evaluation]:
        identity = self.identities.get_or_create_local()
        return self.evaluations.latest_for_works(work_ids, identity.local_user_id, schema_key)

    def count(self) -> int:
        return self.evaluations.count()

    def count_for_fandom(self, profile: FandomProfile) -> int:
        identity = self.identities.get_or_create_local()
        return self.evaluations.count_for_fandom(identity.local_user_id, profile.fandom_key, profile.tag)


@dataclass(slots=True)
class EvaluationBatchSummary:
    batch: EvaluationBatch
    work_set: WorkSet
    schema: EvaluationSchema | None
    total_count: int
    pending_count: int
    running_count: int
    failed_count: int
    skipped_count: int
    completed_count: int

    @property
    def active_count(self) -> int:
        return self.pending_count + self.running_count + self.failed_count + self.skipped_count


@dataclass(slots=True)
class EvaluationSchemaSlot:
    work_set: WorkSet
    schema: EvaluationSchema
    batch: EvaluationBatch | None
    summary: EvaluationBatchSummary | None
    state: str
    total_count: int
    pending_count: int = 0
    running_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    completed_count: int = 0

    @property
    def active_count(self) -> int:
        return self.pending_count + self.running_count + self.failed_count + self.skipped_count

    @property
    def batch_id(self) -> str:
        return self.batch.id if self.batch else ""

    @property
    def is_empty(self) -> bool:
        return self.batch is None and self.completed_count <= 0 and self.active_count <= 0


@dataclass(slots=True)
class EvaluationClusterSummary:
    work_set: WorkSet
    slots: list[EvaluationSchemaSlot]
    total_count: int

    @property
    def active_count(self) -> int:
        return sum(slot.active_count for slot in self.slots)

    @property
    def completed_count(self) -> int:
        return sum(slot.completed_count for slot in self.slots)


@dataclass(slots=True)
class EvaluationBatchWorks:
    batch: EvaluationBatch
    work_set: WorkSet
    schema: EvaluationSchema
    works: list[Work]
    tags_by_work: dict[str, list[WorkTag]]
    latest_evaluations: dict[str, Evaluation]
    summary: EvaluationBatchSummary | None = None


@dataclass(slots=True)
class QueueClusterTarget:
    work_set_id: str
    name: str
    active_count: int
    completed_count: int


@dataclass(slots=True)
class QueueEvaluationConfig:
    include_metadata: bool = True
    include_tags: bool = True
    start_chapter: int = 1
    chapter_window: int = 3
    target_words: int = 5000
    max_words: int = 6500
    skip_empty_chapters: bool = True


@dataclass(slots=True)
class QueueRunStats:
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False
    fatal: bool = False


class EvaluationQueueService:
    def __init__(
        self,
        queue: EvaluationQueueRepository,
        batches: EvaluationBatchRepository,
        work_sets: WorkSetRepository,
        works: WorkRepository,
        tags: TagRepository,
        evaluations: EvaluationRepository,
        schemas: EvaluationSchemaRepository,
        reading: ReadingStateRepository,
        identities: IdentityRepository,
        fandoms: FandomRepository,
    ) -> None:
        self.queue = queue
        self.batches = batches
        self.work_sets = work_sets
        self.works = works
        self.tags = tags
        self.evaluations = evaluations
        self.schemas = schemas
        self.reading = reading
        self.identities = identities
        self.fandoms = fandoms

    def enqueue(
        self,
        work_id: str,
        reason: str = "",
        priority: int = 100,
        *,
        batch_id: str | None = None,
        schema_key: str | None = None,
        fandom_key_value: str | None = None,
    ) -> EvaluationQueueItem:
        schema = self._schema(schema_key)
        if not batch_id:
            batch = self._manual_batch(fandom_key_value or self._active_fandom_key(), schema.schema_key, [work_id])
            batch_id = batch.id
        existing_item = self.active_item_for_work(work_id, batch_id=batch_id, schema_key=schema.schema_key)
        if existing_item:
            return existing_item
        now = utc_now_iso()
        item = EvaluationQueueItem(
            id=str(uuid.uuid4()),
            work_id=work_id,
            reason=reason or None,
            priority=priority,
            queue_status=QueueStatus.QUEUED,
            requested_at=now,
            batch_id=batch_id,
            schema_key=schema.schema_key,
        )
        self.queue.add(item)
        identity = self.identities.get_or_create_local()
        existing = self.reading.get(work_id, identity.local_user_id)
        self.reading.upsert(
            ReadingState(
                work_id=work_id,
                local_user_id=identity.local_user_id,
                state=ReadingStatus.QUEUED,
                last_position_ref=existing.last_position_ref if existing else None,
                last_opened_at=existing.last_opened_at if existing else None,
                personal_priority=existing.personal_priority if existing else None,
                personal_labels=existing.personal_labels if existing else [],
                private_notes=existing.private_notes if existing else None,
            )
        )
        return item

    def list(self, status: QueueStatus | None = None, batch_id: str | None = None) -> list[EvaluationQueueItem]:
        return self.queue.list(status=status, batch_id=batch_id)

    def count_for_fandom(self, fandom_key: str, status: QueueStatus | None = QueueStatus.QUEUED) -> int:
        count = 0
        batch_cache: dict[str, EvaluationBatch | None] = {}
        for item in self.queue.list(status=status):
            batch_id = str(item.batch_id or "")
            if not batch_id:
                continue
            if batch_id not in batch_cache:
                batch_cache[batch_id] = self.batches.get(batch_id)
            batch = batch_cache[batch_id]
            if batch and batch.fandom_key == fandom_key:
                count += 1
        return count

    def active_item_for_work(
        self,
        work_id: str,
        *,
        batch_id: str | None = None,
        schema_key: str | None = None,
    ) -> EvaluationQueueItem | None:
        active_statuses = {QueueStatus.QUEUED, QueueStatus.RUNNING}
        for item in self.queue.list(batch_id=batch_id):
            if item.work_id == work_id and item.queue_status in active_statuses:
                if schema_key and item.schema_key and item.schema_key != schema_key:
                    continue
                return item
        return None

    def is_active_for_work(self, work_id: str) -> bool:
        return self.active_item_for_work(work_id) is not None

    def active_work_ids(self) -> set[str]:
        active_items = [
            item
            for item in self.queue.list()
            if item.queue_status in {QueueStatus.QUEUED, QueueStatus.RUNNING}
        ]
        if not active_items:
            return set()
        identity = self.identities.get_or_create_local()
        completed: set[str] = set()
        by_schema: dict[str, list[str]] = {}
        schema_missing: set[str] = set()
        for item in active_items:
            if item.schema_key:
                by_schema.setdefault(item.schema_key, []).append(item.work_id)
            else:
                schema_missing.add(item.work_id)
        for schema_key, work_ids in by_schema.items():
            latest = self.evaluations.latest_for_works(work_ids, identity.local_user_id, schema_key)
            completed.update(
                work_id
                for work_id, evaluation in latest.items()
                if evaluation.status is EvaluationStatus.COMPLETE
            )
        return {item.work_id for item in active_items if item.work_id not in completed or item.work_id in schema_missing}

    def update_status(self, item_id: str, status: QueueStatus, error_text: str | None = None) -> None:
        self.queue.update_status(item_id, status, error_text)

    def delete(self, item_id: str) -> None:
        self.queue.delete(item_id)

    def delete_many(self, item_ids: list[str]) -> int:
        deleted = 0
        for item_id in item_ids:
            if item_id:
                self.queue.delete(item_id)
                deleted += 1
        return deleted

    def save_page_as_evaluation_queue(
        self,
        *,
        fandom_key: str,
        name: str,
        filter_state: dict[str, Any],
        source_url: str,
        work_ids: list[str],
        page_number: int,
        schema_key: str | None = None,
    ) -> ServiceResult:
        clean_name = (name or "").strip()
        if not clean_name:
            return ServiceResult(False, "Queue needs a name.")
        schema = self._schema(schema_key)
        signature = filter_signature(filter_state)
        now = utc_now_iso()
        existing = self.work_sets.get_by_name(fandom_key, clean_name)
        saved_filter_state = dict(filter_state)
        if existing and isinstance(existing.filter_state.get("_cluster_meta"), dict):
            saved_filter_state["_cluster_meta"] = dict(existing.filter_state["_cluster_meta"])
        work_set = existing or WorkSet(
            id=str(uuid.uuid4()),
            fandom_key=fandom_key,
            name=clean_name,
            filter_state=saved_filter_state,
            filter_signature=signature,
            created_at=now,
            updated_at=now,
        )
        work_set.filter_state = saved_filter_state
        work_set.filter_signature = signature
        self.work_sets.save(work_set)
        self.work_sets.record_page(work_set.id, page_number, source_url, work_ids, now)
        batch = self._ensure_batch(work_set, schema.schema_key)
        queued = self._queue_unevaluated_for_batch(batch, reason=f"Saved queue: {clean_name}")
        completed_count = self._completed_count_for_batch(batch)
        self._sync_batch_status(batch)
        return ServiceResult(
            True,
            f"Saved {clean_name}: queued {queued} work{'s' if queued != 1 else ''}"
            + (f"; {completed_count} already evaluated." if completed_count else "."),
            payload={"work_set": work_set, "batch": batch, "queued": queued, "completed": completed_count},
        )

    def list_queue_batches(self, fandom_key: str) -> list[EvaluationBatchSummary]:
        return [summary for summary in self._batch_summaries(fandom_key) if summary.active_count > 0]

    def list_evaluated_batches(self, fandom_key: str) -> list[EvaluationBatchSummary]:
        return [summary for summary in self._batch_summaries(fandom_key) if summary.completed_count > 0]

    def list_clusters_with_schema_slots(self, fandom_key: str, mode: str) -> list[EvaluationClusterSummary]:
        clusters = self._cluster_summaries(fandom_key)
        if mode == "evaluated":
            return [cluster for cluster in clusters if cluster.completed_count > 0]
        if mode == "queue":
            return [cluster for cluster in clusters if cluster.active_count > 0]
        return clusters

    def cluster_summary_for_work_set(self, work_set_id: str) -> EvaluationClusterSummary | None:
        work_set = self.work_sets.get(work_set_id)
        if not work_set:
            return None
        return self._cluster_summary(work_set, self.schemas.list(), self.identities.get_or_create_local().local_user_id)

    def schema_slot_for_work_set(self, work_set_id: str, schema_key: str) -> EvaluationSchemaSlot | None:
        cluster = self.cluster_summary_for_work_set(work_set_id)
        if not cluster:
            return None
        for slot in cluster.slots:
            if slot.schema.schema_key == schema_key:
                return slot
        return None

    def summary_for_batch(self, batch_id: str) -> EvaluationBatchSummary | None:
        batch = self.batches.get(batch_id)
        if not batch:
            return None
        return self._batch_summary(batch, self.identities.get_or_create_local().local_user_id)

    def pending_works_for_batch(self, batch_id: str) -> EvaluationBatchWorks | None:
        return self._works_for_batch(batch_id, completed=False)

    def evaluated_works_for_batch(self, batch_id: str) -> EvaluationBatchWorks | None:
        return self._works_for_batch(batch_id, completed=True)

    def cluster_targets(self, fandom_key: str) -> list[QueueClusterTarget]:
        return [
            QueueClusterTarget(
                work_set_id=cluster.work_set.id,
                name=cluster.work_set.name,
                active_count=cluster.active_count,
                completed_count=cluster.completed_count,
            )
            for cluster in self._cluster_summaries(fandom_key)
        ]

    def queue_work_to_named_cluster(
        self,
        *,
        fandom_key: str,
        cluster_name: str,
        work_id: str,
        schema_key: str | None = None,
    ) -> ServiceResult:
        clean_name = re.sub(r"\s+", " ", str(cluster_name or "").strip())
        if not clean_name:
            return ServiceResult(False, "Queue needs a name.")
        clean_work_id = str(work_id or "").strip()
        if not clean_work_id:
            return ServiceResult(False, "Work was not found.")
        if not self.works.get(clean_work_id):
            return ServiceResult(False, "Work was not found.")
        schema = self._schema(schema_key)
        work_set = self.work_sets.get_by_name(fandom_key, clean_name)
        if not work_set:
            now = utc_now_iso()
            work_set = WorkSet(
                id=str(uuid.uuid4()),
                fandom_key=fandom_key,
                name=clean_name,
                filter_state={"queue": "manual_named"},
                filter_signature=f"manual_named:{clean_name.casefold()}",
                created_at=now,
                updated_at=now,
            )
            self.work_sets.save(work_set)
        self.work_sets.add_items(work_set.id, [clean_work_id])
        batch = self.batches.get_by_work_set_schema(work_set.id, schema.schema_key)
        if batch and batch.status is EvaluationBatchStatus.ARCHIVED:
            batch.status = EvaluationBatchStatus.QUEUED
            batch.completed_at = None
            batch.updated_at = utc_now_iso()
            self.batches.save(batch)
        batch = batch or self._ensure_batch(work_set, schema.schema_key)
        completed_ids = self._completed_ids_for_batch(batch)
        queued = 0
        already_in_queue = False
        if clean_work_id not in completed_ids:
            queue_statuses = {QueueStatus.QUEUED, QueueStatus.RUNNING, QueueStatus.FAILED, QueueStatus.SKIPPED}
            already_in_queue = any(
                row.work_id == clean_work_id
                and row.queue_status in queue_statuses
                and row.schema_key in {None, "", batch.schema_key}
                for row in self.queue.list(batch_id=batch.id)
            )
            if not already_in_queue:
                self.enqueue(
                    clean_work_id,
                    reason=f"Manual queue: {work_set.name}",
                    priority=100,
                    batch_id=batch.id,
                    schema_key=batch.schema_key,
                    fandom_key_value=fandom_key,
                )
                queued = 1
        self._sync_batch_status(batch)
        if queued:
            message = f"Queued {clean_work_id} in {work_set.name}."
        elif already_in_queue:
            message = f"{clean_work_id} is already in {work_set.name}."
        else:
            message = f"Added {clean_work_id} to {work_set.name}; already evaluated for {schema.name}."
        return ServiceResult(True, message, payload={"work_set": work_set, "batch": batch, "queued": queued})

    def work_ids_for_batch(self, batch_id: str) -> list[str]:
        batch = self.batches.get(batch_id)
        if not batch:
            return []
        return self.work_sets.list_work_ids(batch.work_set_id)

    def sync_batch_status(self, batch_id: str) -> None:
        batch = self.batches.get(batch_id)
        if batch:
            self._sync_batch_status(batch)

    def schema_options_for_work_set(self, work_set_id: str) -> list[tuple[EvaluationSchema, bool]]:
        used = self.batches.schema_keys_for_work_set(work_set_id)
        return [(schema, schema.schema_key in used) for schema in self.schemas.list()]

    def requeue_work_set_under_schema(self, work_set_id: str, schema_key: str) -> ServiceResult:
        work_set = self.work_sets.get(work_set_id)
        if not work_set:
            return ServiceResult(False, "Queue cluster was not found.")
        schema = self._schema(schema_key)
        if self.batches.get_by_work_set_schema(work_set.id, schema.schema_key):
            return ServiceResult(False, f"{work_set.name} has already used {schema.name}.")
        batch = self._ensure_batch(work_set, schema.schema_key)
        queued = self._queue_unevaluated_for_batch(batch, reason=f"Requeued under {schema.name}")
        self._sync_batch_status(batch)
        return ServiceResult(
            True,
            f"Queued {queued} work{'s' if queued != 1 else ''} under {schema.name}.",
            payload={"batch": batch, "queued": queued},
        )

    def create_queue_for_schema_slot(self, work_set_id: str, schema_key: str) -> ServiceResult:
        work_set = self.work_sets.get(work_set_id)
        if not work_set:
            return ServiceResult(False, "Queue cluster was not found.")
        schema = self._schema(schema_key)
        batch = self.batches.get_by_work_set_schema(work_set.id, schema.schema_key)
        if batch:
            summary = self._batch_summary(batch, self.identities.get_or_create_local().local_user_id)
            if summary and summary.total_count > 0 and summary.completed_count >= summary.total_count:
                return ServiceResult(False, f"{work_set.name} has already completed {schema.name}. Clean it up before rerunning.")
            if batch.status is EvaluationBatchStatus.ARCHIVED:
                batch.status = EvaluationBatchStatus.QUEUED
                batch.completed_at = None
                batch.updated_at = utc_now_iso()
                self.batches.save(batch)
        else:
            batch = self._ensure_batch(work_set, schema.schema_key)
        queued = self._queue_unevaluated_for_batch(batch, reason=f"Queued under {schema.name}")
        self._sync_batch_status(batch)
        return ServiceResult(
            True,
            f"Queued {queued} work{'s' if queued != 1 else ''} under {schema.name}.",
            payload={"batch": batch, "queued": queued},
        )

    def clean_queue_schema_slot(self, work_set_id: str, schema_key: str) -> ServiceResult:
        work_set = self.work_sets.get(work_set_id)
        if not work_set:
            return ServiceResult(False, "Queue cluster was not found.")
        schema = self._schema(schema_key)
        batch = self.batches.get_by_work_set_schema(work_set.id, schema.schema_key)
        if not batch:
            return ServiceResult(True, f"{schema.name} has no queued work for {work_set.name}.")
        work_ids = self.work_sets.list_work_ids(work_set.id)
        deleted_rows = self._remove_queue_batch_or_archive(batch)
        deleted_cache = self.works.delete_unprotected_by_ids(work_ids)
        return ServiceResult(
            True,
            f"Cleaned {schema.name} queue for {work_set.name}: {deleted_rows} queue row"
            f"{'s' if deleted_rows != 1 else ''}, and {deleted_cache} now-unprotected cached work"
            f"{'s' if deleted_cache != 1 else ''}.",
        )

    def clean_queue_clusters(self, work_set_ids: list[str]) -> ServiceResult:
        clean_ids = [str(work_set_id) for work_set_id in dict.fromkeys(work_set_ids) if str(work_set_id).strip()]
        if not clean_ids:
            return ServiceResult(False, "Select at least one queue cluster to clean.")
        cleaned_clusters = 0
        cleaned_batches = 0
        deleted_rows = 0
        touched_work_ids: set[str] = set()
        for work_set_id in clean_ids:
            work_set = self.work_sets.get(work_set_id)
            if not work_set:
                continue
            touched_work_ids.update(self.work_sets.list_work_ids(work_set.id))
            batches = self.batches.list_for_work_set(work_set.id)
            for batch in batches:
                deleted_rows += self._remove_queue_batch_or_archive(batch)
                cleaned_batches += 1
            if self.batches.count_for_work_set(work_set.id) == 0:
                self.work_sets.delete(work_set.id)
            cleaned_clusters += 1
        deleted_cache = self.works.delete_unprotected_by_ids(list(touched_work_ids))
        return ServiceResult(
            True,
            f"Cleaned {cleaned_clusters} queue cluster{'s' if cleaned_clusters != 1 else ''}, "
            f"{cleaned_batches} schema slot{'s' if cleaned_batches != 1 else ''}, "
            f"{deleted_rows} queue row{'s' if deleted_rows != 1 else ''}, "
            f"and {deleted_cache} now-unprotected cached work{'s' if deleted_cache != 1 else ''}.",
        )

    def clean_evaluated_schema_slot(self, work_set_id: str, schema_key: str) -> ServiceResult:
        work_set = self.work_sets.get(work_set_id)
        if not work_set:
            return ServiceResult(False, "Queue cluster was not found.")
        schema = self._schema(schema_key)
        batch = self.batches.get_by_work_set_schema(work_set.id, schema.schema_key)
        if not batch:
            return ServiceResult(True, f"{schema.name} is already empty for {work_set.name}.")
        deleted_evaluations, deleted_queue_rows = self._delete_batch_local_data(batch, keep_work_set=True)
        self.batches.delete(batch.id)
        deleted_cache = self.works.delete_unprotected_by_ids(self.work_sets.list_work_ids(work_set.id))
        return ServiceResult(
            True,
            f"Cleared {schema.name} for {work_set.name}: {deleted_evaluations} evaluation record"
            f"{'s' if deleted_evaluations != 1 else ''}, {deleted_queue_rows} queue row"
            f"{'s' if deleted_queue_rows != 1 else ''}, and {deleted_cache} now-unprotected cached work"
            f"{'s' if deleted_cache != 1 else ''}.",
        )

    def clean_evaluated_clusters(self, work_set_ids: list[str]) -> ServiceResult:
        clean_ids = [str(work_set_id) for work_set_id in dict.fromkeys(work_set_ids) if str(work_set_id).strip()]
        if not clean_ids:
            return ServiceResult(False, "Select at least one evaluated cluster to clean.")
        deleted_batches = 0
        deleted_evaluations = 0
        deleted_queue_rows = 0
        touched_work_ids: set[str] = set()
        deleted_clusters = 0
        for work_set_id in clean_ids:
            work_set = self.work_sets.get(work_set_id)
            if not work_set:
                continue
            work_ids = self.work_sets.list_work_ids(work_set.id)
            touched_work_ids.update(work_ids)
            for batch in self.batches.list_for_work_set(work_set.id):
                evaluations, rows = self._delete_batch_local_data(batch, keep_work_set=False, deleting_work_set_ids=set(clean_ids))
                deleted_evaluations += evaluations
                deleted_queue_rows += rows
                self.batches.delete(batch.id)
                deleted_batches += 1
            self.work_sets.delete(work_set.id)
            deleted_clusters += 1
        deleted_cache = self.works.delete_unprotected_by_ids(list(touched_work_ids))
        return ServiceResult(
            True,
            f"Cleaned {deleted_clusters} cluster{'s' if deleted_clusters != 1 else ''}, "
            f"{deleted_batches} schema batch{'es' if deleted_batches != 1 else ''}, "
            f"{deleted_evaluations} evaluation record{'s' if deleted_evaluations != 1 else ''}, "
            f"{deleted_queue_rows} queue row{'s' if deleted_queue_rows != 1 else ''}, "
            f"and {deleted_cache} now-unprotected cached work{'s' if deleted_cache != 1 else ''}.",
        )

    def delete_evaluated_batch(self, batch_id: str) -> ServiceResult:
        batch = self.batches.get(batch_id)
        if not batch:
            return ServiceResult(False, "Evaluated batch was not found.")
        work_set = self.work_sets.get(batch.work_set_id)
        if not work_set:
            self.batches.delete(batch_id)
            return ServiceResult(True, "Removed stale evaluated batch.")
        work_ids = self.work_sets.list_work_ids(work_set.id)
        identity = self.identities.get_or_create_local()
        protected_same_schema_ids: set[str] = set()
        for other in self.batches.list_for_fandom(batch.fandom_key):
            if other.id != batch.id and other.schema_key == batch.schema_key:
                protected_same_schema_ids.update(self.work_sets.list_work_ids(other.work_set_id))
        delete_eval_ids = [work_id for work_id in work_ids if work_id not in protected_same_schema_ids]
        deleted_evaluations = self.evaluations.delete_for_works_schema(delete_eval_ids, identity.local_user_id, batch.schema_key)
        self.queue.delete_for_batch(batch.id)
        self.batches.delete(batch.id)
        if self.batches.count_for_work_set(work_set.id) == 0:
            self.work_sets.delete(work_set.id)
        deleted_cache = self.works.delete_unprotected_by_ids(work_ids)
        return ServiceResult(
            True,
            f"Deleted evaluated batch, {deleted_evaluations} evaluation record{'s' if deleted_evaluations != 1 else ''}, "
            f"and {deleted_cache} now-unprotected cached work{'s' if deleted_cache != 1 else ''}.",
        )

    def update_cluster_metadata(
        self,
        work_set_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        favorite: bool | None = None,
        description: str | None = None,
    ) -> ServiceResult:
        work_set = self.work_sets.get(work_set_id)
        if not work_set:
            return ServiceResult(False, "Queue cluster was not found.")
        if name is not None:
            clean_name = re.sub(r"\s+", " ", str(name or "").strip())
            if not clean_name:
                return ServiceResult(False, "Queue name cannot be blank.")
            duplicate = self.work_sets.get_by_name(work_set.fandom_key, clean_name)
            if duplicate and duplicate.id != work_set.id:
                return ServiceResult(False, f"A queue named {clean_name} already exists.")
            work_set.name = clean_name
        state = dict(work_set.filter_state or {})
        meta = dict(state.get("_cluster_meta") if isinstance(state.get("_cluster_meta"), dict) else {})
        if color is not None:
            clean_color = self._normalize_hex(color)
            if color and not clean_color:
                return ServiceResult(False, "Cluster color must be a hex color.")
            if clean_color:
                meta["color"] = clean_color
            else:
                meta.pop("color", None)
        if favorite is not None:
            meta["favorite"] = bool(favorite)
        if description is not None:
            clean_description = re.sub(r"\s+", " ", str(description or "").strip())
            if clean_description:
                meta["description"] = clean_description[:500]
            else:
                meta.pop("description", None)
        if meta:
            state["_cluster_meta"] = meta
        else:
            state.pop("_cluster_meta", None)
        work_set.filter_state = state
        self.work_sets.save(work_set)
        return ServiceResult(True, "Cluster updated.", payload=work_set)

    @staticmethod
    def _cluster_meta(work_set: WorkSet) -> dict[str, Any]:
        raw = work_set.filter_state.get("_cluster_meta") if isinstance(work_set.filter_state, dict) else {}
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    def _normalize_hex(value: str | None) -> str:
        clean = str(value or "").strip()
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", clean):
            return f"#{clean.lstrip('#').lower()}"
        if re.fullmatch(r"#?[0-9a-fA-F]{3}", clean):
            raw = clean.lstrip("#").lower()
            return "#" + "".join(char * 2 for char in raw)
        return ""

    def _schema(self, schema_key: str | None = None) -> EvaluationSchema:
        schema = self.schemas.get(schema_key or "") if schema_key else self.schemas.active()
        if schema:
            return schema
        schema = self.schemas.get("local_default_v1")
        if schema:
            return schema
        raise ValueError("No evaluation schema is available.")

    def _active_fandom_key(self) -> str:
        profiles = self.fandoms.list()
        selected = [profile for profile in profiles if profile.selected_at]
        if selected:
            selected.sort(key=lambda profile: profile.selected_at or "", reverse=True)
            return selected[0].fandom_key
        if profiles:
            return profiles[0].fandom_key
        return fandom_key(DEFAULT_FANDOM)

    def _manual_batch(self, fandom_key_value: str, schema_key: str, work_ids: list[str] | None = None) -> EvaluationBatch:
        work_set = self.work_sets.get_by_name(fandom_key_value, "Manual Queue") or WorkSet(
            id=str(uuid.uuid4()),
            fandom_key=fandom_key_value,
            name="Manual Queue",
            filter_state={"queue": "manual"},
            filter_signature="manual_queue",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self.work_sets.save(work_set)
        if work_ids:
            self.work_sets.add_items(work_set.id, work_ids)
        return self._ensure_batch(work_set, schema_key)

    def _ensure_batch(self, work_set: WorkSet, schema_key: str) -> EvaluationBatch:
        existing = self.batches.get_by_work_set_schema(work_set.id, schema_key)
        if existing:
            return existing
        now = utc_now_iso()
        batch = EvaluationBatch(
            id=str(uuid.uuid4()),
            work_set_id=work_set.id,
            fandom_key=work_set.fandom_key,
            schema_key=schema_key,
            created_at=now,
            updated_at=now,
            status=EvaluationBatchStatus.QUEUED,
        )
        self.batches.save(batch)
        return batch

    def _completed_ids_for_batch(self, batch: EvaluationBatch) -> set[str]:
        work_ids = self.work_sets.list_work_ids(batch.work_set_id)
        identity = self.identities.get_or_create_local()
        latest = self.evaluations.latest_for_works(work_ids, identity.local_user_id, batch.schema_key)
        return {work_id for work_id, evaluation in latest.items() if evaluation.status is EvaluationStatus.COMPLETE}

    def _completed_count_for_batch(self, batch: EvaluationBatch) -> int:
        return len(self._completed_ids_for_batch(batch))

    def _queue_unevaluated_for_batch(self, batch: EvaluationBatch, *, reason: str) -> int:
        work_ids = self.work_sets.list_work_ids(batch.work_set_id)
        completed_ids = self._completed_ids_for_batch(batch)
        existing_rows = self.queue.list(batch_id=batch.id)
        existing_work_ids = {row.work_id for row in existing_rows if row.schema_key in {None, "", batch.schema_key}}
        queued = 0
        for work_id in work_ids:
            if work_id in completed_ids or work_id in existing_work_ids:
                continue
            self.enqueue(
                work_id,
                reason=reason,
                priority=100,
                batch_id=batch.id,
                schema_key=batch.schema_key,
                fandom_key_value=batch.fandom_key,
            )
            queued += 1
        return queued

    def _cluster_summaries(self, fandom_key: str) -> list[EvaluationClusterSummary]:
        schemas = self.schemas.list()
        local_user_id = self.identities.get_or_create_local().local_user_id
        clusters = [
            self._cluster_summary(work_set, schemas, local_user_id)
            for work_set in self.work_sets.list_for_fandom(fandom_key)
        ]
        clusters.sort(
            key=lambda cluster: (
                not bool(self._cluster_meta(cluster.work_set).get("favorite")),
                str(cluster.work_set.name).casefold(),
            )
        )
        return clusters

    def _cluster_summary(
        self,
        work_set: WorkSet,
        schemas: list[EvaluationSchema],
        local_user_id: str,
    ) -> EvaluationClusterSummary:
        work_ids = self.work_sets.list_work_ids(work_set.id)
        batches_by_schema = {
            batch.schema_key: batch
            for batch in self.batches.list_for_work_set(work_set.id)
        }
        slots: list[EvaluationSchemaSlot] = []
        for schema in schemas:
            batch = batches_by_schema.get(schema.schema_key)
            summary: EvaluationBatchSummary | None = None
            if batch:
                latest = self.evaluations.latest_for_works(work_ids, local_user_id, batch.schema_key)
                rows = self.queue.list(batch_id=batch.id)
                summary = self._batch_summary_from_data(batch, work_set, work_ids, latest, rows)
            slots.append(self._schema_slot_from_summary(work_set, schema, batch, summary, len(work_ids)))
        return EvaluationClusterSummary(work_set=work_set, slots=slots, total_count=len(work_ids))

    def _schema_slot_from_summary(
        self,
        work_set: WorkSet,
        schema: EvaluationSchema,
        batch: EvaluationBatch | None,
        summary: EvaluationBatchSummary | None,
        total_count: int,
    ) -> EvaluationSchemaSlot:
        if not summary:
            return EvaluationSchemaSlot(
                work_set=work_set,
                schema=schema,
                batch=batch,
                summary=None,
                state="empty",
                total_count=total_count,
            )
        active = summary.active_count
        if summary.completed_count and active:
            state = "partial"
        elif summary.completed_count:
            state = "complete"
        elif active:
            state = "queued"
        else:
            state = "empty"
        return EvaluationSchemaSlot(
            work_set=work_set,
            schema=schema,
            batch=batch,
            summary=summary,
            state=state,
            total_count=summary.total_count,
            pending_count=summary.pending_count,
            running_count=summary.running_count,
            failed_count=summary.failed_count,
            skipped_count=summary.skipped_count,
            completed_count=summary.completed_count,
        )

    def _delete_batch_local_data(
        self,
        batch: EvaluationBatch,
        *,
        keep_work_set: bool,
        deleting_work_set_ids: set[str] | None = None,
    ) -> tuple[int, int]:
        work_set = self.work_sets.get(batch.work_set_id)
        deleted_queue_rows = self.queue.delete_for_batch(batch.id)
        if not work_set:
            return 0, deleted_queue_rows
        deleting = set(deleting_work_set_ids or set())
        if not keep_work_set:
            deleting.add(work_set.id)
        work_ids = self.work_sets.list_work_ids(work_set.id)
        identity = self.identities.get_or_create_local()
        protected_same_schema_ids: set[str] = set()
        for other in self.batches.list_for_fandom(batch.fandom_key):
            if other.id == batch.id or other.schema_key != batch.schema_key:
                continue
            if other.work_set_id in deleting:
                continue
            protected_same_schema_ids.update(self.work_sets.list_work_ids(other.work_set_id))
        delete_eval_ids = [work_id for work_id in work_ids if work_id not in protected_same_schema_ids]
        deleted_evaluations = self.evaluations.delete_for_works_schema(delete_eval_ids, identity.local_user_id, batch.schema_key)
        return deleted_evaluations, deleted_queue_rows

    def _remove_queue_batch_or_archive(self, batch: EvaluationBatch) -> int:
        work_set = self.work_sets.get(batch.work_set_id)
        deleted_rows = self.queue.delete_for_batch(batch.id)
        completed = self._completed_count_for_batch(batch) if work_set else 0
        if completed > 0:
            if batch.status is not EvaluationBatchStatus.ARCHIVED:
                batch.status = EvaluationBatchStatus.ARCHIVED
                batch.completed_at = None
                batch.updated_at = utc_now_iso()
                self.batches.save(batch)
        else:
            self.batches.delete(batch.id)
            if work_set and self.batches.count_for_work_set(work_set.id) == 0:
                self.work_sets.delete(work_set.id)
        return deleted_rows

    def _batch_summaries(self, fandom_key: str) -> list[EvaluationBatchSummary]:
        summaries: list[EvaluationBatchSummary] = []
        identity = self.identities.get_or_create_local()
        for batch in self.batches.list_for_fandom(fandom_key):
            summary = self._batch_summary(batch, identity.local_user_id)
            if summary:
                summaries.append(summary)
        summaries.sort(key=lambda summary: not bool(self._cluster_meta(summary.work_set).get("favorite")))
        return summaries

    def _batch_summary(self, batch: EvaluationBatch, local_user_id: str) -> EvaluationBatchSummary | None:
        work_set = self.work_sets.get(batch.work_set_id)
        if not work_set:
            return None
        work_ids = self.work_sets.list_work_ids(work_set.id)
        latest = self.evaluations.latest_for_works(work_ids, local_user_id, batch.schema_key)
        rows = self.queue.list(batch_id=batch.id)
        return self._batch_summary_from_data(batch, work_set, work_ids, latest, rows)

    def _batch_summary_from_data(
        self,
        batch: EvaluationBatch,
        work_set: WorkSet,
        work_ids: list[str],
        latest: dict[str, Evaluation],
        rows: list[EvaluationQueueItem],
    ) -> EvaluationBatchSummary:
        completed_ids = {
            work_id
            for work_id, evaluation in latest.items()
            if evaluation.status is EvaluationStatus.COMPLETE
        }
        running = sum(1 for row in rows if row.queue_status is QueueStatus.RUNNING and row.work_id not in completed_ids)
        failed = sum(1 for row in rows if row.queue_status is QueueStatus.FAILED and row.work_id not in completed_ids)
        skipped = sum(1 for row in rows if row.queue_status is QueueStatus.SKIPPED and row.work_id not in completed_ids)
        queued_rows = sum(1 for row in rows if row.queue_status is QueueStatus.QUEUED and row.work_id not in completed_ids)
        self._sync_batch_status_from_counts(batch, len(work_ids), len(completed_ids))
        return EvaluationBatchSummary(
            batch=batch,
            work_set=work_set,
            schema=self.schemas.get(batch.schema_key),
            total_count=len(work_ids),
            pending_count=queued_rows,
            running_count=running,
            failed_count=failed,
            skipped_count=skipped,
            completed_count=len(completed_ids),
        )

    def _sync_batch_status_from_counts(self, batch: EvaluationBatch, total: int, completed: int) -> None:
        if total <= 0:
            return
        if batch.status is EvaluationBatchStatus.ARCHIVED:
            return
        if completed >= total:
            status = EvaluationBatchStatus.COMPLETE
            completed_at = batch.completed_at or utc_now_iso()
        elif completed:
            status = EvaluationBatchStatus.PARTIAL
            completed_at = None
        else:
            status = EvaluationBatchStatus.QUEUED
            completed_at = None
        if batch.status is status and batch.completed_at == completed_at:
            return
        batch.status = status
        batch.completed_at = completed_at
        batch.updated_at = utc_now_iso()
        self.batches.save(batch)

    def _works_for_batch(self, batch_id: str, *, completed: bool) -> EvaluationBatchWorks | None:
        batch = self.batches.get(batch_id)
        if not batch:
            return None
        work_set = self.work_sets.get(batch.work_set_id)
        schema = self.schemas.get(batch.schema_key)
        if not work_set or not schema:
            return None
        work_ids = self.work_sets.list_work_ids(work_set.id)
        identity = self.identities.get_or_create_local()
        latest = self.evaluations.latest_for_works(work_ids, identity.local_user_id, batch.schema_key)
        rows = self.queue.list(batch_id=batch.id)
        summary = self._batch_summary_from_data(batch, work_set, work_ids, latest, rows)
        if completed:
            selected_ids = [
                work_id
                for work_id in work_ids
                if latest.get(work_id) is not None and latest[work_id].status is EvaluationStatus.COMPLETE
            ]
        else:
            active_statuses = {QueueStatus.QUEUED, QueueStatus.RUNNING, QueueStatus.FAILED, QueueStatus.SKIPPED}
            selected_ids = list(
                dict.fromkeys(
                    row.work_id
                    for row in rows
                    if row.queue_status in active_statuses
                    and row.work_id in work_ids
                    and not (latest.get(row.work_id) and latest[row.work_id].status is EvaluationStatus.COMPLETE)
                )
            )
        works_by_id = {work.work_id: work for work in self.works.list_by_ids(selected_ids)}
        visible_works = [works_by_id[work_id] for work_id in selected_ids if work_id in works_by_id]
        return EvaluationBatchWorks(
            batch=batch,
            work_set=work_set,
            schema=schema,
            works=visible_works,
            tags_by_work=self.tags.list_for_works([work.work_id for work in visible_works]),
            latest_evaluations={work_id: latest[work_id] for work_id in selected_ids if work_id in latest},
            summary=summary,
        )

    def _sync_batch_status(self, batch: EvaluationBatch) -> None:
        work_ids = self.work_sets.list_work_ids(batch.work_set_id)
        self._sync_batch_status_from_counts(batch, len(work_ids), len(self._completed_ids_for_batch(batch)))


class WorkLibraryService:
    def __init__(
        self,
        works: WorkRepository,
        tags: TagRepository,
        collection: WorkCollectionRepository,
        blocked: BlockedWorkRepository,
        blocked_authors: BlockedAuthorRepository,
        blocked_tags: BlockedTagRepository,
        work_sets: WorkSetRepository,
        favorite_tags: FavoriteTagRepository,
        tag_colors: TagColorRepository,
        snapshots: BrowseSnapshotRepository,
        settings: SettingsRepository,
        reading: ReadingStateRepository,
        identities: IdentityRepository,
    ) -> None:
        self.works = works
        self.tags = tags
        self.collection = collection
        self.blocked = blocked
        self.blocked_authors = blocked_authors
        self.blocked_tags = blocked_tags
        self.work_sets = work_sets
        self.favorite_tags = favorite_tags
        self.tag_colors = tag_colors
        self.snapshots = snapshots
        self.settings = settings
        self.reading = reading
        self.identities = identities

    def get(self, work_id: str) -> Work | None:
        return self.works.get(work_id)

    def list_recent(self, limit: int = 50, search: str = "") -> list[Work]:
        return self.works.list_recent(limit, search)

    def list_collected(self, limit: int = 100, search: str = "") -> list[Work]:
        return self._sort_by_recent_read(self.visible_works(self.collection.list_collected(limit, search)))

    def list_work_sets(self, fandom_key: str) -> list[WorkSet]:
        return self.work_sets.list_for_fandom(fandom_key)

    def work_set_works(self, set_id: str) -> list[Work]:
        return self._sort_by_recent_read(self.visible_works(self.works.list_by_ids(self.work_sets.list_work_ids(set_id))))

    def work_set_pages(self, set_id: str):
        return self.work_sets.list_pages(set_id)

    def save_page_as_work_set(
        self,
        *,
        fandom_key: str,
        name: str,
        filter_state: dict[str, Any],
        source_url: str,
        work_ids: list[str],
        page_number: int,
    ) -> ServiceResult:
        clean_name = (name or "").strip()
        if not clean_name:
            return ServiceResult(False, "Work Set needs a name.")
        existing = self.work_sets.get_by_name(fandom_key, clean_name)
        signature = filter_signature(filter_state)
        now = utc_now_iso()
        saved_filter_state = dict(filter_state)
        if existing and isinstance(existing.filter_state.get("_cluster_meta"), dict):
            saved_filter_state["_cluster_meta"] = dict(existing.filter_state["_cluster_meta"])
        work_set = existing or WorkSet(
            id=str(uuid.uuid4()),
            fandom_key=fandom_key,
            name=clean_name,
            filter_state=saved_filter_state,
            filter_signature=signature,
            created_at=now,
            updated_at=now,
        )
        work_set.filter_state = saved_filter_state
        work_set.filter_signature = signature
        self.work_sets.save(work_set)
        self.work_sets.record_page(work_set.id, page_number, source_url, work_ids, now)
        return ServiceResult(True, f"Saved page {page_number} to {clean_name}.", payload=work_set)

    def rename_work_set(self, set_id: str, name: str) -> ServiceResult:
        work_set = self.work_sets.get(set_id)
        if not work_set:
            return ServiceResult(False, "Work Set was not found.")
        work_set.name = name.strip() or work_set.name
        self.work_sets.save(work_set)
        return ServiceResult(True, "Work Set renamed.")

    def delete_work_set(self, set_id: str) -> ServiceResult:
        self.work_sets.delete(set_id)
        return ServiceResult(True, "Work Set deleted.")

    def tags_for_work(self, work_id: str) -> list[WorkTag]:
        return self.tags.list_for_work(work_id)

    def tags_for_works(self, work_ids: list[str]) -> dict[str, list[WorkTag]]:
        return self.tags.list_for_works(work_ids)

    def favorite_tags_for_fandom(self, fandom_key: str) -> list[FavoriteTag]:
        return self.favorite_tags.list_for_fandom(fandom_key)

    def tag_colors_for_fandom(self, fandom_key: str) -> list[TagColorOverride]:
        return self.tag_colors.list_for_fandom(fandom_key)

    def favorite_tag(self, fandom_key: str, tag_type: TagType, tag_text: str, color: str) -> ServiceResult:
        self.favorite_tags.upsert(
            FavoriteTag(
                fandom_key=fandom_key,
                tag_type=tag_type,
                tag_text=tag_text,
                color=color,
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
        )
        return ServiceResult(True, "Favorite tag saved.")

    def set_tag_color(self, fandom_key: str, tag_type: TagType, tag_text: str, color: str) -> ServiceResult:
        clean_color = str(color or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", clean_color):
            return ServiceResult(False, "Tag color must be a hex color.")
        self.tag_colors.upsert(
            TagColorOverride(
                fandom_key=fandom_key,
                tag_type=tag_type,
                tag_text=tag_text,
                color=clean_color.lower(),
                updated_at=utc_now_iso(),
            )
        )
        return ServiceResult(True, "Tag color saved.")

    def unfavorite_tag(self, fandom_key: str, tag_type: TagType, tag_text: str) -> ServiceResult:
        self.favorite_tags.delete(fandom_key, tag_type.value, tag_text)
        return ServiceResult(True, "Favorite tag removed.")

    def count(self) -> int:
        return self.collection.count()

    def cache_count(self) -> int:
        return self.works.count()

    def count_for_fandom(self, profile: FandomProfile) -> int:
        return self.collection.count(profile.fandom_key)

    def cache_count_for_fandom(self, profile: FandomProfile) -> int:
        return self.works.count_for_fandom(profile.fandom_key, profile.tag)

    def collect(self, work_id: str, fandom_key: str | None = None, note: str = "") -> ServiceResult:
        if not self.works.get(work_id):
            return ServiceResult(False, "Work is not cached yet.")
        self.collection.collect(work_id, fandom_key, note)
        return ServiceResult(True, "Added to Works.")

    def collect_many(self, work_ids: list[str], fandom_key: str | None = None) -> ServiceResult:
        added = 0
        visible = {work.work_id for work in self.visible_works(self.works.list_by_ids(work_ids))}
        for work_id in work_ids:
            if work_id in visible:
                self.collection.collect(work_id, fandom_key)
                added += 1
        return ServiceResult(True, f"Added {added} work{'s' if added != 1 else ''} to Works.")

    def uncollect(self, work_id: str) -> None:
        self.collection.uncollect(work_id)

    def is_collected(self, work_id: str) -> bool:
        return self.collection.is_collected(work_id)

    def collected_ids(self, work_ids: list[str]) -> set[str]:
        return self.collection.collected_ids(work_ids)

    def block_work(self, work_id: str, fandom_key: str | None = None, reason: str = "") -> ServiceResult:
        work = self.works.get(work_id)
        self.blocked.block(work_id, fandom_key, reason)
        self.collection.uncollect(work_id)
        suffix = f" {work.title}" if work and work.title else ""
        return ServiceResult(True, f"Work{suffix} blocked.")

    def block_author_for_work(self, work_id: str, fandom_key: str | None = None, reason: str = "") -> ServiceResult:
        work = self.works.get(work_id)
        if not work:
            return ServiceResult(False, "Cannot block author: work is not cached.")
        author_key = work.author_key or normalize_author_key(work.author_name, work.author_url)
        if not author_key:
            return ServiceResult(False, "Cannot block author: this work has no cached author.")
        if self.blocked_authors.is_blocked(author_key):
            return ServiceResult(True, "Author already blocked.")
        self.blocked_authors.block(
            author_key,
            display_name=work.author_name,
            author_url=work.author_url,
            fandom_key=fandom_key,
            reason=reason or f"Blocked from author row on work {work_id}",
        )
        suffix = f" {work.author_name}" if work.author_name else ""
        return ServiceResult(True, f"Author{suffix} blocked.")

    def block_tag(self, fandom_key: str | None, tag_type: TagType, tag_text: str, reason: str = "") -> ServiceResult:
        clean = str(tag_text or "").strip()
        if not clean:
            return ServiceResult(False, "Tag block needs a tag.")
        self.blocked_tags.block(tag_type.value, clean, fandom_key, reason)
        matching_ids = set(self.tags.work_ids_for_tag(tag_type.value, clean))
        for work_id in matching_ids:
            self.blocked.block(work_id, fandom_key, reason or f"Blocked by tag {clean}")
            self.collection.uncollect(work_id)
        return ServiceResult(
            True,
            f"Blocked tag. AO3 will exclude it from live pages; hid {len(matching_ids)} cached match{'es' if len(matching_ids) != 1 else ''}.",
        )

    def unblock_work(self, work_id: str) -> None:
        self.blocked.unblock(work_id)

    def unblock_author(self, author_key: str) -> None:
        self.blocked_authors.unblock(author_key)

    def unblock_many_works(self, work_ids: list[str]) -> int:
        clean = {str(work_id).strip() for work_id in work_ids if str(work_id).strip()}
        for work_id in clean:
            self.blocked.unblock(work_id)
        return len(clean)

    def unblock_many_authors(self, author_keys: list[str]) -> int:
        clean = {str(author_key).strip().casefold() for author_key in author_keys if str(author_key).strip()}
        for author_key in clean:
            self.blocked_authors.unblock(author_key)
        return len(clean)

    def unblock_many_tags(self, tags: list[tuple[TagType | str, str]]) -> int:
        clean: set[tuple[str, str]] = set()
        for tag_type, tag_text in tags:
            type_value = tag_type.value if isinstance(tag_type, TagType) else str(tag_type or "").strip()
            text_value = str(tag_text or "").strip()
            if type_value and text_value:
                clean.add((type_value, text_value))
        for tag_type, tag_text in clean:
            self.blocked_tags.unblock(tag_type, tag_text)
            matching_ids = set(self.tags.work_ids_for_tag(tag_type, tag_text))
            for block in self.blocked.list(max(len(matching_ids) + 100, 200)):
                if block.work_id in matching_ids and str(block.reason or "").startswith("Blocked by tag"):
                    self.blocked.unblock(block.work_id)
        return len(clean)

    def is_blocked(self, work_id: str) -> bool:
        work = self.works.get(work_id)
        return self.is_work_blocked(work)

    def is_work_blocked(self, work: Work | None) -> bool:
        if not work:
            return False
        if self.blocked.is_blocked(work.work_id):
            return True
        author_key = work.author_key or normalize_author_key(work.author_name, work.author_url)
        if author_key and self.blocked_authors.is_blocked(author_key):
            return True
        return bool(self.blocked_tags.matching_work_ids([work.work_id]))

    def visible_works(self, works: list[Work]) -> list[Work]:
        if not works:
            return []
        blocked_ids = self.blocked.blocked_ids([work.work_id for work in works])
        author_keys = [work.author_key or normalize_author_key(work.author_name, work.author_url) for work in works]
        blocked_author_keys = self.blocked_authors.blocked_keys([key for key in author_keys if key])
        blocked_tag_work_ids = self.blocked_tags.matching_work_ids([work.work_id for work in works])
        return [
            work
            for work in works
            if work.work_id not in blocked_ids
            and work.work_id not in blocked_tag_work_ids
            and (work.author_key or normalize_author_key(work.author_name, work.author_url) or "") not in blocked_author_keys
        ]

    def visible_work_ids(self, work_ids: list[str]) -> list[str]:
        visible = self.visible_works(self.works.list_by_ids(work_ids))
        visible_ids = {work.work_id for work in visible}
        return [work_id for work_id in work_ids if work_id in visible_ids]

    def list_blocked(self, limit: int = 100) -> list[BlockedWork]:
        return self.blocked.list(limit)

    def list_blocked_authors(self, limit: int = 100) -> list[BlockedAuthor]:
        return self.blocked_authors.list(limit)

    def list_blocked_tags(self, limit: int = 200, fandom_key: str | None = None) -> list[BlockedTag]:
        return self.blocked_tags.list(limit, fandom_key)

    def blocked_author_groups(self, limit: int = 100, fandom_key: str | None = None) -> list[BlockedAuthorGroup]:
        authors = self.blocked_authors.list(limit)
        if fandom_key:
            authors = [author for author in authors if author.fandom_key == fandom_key]
        if not authors:
            return []
        blocked_work_ids = {
            item.work_id
            for item in self.blocked.list(max(limit * 4, 100))
            if not str(item.reason or "").startswith("Blocked by tag")
        }
        works = self.works.list_by_author_keys([author.author_key for author in authors], limit=max(limit * 10, 500))
        works_by_author: dict[str, list[Work]] = {}
        for work in works:
            key = (work.author_key or normalize_author_key(work.author_name, work.author_url) or "").casefold()
            if key:
                works_by_author.setdefault(key, []).append(work)
        return [
            BlockedAuthorGroup(
                author=author,
                works=works_by_author.get(author.author_key.casefold(), []),
                explicit_work_ids={
                    work.work_id for work in works_by_author.get(author.author_key.casefold(), []) if work.work_id in blocked_work_ids
                },
            )
            for author in authors
        ]

    def standalone_blocked_work_views(self, limit: int = 100, fandom_key: str | None = None) -> list[BlockedWorkView]:
        blocked = self.blocked.list(limit)
        blocked = [item for item in blocked if not str(item.reason or "").startswith("Blocked by tag")]
        if fandom_key:
            blocked = [item for item in blocked if item.fandom_key == fandom_key]
        if not blocked:
            return []
        works_by_id = {work.work_id: work for work in self.works.list_by_ids([item.work_id for item in blocked])}
        views: list[BlockedWorkView] = []
        for item in blocked:
            work = works_by_id.get(item.work_id)
            views.append(BlockedWorkView(block=item, work=work))
        views.sort(
            key=lambda view: (
                (
                    view.work.author_key
                    or normalize_author_key(view.work.author_name, view.work.author_url)
                    if view.work
                    else ""
                ),
                (view.work.title or "" if view.work else view.block.work_id).casefold(),
                view.block.blocked_at,
            )
        )
        return views

    def _sort_by_recent_read(self, works: list[Work]) -> list[Work]:
        if not works:
            return []
        identity = self.identities.get_or_create_local()
        recent_states = {
            state.work_id: state.last_opened_at
            for state in self.reading.list_for_user(identity.local_user_id)
            if state.last_opened_at and state.state not in {ReadingStatus.UNSEEN, ReadingStatus.QUEUED}
        }
        recent: list[tuple[str, int, Work]] = []
        rest: list[tuple[int, Work]] = []
        for index, work in enumerate(works):
            if stamp := recent_states.get(work.work_id):
                recent.append((stamp, index, work))
            else:
                rest.append((index, work))
        recent.sort(key=lambda item: item[0], reverse=True)
        return [work for _, _, work in recent] + [work for _, work in rest]

    def browse_cache_policy(self) -> dict[str, Any]:
        raw = self.settings.get(BROWSE_CACHE_POLICY_KEY, DEFAULT_BROWSE_CACHE_POLICY)
        policy = dict(DEFAULT_BROWSE_CACHE_POLICY)
        if isinstance(raw, dict):
            policy.update(raw)
        try:
            policy["max_cached_works"] = max(1, int(policy.get("max_cached_works") or 120))
        except (TypeError, ValueError):
            policy["max_cached_works"] = 120
        policy["auto_purge_enabled"] = bool(policy.get("auto_purge_enabled"))
        return policy

    def save_browse_cache_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(DEFAULT_BROWSE_CACHE_POLICY)
        normalized.update(policy)
        try:
            normalized["max_cached_works"] = max(1, int(normalized.get("max_cached_works") or 120))
        except (TypeError, ValueError):
            normalized["max_cached_works"] = 120
        normalized["auto_purge_enabled"] = bool(normalized.get("auto_purge_enabled"))
        self.settings.set(BROWSE_CACHE_POLICY_KEY, normalized)
        return normalized

    def maybe_auto_purge_cache(self, keep_work_ids: list[str] | None = None) -> ServiceResult | None:
        policy = self.browse_cache_policy()
        if not policy["auto_purge_enabled"]:
            return None
        if self.cache_count() <= int(policy["max_cached_works"]):
            return None
        return self.smart_purge_cache(keep_work_ids)

    def smart_purge_cache(self, keep_work_ids: list[str] | None = None) -> ServiceResult:
        stale = self.snapshots.delete_stale_missing_works()
        deleted = self.works.delete_uncollected_cache(keep_work_ids)
        return ServiceResult(
            True,
            f"Smart purged {deleted} cached work{'s' if deleted != 1 else ''} and {stale} stale snapshot{'s' if stale != 1 else ''}.",
        )

    def purge_uncollected_cache(self, keep_work_ids: list[str] | None = None) -> ServiceResult:
        return self.smart_purge_cache(keep_work_ids)

    def suggestions(self, query: str = "", context_type: str = "search", limit: int = 12) -> list[str]:
        tag_type = None
        if context_type == "fandom":
            tag_type = "fandom"
        elif context_type == "pairing":
            tag_type = "relationship"
        return self.tags.suggest(query=query, tag_type=tag_type, limit=limit)


class SharedOverlayService:
    def __init__(self, overlays: SharedOverlayRepository) -> None:
        self.overlays = overlays

    def list_recent(self, limit: int = 50) -> list[SharedOverlay]:
        return self.overlays.list_recent(limit)


class AO3BrowseService:
    def __init__(
        self,
        works: WorkRepository,
        tags: TagRepository,
        snapshots: BrowseSnapshotRepository,
        ao3_client: Any,
        blocked: BlockedWorkRepository | None = None,
        blocked_authors: BlockedAuthorRepository | None = None,
        blocked_tags: BlockedTagRepository | None = None,
    ) -> None:
        self.works = works
        self.tags = tags
        self.snapshots = snapshots
        self.ao3_client = ao3_client
        self.blocked = blocked
        self.blocked_authors = blocked_authors
        self.blocked_tags = blocked_tags

    def fetch_browse_url(self, url: str, context_type: str = "search", context_key: str = "") -> BrowseResult:
        url = self.resolve_effective_browse_url(url, context_type, context_key)
        try:
            parsed: ParsedBrowsePage = self.ao3_client.fetch_browse(url)
        except Exception as exc:  # noqa: BLE001
            return BrowseResult(False, f"AO3 browse failed: {exc}")
        return self._store_parsed_browse(parsed, url, context_type, context_key)

    def fetch_fandom(
        self,
        fandom_or_url: str = DEFAULT_FANDOM,
        filter_state: dict[str, Any] | None = None,
        *,
        force_refresh: bool = False,
    ) -> BrowseResult:
        fandom = self.resolve_fandom(fandom_or_url) or DEFAULT_FANDOM
        url = (
            self.resolve_fandom_filter_url(fandom, filter_state)
            if filter_state
            else self.resolve_fandom_works_url(fandom)
        )
        url = self.apply_blocked_tag_exclusions(url)
        try:
            parsed: ParsedBrowsePage = self.ao3_client.fetch_browse(url)
        except Exception as exc:  # noqa: BLE001
            cached = self._cached_result(url)
            if cached:
                cached.message = f"AO3 refresh failed; showing exact cached page. {exc}"
                return cached
            return BrowseResult(False, f"AO3 browse failed: {exc}")
        return self._store_parsed_browse(parsed, url, "fandom", fandom)

    def open_account_session(self, fandom_or_url: str = DEFAULT_FANDOM) -> str:
        fandom = self.resolve_fandom(fandom_or_url) or DEFAULT_FANDOM
        return self.ao3_client.open_account_session(self.apply_blocked_tag_exclusions(self.resolve_fandom_works_url(fandom)))

    def prewarm(self) -> None:
        if hasattr(self.ao3_client, "prewarm"):
            self.ao3_client.prewarm()

    @staticmethod
    def resolve_browse_url(url: str, context_type: str = "search", context_key: str = "") -> str:
        raw = str(url or "").strip()
        query = str(context_key or "").strip()
        if query.startswith(("http://", "https://")):
            return query
        if raw and raw not in {f"{AO3_BASE_URL}/works/search", "/works/search"} and not query:
            return raw
        if context_type in {"fandom", "pairing"} and query:
            return f"{AO3_BASE_URL}/tags/{quote(query, safe='')}/works"
        if context_type == "user_page" and query:
            cleaned = query.strip().strip("/")
            if cleaned.startswith("users/"):
                return f"{AO3_BASE_URL}/{cleaned}"
            return f"{AO3_BASE_URL}/users/{quote(cleaned, safe='')}/works"
        if query:
            return f"{AO3_BASE_URL}/works/search?{urlencode({'work_search[query]': query})}"
        return raw or f"{AO3_BASE_URL}/works/search"

    def resolve_effective_browse_url(self, url: str, context_type: str = "search", context_key: str = "") -> str:
        return self.apply_blocked_tag_exclusions(self.resolve_browse_url(url, context_type, context_key))

    @staticmethod
    def resolve_fandom_works_url(fandom: str) -> str:
        return f"{AO3_BASE_URL}/tags/{quote((fandom or DEFAULT_FANDOM).strip(), safe='')}/works"

    def resolve_effective_fandom_filter_url(self, fandom: str, filter_state: dict[str, Any] | None = None) -> str:
        return self.apply_blocked_tag_exclusions(self.resolve_fandom_filter_url(fandom, filter_state))

    @staticmethod
    def resolve_fandom(fandom_or_url: str) -> str:
        raw = str(fandom_or_url or "").strip()
        if not raw:
            return ""
        if raw.startswith(("http://", "https://")):
            parsed = urlparse(raw)
            query = parse_qs(parsed.query)
            tag_id = (query.get("tag_id") or [""])[0]
            if tag_id:
                return unquote_plus(tag_id)
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] == "tags":
                return unquote(parts[1])
        return raw

    @classmethod
    def resolve_fandom_filter_url(cls, fandom: str, filter_state: dict[str, Any] | None = None) -> str:
        state = filter_state or {}
        selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
        params: list[tuple[str, str]] = [
            ("work_search[sort_column]", normalize_ao3_sort_column(state.get("sort_column"))),
            ("work_search[sort_direction]", "asc" if str(state.get("sort_direction")) == "asc" else "desc"),
            *cls._selected_filter_params(selected, "include_work_search"),
            ("work_search[other_tag_names]", str(state.get("other_tag_names") or "")),
            *cls._selected_filter_params(selected, "exclude_work_search"),
            ("work_search[excluded_tag_names]", str(state.get("excluded_tag_names") or "")),
        ]
        for key in [
            "crossover",
            "complete",
            "words_from",
            "words_to",
            "date_from",
            "date_to",
            "query",
            "language_id",
        ]:
            value = state.get(key)
            if key in {"words_from", "words_to"}:
                value = normalize_word_count_filter(value)
            elif key in {"date_from", "date_to"}:
                value = normalize_ao3_date_filter(value)
            params.append((f"work_search[{key}]", str(value or "")))
        for name, value in state.items():
            if str(name).startswith(("include_work_search", "exclude_work_search")):
                values = value if isinstance(value, (list, tuple, set)) else [value]
                for item in values:
                    params.append((str(name), str(item)))
        params.append(("commit", "Sort and Filter"))
        params.append(("tag_id", cls.resolve_fandom(fandom) or DEFAULT_FANDOM))
        page = _positive_int(state.get("page"))
        if page and page > 1:
            params.append(("page", str(page)))
        return f"{AO3_BASE_URL}/works?{urlencode(params)}"

    def apply_blocked_tag_exclusions(self, url: str) -> str:
        if not self.blocked_tags:
            return url
        blocked = [tag.tag_text.strip() for tag in self.blocked_tags.list(limit=2000) if tag.tag_text.strip()]
        if not blocked:
            return url
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and path_parts[0] == "tags" and path_parts[-1] == "works":
            state: dict[str, Any] = {}
            query = parse_qs(parsed.query)
            page = (query.get("page") or [""])[0]
            if page:
                state["page"] = page
            parsed = urlparse(self.resolve_fandom_filter_url(unquote(path_parts[1]), state))
        params = parse_qsl(parsed.query, keep_blank_values=True)
        key = "work_search[excluded_tag_names]"
        existing: list[str] = []
        kept: list[tuple[str, str]] = []
        insert_at: int | None = None
        for name, value in params:
            if name == key:
                if insert_at is None:
                    insert_at = len(kept)
                existing.extend(self._split_ao3_tag_csv(value))
                continue
            kept.append((name, value))
        merged: list[str] = []
        seen: set[str] = set()
        for tag_text in [*existing, *blocked]:
            clean = tag_text.strip()
            folded = clean.casefold()
            if clean and folded not in seen:
                merged.append(clean)
                seen.add(folded)
        if not merged:
            return url
        if insert_at is None:
            insert_at = next((index for index, (name, _) in enumerate(kept) if name == "commit"), len(kept))
        kept.insert(insert_at, (key, ", ".join(merged)))
        return urlunparse(parsed._replace(query=urlencode(kept)))

    @staticmethod
    def _split_ao3_tag_csv(value: str) -> list[str]:
        return [part.strip() for part in str(value or "").split(",") if part.strip()]

    @staticmethod
    def _selected_filter_params(selected: dict[str, Any], prefix: str) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = []
        for name, values in selected.items():
            if not str(name).startswith(prefix):
                continue
            if isinstance(values, (list, tuple, set)):
                for value in values:
                    params.append((str(name), str(value)))
        return params

    def import_browse_html(
        self,
        html: str,
        source_url: str,
        context_type: str = "search",
        context_key: str = "",
    ) -> BrowseResult:
        if not html.strip():
            return BrowseResult(False, "AO3 browse HTML payload is empty.")
        try:
            parsed: ParsedBrowsePage = self.ao3_client.parse_browse_html(html, source_url)
        except Exception as exc:  # noqa: BLE001
            return BrowseResult(False, f"AO3 browse HTML import failed: {exc}")
        return self._store_parsed_browse(parsed, source_url, context_type, context_key)

    def _store_parsed_browse(
        self,
        parsed: ParsedBrowsePage,
        url: str,
        context_type: str = "search",
        context_key: str = "",
    ) -> BrowseResult:
        work_ids: list[str] = []
        works: list[Work] = []
        for summary in parsed.works:
            work = summary.to_work()
            author_key = work.author_key or normalize_author_key(work.author_name, work.author_url)
            work.author_key = author_key or None
            if self.blocked and self.blocked.is_blocked(work.work_id):
                continue
            if self.blocked_authors and author_key and self.blocked_authors.is_blocked(author_key):
                continue
            blocked_tag = None
            if self.blocked_tags:
                blocked_tag = next(
                    (tag for tag in summary.tags if self.blocked_tags.is_blocked(tag.tag_type.value, tag.tag_text)),
                    None,
                )
            if blocked_tag:
                self.works.upsert(work)
                self.tags.replace_for_work(work.work_id, summary.tags)
                if self.blocked:
                    self.blocked.block(work.work_id, None, f"Blocked by tag {blocked_tag.tag_text}")
                continue
            works.append(work)
            work_ids.append(work.work_id)
            self.works.upsert(work)
            self.tags.replace_for_work(work.work_id, summary.tags)
        snapshot = BrowseSnapshot(
            id=str(uuid.uuid4()),
            source_url=url,
            context_type=context_type or parsed.context_type,
            context_key=context_key or parsed.context_key or url,
            captured_at=utc_now_iso(),
            page_number=parsed.page_number,
            sort_mode=parsed.sort_mode,
            work_ids=work_ids,
        )
        self.snapshots.add(snapshot)
        return BrowseResult(True, f"Loaded {len(works)} works.", snapshot=snapshot, works=works, filter_metadata=parsed.filter_metadata)

    def _cached_result(self, url: str) -> BrowseResult | None:
        snapshot = self.snapshots.latest_for_url(url)
        if not snapshot:
            return None
        visible_ids = [work_id for work_id in snapshot.work_ids if not self.blocked or not self.blocked.is_blocked(work_id)]
        if self.blocked_tags:
            tag_blocked = self.blocked_tags.matching_work_ids(visible_ids)
            visible_ids = [work_id for work_id in visible_ids if work_id not in tag_blocked]
        works = self.works.list_by_ids(visible_ids)
        if len(works) != len(visible_ids):
            self.snapshots.delete_stale_missing_works()
            return None
        if self.blocked_authors:
            blocked_keys = self.blocked_authors.blocked_keys(
                [work.author_key or normalize_author_key(work.author_name, work.author_url) for work in works]
            )
            works = [
                work
                for work in works
                if (work.author_key or normalize_author_key(work.author_name, work.author_url) or "") not in blocked_keys
            ]
        return BrowseResult(True, f"Loaded {len(works)} cached works.", snapshot=snapshot, works=works)

    def recent_snapshots(self) -> list[BrowseSnapshot]:
        return self.snapshots.list_recent()


class AO3WorkFetchService:
    def __init__(self, works: WorkRepository, tags: TagRepository, ao3_client: Any) -> None:
        self.works = works
        self.tags = tags
        self.ao3_client = ao3_client

    def fetch_work(self, url_or_work_id: str) -> WorkFetchResult:
        try:
            parsed: ParsedWorkDetail = self.ao3_client.fetch_work(url_or_work_id)
        except Exception as exc:  # noqa: BLE001
            return WorkFetchResult(False, f"AO3 work fetch failed: {exc}")
        return self._store_parsed_work(parsed)

    def import_work_html(self, html: str, source_url: str) -> WorkFetchResult:
        if not html.strip():
            return WorkFetchResult(False, "AO3 work HTML payload is empty.")
        try:
            parsed: ParsedWorkDetail = self.ao3_client.parse_work_html(html, source_url)
        except Exception as exc:  # noqa: BLE001
            return WorkFetchResult(False, f"AO3 work HTML import failed: {exc}")
        return self._store_parsed_work(parsed)

    def _store_parsed_work(self, parsed: ParsedWorkDetail) -> WorkFetchResult:
        work = parsed.to_work()
        existing = self.works.get(work.work_id)
        if existing:
            if not work.published_at:
                work.published_at = existing.published_at
            if not work.last_ao3_updated_at:
                existing_updated = existing.last_ao3_updated_at
                existing_published = existing.published_at or work.published_at
                if existing_updated and existing_updated != existing_published:
                    work.last_ao3_updated_at = existing_updated
            elif (
                work.published_at
                and existing.last_ao3_updated_at
                and work.last_ao3_updated_at == work.published_at
                and existing.last_ao3_updated_at != work.published_at
            ):
                work.last_ao3_updated_at = existing.last_ao3_updated_at
        work.author_key = work.author_key or normalize_author_key(work.author_name, work.author_url) or None
        self.works.upsert(work)
        self.tags.replace_for_work(work.work_id, parsed.tags)
        return WorkFetchResult(True, "Work refreshed.", work=work)


class ReaderService:
    def __init__(
        self,
        works: WorkRepository,
        reader_assets: ReaderAssetRepository,
        reading: ReadingStateRepository,
        identities: IdentityRepository,
        ao3_client: Any,
    ) -> None:
        self.works = works
        self.reader_assets = reader_assets
        self.reading = reading
        self.identities = identities
        self.ao3_client = ao3_client

    def open_work(self, work_id: str, *, auto_download: bool = True) -> ReaderResult:
        work = self.works.get(work_id)
        if not work:
            return ReaderResult(False, "Work is not cached yet.")
        state = self._reading_state(work_id)
        position = _reader_position(state.last_position_ref)
        self._save_position(work_id, position, state=ReadingStatus.READING)
        asset = self.reader_assets.get_asset(work_id)
        chapters = self.reader_assets.list_chapters(work_id) if asset else []
        if not asset and auto_download:
            refresh = self.refresh_work(work_id)
            if refresh.ok:
                return refresh
            return ReaderResult(
                False,
                refresh.message,
                work=work,
                active_chapter_index=position["chapter_index"],
                scroll_percent=position["scroll_percent"],
                freshness="unknown",
            )
        return ReaderResult(
            True,
            "Reader loaded." if chapters else "No reader download cached yet.",
            work=work,
            asset=asset,
            chapters=chapters,
            active_chapter_index=_clamp_chapter(position["chapter_index"], chapters),
            scroll_percent=position["scroll_percent"],
            freshness=self._freshness(work, asset),
        )

    def cache_work_for_sampling(self, work_id: str) -> ReaderResult:
        work = self.works.get(work_id)
        if not work:
            return ReaderResult(False, "Work is not cached yet.")
        asset = self.reader_assets.get_asset(work_id)
        chapters = self.reader_assets.list_chapters(work_id) if asset else []
        freshness = self._freshness(work, asset)
        if asset and chapters and freshness != "outdated":
            return ReaderResult(True, "Reader sample cache loaded.", work=work, asset=asset, chapters=chapters, freshness=freshness)
        try:
            parsed: ParsedReaderDocument = self.ao3_client.fetch_reader_document(work.ao3_url)
        except Exception as exc:  # noqa: BLE001
            return ReaderResult(
                False,
                f"AO3 reader download failed: {exc}",
                work=work,
                asset=asset,
                chapters=chapters,
                freshness=freshness,
            )
        parsed.work.chapters_current = parsed.work.chapters_current or work.chapters_current
        self.works.upsert(parsed.work)
        now = utc_now_iso()
        asset = ReaderAsset(
            work_id=work_id,
            source_format="html",
            source_url=parsed.source_url,
            download_url=parsed.download_url,
            content_hash=parsed.content_hash,
            downloaded_chapter_count=len(parsed.chapters),
            known_ao3_chapter_count=parsed.work.chapters_current or work.chapters_current,
            downloaded_at=now,
            last_checked_at=now,
        )
        self.reader_assets.replace_document(asset, parsed.chapters)
        return ReaderResult(
            True,
            f"Downloaded {len(parsed.chapters)} chapter{'s' if len(parsed.chapters) != 1 else ''} for evaluation.",
            work=parsed.work,
            asset=asset,
            chapters=parsed.chapters,
            freshness=self._freshness(parsed.work, asset),
        )

    def refresh_work(self, work_id: str) -> ReaderResult:
        work = self.works.get(work_id)
        if not work:
            return ReaderResult(False, "Work is not cached yet.")
        state = self._reading_state(work_id)
        position = _reader_position(state.last_position_ref)
        try:
            parsed: ParsedReaderDocument = self.ao3_client.fetch_reader_document(work.ao3_url)
        except Exception as exc:  # noqa: BLE001
            asset = self.reader_assets.get_asset(work_id)
            chapters = self.reader_assets.list_chapters(work_id) if asset else []
            return ReaderResult(
                False,
                f"AO3 reader download failed: {exc}",
                work=work,
                asset=asset,
                chapters=chapters,
                active_chapter_index=_clamp_chapter(position["chapter_index"], chapters),
                scroll_percent=position["scroll_percent"],
                freshness=self._freshness(work, asset),
            )
        parsed.work.chapters_current = parsed.work.chapters_current or work.chapters_current
        self.works.upsert(parsed.work)
        now = utc_now_iso()
        asset = ReaderAsset(
            work_id=work_id,
            source_format="html",
            source_url=parsed.source_url,
            download_url=parsed.download_url,
            content_hash=parsed.content_hash,
            downloaded_chapter_count=len(parsed.chapters),
            known_ao3_chapter_count=parsed.work.chapters_current or work.chapters_current,
            downloaded_at=now,
            last_checked_at=now,
        )
        self.reader_assets.replace_document(asset, parsed.chapters)
        self._save_position(work_id, position, state=ReadingStatus.READING)
        return ReaderResult(
            True,
            f"Downloaded {len(parsed.chapters)} chapter{'s' if len(parsed.chapters) != 1 else ''}.",
            work=parsed.work,
            asset=asset,
            chapters=parsed.chapters,
            active_chapter_index=_clamp_chapter(position["chapter_index"], parsed.chapters),
            scroll_percent=position["scroll_percent"],
            freshness=self._freshness(parsed.work, asset),
        )

    def set_position(self, work_id: str, chapter_index: int, scroll_percent: float = 0.0, anchor: str = "") -> ServiceResult:
        self._save_position(
            work_id,
            {"chapter_index": max(1, int(chapter_index)), "scroll_percent": max(0.0, min(1.0, float(scroll_percent))), "anchor": anchor},
            state=ReadingStatus.READING,
        )
        return ServiceResult(True, "Reading position saved.")

    def _reading_state(self, work_id: str) -> ReadingState:
        identity = self.identities.get_or_create_local()
        state = self.reading.get(work_id, identity.local_user_id)
        if state:
            return state
        return ReadingState(work_id=work_id, local_user_id=identity.local_user_id, state=ReadingStatus.UNSEEN)

    def _save_position(self, work_id: str, position: dict[str, Any], *, state: ReadingStatus) -> None:
        identity = self.identities.get_or_create_local()
        existing = self.reading.get(work_id, identity.local_user_id)
        self.reading.upsert(
            ReadingState(
                work_id=work_id,
                local_user_id=identity.local_user_id,
                state=state,
                last_position_ref=json.dumps(
                    {
                        "chapter_index": max(1, int(position.get("chapter_index") or 1)),
                        "scroll_percent": max(0.0, min(1.0, float(position.get("scroll_percent") or 0))),
                        "anchor": str(position.get("anchor") or ""),
                        "updated_at": utc_now_iso(),
                    },
                    sort_keys=True,
                ),
                last_opened_at=utc_now_iso(),
                personal_priority=existing.personal_priority if existing else None,
                personal_labels=existing.personal_labels if existing else [],
                private_notes=existing.private_notes if existing else None,
            )
        )

    @staticmethod
    def _freshness(work: Work | None, asset: ReaderAsset | None) -> str:
        if not asset:
            return "missing"
        known = asset.known_ao3_chapter_count or (work.chapters_current if work else None)
        if known and known > asset.downloaded_chapter_count:
            return "outdated"
        if known and known <= asset.downloaded_chapter_count:
            return "current"
        return "unknown"


class SyncService:
    def __init__(self, mode: ModeService, overlays: SharedOverlayRepository, sync: SyncRepository, remote_client: Any) -> None:
        self.mode = mode
        self.overlays = overlays
        self.sync = sync
        self.remote_client = remote_client

    def fetch_overlay(self, work_id: str) -> RemoteResult:
        if self.mode.current_mode() is not RuntimeMode.SHARED:
            return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Shared Mode is off.")
        result = self.remote_client.get_work_overlay(work_id)
        if result.ok and isinstance(result.payload, SharedOverlay):
            self.overlays.upsert(result.payload)
            self.sync.upsert(SyncState(entity_type="shared_overlay", entity_id=work_id, sync_status="pulled", last_pull_at=utc_now_iso()))
        return result


class MergeService:
    def __init__(
        self,
        works: WorkRepository,
        evaluations: EvaluationRepository,
        overlays: SharedOverlayRepository,
        identities: IdentityRepository,
        mode: ModeService,
    ) -> None:
        self.works = works
        self.evaluations = evaluations
        self.overlays = overlays
        self.identities = identities
        self.mode = mode

    def work_view(self, work_id: str) -> MergedWorkView | None:
        work = self.works.get(work_id)
        if not work:
            return None
        identity = self.identities.get_or_create_local()
        local_eval = self.evaluations.latest_for_work(work_id, identity.local_user_id)
        overlay = None
        visibility = self.mode.overlay_visibility()
        if MergePolicy.overlay_allowed(self.mode.current_mode(), visibility):
            overlay = self.overlays.get_for_work(work_id)
        provenance = "merged" if overlay else "local"
        return MergedWorkView(work=work, local_evaluation=local_eval, shared_overlay=overlay, provenance=provenance)


class AdminRemoteService:
    def __init__(self, mode: ModeService, remote_client: Any) -> None:
        self.mode = mode
        self.remote_client = remote_client

    def admin_status(self) -> RemoteResult:
        if not self.mode.admin_widgets_visible():
            return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote admin identity is not active.")
        return RemoteResult(RemoteResultStatus.OK, "Admin panel available.")

    def list_users(self) -> RemoteResult:
        if not self.mode.admin_widgets_visible():
            return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Admin hidden until authenticated remote admin.")
        return self.remote_client.admin_users()


class LocalModelService:
    def __init__(self, settings: SettingsRepository, provider: ModelEvaluationProvider) -> None:
        self.settings = settings
        self.provider = provider

    def config(self) -> dict[str, Any]:
        return {
            "base_url": self.settings.get("lmstudio_base_url", "http://localhost:1234/v1"),
            "model": self.settings.get("lmstudio_model", ""),
            "timeout_seconds": self.settings.get("lmstudio_timeout_seconds", 180),
            "temperature": self.settings.get("lmstudio_temperature", 0.2),
            "context_length": self.settings.get("lmstudio_context_length", 0),
        }

    def save_config(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        temperature: float,
        context_length: int | float | str | None = None,
    ) -> ServiceResult:
        self.settings.set("lmstudio_base_url", base_url.strip().rstrip("/") or "http://localhost:1234/v1")
        self.settings.set("lmstudio_model", model.strip())
        self.settings.set("lmstudio_timeout_seconds", max(5, float(timeout_seconds)))
        self.settings.set("lmstudio_temperature", max(0, min(2, float(temperature))))
        self.settings.set("lmstudio_context_length", max(0, int(float(context_length or 0))))
        return ServiceResult(True, "LM Studio settings saved.")

    def available_models(self) -> RemoteResult:
        try:
            return RemoteResult(RemoteResultStatus.OK, "Loaded LM Studio models.", self.provider.available_models())
        except Exception as exc:  # noqa: BLE001
            return RemoteResult(RemoteResultStatus.OFFLINE, f"LM Studio is not reachable: {exc}", [])

    def available_model_details(self) -> RemoteResult:
        try:
            return RemoteResult(RemoteResultStatus.OK, "Loaded LM Studio models.", self.provider.available_model_details())
        except Exception as exc:  # noqa: BLE001
            return RemoteResult(RemoteResultStatus.OFFLINE, f"LM Studio is not reachable: {exc}", [])

    def begin_queue_model_session(self) -> ServiceResult:
        config = self.config()
        model = str(config.get("model") or "").strip()
        if not model:
            return ServiceResult(False, "Choose an LM Studio model in Settings first.", payload={"fatal": True})
        try:
            existing_id = self.provider.loaded_instance_id(model)
            if existing_id:
                return ServiceResult(
                    True,
                    f"Using loaded LM Studio model {model}.",
                    payload={"model": model, "instance_id": existing_id, "owned": False},
                )
            loaded = self.provider.load_model(model, int(config.get("context_length") or 0) or None)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(False, f"LM Studio model load failed: {exc}", payload={"fatal": True})
        instance_id = str(loaded.get("instance_id") or model)
        return ServiceResult(
            True,
            f"Loaded LM Studio model {model}.",
            payload={"model": model, "instance_id": instance_id, "owned": True, "load": loaded},
        )

    def load_selected_model(self) -> ServiceResult:
        config = self.config()
        model = str(config.get("model") or "").strip()
        if not model:
            return ServiceResult(False, "Choose an LM Studio model first.")
        try:
            loaded = self.provider.load_model(model, int(config.get("context_length") or 0) or None)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(False, f"LM Studio model load failed: {exc}")
        return ServiceResult(True, f"Loaded {model}.", payload=loaded)

    def unload_selected_model(self) -> ServiceResult:
        model = str(self.config().get("model") or "").strip()
        if not model:
            return ServiceResult(False, "Choose an LM Studio model first.")
        try:
            instance_id = self.provider.loaded_instance_id(model)
            if not instance_id:
                return ServiceResult(False, f"{model} is not currently loaded.")
            unloaded = self.provider.unload_model(instance_id)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(False, f"LM Studio model unload failed: {exc}")
        return ServiceResult(True, f"Unloaded {model}.", payload=unloaded)

    def end_queue_model_session(self, session: dict[str, Any] | None) -> ServiceResult:
        if not session or not session.get("owned"):
            return ServiceResult(True, "No AO3 Studio-owned model instance to unload.")
        instance_id = str(session.get("instance_id") or "").strip()
        if not instance_id:
            return ServiceResult(True, "No AO3 Studio-owned model instance to unload.")
        try:
            unloaded = self.provider.unload_model(instance_id)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(False, f"LM Studio model unload failed: {exc}")
        return ServiceResult(True, f"Unloaded LM Studio model {instance_id}.", payload=unloaded)


class QueueEvaluationRunnerService:
    def __init__(
        self,
        *,
        settings: SettingsRepository,
        queue_service: EvaluationQueueService,
        reader_service: ReaderService,
        evaluation_service: EvaluationService,
        local_model_service: LocalModelService,
        queue: EvaluationQueueRepository,
        batches: EvaluationBatchRepository,
        work_sets: WorkSetRepository,
        works: WorkRepository,
        tags: TagRepository,
        evaluations: EvaluationRepository,
        identities: IdentityRepository,
    ) -> None:
        self.settings = settings
        self.queue_service = queue_service
        self.reader_service = reader_service
        self.evaluation_service = evaluation_service
        self.local_model_service = local_model_service
        self.queue = queue
        self.batches = batches
        self.work_sets = work_sets
        self.works = works
        self.tags = tags
        self.evaluations = evaluations
        self.identities = identities

    def config_exists(self) -> bool:
        return self.settings.get(QUEUE_EVAL_CONFIG_KEY, None) is not None

    def config(self) -> QueueEvaluationConfig:
        return self._normalize_config(self.settings.get(QUEUE_EVAL_CONFIG_KEY, DEFAULT_QUEUE_EVAL_CONFIG))

    def save_config(self, values: dict[str, Any]) -> ServiceResult:
        config = self._normalize_config(values)
        self.settings.set(
            QUEUE_EVAL_CONFIG_KEY,
            {
                "include_metadata": config.include_metadata,
                "include_tags": config.include_tags,
                "start_chapter": config.start_chapter,
                "chapter_window": config.chapter_window,
                "target_words": config.target_words,
                "max_words": config.max_words,
                "skip_empty_chapters": config.skip_empty_chapters,
            },
        )
        return ServiceResult(True, "Queue evaluation settings saved.", payload=config)

    def sample_work(self, work_id: str, config: QueueEvaluationConfig | None = None) -> ServiceResult:
        config = config or self.config()
        reader = self.reader_service.cache_work_for_sampling(work_id)
        if not reader.ok or not reader.work:
            return ServiceResult(False, reader.message, payload=reader)
        chapters = sorted(reader.chapters, key=lambda chapter: chapter.chapter_index)
        chapter_texts = [(chapter, self._chapter_text(chapter.html)) for chapter in chapters]
        nonempty = [(chapter, text) for chapter, text in chapter_texts if self._word_count(text) > 0]
        if not nonempty:
            return ServiceResult(False, "No readable chapter text was cached for this work.", payload=reader)

        total_words = sum(self._word_count(text) for _, text in nonempty)
        skipped_empty: list[int] = []
        if total_words <= config.max_words:
            selected = nonempty
            sample_mode = "whole_work"
        else:
            selected = []
            sample_mode = "configured_sample"
            chapter_by_index = {chapter.chapter_index: text for chapter, text in chapter_texts}
            if config.skip_empty_chapters:
                probe = config.start_chapter
                while probe in chapter_by_index and self._word_count(chapter_by_index[probe]) == 0:
                    skipped_empty.append(probe)
                    probe += 1
                start_chapter = probe
            else:
                start_chapter = config.start_chapter
            start_position = next(
                (index for index, (chapter, text) in enumerate(nonempty) if chapter.chapter_index >= start_chapter and text),
                max(0, len(nonempty) - 1),
            )
            sampled_words = 0
            selected_nonempty = 0
            for chapter, text in nonempty[start_position:]:
                selected.append((chapter, text))
                selected_nonempty += 1
                sampled_words += self._word_count(text)
                if sampled_words >= config.max_words:
                    break
                if sampled_words >= config.target_words and selected_nonempty >= config.chapter_window:
                    break
            if not selected:
                selected = nonempty[:1]

        parts = []
        selected_words = 0
        truncated = False
        for chapter, text in selected:
            remaining = config.max_words - selected_words
            if remaining <= 0:
                truncated = True
                break
            chapter_text, word_count, was_truncated = self._limit_words(text, remaining)
            selected_words += word_count
            truncated = truncated or was_truncated
            heading = self._sample_chapter_heading(chapter)
            parts.append(f"{heading}\n{chapter_text}".strip())
            if selected_words >= config.max_words:
                break
        sample_text = "\n\n".join(part for part in parts if part).strip()
        selected_chapters = [chapter for chapter, _ in selected]
        metadata = self._work_metadata(reader.work) if config.include_metadata else {"work_id": reader.work.work_id}
        tag_lines = [
            f"- {tag.tag_type.value}: {tag.tag_text}"
            for tag in self.tags.list_for_work(reader.work.work_id)[:120]
        ] if config.include_tags else []
        chapter_scope = {
            "mode": sample_mode,
            "requested_start_chapter": config.start_chapter,
            "requested_chapter_window": config.chapter_window,
            "target_words": config.target_words,
            "max_words": config.max_words,
            "skip_empty_chapters": config.skip_empty_chapters,
            "actual_chapters": [
                {"chapter_index": chapter.chapter_index, "title": chapter.title}
                for chapter in selected_chapters
            ],
            "actual_start_chapter": selected_chapters[0].chapter_index if selected_chapters else None,
            "actual_end_chapter": selected_chapters[-1].chapter_index if selected_chapters else None,
            "sampled_words": selected_words,
            "total_cached_words": total_words,
            "truncated": truncated,
            "skipped_empty_chapters": skipped_empty,
            "reader_content_hash": reader.asset.content_hash if reader.asset else None,
            "sample_hash": stable_hash(sample_text),
        }
        return ServiceResult(
            True,
            f"Prepared {selected_words:,} sampled words.",
            payload=WorkEvaluationSample(text=sample_text, metadata=metadata, tags=tag_lines, chapter_scope=chapter_scope),
        )

    def run_batch(
        self,
        batch_id: str,
        *,
        work_order: list[str] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ServiceResult:
        batch = self.batches.get(batch_id)
        if not batch:
            return ServiceResult(False, "Queue cluster is unavailable.")
        work_set = self.work_sets.get(batch.work_set_id)
        if not work_set:
            return ServiceResult(False, "Queue cluster is unavailable.")
        identity = self.identities.get_or_create_local()
        active_statuses = {QueueStatus.QUEUED, QueueStatus.RUNNING, QueueStatus.FAILED, QueueStatus.SKIPPED}
        active_rows = [
            row
            for row in self.queue.list(batch_id=batch.id)
            if row.queue_status in active_statuses
        ]
        rows = {row.work_id: row for row in active_rows}
        ordered_work_ids = self._ordered_work_ids([row.work_id for row in active_rows], work_order)
        latest = self.evaluations.latest_for_works(ordered_work_ids, identity.local_user_id, batch.schema_key)
        candidates = [
            work_id
            for work_id in ordered_work_ids
            if not (latest.get(work_id) and latest[work_id].status is EvaluationStatus.COMPLETE)
        ]
        stats = QueueRunStats(total=len(candidates))
        if not candidates:
            self.queue_service.sync_batch_status(batch.id)
            return ServiceResult(True, "No unevaluated works remain in this queue.", payload=stats)

        session_result = self.local_model_service.begin_queue_model_session()
        if not session_result.ok:
            stats.fatal = True
            return ServiceResult(False, session_result.message, payload=stats)
        session = session_result.payload if isinstance(session_result.payload, dict) else {}
        config = self.config()
        fatal_message = ""
        try:
            for work_id in candidates:
                if should_cancel and should_cancel():
                    stats.cancelled = True
                    break
                row = rows.get(work_id)
                if not row:
                    continue
                self.queue.update_status(row.id, QueueStatus.RUNNING)
                sample = self.sample_work(work_id, config)
                if not sample.ok or not isinstance(sample.payload, WorkEvaluationSample):
                    self.queue.update_status(row.id, QueueStatus.FAILED, sample.message)
                    stats.failed += 1
                    continue
                result = self.evaluation_service.evaluate_sample_with_lm_studio(work_id, batch.schema_key, sample.payload)
                if not result.ok:
                    error_text = "; ".join(result.errors[:2]) or result.message
                    self.queue.update_status(row.id, QueueStatus.FAILED, error_text)
                    stats.failed += 1
                    if isinstance(result.payload, dict) and result.payload.get("fatal"):
                        stats.fatal = True
                        fatal_message = result.message
                        break
                    continue
                self.queue.update_status(row.id, QueueStatus.DONE)
                stats.completed += 1
                self.queue_service.sync_batch_status(batch.id)
        finally:
            unload_result = self.local_model_service.end_queue_model_session(session)
            self.queue_service.sync_batch_status(batch.id)

        if stats.fatal:
            return ServiceResult(False, fatal_message or "Queue evaluation stopped after an LM Studio error.", payload=stats)
        if stats.cancelled:
            return ServiceResult(True, f"Queue evaluation stopped after {stats.completed} completed work{'s' if stats.completed != 1 else ''}.", payload=stats)
        message = f"Queue evaluation finished: {stats.completed} completed"
        if stats.failed:
            message += f", {stats.failed} failed"
        if isinstance(unload_result, ServiceResult) and not unload_result.ok:
            message += f"; {unload_result.message}"
        return ServiceResult(True, message + ".", payload=stats)

    @staticmethod
    def _normalize_config(values: dict[str, Any] | QueueEvaluationConfig | None) -> QueueEvaluationConfig:
        if isinstance(values, QueueEvaluationConfig):
            raw = {
                "include_metadata": values.include_metadata,
                "include_tags": values.include_tags,
                "start_chapter": values.start_chapter,
                "chapter_window": values.chapter_window,
                "target_words": values.target_words,
                "max_words": values.max_words,
                "skip_empty_chapters": values.skip_empty_chapters,
            }
        else:
            raw = dict(DEFAULT_QUEUE_EVAL_CONFIG)
            if isinstance(values, dict):
                raw.update(values)
        target_words = max(250, int(float(raw.get("target_words") or DEFAULT_QUEUE_EVAL_CONFIG["target_words"])))
        max_words = max(target_words, int(float(raw.get("max_words") or DEFAULT_QUEUE_EVAL_CONFIG["max_words"])))
        return QueueEvaluationConfig(
            include_metadata=bool(raw.get("include_metadata", True)),
            include_tags=bool(raw.get("include_tags", True)),
            start_chapter=max(1, int(float(raw.get("start_chapter") or 1))),
            chapter_window=max(1, int(float(raw.get("chapter_window") or 1))),
            target_words=target_words,
            max_words=max_words,
            skip_empty_chapters=bool(raw.get("skip_empty_chapters", True)),
        )

    @staticmethod
    def _ordered_work_ids(work_ids: list[str], work_order: list[str] | None) -> list[str]:
        unique_work_ids = [work_id for work_id in dict.fromkeys(work_ids) if work_id]
        if not work_order:
            return unique_work_ids
        requested = [work_id for work_id in dict.fromkeys(work_order) if work_id in set(unique_work_ids)]
        requested_set = set(requested)
        return requested + [work_id for work_id in unique_work_ids if work_id not in requested_set]

    @staticmethod
    def _chapter_text(chapter_html: str) -> str:
        if not chapter_html:
            return ""
        text = BeautifulSoup(chapter_html, "lxml").get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\b[\w'-]+\b", text or ""))

    @classmethod
    def _limit_words(cls, text: str, max_words: int) -> tuple[str, int, bool]:
        words = re.findall(r"\S+", text or "")
        if len(words) <= max_words:
            return text.strip(), cls._word_count(text), False
        limited = " ".join(words[:max_words]).strip()
        return limited, cls._word_count(limited), True

    @staticmethod
    def _sample_chapter_heading(chapter: ReaderChapter) -> str:
        title = re.sub(r"\s+", " ", str(chapter.title or "").strip())
        return f"Chapter {chapter.chapter_index}: {title}" if title else f"Chapter {chapter.chapter_index}"

    @staticmethod
    def _work_metadata(work: Work) -> dict[str, Any]:
        return {
            "work_id": work.work_id,
            "title": work.title,
            "author_name": work.author_name,
            "author_url": work.author_url,
            "rating": work.rating,
            "language": work.language,
            "words": work.words,
            "chapters_current": work.chapters_current,
            "chapters_total": work.chapters_total_text,
            "kudos": work.kudos,
            "bookmarks": work.bookmarks,
            "hits": work.hits,
            "comments": work.comments,
            "summary_text": work.summary_text,
        }


def schema_definition_json(schema: EvaluationSchema) -> str:
    return json.dumps(asdict(schema), sort_keys=True)


def _dimension_from_dict(value: dict[str, Any]):
    from app.domain.entities import ScoreDimension
    from app.domain.enums import ScorePolarity

    try:
        polarity = ScorePolarity(str(value.get("polarity") or ScorePolarity.POSITIVE))
    except ValueError:
        polarity = ScorePolarity.POSITIVE

    return ScoreDimension(
        key=str(value.get("key", "")),
        label=str(value.get("label", value.get("key", ""))),
        description=str(value.get("description", "")),
        weight=float(value.get("weight", 1.0)),
        polarity=polarity,
    )


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _reader_position(value: str | None) -> dict[str, Any]:
    if value:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {
                    "chapter_index": max(1, int(parsed.get("chapter_index") or 1)),
                    "scroll_percent": max(0.0, min(1.0, float(parsed.get("scroll_percent") or 0))),
                    "anchor": str(parsed.get("anchor") or ""),
                }
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return {"chapter_index": 1, "scroll_percent": 0.0, "anchor": ""}


def _clamp_chapter(chapter_index: int, chapters: list[ReaderChapter]) -> int:
    if not chapters:
        return max(1, int(chapter_index or 1))
    return max(1, min(int(chapter_index or 1), len(chapters)))
