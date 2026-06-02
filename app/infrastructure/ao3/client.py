from __future__ import annotations

import re

import httpx

from app.infrastructure.ao3.browser_fetch import BrowserAssistedFetcher, BrowserFetchError
from app.infrastructure.ao3.models import ParsedBrowsePage, ParsedReaderDocument, ParsedWorkDetail
from app.infrastructure.ao3.parser import (
    AO3_BASE_URL,
    parse_browse_page,
    parse_fandom_tag_catalog,
    parse_html_download_url,
    parse_reader_html,
    parse_work_page,
)


class AO3AccessBlockedError(RuntimeError):
    pass


class AO3Client:
    def __init__(self, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.browser_fetcher = BrowserAssistedFetcher()

    def fetch_browse(self, url: str) -> ParsedBrowsePage:
        normalized = self._normalize_url(url)
        try:
            html = self.browser_fetcher.fetch_html(normalized)
            self._raise_if_shielded(html)
            return parse_browse_page(html, normalized)
        except AO3AccessBlockedError:
            raise
        except BrowserFetchError as exc:
            raise AO3AccessBlockedError(str(exc)) from exc
        except Exception:
            response = self._get(normalized)
            return parse_browse_page(response.text, str(response.url))

    def fetch_work(self, url_or_work_id: str) -> ParsedWorkDetail:
        url = self._normalize_work_url(url_or_work_id)
        try:
            html = self.browser_fetcher.fetch_html(url)
            self._raise_if_shielded(html)
            return parse_work_page(html, url)
        except AO3AccessBlockedError:
            raise
        except BrowserFetchError as exc:
            raise AO3AccessBlockedError(str(exc)) from exc
        except Exception:
            response = self._get(url)
            return parse_work_page(response.text, str(response.url))

    def fetch_reader_document(self, url_or_work_id: str) -> ParsedReaderDocument:
        url = self._normalize_work_url(url_or_work_id)
        try:
            work_html = self.browser_fetcher.fetch_html(url)
            self._raise_if_shielded(work_html)
        except AO3AccessBlockedError:
            raise
        except BrowserFetchError as exc:
            raise AO3AccessBlockedError(str(exc)) from exc
        except Exception:
            response = self._get(url)
            work_html = response.text
            url = str(response.url)
        detail = parse_work_page(work_html, url)
        download_url = parse_html_download_url(work_html, url)
        if not download_url:
            raise AO3AccessBlockedError("AO3 HTML download link was not found on this work page.")
        try:
            reader_html = self.browser_fetcher.fetch_html(download_url)
            self._raise_if_shielded(reader_html)
        except AO3AccessBlockedError:
            raise
        except BrowserFetchError as exc:
            raise AO3AccessBlockedError(str(exc)) from exc
        except Exception:
            response = self._get(download_url)
            reader_html = response.text
            download_url = str(response.url)
        return parse_reader_html(reader_html, url, download_url, detail.work, detail.chapters)

    def fetch_fandom_tag_catalog(self, url: str, fandom_key: str):
        normalized = self._normalize_url(url)
        try:
            html = self.browser_fetcher.fetch_html(normalized)
            self._raise_if_shielded(html)
            return parse_fandom_tag_catalog(html, normalized, fandom_key)
        except AO3AccessBlockedError:
            raise
        except BrowserFetchError as exc:
            raise AO3AccessBlockedError(str(exc)) from exc
        except Exception:
            response = self._get(normalized)
            return parse_fandom_tag_catalog(response.text, str(response.url), fandom_key)

    def open_account_session(self, url: str = AO3_BASE_URL) -> str:
        return self._normalize_url(url)

    def prewarm(self) -> None:
        self.browser_fetcher.prewarm()

    @staticmethod
    def parse_browse_html(html: str, source_url: str) -> ParsedBrowsePage:
        return parse_browse_page(html, source_url)

    @staticmethod
    def parse_work_html(html: str, source_url: str) -> ParsedWorkDetail:
        return parse_work_page(html, source_url)

    def _get(self, url: str) -> httpx.Response:
        with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self._browser_headers()) as client:
            response = client.get(
                url,
            )
            if response.status_code == 403 and "Shields are up" in response.text:
                raise AO3AccessBlockedError(
                    "AO3 Shields are up for direct requests. AO3 Studio will retry with Firefox session cookies when available."
                )
            response.raise_for_status()
            return response

    @staticmethod
    def _raise_if_shielded(html: str) -> None:
        if "Shields are up" in html:
            raise AO3AccessBlockedError(
                "AO3 Shields are up for the Firefox-backed request. Open AO3 in Firefox, make sure the page loads there, then retry."
            )

    @staticmethod
    def _normalize_url(url: str) -> str:
        value = url.strip()
        if not value:
            raise ValueError("AO3 URL is required.")
        if value.startswith("/"):
            return f"{AO3_BASE_URL}{value}"
        if not value.startswith("http"):
            return f"{AO3_BASE_URL}/{value.lstrip('/')}"
        return value

    @classmethod
    def _normalize_work_url(cls, url_or_work_id: str) -> str:
        value = url_or_work_id.strip()
        if re.fullmatch(r"\d+", value):
            return f"{AO3_BASE_URL}/works/{value}"
        return cls._normalize_url(value)

    @staticmethod
    def _browser_headers() -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; "
                "rv:151.0) Gecko/20100101 Firefox/151.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }
