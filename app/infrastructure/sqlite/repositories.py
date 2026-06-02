from __future__ import annotations

import json
import platform
import uuid
from dataclasses import asdict
from typing import Any

from app.application.services import normalize_author_key, utc_now_iso
from app.domain.entities import (
    BlockedAuthor,
    BlockedTag,
    BlockedWork,
    BrowseSnapshot,
    CharacterProfile,
    Evaluation,
    EvaluationBatch,
    EvaluationQueueItem,
    EvaluationSchema,
    FandomProfile,
    FandomStyleOverride,
    FandomTagCatalogItem,
    FavoriteTag,
    LocalIdentity,
    ReaderAsset,
    ReaderChapter,
    ReadingState,
    RemoteIdentity,
    ScoreDimension,
    ScoreRange,
    SharedOverlay,
    SyncState,
    TagColorOverride,
    Work,
    WorkRarity,
    WorkSet,
    WorkSetPage,
    WorkTag,
)
from app.domain.enums import (
    AuthState,
    EvaluationBatchStatus,
    EvaluationStatus,
    OverlayVisibility,
    QueueStatus,
    RarityTier,
    ReadingStatus,
    RemoteRole,
    RuntimeMode,
    ScorePolarity,
    TagType,
)
from app.infrastructure.sqlite.database import SQLiteDatabase


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _score_polarity(value: Any) -> ScorePolarity:
    try:
        return ScorePolarity(str(value or ScorePolarity.POSITIVE))
    except ValueError:
        return ScorePolarity.POSITIVE


def _rarity(value: Any) -> RarityTier | None:
    if not value:
        return None
    try:
        return RarityTier(str(value))
    except ValueError:
        return None


def _bool(value: Any) -> bool:
    return bool(int(value or 0))


class SQLiteSettingsRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value_json FROM app_config WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        return _json_loads(row["value_json"], default)

    def set(self, key: str, value: Any) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_config(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, _json_dumps(value), utc_now_iso()),
            )

    def get_mode(self) -> RuntimeMode:
        return RuntimeMode(str(self.get("runtime_mode", RuntimeMode.LOCAL.value)))

    def set_mode(self, mode: RuntimeMode) -> None:
        self.set("runtime_mode", mode.value)

    def get_overlay_visibility(self) -> OverlayVisibility:
        return OverlayVisibility(str(self.get("overlay_visibility", OverlayVisibility.COMMUNITY_AGGREGATE.value)))

    def set_overlay_visibility(self, visibility: OverlayVisibility) -> None:
        self.set("overlay_visibility", visibility.value)


class SQLiteIdentityRepository:
    def __init__(self, db: SQLiteDatabase, settings: SQLiteSettingsRepository) -> None:
        self.db = db
        self.settings = settings

    def get_or_create_local(self) -> LocalIdentity:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM local_user ORDER BY created_at LIMIT 1").fetchone()
            if row:
                return self._row_to_local(row)
            now = utc_now_iso()
            local_user_id = str(uuid.uuid4())
            fingerprint = f"{platform.node()}:{uuid.getnode()}"
            conn.execute(
                """
                INSERT INTO local_user(
                    id, display_name, created_at, last_seen_at, client_install_fingerprint, is_local_owner
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (local_user_id, "Local Reader", now, now, fingerprint, 1),
            )
            return LocalIdentity(
                local_user_id=local_user_id,
                display_name="Local Reader",
                created_at=now,
                last_seen_at=now,
                client_install_fingerprint=fingerprint,
                is_local_owner=True,
            )

    def save_local(self, identity: LocalIdentity) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO local_user(
                    id, display_name, created_at, last_seen_at, client_install_fingerprint, is_local_owner
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = excluded.display_name,
                    last_seen_at = excluded.last_seen_at,
                    client_install_fingerprint = excluded.client_install_fingerprint,
                    is_local_owner = excluded.is_local_owner
                """,
                (
                    identity.local_user_id,
                    identity.display_name,
                    identity.created_at,
                    identity.last_seen_at,
                    identity.client_install_fingerprint,
                    int(identity.is_local_owner),
                ),
            )

    def get_remote(self) -> RemoteIdentity:
        value = self.settings.get("remote_identity", {})
        if not isinstance(value, dict):
            value = {}
        return RemoteIdentity(
            remote_user_id=value.get("remote_user_id"),
            remote_role=RemoteRole(str(value.get("remote_role", RemoteRole.USER.value))),
            auth_state=AuthState(str(value.get("auth_state", AuthState.NOT_CONFIGURED.value))),
            api_base_url=str(value.get("api_base_url", "")),
            api_key_present=bool(value.get("api_key_present", False)),
            jwt_present=bool(value.get("jwt_present", False)),
            last_sync_at=value.get("last_sync_at"),
        )

    def save_remote(self, identity: RemoteIdentity) -> None:
        self.settings.set("remote_identity", asdict(identity))

    @staticmethod
    def _row_to_local(row) -> LocalIdentity:
        return LocalIdentity(
            local_user_id=row["id"],
            display_name=row["display_name"],
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
            client_install_fingerprint=row["client_install_fingerprint"],
            is_local_owner=_bool(row["is_local_owner"]),
        )


class SQLiteWorkRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def upsert(self, work: Work) -> None:
        with self.db.connect() as conn:
            if not str(work.published_at or "").strip():
                cached = conn.execute(
                    "SELECT published_at FROM work_publication_dates WHERE work_id = ?",
                    (work.work_id,),
                ).fetchone()
                if cached:
                    work.published_at = cached["published_at"]
            conn.execute(
                """
                INSERT INTO works(
                    work_id, ao3_url, title, author_name, author_url, author_key, summary_html, summary_text,
                    rating, language, words, chapters_current, chapters_total_text, kudos,
                    bookmarks, hits, comments, published_at, last_ao3_updated_at, last_scraped_at,
                    scrape_version, raw_source_hash, is_deleted_or_missing
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    ao3_url = excluded.ao3_url,
                    title = excluded.title,
                    author_name = excluded.author_name,
                    author_url = excluded.author_url,
                    author_key = excluded.author_key,
                    summary_html = excluded.summary_html,
                    summary_text = excluded.summary_text,
                    rating = excluded.rating,
                    language = excluded.language,
                    words = excluded.words,
                    chapters_current = excluded.chapters_current,
                    chapters_total_text = excluded.chapters_total_text,
                    kudos = excluded.kudos,
                    bookmarks = excluded.bookmarks,
                    hits = excluded.hits,
                    comments = excluded.comments,
                    published_at = excluded.published_at,
                    last_ao3_updated_at = excluded.last_ao3_updated_at,
                    last_scraped_at = excluded.last_scraped_at,
                    scrape_version = excluded.scrape_version,
                    raw_source_hash = excluded.raw_source_hash,
                    is_deleted_or_missing = excluded.is_deleted_or_missing
                """,
                self._params(work),
            )
            if str(work.published_at or "").strip():
                conn.execute(
                    """
                    INSERT INTO work_publication_dates(work_id, published_at, source_url, cached_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(work_id) DO UPDATE SET
                        published_at = COALESCE(NULLIF(excluded.published_at, ''), work_publication_dates.published_at),
                        source_url = COALESCE(excluded.source_url, work_publication_dates.source_url),
                        cached_at = excluded.cached_at
                    """,
                    (work.work_id, work.published_at, work.ao3_url, utc_now_iso()),
                )

    def get(self, work_id: str) -> Work | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM works WHERE work_id = ?", (work_id,)).fetchone()
        return self._row(row) if row else None

    def list_by_ids(self, work_ids: list[str]) -> list[Work]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT * FROM works WHERE work_id IN ({placeholders})", ids).fetchall()
        by_id = {str(row["work_id"]): self._row(row) for row in rows}
        return [work for work_id in ids if (work := by_id.get(work_id))]

    def list_by_author_keys(self, author_keys: list[str], limit: int = 500) -> list[Work]:
        keys = sorted({str(key or "").strip().casefold() for key in author_keys if str(key or "").strip()})
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM works
                WHERE author_key IN ({placeholders})
                ORDER BY author_key ASC, COALESCE(title, work_id) ASC
                LIMIT ?
                """,
                [*keys, limit],
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_recent(self, limit: int = 50, search: str = "") -> list[Work]:
        pattern = f"%{search.strip()}%"
        with self.db.connect() as conn:
            if search.strip():
                rows = conn.execute(
                    """
                    SELECT * FROM works
                    WHERE title LIKE ? OR author_name LIKE ? OR summary_text LIKE ?
                    ORDER BY last_scraped_at DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, pattern, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM works ORDER BY last_scraped_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(row) for row in rows]

    def count(self) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM works").fetchone()[0])

    def delete_uncollected_cache(self, keep_work_ids: list[str] | None = None) -> int:
        keep = [str(work_id) for work_id in (keep_work_ids or []) if str(work_id).strip()]
        keep_clause = ""
        params: list[Any] = []
        if keep:
            placeholders = ",".join("?" for _ in keep)
            keep_clause = f"AND work_id NOT IN ({placeholders})"
            params.extend(keep)
        with self.db.connect() as conn:
            before = int(conn.execute("SELECT COUNT(*) FROM works").fetchone()[0])
            conn.execute(
                f"""
                DELETE FROM works
                WHERE NOT EXISTS (SELECT 1 FROM work_collection WHERE work_collection.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM work_set_items WHERE work_set_items.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM evaluations_local WHERE evaluations_local.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM evaluation_queue WHERE evaluation_queue.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM reading_state WHERE reading_state.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM blocked_works WHERE blocked_works.work_id = works.work_id)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM work_tags
                    JOIN favorite_tags
                      ON favorite_tags.tag_type = work_tags.tag_type
                     AND favorite_tags.tag_text = work_tags.tag_text
                    WHERE work_tags.work_id = works.work_id
                  )
                  {keep_clause}
                """,
                params,
            )
            after = int(conn.execute("SELECT COUNT(*) FROM works").fetchone()[0])
        return before - after

    def delete_unprotected_by_ids(self, work_ids: list[str]) -> int:
        ids = [str(work_id) for work_id in dict.fromkeys(work_ids) if str(work_id).strip()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            before = int(conn.execute("SELECT COUNT(*) FROM works WHERE work_id IN (" + placeholders + ")", ids).fetchone()[0])
            conn.execute(
                f"""
                DELETE FROM works
                WHERE work_id IN ({placeholders})
                  AND NOT EXISTS (SELECT 1 FROM work_collection WHERE work_collection.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM work_set_items WHERE work_set_items.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM evaluations_local WHERE evaluations_local.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM evaluation_queue WHERE evaluation_queue.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM reading_state WHERE reading_state.work_id = works.work_id)
                  AND NOT EXISTS (SELECT 1 FROM blocked_works WHERE blocked_works.work_id = works.work_id)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM work_tags
                    JOIN favorite_tags
                      ON favorite_tags.tag_type = work_tags.tag_type
                     AND favorite_tags.tag_text = work_tags.tag_text
                    WHERE work_tags.work_id = works.work_id
                  )
                """,
                ids,
            )
            after = int(conn.execute("SELECT COUNT(*) FROM works WHERE work_id IN (" + placeholders + ")", ids).fetchone()[0])
        return before - after

    @staticmethod
    def _params(work: Work) -> tuple[Any, ...]:
        return (
            work.work_id,
            work.ao3_url,
            work.title,
            work.author_name,
            work.author_url,
            work.author_key or normalize_author_key(work.author_name, work.author_url) or None,
            work.summary_html,
            work.summary_text,
            work.rating,
            work.language,
            work.words,
            work.chapters_current,
            work.chapters_total_text,
            work.kudos,
            work.bookmarks,
            work.hits,
            work.comments,
            work.published_at,
            work.last_ao3_updated_at,
            work.last_scraped_at or utc_now_iso(),
            work.scrape_version,
            work.raw_source_hash,
            int(work.is_deleted_or_missing),
        )

    @staticmethod
    def _row(row) -> Work:
        return Work(
            work_id=row["work_id"],
            ao3_url=row["ao3_url"],
            title=row["title"],
            author_name=row["author_name"],
            author_url=row["author_url"],
            author_key=row["author_key"],
            summary_html=row["summary_html"],
            summary_text=row["summary_text"],
            rating=row["rating"],
            language=row["language"],
            words=row["words"],
            chapters_current=row["chapters_current"],
            chapters_total_text=row["chapters_total_text"],
            kudos=row["kudos"],
            bookmarks=row["bookmarks"],
            hits=row["hits"],
            comments=row["comments"],
            published_at=row["published_at"],
            last_ao3_updated_at=row["last_ao3_updated_at"],
            last_scraped_at=row["last_scraped_at"],
            scrape_version=row["scrape_version"],
            raw_source_hash=row["raw_source_hash"],
            is_deleted_or_missing=_bool(row["is_deleted_or_missing"]),
        )


class SQLiteTagRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def replace_for_work(self, work_id: str, tags: list[WorkTag]) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM work_tags WHERE work_id = ?", (work_id,))
            conn.executemany(
                """
                INSERT OR IGNORE INTO work_tags(work_id, tag_type, tag_text, tag_url)
                VALUES (?, ?, ?, ?)
                """,
                [(work_id, tag.tag_type.value, tag.tag_text, tag.tag_url) for tag in tags],
            )

    def list_for_work(self, work_id: str) -> list[WorkTag]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM work_tags WHERE work_id = ? ORDER BY tag_type, tag_text",
                (work_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_for_works(self, work_ids: list[str]) -> dict[str, list[WorkTag]]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        grouped: dict[str, list[WorkTag]] = {work_id: [] for work_id in ids}
        if not ids:
            return grouped
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM work_tags
                WHERE work_id IN ({placeholders})
                ORDER BY work_id, tag_type, tag_text
                """,
                ids,
            ).fetchall()
        for row in rows:
            tag = self._row(row)
            grouped.setdefault(tag.work_id, []).append(tag)
        return grouped

    def suggest(self, query: str = "", tag_type: str | None = None, limit: int = 12) -> list[str]:
        pattern = f"%{query.strip()}%"
        params: list[Any] = []
        where = ""
        if query.strip():
            where = "WHERE tag_text LIKE ?"
            params.append(pattern)
        if tag_type:
            where = f"{where} {'AND' if where else 'WHERE'} tag_type = ?"
            params.append(tag_type)
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT tag_text, COUNT(*) AS uses
                FROM work_tags
                {where}
                GROUP BY tag_text
                ORDER BY uses DESC, tag_text
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [str(row["tag_text"]) for row in rows]

    def work_ids_for_tag(self, tag_type: str, tag_text: str) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT work_id FROM work_tags WHERE tag_type = ? AND tag_text = ?",
                (str(tag_type or "").strip(), str(tag_text or "").strip()),
            ).fetchall()
        return [str(row["work_id"]) for row in rows]

    @staticmethod
    def _row(row) -> WorkTag:
        return WorkTag(
            id=row["id"],
            work_id=row["work_id"],
            tag_type=TagType(row["tag_type"]) if row["tag_type"] in TagType._value2member_map_ else TagType.OTHER,
            tag_text=row["tag_text"],
            tag_url=row["tag_url"],
        )


class SQLiteFandomRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def save(self, profile: FandomProfile) -> None:
        now = utc_now_iso()
        created_at = profile.created_at or now
        updated_at = now
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO fandom_profiles(
                    fandom_key, tag, display_name, color, avatar_url, notes,
                    default_filter_json, created_at, updated_at, selected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fandom_key) DO UPDATE SET
                    tag = excluded.tag,
                    display_name = excluded.display_name,
                    color = excluded.color,
                    avatar_url = excluded.avatar_url,
                    notes = excluded.notes,
                    default_filter_json = excluded.default_filter_json,
                    updated_at = excluded.updated_at,
                    selected_at = excluded.selected_at
                """,
                (
                    profile.fandom_key,
                    profile.tag,
                    profile.display_name,
                    profile.color,
                    profile.avatar_url,
                    profile.notes,
                    _json_dumps(profile.default_filter),
                    created_at,
                    updated_at,
                    profile.selected_at,
                ),
            )

    def get(self, fandom_key: str) -> FandomProfile | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM fandom_profiles WHERE fandom_key = ?", (fandom_key,)).fetchone()
        return self._row(row) if row else None

    def get_by_tag(self, tag: str) -> FandomProfile | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM fandom_profiles WHERE lower(tag) = lower(?)", (tag,)).fetchone()
        return self._row(row) if row else None

    def list(self) -> list[FandomProfile]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM fandom_profiles
                ORDER BY selected_at IS NULL, selected_at DESC, display_name
                """
            ).fetchall()
        return [self._row(row) for row in rows]

    def select(self, fandom_key: str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE fandom_profiles SET selected_at = ? WHERE fandom_key = ?", (utc_now_iso(), fandom_key))

    @staticmethod
    def _row(row) -> FandomProfile:
        return FandomProfile(
            fandom_key=row["fandom_key"],
            tag=row["tag"],
            display_name=row["display_name"],
            color=row["color"],
            avatar_url=row["avatar_url"],
            notes=row["notes"],
            default_filter=dict(_json_loads(row["default_filter_json"], {})),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            selected_at=row["selected_at"],
        )


class SQLiteCharacterProfileRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def save(self, character: CharacterProfile) -> None:
        now = utc_now_iso()
        created_at = character.created_at or now
        with self.db.connect() as conn:
            id_row = conn.execute("SELECT id FROM character_profiles WHERE id = ?", (character.id,)).fetchone()
            name_row = conn.execute(
                "SELECT id FROM character_profiles WHERE fandom_key = ? AND name = ?",
                (character.fandom_key, character.name),
            ).fetchone()
            target_id = character.id
            if name_row is not None:
                target_id = name_row["id"]
                if id_row is not None and id_row["id"] != target_id:
                    conn.execute("DELETE FROM character_profiles WHERE id = ?", (character.id,))
            elif id_row is None:
                conn.execute(
                    """
                    INSERT INTO character_profiles(
                        id, fandom_key, name, color, avatar_url, tag_urls_json, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        character.id,
                        character.fandom_key,
                        character.name,
                        character.color,
                        character.avatar_url,
                        _json_dumps(character.tag_urls),
                        character.notes,
                        created_at,
                        now,
                    ),
                )
                return
            conn.execute(
                """
                UPDATE character_profiles
                SET fandom_key = ?,
                    name = ?,
                    color = ?,
                    avatar_url = ?,
                    tag_urls_json = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    character.fandom_key,
                    character.name,
                    character.color,
                    character.avatar_url,
                    _json_dumps(character.tag_urls),
                    character.notes,
                    now,
                    target_id,
                ),
            )

    def delete(self, character_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM character_profiles WHERE id = ?", (character_id,))

    def list_for_fandom(self, fandom_key: str) -> list[CharacterProfile]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM character_profiles WHERE fandom_key = ? ORDER BY name",
                (fandom_key,),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> CharacterProfile:
        return CharacterProfile(
            id=row["id"],
            fandom_key=row["fandom_key"],
            name=row["name"],
            color=row["color"],
            avatar_url=row["avatar_url"],
            tag_urls=list(_json_loads(row["tag_urls_json"], [])),
            notes=row["notes"] if "notes" in row.keys() else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SQLiteFandomTagCatalogRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def replace_for_fandom(self, fandom_key: str, items: list[FandomTagCatalogItem]) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM fandom_tag_catalog WHERE fandom_key = ?", (fandom_key,))
            conn.executemany(
                """
                INSERT OR IGNORE INTO fandom_tag_catalog(
                    fandom_key, tag_text, tag_url, category, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.fandom_key,
                        item.tag_text,
                        item.tag_url,
                        item.category,
                        item.source,
                        item.fetched_at or utc_now_iso(),
                    )
                    for item in items
                ],
            )

    def suggest(
        self,
        fandom_key: str,
        query: str = "",
        limit: int = 20,
        category: str | None = None,
    ) -> list[FandomTagCatalogItem]:
        clauses = ["fandom_key = ?"]
        params: list[Any] = [fandom_key]
        if query.strip():
            clauses.append("tag_text LIKE ?")
            params.append(f"%{query.strip()}%")
        if category:
            clauses.append("category = ?")
            params.append(category)
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM fandom_tag_catalog
                WHERE {' AND '.join(clauses)}
                ORDER BY
                    CASE category
                        WHEN 'character' THEN 0
                        WHEN 'relationship' THEN 1
                        WHEN 'same_meaning' THEN 2
                        ELSE 3
                    END,
                    tag_text
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def count(self, fandom_key: str) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM fandom_tag_catalog WHERE fandom_key = ?", (fandom_key,)).fetchone()[0])

    @staticmethod
    def _row(row) -> FandomTagCatalogItem:
        return FandomTagCatalogItem(
            id=row["id"],
            fandom_key=row["fandom_key"],
            tag_text=row["tag_text"],
            tag_url=row["tag_url"],
            category=row["category"],
            source=row["source"],
            fetched_at=row["fetched_at"],
        )


class SQLiteFandomStyleRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get(self, fandom_key: str) -> FandomStyleOverride | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM fandom_style_overrides WHERE fandom_key = ?",
                (fandom_key,),
            ).fetchone()
        if not row:
            return None
        return FandomStyleOverride(
            fandom_key=row["fandom_key"],
            enabled=_bool(row["enabled"]),
            settings=dict(_json_loads(row["settings_json"], {})),
            updated_at=row["updated_at"],
        )

    def save(self, override: FandomStyleOverride) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO fandom_style_overrides(fandom_key, enabled, settings_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fandom_key) DO UPDATE SET
                    enabled = excluded.enabled,
                    settings_json = excluded.settings_json,
                    updated_at = excluded.updated_at
                """,
                (
                    override.fandom_key,
                    int(override.enabled),
                    _json_dumps(override.settings),
                    override.updated_at or utc_now_iso(),
                ),
            )


class SQLiteWorkSetRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def save(self, work_set: WorkSet) -> None:
        now = utc_now_iso()
        created_at = work_set.created_at or now
        updated_at = now
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO work_sets(
                    id, fandom_key, name, filter_state_json, filter_signature,
                    created_at, updated_at, last_refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    fandom_key = excluded.fandom_key,
                    name = excluded.name,
                    filter_state_json = excluded.filter_state_json,
                    filter_signature = excluded.filter_signature,
                    updated_at = excluded.updated_at,
                    last_refreshed_at = excluded.last_refreshed_at
                """,
                (
                    work_set.id,
                    work_set.fandom_key,
                    work_set.name,
                    _json_dumps(work_set.filter_state),
                    work_set.filter_signature,
                    created_at,
                    updated_at,
                    work_set.last_refreshed_at,
                ),
            )

    def get(self, set_id: str) -> WorkSet | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM work_sets WHERE id = ?", (set_id,)).fetchone()
        return self._row(row) if row else None

    def get_by_name(self, fandom_key: str, name: str) -> WorkSet | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_sets WHERE fandom_key = ? AND lower(name) = lower(?)",
                (fandom_key, name),
            ).fetchone()
        return self._row(row) if row else None

    def list_for_fandom(self, fandom_key: str) -> list[WorkSet]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM work_sets WHERE fandom_key = ? ORDER BY updated_at DESC, name",
                (fandom_key,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def delete(self, set_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM work_sets WHERE id = ?", (set_id,))

    def add_items(self, set_id: str, work_ids: list[str]) -> None:
        clean_ids = [str(work_id) for work_id in dict.fromkeys(work_ids) if str(work_id).strip()]
        if not clean_ids:
            return
        now = utc_now_iso()
        with self.db.connect() as conn:
            for work_id in clean_ids:
                conn.execute(
                    """
                    INSERT INTO work_set_items(set_id, work_id, first_seen_at, last_seen_at, last_page_number)
                    VALUES (?, ?, ?, ?, NULL)
                    ON CONFLICT(set_id, work_id) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at
                    """,
                    (set_id, work_id, now, now),
                )
            conn.execute("UPDATE work_sets SET updated_at = ? WHERE id = ?", (now, set_id))

    def record_page(self, set_id: str, page_number: int, source_url: str, work_ids: list[str], captured_at: str) -> None:
        now = utc_now_iso()
        clean_ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        page_id = f"{set_id}:{page_number}"
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO work_set_pages(
                    id, set_id, page_number, source_url, work_ids_json, captured_at, last_refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(set_id, page_number) DO UPDATE SET
                    source_url = excluded.source_url,
                    work_ids_json = excluded.work_ids_json,
                    captured_at = excluded.captured_at,
                    last_refreshed_at = excluded.last_refreshed_at
                """,
                (page_id, set_id, page_number, source_url, _json_dumps(clean_ids), captured_at, now),
            )
            conn.execute("DELETE FROM work_set_items WHERE set_id = ?", (set_id,))
            rows = conn.execute("SELECT page_number, work_ids_json FROM work_set_pages WHERE set_id = ?", (set_id,)).fetchall()
            for row in rows:
                for work_id in list(_json_loads(row["work_ids_json"], [])):
                    conn.execute(
                        """
                        INSERT INTO work_set_items(set_id, work_id, first_seen_at, last_seen_at, last_page_number)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(set_id, work_id) DO UPDATE SET
                            last_seen_at = excluded.last_seen_at,
                            last_page_number = excluded.last_page_number
                        """,
                        (set_id, str(work_id), now, now, row["page_number"]),
                    )
            conn.execute(
                "UPDATE work_sets SET updated_at = ?, last_refreshed_at = ? WHERE id = ?",
                (now, now, set_id),
            )

    def list_pages(self, set_id: str) -> list[WorkSetPage]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM work_set_pages WHERE set_id = ? ORDER BY page_number",
                (set_id,),
            ).fetchall()
        return [self._page_row(row) for row in rows]

    def list_work_ids(self, set_id: str) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT work_id FROM work_set_items WHERE set_id = ? ORDER BY last_page_number, first_seen_at",
                (set_id,),
            ).fetchall()
        return [str(row["work_id"]) for row in rows]

    def is_in_any_set(self, work_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM work_set_items WHERE work_id = ? LIMIT 1", (work_id,)).fetchone()
        return bool(row)

    @staticmethod
    def _row(row) -> WorkSet:
        return WorkSet(
            id=row["id"],
            fandom_key=row["fandom_key"],
            name=row["name"],
            filter_state=dict(_json_loads(row["filter_state_json"], {})),
            filter_signature=row["filter_signature"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_refreshed_at=row["last_refreshed_at"],
        )

    @staticmethod
    def _page_row(row) -> WorkSetPage:
        return WorkSetPage(
            id=row["id"],
            set_id=row["set_id"],
            page_number=row["page_number"],
            source_url=row["source_url"],
            work_ids=list(_json_loads(row["work_ids_json"], [])),
            captured_at=row["captured_at"],
            last_refreshed_at=row["last_refreshed_at"],
        )


class SQLiteFavoriteTagRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def upsert(self, favorite: FavoriteTag) -> None:
        now = utc_now_iso()
        created_at = favorite.created_at or now
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO favorite_tags(
                    fandom_key, tag_type, tag_text, color, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fandom_key, tag_type, tag_text) DO UPDATE SET
                    color = excluded.color,
                    updated_at = excluded.updated_at
                """,
                (
                    favorite.fandom_key,
                    favorite.tag_type.value,
                    favorite.tag_text,
                    favorite.color,
                    created_at,
                    now,
                ),
            )

    def delete(self, fandom_key: str, tag_type: str, tag_text: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "DELETE FROM favorite_tags WHERE fandom_key = ? AND tag_type = ? AND tag_text = ?",
                (fandom_key, tag_type, tag_text),
            )

    def get(self, fandom_key: str, tag_type: str, tag_text: str) -> FavoriteTag | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM favorite_tags WHERE fandom_key = ? AND tag_type = ? AND tag_text = ?",
                (fandom_key, tag_type, tag_text),
            ).fetchone()
        return self._row(row) if row else None

    def list_for_fandom(self, fandom_key: str) -> list[FavoriteTag]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM favorite_tags WHERE fandom_key = ? ORDER BY tag_type, tag_text",
                (fandom_key,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def protected_work_ids(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT work_tags.work_id
                FROM work_tags
                JOIN favorite_tags
                  ON favorite_tags.tag_type = work_tags.tag_type
                 AND favorite_tags.tag_text = work_tags.tag_text
                """
            ).fetchall()
        return [str(row["work_id"]) for row in rows]

    @staticmethod
    def _row(row) -> FavoriteTag:
        return FavoriteTag(
            id=row["id"],
            fandom_key=row["fandom_key"],
            tag_type=TagType(row["tag_type"]) if row["tag_type"] in TagType._value2member_map_ else TagType.OTHER,
            tag_text=row["tag_text"],
            color=row["color"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SQLiteTagColorRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def upsert(self, color: TagColorOverride) -> None:
        now = utc_now_iso()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO tag_color_overrides(fandom_key, tag_type, tag_text, color, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(fandom_key, tag_type, tag_text) DO UPDATE SET
                    color = excluded.color,
                    updated_at = excluded.updated_at
                """,
                (color.fandom_key, color.tag_type.value, color.tag_text, color.color, color.updated_at or now),
            )

    def delete(self, fandom_key: str, tag_type: str, tag_text: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "DELETE FROM tag_color_overrides WHERE fandom_key = ? AND tag_type = ? AND tag_text = ?",
                (fandom_key, tag_type, tag_text),
            )

    def list_for_fandom(self, fandom_key: str) -> list[TagColorOverride]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tag_color_overrides WHERE fandom_key = ? ORDER BY tag_type, tag_text",
                (fandom_key,),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> TagColorOverride:
        return TagColorOverride(
            id=row["id"],
            fandom_key=row["fandom_key"],
            tag_type=TagType(row["tag_type"]) if row["tag_type"] in TagType._value2member_map_ else TagType.OTHER,
            tag_text=row["tag_text"],
            color=row["color"],
            updated_at=row["updated_at"],
        )


class SQLiteWorkCollectionRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def collect(self, work_id: str, fandom_key: str | None, note: str = "") -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO work_collection(work_id, fandom_key, collected_at, note)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    fandom_key = excluded.fandom_key,
                    note = excluded.note
                """,
                (work_id, fandom_key, utc_now_iso(), note or None),
            )

    def uncollect(self, work_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM work_collection WHERE work_id = ?", (work_id,))

    def is_collected(self, work_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM work_collection WHERE work_id = ?", (work_id,)).fetchone()
        return bool(row)

    def collected_ids(self, work_ids: list[str]) -> set[str]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        if not ids:
            return set()
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT work_id FROM work_collection WHERE work_id IN ({placeholders})",
                ids,
            ).fetchall()
        return {str(row["work_id"]) for row in rows}

    def list_collected(self, limit: int = 100, search: str = "") -> list[Work]:
        pattern = f"%{search.strip()}%"
        params: list[Any] = []
        where = ""
        if search.strip():
            where = "WHERE works.title LIKE ? OR works.author_name LIKE ? OR works.summary_text LIKE ?"
            params.extend([pattern, pattern, pattern])
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT works.*
                FROM work_collection
                JOIN works ON works.work_id = work_collection.work_id
                {where}
                ORDER BY work_collection.collected_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [SQLiteWorkRepository._row(row) for row in rows]

    def count(self) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM work_collection").fetchone()[0])


class SQLiteBlockedWorkRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def block(self, work_id: str, fandom_key: str | None = None, reason: str = "") -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO blocked_works(work_id, fandom_key, reason, blocked_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    fandom_key = excluded.fandom_key,
                    reason = excluded.reason,
                    blocked_at = excluded.blocked_at
                """,
                (work_id, fandom_key, reason or None, utc_now_iso()),
            )

    def unblock(self, work_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM blocked_works WHERE work_id = ?", (work_id,))

    def is_blocked(self, work_id: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM blocked_works WHERE work_id = ?", (work_id,)).fetchone()
        return bool(row)

    def blocked_ids(self, work_ids: list[str]) -> set[str]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        if not ids:
            return set()
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT work_id FROM blocked_works WHERE work_id IN ({placeholders})", ids).fetchall()
        return {str(row["work_id"]) for row in rows}

    def list(self, limit: int = 100) -> list[BlockedWork]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM blocked_works ORDER BY blocked_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            BlockedWork(
                work_id=row["work_id"],
                fandom_key=row["fandom_key"],
                reason=row["reason"],
                blocked_at=row["blocked_at"],
            )
            for row in rows
        ]


class SQLiteBlockedAuthorRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def block(
        self,
        author_key: str,
        display_name: str | None = None,
        author_url: str | None = None,
        fandom_key: str | None = None,
        reason: str = "",
    ) -> None:
        key = str(author_key or "").strip().casefold()
        if not key:
            return
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO blocked_authors(author_key, display_name, author_url, fandom_key, reason, blocked_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(author_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    author_url = excluded.author_url,
                    fandom_key = excluded.fandom_key,
                    reason = excluded.reason,
                    blocked_at = excluded.blocked_at
                """,
                (key, display_name, author_url, fandom_key, reason or None, utc_now_iso()),
            )

    def unblock(self, author_key: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM blocked_authors WHERE author_key = ?", (str(author_key or "").strip().casefold(),))

    def is_blocked(self, author_key: str) -> bool:
        key = str(author_key or "").strip().casefold()
        if not key:
            return False
        with self.db.connect() as conn:
            row = conn.execute("SELECT 1 FROM blocked_authors WHERE author_key = ?", (key,)).fetchone()
        return bool(row)

    def blocked_keys(self, author_keys: list[str]) -> set[str]:
        keys = [str(key).strip().casefold() for key in author_keys if str(key).strip()]
        if not keys:
            return set()
        placeholders = ",".join("?" for _ in keys)
        with self.db.connect() as conn:
            rows = conn.execute(f"SELECT author_key FROM blocked_authors WHERE author_key IN ({placeholders})", keys).fetchall()
        return {str(row["author_key"]) for row in rows}

    def list(self, limit: int = 100) -> list[BlockedAuthor]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM blocked_authors ORDER BY blocked_at DESC LIMIT ?", (limit,)).fetchall()
        return [
            BlockedAuthor(
                author_key=row["author_key"],
                display_name=row["display_name"],
                author_url=row["author_url"],
                fandom_key=row["fandom_key"],
                reason=row["reason"],
                blocked_at=row["blocked_at"],
            )
            for row in rows
        ]


class SQLiteBlockedTagRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def block(self, tag_type: str, tag_text: str, fandom_key: str | None = None, reason: str = "") -> None:
        clean_type = str(tag_type or "").strip()
        clean_text = str(tag_text or "").strip()
        if not clean_type or not clean_text:
            return
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO blocked_tags(tag_type, tag_text, fandom_key, reason, blocked_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tag_type, tag_text) DO UPDATE SET
                    fandom_key = excluded.fandom_key,
                    reason = excluded.reason,
                    blocked_at = excluded.blocked_at
                """,
                (clean_type, clean_text, fandom_key, reason or None, utc_now_iso()),
            )

    def unblock(self, tag_type: str, tag_text: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "DELETE FROM blocked_tags WHERE tag_type = ? AND tag_text = ?",
                (str(tag_type or "").strip(), str(tag_text or "").strip()),
            )

    def is_blocked(self, tag_type: str, tag_text: str) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM blocked_tags WHERE tag_type = ? AND tag_text = ?",
                (str(tag_type or "").strip(), str(tag_text or "").strip()),
            ).fetchone()
        return bool(row)

    def list(self, limit: int = 200, fandom_key: str | None = None) -> list[BlockedTag]:
        params: list[Any] = []
        where = ""
        if fandom_key:
            where = "WHERE fandom_key = ?"
            params.append(fandom_key)
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM blocked_tags {where} ORDER BY blocked_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def matching_work_ids(self, work_ids: list[str]) -> set[str]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        if not ids:
            return set()
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT work_tags.work_id
                FROM work_tags
                JOIN blocked_tags
                  ON blocked_tags.tag_type = work_tags.tag_type
                 AND blocked_tags.tag_text = work_tags.tag_text
                WHERE work_tags.work_id IN ({placeholders})
                """,
                ids,
            ).fetchall()
        return {str(row["work_id"]) for row in rows}

    def all_matching_work_ids(self) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT work_tags.work_id
                FROM work_tags
                JOIN blocked_tags
                  ON blocked_tags.tag_type = work_tags.tag_type
                 AND blocked_tags.tag_text = work_tags.tag_text
                """
            ).fetchall()
        return {str(row["work_id"]) for row in rows}

    @staticmethod
    def _row(row) -> BlockedTag:
        tag_type = row["tag_type"]
        return BlockedTag(
            id=row["id"],
            tag_type=TagType(tag_type) if tag_type in TagType._value2member_map_ else TagType.OTHER,
            tag_text=row["tag_text"],
            fandom_key=row["fandom_key"],
            reason=row["reason"],
            blocked_at=row["blocked_at"],
        )


class SQLiteBrowseSnapshotRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def add(self, snapshot: BrowseSnapshot) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO browse_snapshots(
                    id, source_url, context_type, context_key, captured_at, page_number, sort_mode, work_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.source_url,
                    snapshot.context_type,
                    snapshot.context_key,
                    snapshot.captured_at,
                    snapshot.page_number,
                    snapshot.sort_mode,
                    _json_dumps(snapshot.work_ids),
                ),
            )

    def list_recent(self, limit: int = 25) -> list[BrowseSnapshot]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM browse_snapshots ORDER BY captured_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def latest_for_url(self, source_url: str) -> BrowseSnapshot | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM browse_snapshots
                WHERE source_url = ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (source_url,),
            ).fetchone()
        return self._row(row) if row else None

    def delete_stale_missing_works(self) -> int:
        deleted = 0
        with self.db.connect() as conn:
            rows = conn.execute("SELECT id, work_ids_json FROM browse_snapshots").fetchall()
            for row in rows:
                work_ids = [str(work_id) for work_id in _json_loads(row["work_ids_json"], [])]
                if not work_ids:
                    continue
                placeholders = ",".join("?" for _ in work_ids)
                count = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM works WHERE work_id IN ({placeholders})",
                        work_ids,
                    ).fetchone()[0]
                )
                if count != len(set(work_ids)):
                    conn.execute("DELETE FROM browse_snapshots WHERE id = ?", (row["id"],))
                    deleted += 1
        return deleted

    @staticmethod
    def _row(row) -> BrowseSnapshot:
        return BrowseSnapshot(
            id=row["id"],
            source_url=row["source_url"],
            context_type=row["context_type"],
            context_key=row["context_key"],
            captured_at=row["captured_at"],
            page_number=row["page_number"],
            sort_mode=row["sort_mode"],
            work_ids=list(_json_loads(row["work_ids_json"], [])),
        )


class SQLiteEvaluationSchemaRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def save(self, schema: EvaluationSchema) -> None:
        if schema.is_active:
            with self.db.connect() as conn:
                conn.execute("UPDATE schemas_local SET is_active = 0")
        definition = asdict(schema)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO schemas_local(
                    schema_key, name, version, definition_json, is_active,
                    is_official_shared_compatible, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(schema_key) DO UPDATE SET
                    name = excluded.name,
                    version = excluded.version,
                    definition_json = excluded.definition_json,
                    is_active = excluded.is_active,
                    is_official_shared_compatible = excluded.is_official_shared_compatible
                """,
                (
                    schema.schema_key,
                    schema.name,
                    schema.version,
                    _json_dumps(definition),
                    int(schema.is_active),
                    int(schema.is_official_shared_compatible),
                    schema.created_at or utc_now_iso(),
                ),
            )

    def get(self, schema_key: str) -> EvaluationSchema | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM schemas_local WHERE schema_key = ?", (schema_key,)).fetchone()
        return self._row(row) if row else None

    def active(self) -> EvaluationSchema | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM schemas_local WHERE is_active = 1 LIMIT 1").fetchone()
        return self._row(row) if row else None

    def list(self) -> list[EvaluationSchema]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM schemas_local ORDER BY is_active DESC, name").fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> EvaluationSchema:
        definition = _json_loads(row["definition_json"], {})
        dimensions = [
            ScoreDimension(
                key=str(item.get("key", "")),
                label=str(item.get("label", item.get("key", ""))),
                description=str(item.get("description", "")),
                weight=float(item.get("weight", 1.0)),
                polarity=_score_polarity(item.get("polarity")),
            )
            for item in definition.get("dimensions", [])
        ]
        score_range = definition.get("score_range") or {}
        return EvaluationSchema(
            schema_key=row["schema_key"],
            name=row["name"],
            version=row["version"],
            label=str(definition.get("label", row["name"])),
            description=str(definition.get("description", "")),
            dimensions=dimensions,
            score_range=ScoreRange(
                minimum=int(score_range.get("minimum", 1)),
                maximum=int(score_range.get("maximum", 10)),
                step=int(score_range.get("step", 1)),
            ),
            required_fields=list(definition.get("required_fields", [])),
            justification_rules=dict(definition.get("justification_rules", {})),
            aggregation_rules=dict(definition.get("aggregation_rules", {})),
            shared_compatibility=dict(definition.get("shared_compatibility", {})),
            prompt_template=str(definition.get("prompt_template", "")),
            is_active=_bool(row["is_active"]),
            is_official_shared_compatible=_bool(row["is_official_shared_compatible"]),
            created_at=row["created_at"],
        )


class SQLiteEvaluationRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def save(self, evaluation: Evaluation) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluations_local(
                    id, work_id, local_user_id, schema_key, schema_version, scores_json,
                    subscores_json, notes_markdown, evidence_json, model_name, model_prompt_hash,
                    chapter_scope_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scores_json = excluded.scores_json,
                    subscores_json = excluded.subscores_json,
                    notes_markdown = excluded.notes_markdown,
                    evidence_json = excluded.evidence_json,
                    model_name = excluded.model_name,
                    model_prompt_hash = excluded.model_prompt_hash,
                    chapter_scope_json = excluded.chapter_scope_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    evaluation.id,
                    evaluation.work_id,
                    evaluation.local_user_id,
                    evaluation.schema_key,
                    evaluation.schema_version,
                    _json_dumps(evaluation.scores),
                    _json_dumps(evaluation.subscores) if evaluation.subscores is not None else None,
                    evaluation.notes_markdown,
                    _json_dumps(evaluation.evidence) if evaluation.evidence is not None else None,
                    evaluation.model_name,
                    evaluation.model_prompt_hash,
                    _json_dumps(evaluation.chapter_scope) if evaluation.chapter_scope is not None else None,
                    evaluation.status.value,
                    evaluation.created_at,
                    evaluation.updated_at,
                ),
            )

    def list_for_work(self, work_id: str, local_user_id: str | None = None) -> list[Evaluation]:
        with self.db.connect() as conn:
            if local_user_id:
                rows = conn.execute(
                    """
                    SELECT * FROM evaluations_local
                    WHERE work_id = ? AND local_user_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (work_id, local_user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evaluations_local WHERE work_id = ? ORDER BY updated_at DESC",
                    (work_id,),
                ).fetchall()
        return [self._row(row) for row in rows]

    def latest_for_work(self, work_id: str, local_user_id: str, schema_key: str | None = None) -> Evaluation | None:
        with self.db.connect() as conn:
            if schema_key:
                row = conn.execute(
                    """
                    SELECT * FROM evaluations_local
                    WHERE work_id = ? AND local_user_id = ? AND schema_key = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (work_id, local_user_id, schema_key),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM evaluations_local
                    WHERE work_id = ? AND local_user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (work_id, local_user_id),
                ).fetchone()
        return self._row(row) if row else None

    def latest_for_works(
        self,
        work_ids: list[str],
        local_user_id: str,
        schema_key: str | None = None,
    ) -> dict[str, Evaluation]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        params: list[Any] = [*ids, local_user_id]
        schema_clause = ""
        if schema_key:
            schema_clause = "AND schema_key = ?"
            params.append(schema_key)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM evaluations_local
                WHERE work_id IN ({placeholders})
                  AND local_user_id = ?
                  {schema_clause}
                ORDER BY work_id, updated_at DESC
                """,
                params,
            ).fetchall()
        latest: dict[str, Evaluation] = {}
        for row in rows:
            work_id = str(row["work_id"])
            if work_id not in latest:
                latest[work_id] = self._row(row)
        return latest

    def count(self) -> int:
        with self.db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM evaluations_local").fetchone()[0])

    def delete_for_works_schema(self, work_ids: list[str], local_user_id: str, schema_key: str) -> int:
        ids = [str(work_id) for work_id in dict.fromkeys(work_ids) if str(work_id).strip()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            before = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM evaluations_local
                    WHERE work_id IN ({placeholders})
                      AND local_user_id = ?
                      AND schema_key = ?
                    """,
                    [*ids, local_user_id, schema_key],
                ).fetchone()[0]
            )
            conn.execute(
                f"""
                DELETE FROM evaluations_local
                WHERE work_id IN ({placeholders})
                  AND local_user_id = ?
                  AND schema_key = ?
                """,
                [*ids, local_user_id, schema_key],
            )
        return before

    @staticmethod
    def _row(row) -> Evaluation:
        return Evaluation(
            id=row["id"],
            work_id=row["work_id"],
            local_user_id=row["local_user_id"],
            schema_key=row["schema_key"],
            schema_version=row["schema_version"],
            scores=dict(_json_loads(row["scores_json"], {})),
            subscores=_json_loads(row["subscores_json"], None),
            notes_markdown=row["notes_markdown"],
            evidence=_json_loads(row["evidence_json"], None),
            model_name=row["model_name"],
            model_prompt_hash=row["model_prompt_hash"],
            chapter_scope=_json_loads(row["chapter_scope_json"], None),
            status=EvaluationStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SQLiteEvaluationBatchRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def save(self, batch: EvaluationBatch) -> None:
        now = utc_now_iso()
        created_at = batch.created_at or now
        updated_at = batch.updated_at or now
        with self.db.connect() as conn:
            existing = conn.execute("SELECT id FROM evaluation_batches WHERE id = ?", (batch.id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE evaluation_batches
                    SET work_set_id = ?,
                        fandom_key = ?,
                        schema_key = ?,
                        updated_at = ?,
                        completed_at = ?,
                        status = ?
                    WHERE id = ?
                    """,
                    (
                        batch.work_set_id,
                        batch.fandom_key,
                        batch.schema_key,
                        updated_at,
                        batch.completed_at,
                        batch.status.value,
                        batch.id,
                    ),
                )
                return
            conn.execute(
                """
                INSERT INTO evaluation_batches(
                    id, work_set_id, fandom_key, schema_key, created_at, updated_at, completed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.id,
                    batch.work_set_id,
                    batch.fandom_key,
                    batch.schema_key,
                    created_at,
                    updated_at,
                    batch.completed_at,
                    batch.status.value,
                ),
            )

    def get(self, batch_id: str) -> EvaluationBatch | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM evaluation_batches WHERE id = ?", (batch_id,)).fetchone()
        return self._row(row) if row else None

    def get_by_work_set_schema(self, work_set_id: str, schema_key: str) -> EvaluationBatch | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_batches WHERE work_set_id = ? AND schema_key = ?",
                (work_set_id, schema_key),
            ).fetchone()
        return self._row(row) if row else None

    def list_for_fandom(self, fandom_key: str) -> list[EvaluationBatch]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM evaluation_batches
                WHERE fandom_key = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (fandom_key,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def list_for_work_set(self, work_set_id: str) -> list[EvaluationBatch]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluation_batches WHERE work_set_id = ? ORDER BY updated_at DESC",
                (work_set_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def schema_keys_for_work_set(self, work_set_id: str) -> set[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT schema_key FROM evaluation_batches WHERE work_set_id = ?",
                (work_set_id,),
            ).fetchall()
        return {str(row["schema_key"]) for row in rows}

    def count_for_work_set(self, work_set_id: str) -> int:
        with self.db.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM evaluation_batches WHERE work_set_id = ?",
                    (work_set_id,),
                ).fetchone()[0]
            )

    def delete(self, batch_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM evaluation_batches WHERE id = ?", (batch_id,))

    @staticmethod
    def _row(row) -> EvaluationBatch:
        return EvaluationBatch(
            id=row["id"],
            work_set_id=row["work_set_id"],
            fandom_key=row["fandom_key"],
            schema_key=row["schema_key"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            status=EvaluationBatchStatus(row["status"]),
        )


class SQLiteEvaluationQueueRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def add(self, item: EvaluationQueueItem) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_queue(
                    id, work_id, reason, priority, queue_status, requested_at,
                    finished_at, error_text, batch_id, schema_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.work_id,
                    item.reason,
                    item.priority,
                    item.queue_status.value,
                    item.requested_at,
                    item.finished_at,
                    item.error_text,
                    item.batch_id,
                    item.schema_key,
                ),
            )

    def list(self, status: QueueStatus | None = None, batch_id: str | None = None) -> list[EvaluationQueueItem]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("queue_status = ?")
            params.append(status.value)
        if batch_id:
            where.append("batch_id = ?")
            params.append(batch_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM evaluation_queue {where_sql} ORDER BY priority, requested_at",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, item_id: str) -> EvaluationQueueItem | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM evaluation_queue WHERE id = ?", (item_id,)).fetchone()
        return self._row(row) if row else None

    def update_status(self, item_id: str, status: QueueStatus, error_text: str | None = None) -> None:
        finished_at = utc_now_iso() if status in {QueueStatus.DONE, QueueStatus.FAILED, QueueStatus.SKIPPED} else None
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE evaluation_queue
                SET queue_status = ?, finished_at = ?, error_text = ?
                WHERE id = ?
                """,
                (status.value, finished_at, error_text, item_id),
            )

    def delete(self, item_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM evaluation_queue WHERE id = ?", (item_id,))

    def delete_for_batch(self, batch_id: str) -> int:
        with self.db.connect() as conn:
            before = int(
                conn.execute(
                    "SELECT COUNT(*) FROM evaluation_queue WHERE batch_id = ?",
                    (batch_id,),
                ).fetchone()[0]
            )
            conn.execute("DELETE FROM evaluation_queue WHERE batch_id = ?", (batch_id,))
        return before

    @staticmethod
    def _row(row) -> EvaluationQueueItem:
        return EvaluationQueueItem(
            id=row["id"],
            work_id=row["work_id"],
            reason=row["reason"],
            priority=row["priority"],
            queue_status=QueueStatus(row["queue_status"]),
            requested_at=row["requested_at"],
            finished_at=row["finished_at"],
            error_text=row["error_text"],
            batch_id=row["batch_id"] if "batch_id" in row.keys() else None,
            schema_key=row["schema_key"] if "schema_key" in row.keys() else None,
        )


class SQLiteReadingStateRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get(self, work_id: str, local_user_id: str) -> ReadingState | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reading_state WHERE work_id = ? AND local_user_id = ?",
                (work_id, local_user_id),
            ).fetchone()
        return self._row(row) if row else None

    def upsert(self, state: ReadingState) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO reading_state(
                    work_id, local_user_id, state, last_position_ref, last_opened_at,
                    personal_priority, personal_labels_json, private_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id, local_user_id) DO UPDATE SET
                    state = excluded.state,
                    last_position_ref = excluded.last_position_ref,
                    last_opened_at = excluded.last_opened_at,
                    personal_priority = excluded.personal_priority,
                    personal_labels_json = excluded.personal_labels_json,
                    private_notes = excluded.private_notes
                """,
                (
                    state.work_id,
                    state.local_user_id,
                    state.state.value,
                    state.last_position_ref,
                    state.last_opened_at,
                    state.personal_priority,
                    _json_dumps(state.personal_labels),
                    state.private_notes,
                ),
            )

    def list_for_user(self, local_user_id: str) -> list[ReadingState]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM reading_state WHERE local_user_id = ?", (local_user_id,)).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> ReadingState:
        return ReadingState(
            work_id=row["work_id"],
            local_user_id=row["local_user_id"],
            state=ReadingStatus(row["state"]),
            last_position_ref=row["last_position_ref"],
            last_opened_at=row["last_opened_at"],
            personal_priority=row["personal_priority"],
            personal_labels=list(_json_loads(row["personal_labels_json"], [])),
            private_notes=row["private_notes"],
        )


class SQLiteReaderAssetRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get_asset(self, work_id: str) -> ReaderAsset | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM reader_assets WHERE work_id = ?", (work_id,)).fetchone()
        return self._asset_row(row) if row else None

    def list_chapters(self, work_id: str) -> list[ReaderChapter]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM reader_chapters WHERE work_id = ? ORDER BY chapter_index",
                (work_id,),
            ).fetchall()
        return [self._chapter_row(row) for row in rows]

    def replace_document(self, asset: ReaderAsset, chapters: list[ReaderChapter]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO reader_assets(
                    work_id, source_format, source_url, download_url, content_hash,
                    downloaded_chapter_count, known_ao3_chapter_count, downloaded_at, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    source_format = excluded.source_format,
                    source_url = excluded.source_url,
                    download_url = excluded.download_url,
                    content_hash = excluded.content_hash,
                    downloaded_chapter_count = excluded.downloaded_chapter_count,
                    known_ao3_chapter_count = excluded.known_ao3_chapter_count,
                    downloaded_at = excluded.downloaded_at,
                    last_checked_at = excluded.last_checked_at
                """,
                (
                    asset.work_id,
                    asset.source_format,
                    asset.source_url,
                    asset.download_url,
                    asset.content_hash,
                    asset.downloaded_chapter_count,
                    asset.known_ao3_chapter_count,
                    asset.downloaded_at,
                    asset.last_checked_at,
                ),
            )
            conn.execute("DELETE FROM reader_chapters WHERE work_id = ?", (asset.work_id,))
            conn.executemany(
                """
                INSERT INTO reader_chapters(
                    work_id, chapter_index, title, ao3_url, anchor, html, text_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chapter.work_id,
                        chapter.chapter_index,
                        chapter.title,
                        chapter.ao3_url,
                        chapter.anchor,
                        chapter.html,
                        chapter.text_hash,
                    )
                    for chapter in chapters
                ],
            )

    def delete_for_work(self, work_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM reader_assets WHERE work_id = ?", (work_id,))

    @staticmethod
    def _asset_row(row) -> ReaderAsset:
        return ReaderAsset(
            work_id=row["work_id"],
            source_format=row["source_format"],
            source_url=row["source_url"],
            download_url=row["download_url"],
            content_hash=row["content_hash"],
            downloaded_chapter_count=int(row["downloaded_chapter_count"]),
            known_ao3_chapter_count=row["known_ao3_chapter_count"],
            downloaded_at=row["downloaded_at"],
            last_checked_at=row["last_checked_at"],
        )

    @staticmethod
    def _chapter_row(row) -> ReaderChapter:
        return ReaderChapter(
            work_id=row["work_id"],
            chapter_index=int(row["chapter_index"]),
            title=row["title"],
            ao3_url=row["ao3_url"],
            anchor=row["anchor"],
            html=row["html"],
            text_hash=row["text_hash"],
        )


class SQLiteRarityRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get(self, work_id: str, local_user_id: str) -> WorkRarity | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_rarity_local WHERE work_id = ? AND local_user_id = ?",
                (work_id, local_user_id),
            ).fetchone()
        return self._row(row) if row else None

    def list_for_works(self, work_ids: list[str], local_user_id: str) -> dict[str, WorkRarity]:
        ids = [str(work_id) for work_id in work_ids if str(work_id).strip()]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM work_rarity_local
                WHERE work_id IN ({placeholders})
                  AND local_user_id = ?
                """,
                [*ids, local_user_id],
            ).fetchall()
        return {str(row["work_id"]): self._row(row) for row in rows}

    def upsert(self, rarity: WorkRarity) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO work_rarity_local(
                    work_id, local_user_id, manual_rarity, manual_updated_at,
                    computed_quality_score, computed_rarity, computed_schema_key,
                    computed_schema_version, computed_evaluation_id, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id, local_user_id) DO UPDATE SET
                    manual_rarity = excluded.manual_rarity,
                    manual_updated_at = excluded.manual_updated_at,
                    computed_quality_score = excluded.computed_quality_score,
                    computed_rarity = excluded.computed_rarity,
                    computed_schema_key = excluded.computed_schema_key,
                    computed_schema_version = excluded.computed_schema_version,
                    computed_evaluation_id = excluded.computed_evaluation_id,
                    computed_at = excluded.computed_at
                """,
                (
                    rarity.work_id,
                    rarity.local_user_id,
                    rarity.manual_rarity.value if rarity.manual_rarity else None,
                    rarity.manual_updated_at,
                    rarity.computed_quality_score,
                    rarity.computed_rarity.value if rarity.computed_rarity else None,
                    rarity.computed_schema_key,
                    rarity.computed_schema_version,
                    rarity.computed_evaluation_id,
                    rarity.computed_at,
                ),
            )

    def set_manual(self, work_id: str, local_user_id: str, rarity: str | None, updated_at: str | None) -> None:
        existing = self.get(work_id, local_user_id) or WorkRarity(work_id=work_id, local_user_id=local_user_id)
        existing.manual_rarity = _rarity(rarity)
        existing.manual_updated_at = updated_at if existing.manual_rarity else None
        self.upsert(existing)

    @staticmethod
    def _row(row) -> WorkRarity:
        return WorkRarity(
            work_id=row["work_id"],
            local_user_id=row["local_user_id"],
            manual_rarity=_rarity(row["manual_rarity"]),
            manual_updated_at=row["manual_updated_at"],
            computed_quality_score=row["computed_quality_score"],
            computed_rarity=_rarity(row["computed_rarity"]),
            computed_schema_key=row["computed_schema_key"],
            computed_schema_version=row["computed_schema_version"],
            computed_evaluation_id=row["computed_evaluation_id"],
            computed_at=row["computed_at"],
        )


class SQLiteSyncRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get(self, entity_type: str, entity_id: str) -> SyncState | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM remote_sync_state WHERE entity_type = ? AND entity_id = ?",
                (entity_type, entity_id),
            ).fetchone()
        return self._row(row) if row else None

    def upsert(self, state: SyncState) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO remote_sync_state(
                    entity_type, entity_id, remote_id, last_push_at, last_pull_at, sync_status, sync_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    remote_id = excluded.remote_id,
                    last_push_at = excluded.last_push_at,
                    last_pull_at = excluded.last_pull_at,
                    sync_status = excluded.sync_status,
                    sync_hash = excluded.sync_hash
                """,
                (
                    state.entity_type,
                    state.entity_id,
                    state.remote_id,
                    state.last_push_at,
                    state.last_pull_at,
                    state.sync_status,
                    state.sync_hash,
                ),
            )

    @staticmethod
    def _row(row) -> SyncState:
        return SyncState(
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            remote_id=row["remote_id"],
            last_push_at=row["last_push_at"],
            last_pull_at=row["last_pull_at"],
            sync_status=row["sync_status"],
            sync_hash=row["sync_hash"],
        )


class SQLiteSharedOverlayRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self.db = db

    def get_for_work(self, work_id: str) -> SharedOverlay | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM shared_overlay_cache WHERE work_id = ? ORDER BY last_fetched_at DESC LIMIT 1",
                (work_id,),
            ).fetchone()
        return self._row(row) if row else None

    def upsert(self, overlay: SharedOverlay) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO shared_overlay_cache(
                    id, work_id, remote_schema_version, aggregate_scores_json, evaluation_count,
                    divergence_flags_json, last_fetched_at, source_etag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    aggregate_scores_json = excluded.aggregate_scores_json,
                    evaluation_count = excluded.evaluation_count,
                    divergence_flags_json = excluded.divergence_flags_json,
                    last_fetched_at = excluded.last_fetched_at,
                    source_etag = excluded.source_etag
                """,
                (
                    overlay.id,
                    overlay.work_id,
                    overlay.remote_schema_version,
                    _json_dumps(overlay.aggregate_scores) if overlay.aggregate_scores is not None else None,
                    overlay.evaluation_count,
                    _json_dumps(overlay.divergence_flags) if overlay.divergence_flags is not None else None,
                    overlay.last_fetched_at,
                    overlay.source_etag,
                ),
            )

    def clear_for_work(self, work_id: str) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM shared_overlay_cache WHERE work_id = ?", (work_id,))

    def list_recent(self, limit: int = 50) -> list[SharedOverlay]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM shared_overlay_cache ORDER BY last_fetched_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> SharedOverlay:
        return SharedOverlay(
            id=row["id"],
            work_id=row["work_id"],
            remote_schema_version=row["remote_schema_version"],
            aggregate_scores=_json_loads(row["aggregate_scores_json"], None),
            evaluation_count=row["evaluation_count"],
            divergence_flags=_json_loads(row["divergence_flags_json"], None),
            last_fetched_at=row["last_fetched_at"],
            source_etag=row["source_etag"],
        )
