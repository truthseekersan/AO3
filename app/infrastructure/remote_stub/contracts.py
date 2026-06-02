from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"


class MeResponse(BaseModel):
    remote_user_id: str | None = None
    remote_role: str = "user"
    display_name: str | None = None


class WorkOverlayResponse(BaseModel):
    work_id: str
    remote_schema_version: str
    aggregate_scores: dict[str, Any] = Field(default_factory=dict)
    evaluation_count: int = 0
    divergence_flags: dict[str, Any] = Field(default_factory=dict)
    source_etag: str | None = None


class EvaluationPublishRequest(BaseModel):
    work_id: str
    schema_key: str
    schema_version: str
    scores: dict[str, Any]
    notes_markdown: str | None = None
    evidence: dict[str, Any] | None = None


class SyncPushRequest(BaseModel):
    entities: list[dict[str, Any]] = Field(default_factory=list)


class SyncPullRequest(BaseModel):
    since: str | None = None
    entity_types: list[str] = Field(default_factory=list)


class AdminUserResponse(BaseModel):
    remote_user_id: str
    display_name: str | None = None
    role: str = "user"
    disabled: bool = False


class ModerationDivergenceResponse(BaseModel):
    work_id: str
    flags: dict[str, Any] = Field(default_factory=dict)
