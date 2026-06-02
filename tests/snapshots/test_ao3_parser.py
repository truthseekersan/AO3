from __future__ import annotations

from pathlib import Path

from app.domain.enums import TagType
from app.infrastructure.ao3.models import ChapterReference
from app.infrastructure.ao3.parser import (
    parse_browse_page,
    parse_fandom_tag_catalog,
    parse_html_download_url,
    parse_reader_html,
    parse_work_page,
)

SNAPSHOT_DIR = Path(__file__).parent


def test_parse_browse_page() -> None:
    html = (SNAPSHOT_DIR / "ao3_browse_sample.html").read_text(encoding="utf-8")
    page = parse_browse_page(html, "https://archiveofourown.org/tags/Fandom/works?page=2")

    assert len(page.works) == 1
    summary = page.works[0]
    assert summary.work.work_id == "12345"
    assert summary.work.words == 12345
    assert summary.work.chapters_current == 3
    assert summary.work.chapters_total_text == "7"
    assert {tag.tag_type for tag in summary.tags} >= {TagType.FANDOM, TagType.RELATIONSHIP, TagType.FREEFORM, TagType.CATEGORY}
    assert any(tag.tag_type is TagType.CATEGORY and tag.tag_text == "F/F" for tag in summary.tags)
    assert page.filter_metadata is not None
    assert page.filter_metadata.fandom == "Fandom"
    assert page.filter_metadata.sort_options[0].value == "revised_at"
    assert page.filter_metadata.language_options[1].label == "English"
    include_ratings = next(group for group in page.filter_metadata.groups if group.mode == "include" and group.key == "ratings")
    exclude_ratings = next(group for group in page.filter_metadata.groups if group.mode == "exclude" and group.key == "ratings")
    assert include_ratings.options[0].label == "Teen And Up Audiences"
    assert include_ratings.options[0].count == 3523
    assert exclude_ratings.options[0].value == "13"


def test_parse_work_page() -> None:
    html = (SNAPSHOT_DIR / "ao3_work_sample.html").read_text(encoding="utf-8")
    detail = parse_work_page(html, "https://archiveofourown.org/works/12345")

    assert detail.work.title == "A Useful Work"
    assert detail.work.author_name == "example"
    assert detail.work.published_at == "01 Jan 2026"
    assert detail.work.last_ao3_updated_at == "08 Jan 2026"
    assert detail.work.kudos == 456
    assert detail.chapters[0].label == "Chapter 1"
    assert parse_html_download_url(html, "https://archiveofourown.org/works/12345").endswith("A%20Useful%20Work.html?updated_at=123")


def test_parse_work_page_does_not_use_published_as_updated() -> None:
    html = """
    <html><body>
      <h2 class="title">Only Published</h2>
      <h3 class="byline"><a rel="author" href="/users/example/pseuds/example">example</a></h3>
      <dl class="work meta group">
        <dd class="published">01 Jan 2026</dd>
        <dd class="words">1,000</dd>
      </dl>
    </body></html>
    """
    detail = parse_work_page(html, "https://archiveofourown.org/works/999")

    assert detail.work.published_at == "01 Jan 2026"
    assert detail.work.last_ao3_updated_at is None


def test_parse_reader_html_download() -> None:
    work_html = (SNAPSHOT_DIR / "ao3_work_sample.html").read_text(encoding="utf-8")
    reader_html = (SNAPSHOT_DIR / "ao3_reader_download_sample.html").read_text(encoding="utf-8")
    detail = parse_work_page(work_html, "https://archiveofourown.org/works/12345")

    document = parse_reader_html(
        reader_html,
        "https://archiveofourown.org/works/12345",
        "https://archiveofourown.org/downloads/12345/A%20Useful%20Work.html",
        detail.work,
    )

    assert document.content_hash
    assert len(document.chapters) == 2
    assert document.chapters[0].title == "Chapter 1: Arrival"
    assert "Max Caulfield" in document.chapters[0].html
    assert "<script" not in document.chapters[1].html


def test_parse_reader_html_uses_work_page_chapter_titles_when_download_is_generic() -> None:
    work_html = (SNAPSHOT_DIR / "ao3_work_sample.html").read_text(encoding="utf-8")
    detail = parse_work_page(work_html, "https://archiveofourown.org/works/12345")
    reader_html = """
    <html><body><div id="chapters">
      <div class="chapter" id="chapter-1"><h3>Chapter 1</h3><div class="userstuff"><p>One.</p></div></div>
    </div></body></html>
    """

    document = parse_reader_html(
        reader_html,
        "https://archiveofourown.org/works/12345",
        "https://archiveofourown.org/downloads/12345/work.html",
        detail.work,
        [ChapterReference("Chapter 1: A Real Title", "https://archiveofourown.org/works/12345/chapters/1", 1)],
    )

    assert document.chapters[0].title == "Chapter 1: A Real Title"


def test_parse_fandom_tag_catalog() -> None:
    html = (SNAPSHOT_DIR / "ao3_fandom_tag_sample.html").read_text(encoding="utf-8")
    items = parse_fandom_tag_catalog(html, "https://archiveofourown.org/tags/Life", "life")

    by_text = {item.tag_text: item for item in items}

    assert by_text["Video Games"].category == "parent"
    assert by_text["Amberpricefield - Fandom"].category == "same_meaning"
    assert by_text['Maxine "Max" Caulfield/Chloe Price'].category == "relationship"
    assert by_text['Maxine "Max" Caulfield & Victoria Chase'].category == "platonic"
    assert by_text["Chloe Price (Life is Strange)"].category == "character"
