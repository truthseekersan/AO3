from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.entities import BrowseSnapshot, Evaluation, ReaderAsset, ReaderChapter, SharedOverlay, Work
from app.domain.enums import RemoteResultStatus


@dataclass(slots=True)
class ServiceResult:
    ok: bool
    message: str = ""
    payload: Any = None


@dataclass(slots=True)
class BrowseResult(ServiceResult):
    snapshot: BrowseSnapshot | None = None
    works: list[Work] = field(default_factory=list)
    filter_metadata: Any | None = None


@dataclass(slots=True)
class WorkFetchResult(ServiceResult):
    work: Work | None = None


@dataclass(slots=True)
class ReaderResult(ServiceResult):
    work: Work | None = None
    asset: ReaderAsset | None = None
    chapters: list[ReaderChapter] = field(default_factory=list)
    active_chapter_index: int = 1
    scroll_percent: float = 0.0
    freshness: str = "unknown"


@dataclass(slots=True)
class EvaluationResult(ServiceResult):
    evaluation: Evaluation | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RemoteResult:
    status: RemoteResultStatus
    message: str
    payload: Any = None

    @property
    def ok(self) -> bool:
        return self.status is RemoteResultStatus.OK


@dataclass(slots=True)
class MergedWorkView:
    work: Work
    local_evaluation: Evaluation | None = None
    shared_overlay: SharedOverlay | None = None
    provenance: str = "local"
