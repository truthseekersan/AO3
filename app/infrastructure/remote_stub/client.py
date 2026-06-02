from __future__ import annotations

from app.application.dto import RemoteResult
from app.application.services import utc_now_iso
from app.domain.entities import SharedOverlay
from app.domain.enums import RemoteResultStatus


class RemoteStubClient:
    """Typed future-API surface that never blocks Local Mode."""

    def login(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote login is not implemented in the local MVP.")

    def refresh(self) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote refresh is not implemented in the local MVP.")

    def me(self) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote identity is not configured.")

    def get_work_overlay(self, work_id: str) -> RemoteResult:
        overlay = SharedOverlay(
            id=f"stub-overlay-{work_id}",
            work_id=work_id,
            remote_schema_version="official-v0-stub",
            aggregate_scores={"story_fit": 7, "craft": 7, "emotional_pull": 7},
            evaluation_count=0,
            divergence_flags={"stub": True},
            last_fetched_at=utc_now_iso(),
            source_etag="stub",
        )
        return RemoteResult(RemoteResultStatus.OK, "Loaded placeholder shared overlay.", overlay)

    def publish_evaluation(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Publishing waits for the remote API.")

    def evaluations_for_work(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote evaluations are not configured.")

    def official_schemas(self) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote official schemas are not configured.")

    def sync_push(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote sync push is not configured.")

    def sync_pull(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote sync pull is not configured.")

    def admin_users(self) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote admin API is not configured.")

    def admin_ban_user(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote admin API is not configured.")

    def admin_delete_user_evaluations(self, *_args, **_kwargs) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote admin API is not configured.")

    def admin_divergence(self) -> RemoteResult:
        return RemoteResult(RemoteResultStatus.NOT_CONFIGURED, "Remote admin API is not configured.")
