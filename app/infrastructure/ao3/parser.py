from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, unquote, unquote_plus, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.application.services import normalize_author_key, utc_now_iso
from app.domain.entities import FandomTagCatalogItem, ReaderChapter, Work, WorkTag
from app.domain.enums import TagType
from app.infrastructure.ao3.models import (
    AO3FilterGroup,
    AO3FilterMetadata,
    AO3FilterOption,
    ChapterReference,
    ParsedBrowsePage,
    ReaderDocument,
    WorkDetail,
    WorkSummary,
)

AO3_BASE_URL = "https://archiveofourown.org"
SCRAPE_VERSION = "ao3-html-v1"


def _source_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()


def _text(element: Tag | None) -> str:
    if not element:
        return ""
    return " ".join(element.get_text(" ", strip=True).split())


def _html(element: Tag | None) -> str:
    return str(element.decode_contents()).strip() if element else ""


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return urljoin(AO3_BASE_URL, url)


def _int_text(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _work_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"/works/(\d+)", url)
    return match.group(1) if match else None


def _fandom_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    tag_id = (query.get("tag_id") or [""])[0]
    if tag_id:
        return unquote_plus(tag_id)
    match = re.search(r"/tags/([^/]+)(?:/works)?/?$", parsed.path)
    if match:
        return unquote(match.group(1))
    return ""


def _sort_mode_from_url(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    sort_mode = (query.get("work_search[sort_column]") or [""])[0]
    return sort_mode or None


def _filter_key_from_name(name: str) -> str:
    match = re.search(r"_work_search\[([^\]]+)\]", name)
    raw = match.group(1) if match else name
    return {
        "rating_ids": "ratings",
        "archive_warning_ids": "warnings",
        "category_ids": "categories",
        "fandom_ids": "fandoms",
        "character_ids": "characters",
        "relationship_ids": "relationships",
        "freeform_ids": "additional_tags",
    }.get(raw, raw)


def _clean_filter_label(value: str) -> tuple[str, int | None]:
    text = " ".join(value.split())
    count_match = re.search(r"\(([\d,]+)\)\s*$", text)
    count = int(count_match.group(1).replace(",", "")) if count_match else None
    if count_match:
        text = text[: count_match.start()].strip()
    return text, count


def _option_from_input(input_node: Tag) -> AO3FilterOption | None:
    name = str(input_node.get("name") or "")
    value = str(input_node.get("value") or "")
    if not name or not value:
        return None
    parent = input_node.find_parent("li") or input_node.parent
    label_node = None
    input_id = input_node.get("id")
    if input_id:
        root = input_node.find_parent("form") or input_node.find_parent()
        if root:
            label_node = root.select_one(f"label[for='{input_id}']")
    if not label_node and isinstance(parent, Tag):
        label_node = parent.find("label")
    label, count = _clean_filter_label(_text(label_node or parent or input_node))
    if not label:
        label = value
    return AO3FilterOption(
        label=label,
        name=name,
        value=value,
        input_type=str(input_node.get("type") or "checkbox"),
        count=count,
    )


def _select_options(select: Tag | None) -> list[AO3FilterOption]:
    if not isinstance(select, Tag):
        return []
    name = str(select.get("name") or "")
    options: list[AO3FilterOption] = []
    for option in select.select("option"):
        label = _text(option) or "Any"
        options.append(
            AO3FilterOption(
                label=label,
                name=name,
                value=str(option.get("value") or ""),
                input_type="select",
            )
        )
    return options


def _next_dd(node: Tag) -> Tag | None:
    sibling = node.find_next_sibling()
    while sibling is not None:
        if isinstance(sibling, Tag) and sibling.name == "dd":
            return sibling
        sibling = sibling.find_next_sibling()
    return None


def _filter_metadata(soup: BeautifulSoup, source_url: str) -> AO3FilterMetadata | None:
    form = soup.select_one("form#work-filters")
    if not isinstance(form, Tag):
        return None
    metadata = AO3FilterMetadata(
        fandom=_fandom_from_url(source_url),
        sort_options=_select_options(form.select_one("select[name='work_search[sort_column]']")),
        language_options=_select_options(form.select_one("select[name='work_search[language_id]']")),
    )
    seen: set[tuple[str, str]] = set()
    for dt in form.select("dt"):
        if not isinstance(dt, Tag):
            continue
        raw_label = _text(dt).replace("?", "").strip()
        if "heading" in set(dt.get("class", [])) or raw_label.lower() in {"include", "exclude", "more options"}:
            continue
        dd = _next_dd(dt)
        if not isinstance(dd, Tag):
            continue
        inputs = [
            node
            for node in dd.select("input[name]")
            if isinstance(node, Tag) and str(node.get("name", "")).startswith(("include_work_search", "exclude_work_search"))
        ]
        if not inputs:
            continue
        mode = "include" if str(inputs[0].get("name", "")).startswith("include_") else "exclude"
        key = _filter_key_from_name(str(inputs[0].get("name") or ""))
        if (mode, key) in seen:
            continue
        seen.add((mode, key))
        label = re.sub(r"^(Include|Exclude)\s+", "", raw_label, flags=re.IGNORECASE) or key.replace("_", " ").title()
        options = [option for input_node in inputs if (option := _option_from_input(input_node))]
        if options:
            metadata.groups.append(AO3FilterGroup(key=key, label=label, mode=mode, options=options))
    return metadata


def _tag_type_from_classes(classes: list[str]) -> TagType:
    class_set = set(classes)
    if "fandoms" in class_set or "fandom" in class_set:
        return TagType.FANDOM
    if "relationships" in class_set or "relationship" in class_set:
        return TagType.RELATIONSHIP
    if "characters" in class_set or "character" in class_set:
        return TagType.CHARACTER
    if "freeforms" in class_set or "freeform" in class_set:
        return TagType.FREEFORM
    if "warnings" in class_set or "warning" in class_set:
        return TagType.WARNING
    if "category" in class_set or "categories" in class_set:
        return TagType.CATEGORY
    if "rating" in class_set or "ratings" in class_set:
        return TagType.RATING
    return TagType.OTHER


def _tags_from_container(work_id: str, container: Tag) -> list[WorkTag]:
    tags: list[WorkTag] = []
    for item in container.select("ul.tags li"):
        if not isinstance(item, Tag):
            continue
        link = item.select_one("a.tag") or item.select_one("a")
        tag_text = _text(link or item)
        if not tag_text:
            continue
        tags.append(
            WorkTag(
                work_id=work_id,
                tag_type=_tag_type_from_classes(list(item.get("class", []))),
                tag_text=tag_text,
                tag_url=_absolute(link.get("href") if isinstance(link, Tag) else None),
            )
        )
    existing = {(tag.tag_type, tag.tag_text) for tag in tags}
    for text in _required_category_tags(container):
        key = (TagType.CATEGORY, text)
        if key not in existing:
            tags.append(WorkTag(work_id=work_id, tag_type=TagType.CATEGORY, tag_text=text))
            existing.add(key)
    return tags


def _required_category_tags(container: Tag) -> list[str]:
    labels: list[str] = []
    class_map = {
        "category-f-f": "F/F",
        "category-fm": "F/M",
        "category-f-m": "F/M",
        "category-m-m": "M/M",
        "category-gen": "Gen",
        "category-multi": "Multi",
        "category-other": "Other",
    }
    for node in container.select("ul.required-tags li, .required-tags li, .required-tags span, li[class*='category-'], span[class*='category-']"):
        if not isinstance(node, Tag):
            continue
        classes = [str(item).strip().casefold() for item in node.get("class", [])]
        text = _text(node) or str(node.get("title") or node.get("aria-label") or "").strip()
        for cls in classes:
            if cls in class_map:
                text = class_map[cls]
                break
        if text:
            for candidate in ["F/F", "F/M", "M/M", "Gen", "Multi", "Other"]:
                if candidate.casefold() in text.casefold() and candidate not in labels:
                    labels.append(candidate)
    return labels


def _stat(container: Tag, name: str) -> int | None:
    node = container.select_one(f"dd.{name}")
    return _int_text(_text(node))


def _chapters(container: Tag) -> tuple[int | None, str | None]:
    chapter_text = _text(container.select_one("dd.chapters"))
    if not chapter_text:
        return None, None
    parts = [part.strip() for part in chapter_text.split("/")]
    current = _int_text(parts[0]) if parts else None
    total = parts[1] if len(parts) > 1 else None
    return current, total


def parse_browse_page(html: str, source_url: str) -> ParsedBrowsePage:
    soup = BeautifulSoup(html, "lxml")
    works: list[WorkSummary] = []
    for blurb in soup.select("li.work.blurb, li[role='article'].work"):
        if not isinstance(blurb, Tag):
            continue
        link = blurb.select_one("h4.heading a[href*='/works/']")
        work_id = _work_id_from_url(link.get("href") if isinstance(link, Tag) else None)
        if not work_id:
            id_attr = str(blurb.get("id", ""))
            work_id = id_attr.replace("work_", "") if id_attr.startswith("work_") else ""
        if not work_id:
            continue
        title = _text(link)
        author_link = blurb.select_one("h4.heading a[rel='author']") or blurb.select_one("a[rel='author']")
        author_name = _text(author_link) or None
        author_url = _absolute(author_link.get("href") if isinstance(author_link, Tag) else None)
        summary = blurb.select_one("blockquote.userstuff.summary") or blurb.select_one("blockquote.summary")
        current, total = _chapters(blurb)
        work = Work(
            work_id=work_id,
            ao3_url=_absolute(link.get("href") if isinstance(link, Tag) else None) or f"{AO3_BASE_URL}/works/{work_id}",
            title=title or None,
            author_name=author_name,
            author_url=author_url,
            author_key=normalize_author_key(author_name, author_url) or None,
            summary_html=_html(summary) or None,
            summary_text=_text(summary) or None,
            rating=_text(blurb.select_one("span.rating, a.rating, li.rating")) or None,
            language=_text(blurb.select_one("dd.language")) or None,
            words=_stat(blurb, "words"),
            chapters_current=current,
            chapters_total_text=total,
            kudos=_stat(blurb, "kudos"),
            bookmarks=_stat(blurb, "bookmarks"),
            hits=_stat(blurb, "hits"),
            comments=_stat(blurb, "comments"),
            published_at=_text(blurb.select_one("dd.published")) or None,
            last_ao3_updated_at=_text(blurb.select_one("p.datetime, p.updated, dd.status")) or None,
            last_scraped_at=utc_now_iso(),
            scrape_version=SCRAPE_VERSION,
            raw_source_hash=_source_hash(str(blurb)),
        )
        works.append(WorkSummary(work=work, tags=_tags_from_container(work_id, blurb)))
    page_number = None
    page_match = re.search(r"[?&]page=(\d+)", source_url)
    if page_match:
        page_number = int(page_match.group(1))
    context_key = urlparse(source_url).path.strip("/") or source_url
    metadata = _filter_metadata(soup, source_url)
    return ParsedBrowsePage(
        source_url=source_url,
        works=works,
        context_type="fandom" if metadata and metadata.fandom else "browse",
        context_key=metadata.fandom if metadata and metadata.fandom else context_key,
        page_number=page_number,
        sort_mode=_sort_mode_from_url(source_url),
        filter_metadata=metadata,
    )


def parse_work_page(html: str, source_url: str) -> WorkDetail:
    soup = BeautifulSoup(html, "lxml")
    work_id = _work_id_from_url(source_url) or _work_id_from_url(str(soup.select_one("link[rel='canonical']")))
    if not work_id:
        title_text = soup.get_text(" ", strip=True)
        work_id = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
        missing = "could have been deleted" in title_text.lower() or "error 404" in title_text.lower()
        return WorkDetail(
            work=Work(
                work_id=work_id,
                ao3_url=source_url,
                title="Deleted or unavailable work" if missing else None,
                last_scraped_at=utc_now_iso(),
                scrape_version=SCRAPE_VERSION,
                raw_source_hash=_source_hash(html),
                is_deleted_or_missing=missing,
            )
        )
    title = _text(soup.select_one("h2.title"))
    author = soup.select_one("h3.byline a[rel='author'], h3.byline a")
    author_name = _text(author) or None
    author_url = _absolute(author.get("href") if isinstance(author, Tag) else None)
    summary = soup.select_one("div.summary blockquote.userstuff") or soup.select_one("blockquote.userstuff.summary")
    meta = soup.select_one("dl.work.meta.group") or soup
    current, total = _chapters(meta)
    work = Work(
        work_id=work_id,
        ao3_url=source_url,
        title=title or None,
        author_name=author_name,
        author_url=author_url,
        author_key=normalize_author_key(author_name, author_url) or None,
        summary_html=_html(summary) or None,
        summary_text=_text(summary) or None,
        rating=_text(meta.select_one("dd.rating a, dd.rating")) or None,
        language=_text(meta.select_one("dd.language")) or None,
        words=_stat(meta, "words"),
        chapters_current=current,
        chapters_total_text=total,
        kudos=_stat(meta, "kudos"),
        bookmarks=_stat(meta, "bookmarks"),
        hits=_stat(meta, "hits"),
        comments=_stat(meta, "comments"),
        published_at=_text(meta.select_one("dd.published")) or None,
        last_ao3_updated_at=_text(meta.select_one("dd.status, p.datetime")) or None,
        last_scraped_at=utc_now_iso(),
        scrape_version=SCRAPE_VERSION,
        raw_source_hash=_source_hash(html),
        is_deleted_or_missing=False,
    )
    tags = _tags_from_work_meta(work_id, meta)
    chapters = _chapter_refs(soup)
    return WorkDetail(work=work, tags=tags, chapters=chapters)


def parse_html_download_url(html: str, source_url: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    selectors = [
        "li.download a[href]",
        "a[href*='/downloads/'][href]",
        "a[href*='download'][href]",
    ]
    for selector in selectors:
        for link in soup.select(selector):
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href") or "")
            label = _text(link).lower()
            marker = f"{href} {label}".lower()
            if ".html" in marker and ("download" in marker or label == "html"):
                return _absolute(href)
    return None


def parse_reader_html(
    html: str,
    source_url: str,
    download_url: str,
    work: Work,
    chapter_refs: list[ChapterReference] | None = None,
) -> ReaderDocument:
    soup = BeautifulSoup(html, "lxml")
    for node in soup.select("script, style, noscript, iframe, nav, header, footer, form"):
        node.decompose()
    chapters: list[ReaderChapter] = []
    ref_titles = {
        ref.chapter_number: ref.label
        for ref in chapter_refs or []
        if ref.chapter_number and ref.label and not _is_generic_chapter_title(ref.label, ref.chapter_number)
    }
    for index, node in enumerate(_reader_chapter_nodes(soup), start=1):
        title = _reader_chapter_title(node, index)
        if _is_generic_chapter_title(title, index) and index in ref_titles:
            title = ref_titles[index]
        anchor = str(node.get("id") or f"chapter-{index}") if isinstance(node, Tag) else f"chapter-{index}"
        body = _reader_chapter_body(node)
        clean_html = _sanitize_reader_html(body)
        text_hash = hashlib.sha256(BeautifulSoup(clean_html, "lxml").get_text(" ", strip=True).encode("utf-8")).hexdigest()
        chapters.append(
            ReaderChapter(
                work_id=work.work_id,
                chapter_index=index,
                title=title,
                ao3_url=f"{source_url}#{anchor}" if anchor else source_url,
                anchor=anchor,
                html=clean_html,
                text_hash=text_hash,
            )
        )
    if not chapters:
        fallback = soup.select_one("#chapters, #workskin, body") or soup
        clean_html = _sanitize_reader_html(str(fallback))
        text_hash = hashlib.sha256(BeautifulSoup(clean_html, "lxml").get_text(" ", strip=True).encode("utf-8")).hexdigest()
        chapters.append(
            ReaderChapter(
                work_id=work.work_id,
                chapter_index=1,
                title="Chapter 1",
                ao3_url=source_url,
                anchor="chapter-1",
                html=clean_html,
                text_hash=text_hash,
            )
        )
    return ReaderDocument(
        work=work,
        source_url=source_url,
        download_url=download_url,
        content_hash=_source_hash(html),
        chapters=chapters,
    )


def parse_fandom_tag_catalog(html: str, source_url: str, fandom_key: str) -> list[FandomTagCatalogItem]:
    soup = BeautifulSoup(html, "lxml")
    fetched_at = utc_now_iso()
    items: dict[tuple[str, str], FandomTagCatalogItem] = {}
    for link in soup.select("a[href*='/tags/'], a[href*='/fandoms/']"):
        if not isinstance(link, Tag):
            continue
        text = _text(link)
        href = str(link.get("href") or "")
        if not text or text in {"works", "bookmarks"}:
            continue
        category = _catalog_category(link)
        key = (text.lower(), category)
        items[key] = FandomTagCatalogItem(
            fandom_key=fandom_key,
            tag_text=text,
            tag_url=_absolute(href),
            category=category,
            source=source_url,
            fetched_at=fetched_at,
        )
    return list(items.values())


def _reader_chapter_nodes(soup: BeautifulSoup) -> list[Tag]:
    candidates = [
        node
        for node in soup.select("#chapters .chapter, .chapter, section.chapter, article.chapter")
        if isinstance(node, Tag) and _text(node)
    ]
    if candidates:
        return candidates
    userstuff = [
        node
        for node in soup.select("#chapters .userstuff, #workskin .userstuff")
        if isinstance(node, Tag) and _text(node)
    ]
    if len(userstuff) > 1:
        return userstuff
    headings = [
        heading
        for heading in soup.find_all(["h2", "h3", "h4"])
        if isinstance(heading, Tag) and re.search(r"\bchapter\b", _text(heading), re.IGNORECASE)
    ]
    nodes: list[Tag] = []
    for heading in headings:
        parts = [str(heading)]
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in {"h2", "h3", "h4"} and re.search(
                r"\bchapter\b", _text(sibling), re.IGNORECASE
            ):
                break
            parts.append(str(sibling))
        fragment = BeautifulSoup(f"<div>{''.join(parts)}</div>", "lxml").select_one("div")
        if isinstance(fragment, Tag) and _text(fragment):
            nodes.append(fragment)
    return nodes


def _reader_chapter_title(node: Tag, index: int) -> str:
    heading = node.select_one("h1, h2, h3, h4")
    title = _text(heading) if isinstance(heading, Tag) else ""
    return title or f"Chapter {index}"


def _is_generic_chapter_title(title: str, index: int) -> bool:
    normalized = re.sub(r"\s+", " ", str(title or "").strip()).casefold()
    return normalized in {f"chapter {index}", f"chapter {index}:", str(index)}


def _reader_chapter_body(node: Tag) -> str:
    body = node.select_one(".userstuff")
    return str(body if isinstance(body, Tag) else node)


def _sanitize_reader_html(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "lxml")
    allowed_tags = {
        "a",
        "b",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "li",
        "ol",
        "p",
        "pre",
        "section",
        "span",
        "strong",
        "u",
        "ul",
    }
    for tag in list(soup.find_all(True)):
        if tag.name in {"script", "style", "noscript", "iframe", "object", "embed"}:
            tag.decompose()
            continue
        if tag.name not in allowed_tags:
            tag.unwrap()
            continue
        attrs: dict[str, str] = {}
        if tag.name == "a" and tag.get("href"):
            attrs["href"] = _absolute(str(tag.get("href")))
            attrs["target"] = "_blank"
            attrs["rel"] = "noopener noreferrer"
        if tag.get("id"):
            attrs["id"] = re.sub(r"[^a-zA-Z0-9_-]", "-", str(tag.get("id")))[:80]
        tag.attrs = attrs
    body = soup.body or soup
    return str(body.decode_contents()).strip()


def _catalog_category(link: Tag) -> str:
    href = str(link.get("href") or "")
    text = _text(link)
    section_text = ""
    parent = link.find_parent(["ul", "ol", "dl", "section", "div"]) or link.parent
    if isinstance(parent, Tag):
        heading = parent.find_previous(["h2", "h3", "h4", "dt"])
        section_text = _text(heading).lower() if isinstance(heading, Tag) else ""
    lower = f"{section_text} {text}".lower()
    if "/fandoms/" in href:
        return "relationship_index"
    if "parent tags" in lower:
        return "parent"
    if "same meaning" in lower:
        return "same_meaning"
    if "/works" in href and "*s*" in href:
        return "relationship"
    if "/works" in href and "*a*" in href:
        return "platonic"
    if "character" in lower:
        return "character"
    return "related"


def _tags_from_work_meta(work_id: str, meta: Tag) -> list[WorkTag]:
    tags: list[WorkTag] = []
    tag_sections = {
        TagType.FANDOM: "dd.fandom.tags a.tag, dd.fandom a",
        TagType.RELATIONSHIP: "dd.relationship.tags a.tag, dd.relationship a",
        TagType.CHARACTER: "dd.character.tags a.tag, dd.character a",
        TagType.FREEFORM: "dd.freeform.tags a.tag, dd.freeform a",
        TagType.WARNING: "dd.warning.tags a.tag, dd.warning a",
        TagType.CATEGORY: "dd.category.tags a.tag, dd.category a",
    }
    for tag_type, selector in tag_sections.items():
        for link in meta.select(selector):
            text = _text(link)
            if text:
                tags.append(
                    WorkTag(
                        work_id=work_id,
                        tag_type=tag_type,
                        tag_text=text,
                        tag_url=_absolute(link.get("href")),
                    )
                )
    if not tags:
        tags = _tags_from_container(work_id, meta)
    return tags


def _chapter_refs(soup: BeautifulSoup) -> list[ChapterReference]:
    refs: list[ChapterReference] = []
    for index, link in enumerate(soup.select("ol.chapter.index a[href*='/chapters/'], select#selected_id option"), start=1):
        if not isinstance(link, Tag):
            continue
        href = link.get("href") or link.get("value")
        label = _text(link)
        if not href or not label:
            continue
        refs.append(ChapterReference(label=label, url=_absolute(href) or str(href), chapter_number=index))
    return refs
