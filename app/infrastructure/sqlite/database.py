from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.infrastructure.config.paths import DATABASE_PATH, ensure_config_dirs


class SQLiteDatabase:
    def __init__(self, path: Path | None = None) -> None:
        ensure_config_dirs()
        self.path = path or DATABASE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version < 1:
                self._migrate_v1(conn)
                conn.execute("PRAGMA user_version = 1")
                version = 1
            if version < 2:
                self._migrate_v2(conn)
                conn.execute("PRAGMA user_version = 2")
                version = 2
            if version < 3:
                self._migrate_v3(conn)
                conn.execute("PRAGMA user_version = 3")
                version = 3
            if version < 4:
                self._migrate_v4(conn)
                conn.execute("PRAGMA user_version = 4")
                version = 4
            if version < 5:
                self._migrate_v5(conn)
                conn.execute("PRAGMA user_version = 5")
                version = 5
            if version < 6:
                self._migrate_v6(conn)
                conn.execute("PRAGMA user_version = 6")
                version = 6
            if version < 7:
                self._migrate_v7(conn)
                conn.execute("PRAGMA user_version = 7")
                version = 7
            if version < 8:
                self._migrate_v8(conn)
                conn.execute("PRAGMA user_version = 8")
                version = 8
            if version < 9:
                self._migrate_v9(conn)
                conn.execute("PRAGMA user_version = 9")
                version = 9
            if version < 10:
                self._migrate_v10(conn)
                conn.execute("PRAGMA user_version = 10")
                version = 10
            if version < 11:
                self._migrate_v11(conn)
                conn.execute("PRAGMA user_version = 11")
                version = 11
            if version < 12:
                self._migrate_v12(conn)
                conn.execute("PRAGMA user_version = 12")

    @staticmethod
    def _migrate_v1(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS local_user (
                id TEXT PRIMARY KEY,
                display_name TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                client_install_fingerprint TEXT,
                is_local_owner INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS works (
                work_id TEXT PRIMARY KEY,
                ao3_url TEXT NOT NULL,
                title TEXT,
                author_name TEXT,
                author_url TEXT,
                summary_html TEXT,
                summary_text TEXT,
                rating TEXT,
                language TEXT,
                words INTEGER,
                chapters_current INTEGER,
                chapters_total_text TEXT,
                kudos INTEGER,
                bookmarks INTEGER,
                hits INTEGER,
                comments INTEGER,
                last_ao3_updated_at TEXT,
                last_scraped_at TEXT NOT NULL,
                scrape_version TEXT NOT NULL,
                raw_source_hash TEXT,
                is_deleted_or_missing INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS work_tags (
                id INTEGER PRIMARY KEY,
                work_id TEXT NOT NULL,
                tag_type TEXT NOT NULL,
                tag_text TEXT NOT NULL,
                tag_url TEXT,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE,
                UNIQUE(work_id, tag_type, tag_text)
            );

            CREATE TABLE IF NOT EXISTS browse_snapshots (
                id TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                context_type TEXT NOT NULL,
                context_key TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                page_number INTEGER,
                sort_mode TEXT,
                work_ids_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evaluations_local (
                id TEXT PRIMARY KEY,
                work_id TEXT NOT NULL,
                local_user_id TEXT NOT NULL,
                schema_key TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                scores_json TEXT NOT NULL,
                subscores_json TEXT,
                notes_markdown TEXT,
                evidence_json TEXT,
                model_name TEXT,
                model_prompt_hash TEXT,
                chapter_scope_json TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE,
                FOREIGN KEY(local_user_id) REFERENCES local_user(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS evaluation_queue (
                id TEXT PRIMARY KEY,
                work_id TEXT NOT NULL,
                reason TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                queue_status TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                finished_at TEXT,
                error_text TEXT,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reading_state (
                work_id TEXT NOT NULL,
                local_user_id TEXT NOT NULL,
                state TEXT NOT NULL,
                last_position_ref TEXT,
                last_opened_at TEXT,
                personal_priority INTEGER,
                personal_labels_json TEXT,
                private_notes TEXT,
                PRIMARY KEY(work_id, local_user_id),
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE,
                FOREIGN KEY(local_user_id) REFERENCES local_user(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS schemas_local (
                schema_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL,
                definition_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                is_official_shared_compatible INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS remote_sync_state (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                remote_id TEXT,
                last_push_at TEXT,
                last_pull_at TEXT,
                sync_status TEXT NOT NULL,
                sync_hash TEXT,
                PRIMARY KEY (entity_type, entity_id)
            );

            CREATE TABLE IF NOT EXISTS shared_overlay_cache (
                id TEXT PRIMARY KEY,
                work_id TEXT NOT NULL,
                remote_schema_version TEXT NOT NULL,
                aggregate_scores_json TEXT,
                evaluation_count INTEGER,
                divergence_flags_json TEXT,
                last_fetched_at TEXT NOT NULL,
                source_etag TEXT,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_work_tags_work_id ON work_tags(work_id);
            CREATE INDEX IF NOT EXISTS idx_evaluations_work_user ON evaluations_local(work_id, local_user_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_queue_status_priority ON evaluation_queue(queue_status, priority, requested_at);
            CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON browse_snapshots(captured_at);
            CREATE INDEX IF NOT EXISTS idx_overlays_work ON shared_overlay_cache(work_id);
            """
        )

    @staticmethod
    def _migrate_v2(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fandom_profiles (
                fandom_key TEXT PRIMARY KEY,
                tag TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#58a6ff',
                avatar_url TEXT,
                notes TEXT,
                default_filter_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                selected_at TEXT
            );

            CREATE TABLE IF NOT EXISTS character_profiles (
                id TEXT PRIMARY KEY,
                fandom_key TEXT NOT NULL,
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#58a6ff',
                avatar_url TEXT,
                tag_urls_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE,
                UNIQUE(fandom_key, name)
            );

            CREATE TABLE IF NOT EXISTS work_collection (
                work_id TEXT PRIMARY KEY,
                fandom_key TEXT,
                collected_at TEXT NOT NULL,
                note TEXT,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS blocked_works (
                work_id TEXT PRIMARY KEY,
                fandom_key TEXT,
                reason TEXT,
                blocked_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_fandom_profiles_selected ON fandom_profiles(selected_at);
            CREATE INDEX IF NOT EXISTS idx_character_profiles_fandom ON character_profiles(fandom_key, name);
            CREATE INDEX IF NOT EXISTS idx_work_collection_fandom ON work_collection(fandom_key, collected_at);
            CREATE INDEX IF NOT EXISTS idx_blocked_works_fandom ON blocked_works(fandom_key, blocked_at);
            """
        )

    @staticmethod
    def _migrate_v3(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fandom_tag_catalog (
                id INTEGER PRIMARY KEY,
                fandom_key TEXT NOT NULL,
                tag_text TEXT NOT NULL,
                tag_url TEXT,
                category TEXT NOT NULL,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE,
                UNIQUE(fandom_key, tag_text, category)
            );

            CREATE INDEX IF NOT EXISTS idx_fandom_tag_catalog_lookup
                ON fandom_tag_catalog(fandom_key, category, tag_text);
            """
        )

    @staticmethod
    def _migrate_v4(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_sets (
                id TEXT PRIMARY KEY,
                fandom_key TEXT NOT NULL,
                name TEXT NOT NULL,
                filter_state_json TEXT NOT NULL,
                filter_signature TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_refreshed_at TEXT,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE,
                UNIQUE(fandom_key, name)
            );

            CREATE TABLE IF NOT EXISTS work_set_pages (
                id TEXT PRIMARY KEY,
                set_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                source_url TEXT NOT NULL,
                work_ids_json TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                last_refreshed_at TEXT,
                FOREIGN KEY(set_id) REFERENCES work_sets(id) ON DELETE CASCADE,
                UNIQUE(set_id, page_number)
            );

            CREATE TABLE IF NOT EXISTS work_set_items (
                set_id TEXT NOT NULL,
                work_id TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_page_number INTEGER,
                PRIMARY KEY(set_id, work_id),
                FOREIGN KEY(set_id) REFERENCES work_sets(id) ON DELETE CASCADE,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorite_tags (
                id INTEGER PRIMARY KEY,
                fandom_key TEXT NOT NULL,
                tag_type TEXT NOT NULL,
                tag_text TEXT NOT NULL,
                color TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE,
                UNIQUE(fandom_key, tag_type, tag_text)
            );

            CREATE INDEX IF NOT EXISTS idx_work_sets_fandom_updated
                ON work_sets(fandom_key, updated_at);
            CREATE INDEX IF NOT EXISTS idx_work_set_pages_set_page
                ON work_set_pages(set_id, page_number);
            CREATE INDEX IF NOT EXISTS idx_work_set_items_work
                ON work_set_items(work_id);
            CREATE INDEX IF NOT EXISTS idx_favorite_tags_fandom
                ON favorite_tags(fandom_key, tag_type, tag_text);
            """
        )

    @staticmethod
    def _migrate_v5(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(character_profiles)").fetchall()
        }
        if "notes" not in columns:
            conn.execute("ALTER TABLE character_profiles ADD COLUMN notes TEXT")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reader_assets (
                work_id TEXT PRIMARY KEY,
                source_format TEXT NOT NULL,
                source_url TEXT NOT NULL,
                download_url TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                downloaded_chapter_count INTEGER NOT NULL,
                known_ao3_chapter_count INTEGER,
                downloaded_at TEXT NOT NULL,
                last_checked_at TEXT,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS reader_chapters (
                work_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                ao3_url TEXT,
                anchor TEXT,
                html TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                PRIMARY KEY(work_id, chapter_index),
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_reader_chapters_work
                ON reader_chapters(work_id, chapter_index);
            """
        )

    @staticmethod
    def _migrate_v6(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS fandom_style_overrides (
                fandom_key TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                settings_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS work_rarity_local (
                work_id TEXT NOT NULL,
                local_user_id TEXT NOT NULL,
                manual_rarity TEXT,
                manual_updated_at TEXT,
                computed_quality_score REAL,
                computed_rarity TEXT,
                computed_schema_key TEXT,
                computed_schema_version TEXT,
                computed_evaluation_id TEXT,
                computed_at TEXT,
                PRIMARY KEY(work_id, local_user_id),
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE,
                FOREIGN KEY(local_user_id) REFERENCES local_user(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_work_rarity_effective
                ON work_rarity_local(local_user_id, manual_rarity, computed_rarity);
            """
        )

    @staticmethod
    def _migrate_v7(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(works)").fetchall()
        }
        if "author_key" not in columns:
            conn.execute("ALTER TABLE works ADD COLUMN author_key TEXT")
        rows = conn.execute(
            """
            SELECT work_id, author_name, author_url
            FROM works
            WHERE author_key IS NULL OR author_key = ''
            """
        ).fetchall()
        conn.executemany(
            "UPDATE works SET author_key = ? WHERE work_id = ?",
            [
                (SQLiteDatabase._author_key(row["author_name"], row["author_url"]) or None, row["work_id"])
                for row in rows
            ],
        )
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_works_author_key
                ON works(author_key);

            CREATE TABLE IF NOT EXISTS blocked_authors (
                author_key TEXT PRIMARY KEY,
                display_name TEXT,
                author_url TEXT,
                fandom_key TEXT,
                reason TEXT,
                blocked_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_blocked_authors_fandom
                ON blocked_authors(fandom_key, blocked_at);
            """
        )

    @staticmethod
    def _migrate_v8(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(works)").fetchall()
        }
        if "published_at" not in columns:
            conn.execute("ALTER TABLE works ADD COLUMN published_at TEXT")

    @staticmethod
    def _migrate_v9(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_publication_dates (
                work_id TEXT PRIMARY KEY,
                published_at TEXT NOT NULL,
                source_url TEXT,
                cached_at TEXT NOT NULL
            );

            INSERT OR IGNORE INTO work_publication_dates(work_id, published_at, source_url, cached_at)
            SELECT work_id, published_at, ao3_url, COALESCE(last_scraped_at, datetime('now'))
            FROM works
            WHERE published_at IS NOT NULL AND TRIM(published_at) != '';
            """
        )

    @staticmethod
    def _migrate_v10(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blocked_tags (
                id INTEGER PRIMARY KEY,
                tag_type TEXT NOT NULL,
                tag_text TEXT NOT NULL,
                fandom_key TEXT,
                reason TEXT,
                blocked_at TEXT NOT NULL,
                UNIQUE(tag_type, tag_text),
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_blocked_tags_fandom
                ON blocked_tags(fandom_key, blocked_at);

            CREATE INDEX IF NOT EXISTS idx_blocked_tags_lookup
                ON blocked_tags(tag_type, tag_text);
            """
        )

    @staticmethod
    def _migrate_v11(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tag_color_overrides (
                id INTEGER PRIMARY KEY,
                fandom_key TEXT NOT NULL,
                tag_type TEXT NOT NULL,
                tag_text TEXT NOT NULL,
                color TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE,
                UNIQUE(fandom_key, tag_type, tag_text)
            );

            CREATE INDEX IF NOT EXISTS idx_tag_color_overrides_fandom
                ON tag_color_overrides(fandom_key, tag_type, tag_text);
            """
        )

    @staticmethod
    def _migrate_v12(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evaluation_batches (
                id TEXT PRIMARY KEY,
                work_set_id TEXT NOT NULL,
                fandom_key TEXT NOT NULL,
                schema_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                FOREIGN KEY(work_set_id) REFERENCES work_sets(id) ON DELETE CASCADE,
                FOREIGN KEY(fandom_key) REFERENCES fandom_profiles(fandom_key) ON DELETE CASCADE,
                UNIQUE(work_set_id, schema_key)
            );

            CREATE INDEX IF NOT EXISTS idx_evaluation_batches_fandom
                ON evaluation_batches(fandom_key, updated_at);
            CREATE INDEX IF NOT EXISTS idx_evaluation_batches_work_set
                ON evaluation_batches(work_set_id, schema_key);
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(evaluation_queue)").fetchall()
        }
        if "batch_id" not in columns:
            conn.execute("ALTER TABLE evaluation_queue ADD COLUMN batch_id TEXT")
        if "schema_key" not in columns:
            conn.execute("ALTER TABLE evaluation_queue ADD COLUMN schema_key TEXT")
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_queue_batch_status
                ON evaluation_queue(batch_id, queue_status, priority, requested_at);
            CREATE INDEX IF NOT EXISTS idx_queue_schema_work
                ON evaluation_queue(schema_key, work_id, queue_status);
            """
        )

        schema_row = conn.execute("SELECT schema_key FROM schemas_local WHERE is_active = 1 LIMIT 1").fetchone()
        schema_key = str(schema_row["schema_key"] if schema_row else "local_default_v1")
        now = SQLiteDatabase._utc_now_iso()

        work_sets = conn.execute("SELECT id, fandom_key FROM work_sets").fetchall()
        for row in work_sets:
            batch_id = SQLiteDatabase._stable_batch_id(str(row["id"]), schema_key)
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_batches(
                    id, work_set_id, fandom_key, schema_key, created_at, updated_at, completed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'queued')
                """,
                (batch_id, row["id"], row["fandom_key"], schema_key, now, now),
            )

        legacy_rows = conn.execute(
            "SELECT id, work_id FROM evaluation_queue WHERE batch_id IS NULL OR batch_id = ''"
        ).fetchall()
        if legacy_rows:
            fandom_row = conn.execute(
                """
                SELECT fandom_key
                FROM fandom_profiles
                ORDER BY selected_at IS NULL, selected_at DESC, created_at DESC
                LIMIT 1
                """
            ).fetchone()
            if fandom_row:
                fandom_key = str(fandom_row["fandom_key"])
                set_row = conn.execute(
                    "SELECT id FROM work_sets WHERE fandom_key = ? AND lower(name) = lower(?) LIMIT 1",
                    (fandom_key, "Manual Queue"),
                ).fetchone()
                if set_row:
                    set_id = str(set_row["id"])
                else:
                    set_id = str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO work_sets(
                            id, fandom_key, name, filter_state_json, filter_signature,
                            created_at, updated_at, last_refreshed_at
                        ) VALUES (?, ?, 'Manual Queue', ?, 'manual_queue', ?, ?, NULL)
                        """,
                        (set_id, fandom_key, '{"queue":"manual"}', now, now),
                    )
                for row in legacy_rows:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO work_set_items(
                            set_id, work_id, first_seen_at, last_seen_at, last_page_number
                        ) VALUES (?, ?, ?, ?, NULL)
                        """,
                        (set_id, row["work_id"], now, now),
                    )
                batch_id = SQLiteDatabase._stable_batch_id(set_id, schema_key)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO evaluation_batches(
                        id, work_set_id, fandom_key, schema_key, created_at, updated_at, completed_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'queued')
                    """,
                    (batch_id, set_id, fandom_key, schema_key, now, now),
                )
                conn.execute(
                    """
                    UPDATE evaluation_queue
                    SET batch_id = ?, schema_key = COALESCE(NULLIF(schema_key, ''), ?)
                    WHERE batch_id IS NULL OR batch_id = ''
                    """,
                    (batch_id, schema_key),
                )
        conn.execute(
            "UPDATE evaluation_queue SET schema_key = ? WHERE schema_key IS NULL OR schema_key = ''",
            (schema_key,),
        )

    @staticmethod
    def _stable_batch_id(work_set_id: str, schema_key: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ao3-studio:evaluation-batch:{work_set_id}:{schema_key}"))

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _author_key(author_name: str | None, author_url: str | None) -> str:
        raw_url = str(author_url or "").strip()
        if raw_url:
            path = urlparse(raw_url).path.strip("/")
            if path:
                return path.casefold()
            return raw_url.casefold()
        return re.sub(r"\s+", " ", str(author_name or "").strip()).casefold()
