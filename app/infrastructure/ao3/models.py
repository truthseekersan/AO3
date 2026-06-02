from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.entities import ReaderChapter, Work, WorkTag


@dataclass(slots=True)
class BrowseContext:
    source_url: str
    context_type: str = "search"
    context_key: str = ""
    page_number: int | None = None
    sort_mode: str | None = None


@dataclass(slots=True)
class ChapterReference:
    label: str
    url: str
    chapter_number: int | None = None


@dataclass(slots=True)
class WorkSummary:
    work: Work
    tags: list[WorkTag] = field(default_factory=list)

    def to_work(self) -> Work:
        return self.work


@dataclass(slots=True)
class WorkDetail:
    work: Work
    tags: list[WorkTag] = field(default_factory=list)
    chapters: list[ChapterReference] = field(default_factory=list)

    def to_work(self) -> Work:
        return self.work


@dataclass(slots=True)
class ReaderDocument:
    work: Work
    source_url: str
    download_url: str
    content_hash: str
    chapters: list[ReaderChapter] = field(default_factory=list)


@dataclass(slots=True)
class ScrapeHealthResult:
    ok: bool
    message: str
    parser_version: str = "ao3-html-v1"


@dataclass(slots=True)
class AO3FilterOption:
    label: str
    name: str
    value: str
    input_type: str = "checkbox"
    count: int | None = None


@dataclass(slots=True)
class AO3FilterGroup:
    key: str
    label: str
    mode: str
    options: list[AO3FilterOption] = field(default_factory=list)


@dataclass(slots=True)
class AO3FilterMetadata:
    fandom: str = ""
    sort_options: list[AO3FilterOption] = field(default_factory=list)
    language_options: list[AO3FilterOption] = field(default_factory=list)
    groups: list[AO3FilterGroup] = field(default_factory=list)


@dataclass(slots=True)
class ParsedBrowsePage:
    source_url: str
    works: list[WorkSummary]
    context_type: str = "search"
    context_key: str = ""
    page_number: int | None = None
    sort_mode: str | None = None
    filter_metadata: AO3FilterMetadata | None = None


ParsedWorkDetail = WorkDetail
ParsedReaderDocument = ReaderDocument
