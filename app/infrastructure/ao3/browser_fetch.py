from __future__ import annotations

import configparser
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - exercised only in minimal test envs
    curl_requests = None

AO3_COOKIE_HOST = "%archiveofourown.org"


class BrowserFetchError(RuntimeError):
    pass


@dataclass(slots=True)
class FirefoxCookieSnapshot:
    profile_name: str
    profile_path: Path
    cookies: dict[str, str]
    cookie_names: list[str]


class BrowserAssistedFetcher:
    """Fetch AO3 through the user's local Firefox session cookies.

    AO3 Studio must not launch a separate hidden browser. Firefox is the user's
    active AO3 session, so this adapter copies Firefox's cookie DB locally,
    reads only AO3 cookies, and uses them for local-first AO3 requests.
    """

    def __init__(self, timeout: float = 2.0) -> None:
        self.timeout = timeout

    def fetch_html(self, url: str, timeout: float | None = None) -> str:
        if curl_requests is None:
            raise BrowserFetchError("curl_cffi is not installed in this Python environment.")
        snapshot = self._best_firefox_cookie_snapshot()
        if not snapshot:
            raise BrowserFetchError(
                "No AO3 cookies were found in Firefox. Open AO3 in Firefox, log in or clear the AO3 check, then retry."
            )
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                response = curl_requests.get(
                    url,
                    impersonate="firefox",
                    cookies=snapshot.cookies,
                    headers=self._firefox_headers(),
                    timeout=timeout or self.timeout,
                    allow_redirects=True,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
            if response.status_code == 403 and "Shields are up" in response.text:
                raise BrowserFetchError(
                    f"AO3 rejected the Firefox session from profile '{snapshot.profile_name}'. "
                    "Open AO3 in Firefox, make sure the page loads there, then retry."
                )
            response.raise_for_status()
            return response.text
        try:
            raise last_error or BrowserFetchError("Firefox-session AO3 request failed.")
        except Exception as exc:  # noqa: BLE001
            raise BrowserFetchError(f"Firefox-session AO3 request failed after two fast attempts: {exc}") from exc

    def open_account_session(self, url: str) -> str:
        return url

    def prewarm(self) -> None:
        return

    def _best_firefox_cookie_snapshot(self) -> FirefoxCookieSnapshot | None:
        snapshots = [snapshot for profile in self._firefox_profiles() if (snapshot := self._cookie_snapshot(profile))]
        if not snapshots:
            return None
        return max(snapshots, key=self._snapshot_score)

    @staticmethod
    def _snapshot_score(snapshot: FirefoxCookieSnapshot) -> tuple[int, float]:
        names = set(snapshot.cookie_names)
        score = 0
        if "user_credentials" in names:
            score += 100
        if "_otwarchive_session" in names:
            score += 80
        if "cf_clearance" in names:
            score += 40
        if "__cf_bm" in names:
            score += 20
        try:
            mtime = snapshot.profile_path.joinpath("cookies.sqlite").stat().st_mtime
        except OSError:
            mtime = 0.0
        return score, mtime

    def _cookie_snapshot(self, profile: tuple[str, Path]) -> FirefoxCookieSnapshot | None:
        profile_name, profile_path = profile
        cookie_db = profile_path / "cookies.sqlite"
        if not cookie_db.exists():
            return None
        temp_path = Path(tempfile.gettempdir()) / f"ao3_studio_firefox_cookies_{uuid.uuid4().hex}.sqlite"
        try:
            shutil.copy2(cookie_db, temp_path)
            rows = self._read_cookie_rows(temp_path)
        except (OSError, sqlite3.Error):
            return None
        finally:
            temp_path.unlink(missing_ok=True)
        if not rows:
            return None
        cookies: dict[str, str] = {}
        names: list[str] = []
        now = int(time.time())
        for row in rows:
            expiry = int(row["expiry"] or 0)
            if expiry and expiry < now:
                continue
            name = str(row["name"] or "")
            value = str(row["value"] or "")
            host = str(row["host"] or "")
            if not name or not value or not host:
                continue
            cookies[name] = value
            names.append(name)
        if not names:
            return None
        return FirefoxCookieSnapshot(profile_name=profile_name, profile_path=profile_path, cookies=cookies, cookie_names=names)

    @staticmethod
    def _read_cookie_rows(cookie_db: Path) -> list[sqlite3.Row]:
        connection = sqlite3.connect(cookie_db)
        connection.row_factory = sqlite3.Row
        try:
            return list(
                connection.execute(
                    """
                    SELECT host, name, value, path, expiry
                    FROM moz_cookies
                    WHERE host LIKE ?
                    ORDER BY lastAccessed DESC
                    """,
                    (AO3_COOKIE_HOST,),
                )
            )
        finally:
            connection.close()

    @classmethod
    def _firefox_profiles(cls) -> list[tuple[str, Path]]:
        root = cls._firefox_root()
        profiles_root = root / "Profiles"
        profiles: list[tuple[str, Path]] = []
        seen: set[Path] = set()
        for name, path in cls._profiles_from_ini(root / "profiles.ini"):
            resolved = path if path.is_absolute() else root / path
            if resolved.exists() and resolved not in seen:
                profiles.append((name, resolved))
                seen.add(resolved)
        if profiles_root.exists():
            for path in profiles_root.iterdir():
                if path.is_dir() and path not in seen:
                    profiles.append((path.name, path))
                    seen.add(path)
        return profiles

    @staticmethod
    def _profiles_from_ini(path: Path) -> list[tuple[str, Path]]:
        if not path.exists():
            return []
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        default_first: list[tuple[str, Path]] = []
        other: list[tuple[str, Path]] = []
        for section in parser.sections():
            if not section.startswith("Profile"):
                continue
            raw_path = parser.get(section, "Path", fallback="")
            if not raw_path:
                continue
            name = parser.get(section, "Name", fallback=Path(raw_path).name)
            target = Path(raw_path)
            bucket = default_first if parser.get(section, "Default", fallback="") == "1" else other
            bucket.append((name, target))
        return default_first + other

    @staticmethod
    def _firefox_root() -> Path:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Mozilla" / "Firefox"
        return Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox"

    @staticmethod
    def _firefox_headers() -> dict[str, str]:
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Sec-GPC": "1",
            "Upgrade-Insecure-Requests": "1",
        }
