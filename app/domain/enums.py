from __future__ import annotations

from enum import StrEnum


class RuntimeMode(StrEnum):
    LOCAL = "local"
    SHARED = "shared"


class RemoteRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class AuthState(StrEnum):
    NOT_CONFIGURED = "not_configured"
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    ERROR = "error"


class EvaluationStatus(StrEnum):
    DRAFT = "draft"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class EvaluationBatchStatus(StrEnum):
    QUEUED = "queued"
    PARTIAL = "partial"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class ScorePolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class QueueStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ReadingStatus(StrEnum):
    UNSEEN = "unseen"
    QUEUED = "queued"
    SAMPLING = "sampling"
    READING = "reading"
    FINISHED = "finished"
    ABANDONED = "abandoned"


class RemoteResultStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    OFFLINE = "offline"
    OK = "ok"
    ERROR = "error"


class OverlayVisibility(StrEnum):
    LOCAL_ONLY = "local_only"
    LOCAL_AND_MINE = "local_and_mine"
    COMMUNITY_AGGREGATE = "community_aggregate"
    FULL_REMOTE_DETAILS = "full_remote_details"


class RarityTier(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    BEST = "best"


class TagType(StrEnum):
    FANDOM = "fandom"
    RELATIONSHIP = "relationship"
    CHARACTER = "character"
    FREEFORM = "freeform"
    WARNING = "warning"
    CATEGORY = "category"
    RATING = "rating"
    OTHER = "other"
