from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import (
    AuthState,
    EvaluationBatchStatus,
    EvaluationStatus,
    QueueStatus,
    RarityTier,
    ReadingStatus,
    RemoteRole,
    ScorePolarity,
    TagType,
)

JsonDict = dict[str, Any]


@dataclass(slots=True)
class LocalIdentity:
    local_user_id: str
    display_name: str | None
    created_at: str
    last_seen_at: str
    client_install_fingerprint: str | None = None
    is_local_owner: bool = True


@dataclass(slots=True)
class RemoteIdentity:
    remote_user_id: str | None = None
    remote_role: RemoteRole = RemoteRole.USER
    auth_state: AuthState = AuthState.NOT_CONFIGURED
    api_base_url: str = ""
    api_key_present: bool = False
    jwt_present: bool = False
    last_sync_at: str | None = None


@dataclass(slots=True)
class Work:
    work_id: str
    ao3_url: str
    title: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    author_key: str | None = None
    summary_html: str | None = None
    summary_text: str | None = None
    rating: str | None = None
    language: str | None = None
    words: int | None = None
    chapters_current: int | None = None
    chapters_total_text: str | None = None
    kudos: int | None = None
    bookmarks: int | None = None
    hits: int | None = None
    comments: int | None = None
    published_at: str | None = None
    last_ao3_updated_at: str | None = None
    last_scraped_at: str = ""
    scrape_version: str = "ao3-html-v1"
    raw_source_hash: str | None = None
    is_deleted_or_missing: bool = False


@dataclass(slots=True)
class WorkTag:
    work_id: str
    tag_type: TagType
    tag_text: str
    tag_url: str | None = None
    id: int | None = None


@dataclass(slots=True)
class FandomProfile:
    fandom_key: str
    tag: str
    display_name: str
    color: str = "#58a6ff"
    avatar_url: str | None = None
    notes: str | None = None
    default_filter: JsonDict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    selected_at: str | None = None


@dataclass(slots=True)
class CharacterProfile:
    id: str
    fandom_key: str
    name: str
    full_name: str = ""
    color: str = "#58a6ff"
    avatar_url: str | None = None
    tag_urls: list[str] = field(default_factory=list)
    notes: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class FandomTagCatalogItem:
    fandom_key: str
    tag_text: str
    tag_url: str | None = None
    category: str = "related"
    source: str = "ao3"
    fetched_at: str = ""
    id: int | None = None


@dataclass(slots=True)
class WorkCollectionItem:
    work_id: str
    fandom_key: str | None
    collected_at: str
    note: str | None = None


@dataclass(slots=True)
class BlockedWork:
    work_id: str
    fandom_key: str | None
    blocked_at: str
    reason: str | None = None


@dataclass(slots=True)
class BlockedAuthor:
    author_key: str
    display_name: str | None
    author_url: str | None
    fandom_key: str | None
    blocked_at: str
    reason: str | None = None


@dataclass(slots=True)
class BlockedAuthorGroup:
    author: BlockedAuthor
    works: list[Work] = field(default_factory=list)
    explicit_work_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class BlockedWorkView:
    block: BlockedWork
    work: Work | None = None


@dataclass(slots=True)
class BlockedTag:
    tag_type: TagType
    tag_text: str
    fandom_key: str | None
    blocked_at: str
    reason: str | None = None
    id: int | None = None


@dataclass(slots=True)
class BrowseSnapshot:
    id: str
    source_url: str
    context_type: str
    context_key: str
    captured_at: str
    page_number: int | None
    sort_mode: str | None
    work_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkSet:
    id: str
    fandom_key: str
    name: str
    filter_state: JsonDict
    filter_signature: str
    created_at: str
    updated_at: str
    last_refreshed_at: str | None = None


@dataclass(slots=True)
class WorkSetPage:
    id: str
    set_id: str
    page_number: int
    source_url: str
    work_ids: list[str]
    captured_at: str
    last_refreshed_at: str | None = None


@dataclass(slots=True)
class WorkSetItem:
    set_id: str
    work_id: str
    first_seen_at: str
    last_seen_at: str
    last_page_number: int | None = None


@dataclass(slots=True)
class FavoriteTag:
    fandom_key: str
    tag_type: TagType
    tag_text: str
    color: str
    created_at: str
    updated_at: str
    id: int | None = None


@dataclass(slots=True)
class TagColorOverride:
    fandom_key: str
    tag_type: TagType
    tag_text: str
    color: str
    updated_at: str
    id: int | None = None


@dataclass(slots=True)
class FandomStyleOverride:
    fandom_key: str
    enabled: bool
    settings: JsonDict = field(default_factory=dict)
    updated_at: str = ""


@dataclass(slots=True)
class WorkRarity:
    work_id: str
    local_user_id: str
    manual_rarity: RarityTier | None = None
    manual_updated_at: str | None = None
    computed_quality_score: float | None = None
    computed_rarity: RarityTier | None = None
    computed_schema_key: str | None = None
    computed_schema_version: str | None = None
    computed_evaluation_id: str | None = None
    computed_at: str | None = None

    @property
    def effective_rarity(self) -> RarityTier:
        return self.manual_rarity or self.computed_rarity or RarityTier.COMMON


@dataclass(slots=True)
class ScoreDimension:
    key: str
    label: str
    description: str = ""
    weight: float = 1.0
    polarity: ScorePolarity = ScorePolarity.POSITIVE


@dataclass(slots=True)
class ScoreRange:
    minimum: int = 1
    maximum: int = 10
    step: int = 1


@dataclass(slots=True)
class EvaluationSchema:
    schema_key: str
    name: str
    version: str
    label: str
    description: str
    dimensions: list[ScoreDimension]
    score_range: ScoreRange = field(default_factory=ScoreRange)
    required_fields: list[str] = field(default_factory=list)
    justification_rules: JsonDict = field(default_factory=dict)
    aggregation_rules: JsonDict = field(default_factory=dict)
    shared_compatibility: JsonDict = field(default_factory=dict)
    prompt_template: str = ""
    is_active: bool = False
    is_official_shared_compatible: bool = False
    created_at: str = ""


@dataclass(slots=True)
class Evaluation:
    id: str
    work_id: str
    local_user_id: str
    schema_key: str
    schema_version: str
    scores: JsonDict
    status: EvaluationStatus
    created_at: str
    updated_at: str
    subscores: JsonDict | None = None
    notes_markdown: str | None = None
    evidence: JsonDict | None = None
    model_name: str | None = None
    model_prompt_hash: str | None = None
    chapter_scope: JsonDict | None = None


@dataclass(slots=True)
class EvaluationBatch:
    id: str
    work_set_id: str
    fandom_key: str
    schema_key: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    status: EvaluationBatchStatus = EvaluationBatchStatus.QUEUED


@dataclass(slots=True)
class EvaluationQueueItem:
    id: str
    work_id: str
    priority: int
    queue_status: QueueStatus
    requested_at: str
    reason: str | None = None
    finished_at: str | None = None
    error_text: str | None = None
    batch_id: str | None = None
    schema_key: str | None = None


@dataclass(slots=True)
class ReadingState:
    work_id: str
    local_user_id: str
    state: ReadingStatus
    last_position_ref: str | None = None
    last_opened_at: str | None = None
    personal_priority: int | None = None
    personal_labels: list[str] = field(default_factory=list)
    private_notes: str | None = None


@dataclass(slots=True)
class ReaderAsset:
    work_id: str
    source_format: str
    source_url: str
    download_url: str
    content_hash: str
    downloaded_chapter_count: int
    known_ao3_chapter_count: int | None = None
    downloaded_at: str = ""
    last_checked_at: str | None = None


@dataclass(slots=True)
class ReaderChapter:
    work_id: str
    chapter_index: int
    title: str
    ao3_url: str | None
    anchor: str | None
    html: str
    text_hash: str


@dataclass(slots=True)
class WorkEvaluationSample:
    text: str
    metadata: JsonDict
    tags: list[str]
    chapter_scope: JsonDict


@dataclass(slots=True)
class SyncState:
    entity_type: str
    entity_id: str
    sync_status: str
    remote_id: str | None = None
    last_push_at: str | None = None
    last_pull_at: str | None = None
    sync_hash: str | None = None


@dataclass(slots=True)
class SharedOverlay:
    id: str
    work_id: str
    remote_schema_version: str
    last_fetched_at: str
    aggregate_scores: JsonDict | None = None
    evaluation_count: int | None = None
    divergence_flags: JsonDict | None = None
    source_etag: str | None = None
