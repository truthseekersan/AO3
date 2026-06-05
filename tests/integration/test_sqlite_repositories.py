from __future__ import annotations

import json
import sqlite3
from zipfile import ZipFile
import io
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.application.composition import build_container
from app.application.services import (
    AO3BrowseService,
    QueueEvaluationConfig,
    STYLE_OVERRIDE_SECTIONS_KEY,
    fandom_key,
    filter_signature,
    normalize_ao3_date_filter,
    normalize_author_key,
    normalize_word_count_filter,
)
from app.domain.entities import (
    BrowseSnapshot,
    EvaluationBatch,
    Evaluation,
    EvaluationQueueItem,
    FandomDirectorySource,
    FandomProfile,
    FandomSuggestion,
    ReaderAsset,
    ReaderChapter,
    ReadingState,
    Work,
    WorkSet,
    WorkTag,
)
from app.domain.enums import (
    EvaluationBatchStatus,
    EvaluationStatus,
    QueueStatus,
    RarityTier,
    ReadingStatus,
    RuntimeMode,
    ScorePolarity,
    TagType,
)
from app.infrastructure.ao3.models import ParsedBrowsePage, ReaderDocument, WorkSummary
from app.infrastructure.ao3.parser import parse_fandom_tag_catalog


def test_sqlite_bootstrap_identity_and_crud(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    identity = container.identity_service.bootstrap()

    assert identity.local_user_id
    assert container.mode_service.current_mode() is RuntimeMode.LOCAL

    work = Work(
        work_id="12345",
        ao3_url="https://archiveofourown.org/works/12345",
        title="A Useful Work",
        author_name="example",
        published_at="2026-01-01",
        last_ao3_updated_at="2026-01-08",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)
    container.tag_repo.replace_for_work("12345", [WorkTag("12345", TagType.FANDOM, "Fandom")])

    assert container.work_library_service.get("12345").title == "A Useful Work"
    assert container.work_library_service.get("12345").published_at == "2026-01-01"
    assert container.work_library_service.get("12345").last_ao3_updated_at == "2026-01-08"
    assert container.work_library_service.tags_for_work("12345")[0].tag_text == "Fandom"

    result = container.evaluation_service.save_manual(
        work_id="12345",
        schema_key=container.schema_service.active_schema().schema_key,
        scores={"story_fit": 8, "craft": 9, "emotional_pull": 7},
        notes_markdown="Good.",
    )
    assert result.ok
    assert container.evaluation_service.latest_for_work("12345").scores["craft"] == 9


def test_browse_batch_repository_reads_match_per_work_reads(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    works = [
        Work(
            work_id=work_id,
            ao3_url=f"https://archiveofourown.org/works/{work_id}",
            title=f"Work {work_id}",
            last_scraped_at="2026-01-01T00:00:00Z",
            scrape_version="test",
        )
        for work_id in ["batch-a", "batch-b", "batch-c"]
    ]
    for work in works:
        container.work_repo.upsert(work)
    container.tag_repo.replace_for_work(
        "batch-a",
        [
            WorkTag("batch-a", TagType.FANDOM, "Batch Fandom"),
            WorkTag("batch-a", TagType.CHARACTER, "Batch Character"),
        ],
    )
    container.tag_repo.replace_for_work("batch-b", [WorkTag("batch-b", TagType.FREEFORM, "Batch Freeform")])
    active = container.fandom_service.ensure_default()
    container.collection_repo.collect("batch-b", active.fandom_key)
    container.rarity_service.set_manual("batch-c", RarityTier.RARE)
    schema = container.schema_service.active_schema()
    result_a = container.evaluation_service.save_manual(
        work_id="batch-a",
        schema_key=schema.schema_key,
        scores={"story_fit": 8, "craft": 7, "emotional_pull": 6},
    )
    result_b = container.evaluation_service.save_manual(
        work_id="batch-b",
        schema_key=schema.schema_key,
        scores={"story_fit": 5, "craft": 6, "emotional_pull": 7},
    )
    assert result_a.ok
    assert result_b.ok

    ids = ["batch-b", "batch-a", "missing", "batch-c"]
    tags_by_work = container.tag_repo.list_for_works(ids)
    collected_ids = container.collection_repo.collected_ids(ids)
    identity = container.identity_service.bootstrap()
    rarities_by_work = container.rarity_repo.list_for_works(ids, identity.local_user_id)
    latest_by_work = container.evaluation_repo.latest_for_works(ids, identity.local_user_id, schema.schema_key)

    assert tags_by_work["batch-a"] == container.tag_repo.list_for_work("batch-a")
    assert tags_by_work["batch-b"] == container.tag_repo.list_for_work("batch-b")
    assert tags_by_work["batch-c"] == []
    assert collected_ids == {"batch-b"}
    assert rarities_by_work["batch-c"].manual_rarity is RarityTier.RARE
    assert latest_by_work["batch-a"].scores["story_fit"] == 8
    assert latest_by_work["batch-b"].scores["emotional_pull"] == 7


def test_v12_migrates_work_sets_and_flat_queue_items_to_schema_batches(tmp_path) -> None:
    path = tmp_path / "ao3.sqlite"
    container = build_container(path)
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    for work_id in ["legacy-set-work", "legacy-queue-work"]:
        container.work_repo.upsert(
            Work(
                work_id=work_id,
                ao3_url=f"https://archiveofourown.org/works/{work_id}",
                title=work_id,
                last_scraped_at="2026-01-01T00:00:00Z",
            )
        )
    state = {"fandom": profile.tag, "sort_column": "revised_at", "page": 1}
    container.work_set_repo.save(
        WorkSet(
            "legacy-set",
            profile.fandom_key,
            "Legacy Set",
            state,
            filter_signature(state),
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        )
    )
    container.work_set_repo.record_page("legacy-set", 1, "https://example.test", ["legacy-set-work"], "2026-01-01T00:00:00Z")

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DROP TABLE evaluation_batches")
        conn.execute(
            """
            CREATE TABLE evaluation_queue_legacy (
                id TEXT PRIMARY KEY,
                work_id TEXT NOT NULL,
                reason TEXT,
                priority INTEGER NOT NULL DEFAULT 100,
                queue_status TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                finished_at TEXT,
                error_text TEXT,
                FOREIGN KEY(work_id) REFERENCES works(work_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            INSERT INTO evaluation_queue_legacy(
                id, work_id, reason, priority, queue_status, requested_at, finished_at, error_text
            ) VALUES ('legacy-queue-item', 'legacy-queue-work', 'old queue', 100, 'queued', '2026-01-01T00:00:00Z', NULL, NULL)
            """
        )
        conn.execute("DROP TABLE evaluation_queue")
        conn.execute("ALTER TABLE evaluation_queue_legacy RENAME TO evaluation_queue")
        conn.execute("PRAGMA user_version = 11")
        conn.execute("PRAGMA foreign_keys = ON")

    migrated = build_container(path)

    assert migrated.batch_repo.get_by_work_set_schema("legacy-set", schema.schema_key) is not None
    manual_set = migrated.work_set_repo.get_by_name(profile.fandom_key, "Manual Queue")
    assert manual_set is not None
    manual_batch = migrated.batch_repo.get_by_work_set_schema(manual_set.id, schema.schema_key)
    assert manual_batch is not None
    item = migrated.queue_repo.get("legacy-queue-item")
    assert item is not None
    assert item.batch_id == manual_batch.id
    assert item.schema_key == schema.schema_key
    assert migrated.work_set_repo.list_work_ids(manual_set.id) == ["legacy-queue-work"]


def test_duplicate_work_set_schema_batch_is_rejected(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    state = {"fandom": profile.tag, "sort_column": "revised_at", "page": 1}
    container.work_set_repo.save(
        WorkSet("duplicate-set", profile.fandom_key, "Duplicate Set", state, filter_signature(state), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    batch = EvaluationBatch(
        "batch-one",
        "duplicate-set",
        profile.fandom_key,
        schema.schema_key,
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
        status=EvaluationBatchStatus.QUEUED,
    )
    container.batch_repo.save(batch)

    with pytest.raises(sqlite3.IntegrityError):
        container.batch_repo.save(
            EvaluationBatch(
                "batch-two",
                "duplicate-set",
                profile.fandom_key,
                schema.schema_key,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
                status=EvaluationBatchStatus.QUEUED,
            )
        )


def test_named_queue_save_queues_only_unevaluated_and_splits_partial_results(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    for work_id in ["queue-a", "queue-b", "queue-c"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )
    container.evaluation_service.save_manual(
        work_id="queue-b",
        schema_key=schema.schema_key,
        scores={"story_fit": 7, "craft": 7, "emotional_pull": 7},
        status=EvaluationStatus.COMPLETE,
    )

    result = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Page Queue",
        filter_state={"fandom": profile.tag, "sort_column": "revised_at", "page": 1},
        source_url="https://example.test",
        work_ids=["queue-a", "queue-b", "queue-c"],
        page_number=1,
        schema_key=schema.schema_key,
    )

    assert result.ok
    batch = result.payload["batch"]
    queued_ids = {item.work_id for item in container.queue_repo.list(batch_id=batch.id)}
    assert queued_ids == {"queue-a", "queue-c"}
    assert {work.work_id for work in container.queue_service.pending_works_for_batch(batch.id).works} == {"queue-a", "queue-c"}
    assert [work.work_id for work in container.queue_service.evaluated_works_for_batch(batch.id).works] == ["queue-b"]
    queue_summary = container.queue_service.list_queue_batches(profile.fandom_key)[0]
    evaluated_summary = container.queue_service.list_evaluated_batches(profile.fandom_key)[0]
    assert queue_summary.active_count == 2
    assert evaluated_summary.completed_count == 1
    container.evaluation_service.save_manual(
        work_id="queue-a",
        schema_key=schema.schema_key,
        scores={"story_fit": 8, "craft": 8, "emotional_pull": 8},
        status=EvaluationStatus.COMPLETE,
    )
    assert "queue-a" not in container.queue_service.active_work_ids()


def test_requeue_under_new_schema_skips_completed_and_forbids_used_schema(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    active_schema = container.schema_service.active_schema()
    alt_schema = container.schema_service.active_schema()
    alt_schema.schema_key = "alternate_queue_schema"
    alt_schema.name = "Alternate Queue Schema"
    alt_schema.is_active = False
    container.schema_service.save_schema(alt_schema)
    for work_id in ["requeue-a", "requeue-b"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )
    saved = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Schema Queue",
        filter_state={"fandom": profile.tag, "sort_column": "revised_at", "page": 1},
        source_url="https://example.test",
        work_ids=["requeue-a", "requeue-b"],
        page_number=1,
        schema_key=active_schema.schema_key,
    )
    work_set = saved.payload["work_set"]
    container.evaluation_service.save_manual(
        work_id="requeue-a",
        schema_key=alt_schema.schema_key,
        scores={"story_fit": 8, "craft": 8, "emotional_pull": 8},
        status=EvaluationStatus.COMPLETE,
    )

    duplicate = container.queue_service.requeue_work_set_under_schema(work_set.id, active_schema.schema_key)
    requeued = container.queue_service.requeue_work_set_under_schema(work_set.id, alt_schema.schema_key)

    assert not duplicate.ok
    assert requeued.ok
    alt_batch = requeued.payload["batch"]
    assert {item.work_id for item in container.queue_repo.list(batch_id=alt_batch.id)} == {"requeue-b"}
    assert not container.queue_service.requeue_work_set_under_schema(work_set.id, alt_schema.schema_key).ok


def test_grouped_cluster_schema_slots_queue_and_cleanup_schema(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    active_schema = container.schema_service.active_schema()
    alt_schema = replace(active_schema, schema_key="slot_alt_schema", name="Slot Alt Schema", is_active=False)
    container.schema_service.save_schema(alt_schema)
    for work_id in ["slot-a", "slot-b"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )
    saved = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Slot Cluster",
        filter_state={"fandom": profile.tag, "sort_column": "revised_at", "page": 1},
        source_url="https://example.test/slot",
        work_ids=["slot-a", "slot-b"],
        page_number=1,
        schema_key=active_schema.schema_key,
    )
    work_set = saved.payload["work_set"]

    cluster = container.queue_service.cluster_summary_for_work_set(work_set.id)
    slots = {slot.schema.schema_key: slot for slot in cluster.slots}
    assert slots[active_schema.schema_key].state == "queued"
    assert slots[alt_schema.schema_key].state == "empty"
    assert slots[alt_schema.schema_key].batch is None

    created = container.queue_service.create_queue_for_schema_slot(work_set.id, alt_schema.schema_key)
    assert created.ok
    alt_batch = created.payload["batch"]
    assert {item.work_id for item in container.queue_repo.list(batch_id=alt_batch.id)} == {"slot-a", "slot-b"}

    for work_id in ["slot-a", "slot-b"]:
        container.evaluation_service.save_manual(
            work_id=work_id,
            schema_key=alt_schema.schema_key,
            scores={"story_fit": 9, "craft": 9, "emotional_pull": 9},
            status=EvaluationStatus.COMPLETE,
        )
    completed_slot = {
        slot.schema.schema_key: slot
        for slot in container.queue_service.cluster_summary_for_work_set(work_set.id).slots
    }[alt_schema.schema_key]
    assert completed_slot.state == "complete"
    assert not container.queue_service.create_queue_for_schema_slot(work_set.id, alt_schema.schema_key).ok

    cleaned = container.queue_service.clean_evaluated_schema_slot(work_set.id, alt_schema.schema_key)
    assert cleaned.ok
    assert container.batch_repo.get(alt_batch.id) is None
    assert container.work_set_repo.get(work_set.id) is not None
    assert container.evaluation_service.latest_for_work("slot-a", alt_schema.schema_key) is None
    empty_slot = {
        slot.schema.schema_key: slot
        for slot in container.queue_service.cluster_summary_for_work_set(work_set.id).slots
    }[alt_schema.schema_key]
    assert empty_slot.state == "empty"
    assert container.queue_service.create_queue_for_schema_slot(work_set.id, alt_schema.schema_key).ok


def test_queue_cleanup_archives_partial_batch_and_preserves_evaluated_results(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    for work_id in ["queue-clean-a", "queue-clean-b"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )
    saved = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Queue Cleanup Cluster",
        filter_state={"fandom": profile.tag, "sort_column": "revised_at", "page": 1},
        source_url="https://example.test/queue-clean",
        work_ids=["queue-clean-a", "queue-clean-b"],
        page_number=1,
        schema_key=schema.schema_key,
    )
    work_set = saved.payload["work_set"]
    batch = saved.payload["batch"]
    container.evaluation_service.save_manual(
        work_id="queue-clean-a",
        schema_key=schema.schema_key,
        scores={"story_fit": 8, "craft": 8, "emotional_pull": 8},
        status=EvaluationStatus.COMPLETE,
    )

    cleaned = container.queue_service.clean_queue_schema_slot(work_set.id, schema.schema_key)

    assert cleaned.ok
    archived = container.batch_repo.get(batch.id)
    assert archived is not None
    assert archived.status is EvaluationBatchStatus.ARCHIVED
    assert container.queue_repo.list(batch_id=batch.id) == []
    assert container.queue_service.list_queue_batches(profile.fandom_key) == []
    evaluated = container.queue_service.list_evaluated_batches(profile.fandom_key)
    assert len(evaluated) == 1
    assert evaluated[0].completed_count == 1
    assert container.evaluation_service.latest_for_work("queue-clean-a", schema.schema_key) is not None
    assert container.queue_service.pending_works_for_batch(batch.id).works == []

    container.work_repo.upsert(
        Work("queue-clean-c", "https://archiveofourown.org/works/queue-clean-c", title="queue-clean-c", last_scraped_at="2026-01-01T00:00:00Z")
    )
    manual = container.queue_service.queue_work_to_named_cluster(
        fandom_key=profile.fandom_key,
        cluster_name="Queue Cleanup Cluster",
        work_id="queue-clean-c",
        schema_key=schema.schema_key,
    )

    assert manual.ok
    assert {item.work_id for item in container.queue_repo.list(batch_id=batch.id)} == {"queue-clean-c"}
    assert {work.work_id for work in container.queue_service.pending_works_for_batch(batch.id).works} == {"queue-clean-c"}

    requeued = container.queue_service.create_queue_for_schema_slot(work_set.id, schema.schema_key)

    assert requeued.ok
    assert {item.work_id for item in container.queue_repo.list(batch_id=batch.id)} == {"queue-clean-b", "queue-clean-c"}
    assert container.batch_repo.get(batch.id).status is EvaluationBatchStatus.PARTIAL


def test_cluster_metadata_persists_and_favorites_sort_first(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    for work_id in ["plain-work", "favorite-work"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )

    plain = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Plain Cluster",
        filter_state={"fandom": profile.tag, "sort_column": "revised_at", "page": 1},
        source_url="https://example.test/plain",
        work_ids=["plain-work"],
        page_number=1,
        schema_key=schema.schema_key,
    )
    favorite = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Favorite Cluster",
        filter_state={"fandom": profile.tag, "sort_column": "revised_at", "page": 1},
        source_url="https://example.test/favorite",
        work_ids=["favorite-work"],
        page_number=1,
        schema_key=schema.schema_key,
    )

    result = container.queue_service.update_cluster_metadata(
        favorite.payload["work_set"].id,
        color="#ff66aa",
        favorite=True,
        description="Evaluate the weird page first.",
    )

    assert result.ok
    rename = container.queue_service.update_cluster_metadata(
        favorite.payload["work_set"].id,
        name="Renamed Favorite Cluster",
    )

    assert rename.ok
    assert container.work_set_repo.get(favorite.payload["work_set"].id).name == "Renamed Favorite Cluster"
    assert not container.queue_service.update_cluster_metadata(favorite.payload["work_set"].id, name="Plain Cluster").ok
    assert not container.queue_service.update_cluster_metadata(favorite.payload["work_set"].id, name=" ").ok
    summaries = container.queue_service.list_queue_batches(profile.fandom_key)
    assert [summary.work_set.name for summary in summaries[:2]] == ["Renamed Favorite Cluster", "Plain Cluster"]
    stored = container.work_set_repo.get(favorite.payload["work_set"].id)
    assert stored.filter_state["_cluster_meta"] == {
        "color": "#ff66aa",
        "favorite": True,
        "description": "Evaluate the weird page first.",
    }
    renamed_refresh = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=profile.fandom_key,
        name="Renamed Favorite Cluster",
        filter_state={"fandom": profile.tag, "sort_column": "created_at", "page": 2},
        source_url="https://example.test/favorite-2",
        work_ids=["favorite-work"],
        page_number=2,
        schema_key=schema.schema_key,
    )
    assert renamed_refresh.ok
    assert container.work_set_repo.get(favorite.payload["work_set"].id).filter_state["_cluster_meta"]["color"] == "#ff66aa"


def test_manual_named_queue_targets_existing_or_new_cluster_without_default_drawer(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    for work_id in ["manual-new", "manual-evaluated", "manual-extra"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )
    container.evaluation_service.save_manual(
        work_id="manual-evaluated",
        schema_key=schema.schema_key,
        scores={"story_fit": 8, "craft": 8, "emotional_pull": 8},
        status=EvaluationStatus.COMPLETE,
    )

    created = container.queue_service.queue_work_to_named_cluster(
        fandom_key=profile.fandom_key,
        cluster_name="Named Manual",
        work_id="manual-new",
        schema_key=schema.schema_key,
    )
    evaluated = container.queue_service.queue_work_to_named_cluster(
        fandom_key=profile.fandom_key,
        cluster_name="Named Manual",
        work_id="manual-evaluated",
        schema_key=schema.schema_key,
    )
    extra = container.queue_service.queue_work_to_named_cluster(
        fandom_key=profile.fandom_key,
        cluster_name="Another Manual",
        work_id="manual-extra",
        schema_key=schema.schema_key,
    )
    duplicate = container.queue_service.queue_work_to_named_cluster(
        fandom_key=profile.fandom_key,
        cluster_name="Named Manual",
        work_id="manual-new",
        schema_key=schema.schema_key,
    )

    assert created.ok
    assert evaluated.ok
    assert extra.ok
    assert duplicate.ok
    assert "already in Named Manual" in duplicate.message
    manual_set = container.work_set_repo.get_by_name(profile.fandom_key, "Manual Queue")
    assert manual_set is None
    named_set = container.work_set_repo.get_by_name(profile.fandom_key, "Named Manual")
    assert named_set is not None
    batch = container.batch_repo.get_by_work_set_schema(named_set.id, schema.schema_key)
    assert batch is not None
    assert {item.work_id for item in container.queue_repo.list(batch_id=batch.id)} == {"manual-new"}
    assert {work.work_id for work in container.queue_service.pending_works_for_batch(batch.id).works} == {"manual-new"}
    assert [work.work_id for work in container.queue_service.evaluated_works_for_batch(batch.id).works] == ["manual-evaluated"]
    assert [target.name for target in container.queue_service.cluster_targets(profile.fandom_key)] == ["Another Manual", "Named Manual"]


def test_evaluated_batch_delete_removes_only_unprotected_cached_work(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    schema = container.schema_service.active_schema()
    for work_id in ["delete-free", "delete-kept"]:
        container.work_repo.upsert(
            Work(work_id, f"https://archiveofourown.org/works/{work_id}", title=work_id, last_scraped_at="2026-01-01T00:00:00Z")
        )
        container.evaluation_service.save_manual(
            work_id=work_id,
            schema_key=schema.schema_key,
            scores={"story_fit": 6, "craft": 6, "emotional_pull": 6},
            status=EvaluationStatus.COMPLETE,
        )
    container.collection_repo.collect("delete-kept", profile.fandom_key)
    state = {"fandom": profile.tag, "sort_column": "revised_at", "page": 1}
    container.work_set_repo.save(
        WorkSet("delete-set", profile.fandom_key, "Delete Set", state, filter_signature(state), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    container.work_set_repo.record_page("delete-set", 1, "https://example.test", ["delete-free", "delete-kept"], "2026-01-01T00:00:00Z")
    batch = EvaluationBatch(
        "delete-batch",
        "delete-set",
        profile.fandom_key,
        schema.schema_key,
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
        status=EvaluationBatchStatus.COMPLETE,
    )
    container.batch_repo.save(batch)

    result = container.queue_service.delete_evaluated_batch(batch.id)

    assert result.ok
    assert container.batch_repo.get(batch.id) is None
    assert container.work_set_repo.get("delete-set") is None
    assert container.evaluation_service.latest_for_work("delete-free", schema.schema_key) is None
    assert container.evaluation_service.latest_for_work("delete-kept", schema.schema_key) is None
    assert container.work_repo.get("delete-free") is None
    assert container.work_repo.get("delete-kept") is not None


def test_publication_date_survives_cache_purge(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        work_id="pub-cache",
        ao3_url="https://archiveofourown.org/works/pub-cache",
        title="Publication Cache",
        published_at="2026-03-23",
        last_scraped_at="2026-05-23T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)

    assert container.work_repo.delete_uncollected_cache() == 1

    container.work_repo.upsert(
        Work(
            work_id="pub-cache",
            ao3_url="https://archiveofourown.org/works/pub-cache",
            title="Publication Cache Reloaded",
            last_scraped_at="2026-05-24T00:00:00Z",
            scrape_version="test",
        )
    )

    restored = container.work_repo.get("pub-cache")
    assert restored is not None
    assert restored.published_at == "2026-03-23"


def test_queue_transition(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        work_id="12345",
        ao3_url="https://archiveofourown.org/works/12345",
        title="A Useful Work",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)
    item = container.queue_service.enqueue("12345")
    container.queue_service.update_status(item.id, status=QueueStatus.DONE)

    assert container.queue_service.list()[0].queue_status.value == "done"


def test_queue_enqueue_reuses_active_work_item(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        work_id="12345",
        ao3_url="https://archiveofourown.org/works/12345",
        title="A Useful Work",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)

    first = container.queue_service.enqueue("12345")
    second = container.queue_service.enqueue("12345")

    assert second.id == first.id
    assert len(container.queue_service.list(QueueStatus.QUEUED)) == 1
    assert container.queue_service.is_active_for_work("12345")


def test_queue_delete(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        work_id="12345",
        ao3_url="https://archiveofourown.org/works/12345",
        title="A Useful Work",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)
    item = container.queue_service.enqueue("12345")

    assert container.queue_service.delete_many([item.id]) == 1
    assert container.queue_service.list() == []


def test_old_required_schema_json_loads_with_positive_polarity(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    definition = {
        "label": "Old",
        "description": "",
        "dimensions": [{"key": "craft", "label": "Craft", "weight": 1.0, "required": True}],
        "score_range": {"minimum": 1, "maximum": 10, "step": 1},
    }
    with container.db.connect() as conn:
        conn.execute("UPDATE schemas_local SET is_active = 0")
        conn.execute(
            """
            INSERT INTO schemas_local(schema_key, name, version, definition_json, is_active, is_official_shared_compatible, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("old_required", "Old Required", "1.0.0", json.dumps(definition), 1, 0, "2026-01-01T00:00:00Z"),
        )

    schema = container.schema_repo.get("old_required")

    assert schema is not None
    assert schema.dimensions[0].polarity is ScorePolarity.POSITIVE


def test_import_browse_html_when_live_fetch_is_blocked(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    html = Path("tests/snapshots/ao3_browse_sample.html").read_text(encoding="utf-8")

    result = container.browse_service.import_browse_html(
        html,
        "https://archiveofourown.org/tags/Fandom/works",
        context_type="fandom",
        context_key="Fandom",
    )

    assert result.ok
    assert container.work_library_service.get("12345").title == "A Useful Work"


def test_browse_service_builds_ao3_search_urls() -> None:
    assert (
        AO3BrowseService.resolve_browse_url("", "search", "life is strange")
        == "https://archiveofourown.org/works/search?work_search%5Bquery%5D=life+is+strange"
    )
    assert (
        AO3BrowseService.resolve_browse_url("", "fandom", "Life is Strange")
        == "https://archiveofourown.org/tags/Life%20is%20Strange/works"
    )


def test_browse_service_builds_fandom_scoped_filter_urls() -> None:
    url = AO3BrowseService.resolve_fandom_filter_url(
        "Life is Strange (Video Games 2015 2017 2024 2026)",
        {"query": "overlooked", "sort_column": "revised_at", "page": 6},
    )

    assert url.startswith("https://archiveofourown.org/works?work_search%5Bsort_column%5D=revised_at")
    assert "work_search%5Bsort_direction%5D=desc" in url
    assert "work_search%5Bquery%5D=overlooked" in url
    assert "commit=Sort+and+Filter" in url
    assert "tag_id=Life+is+Strange+%28Video+Games+2015+2017+2024+2026%29" in url
    assert "page=6" in url


def test_browse_service_matches_ao3_filter_parameter_shape() -> None:
    url = AO3BrowseService.resolve_fandom_filter_url(
        "Life is Strange (Video Games 2015 2017 2024 2026)",
        {
            "query": "",
            "sort_column": "revised_at",
            "selected": {
                "include_work_search[character_ids][]": ["10872457"],
                "exclude_work_search[character_ids][]": ["4149650"],
            },
        },
    )

    assert "work_search%5Bsort_column%5D=revised_at&work_search%5Bsort_direction%5D=desc&include_work_search%5Bcharacter_ids%5D%5B%5D=10872457" in url
    assert "&work_search%5Bother_tag_names%5D=&exclude_work_search%5Bcharacter_ids%5D%5B%5D=4149650" in url
    assert "&commit=Sort+and+Filter&tag_id=Life+is+Strange+%28Video+Games+2015+2017+2024+2026%29" in url


def test_blocked_tags_are_added_to_ao3_excluded_tag_filter(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    container.work_library_service.block_tag(profile.fandom_key, TagType.FREEFORM, "Hard No")
    container.work_library_service.block_tag(profile.fandom_key, TagType.RELATIONSHIP, 'Maxine "Max" Caulfield/Chloe Price')

    url = container.browse_service.resolve_effective_fandom_filter_url(
        profile.tag,
        {"excluded_tag_names": "Existing Bad, hard no", "page": 2},
    )
    query = parse_qs(urlparse(url).query)

    assert query["work_search[excluded_tag_names]"] == [
        'Existing Bad, hard no, Maxine "Max" Caulfield/Chloe Price',
    ]
    assert query["page"] == ["2"]
    assert query["tag_id"] == [profile.tag]


def test_blocked_tags_convert_plain_fandom_url_to_official_filter_shape(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    container.work_library_service.block_tag(profile.fandom_key, TagType.FREEFORM, "Hard No")

    url = container.browse_service.resolve_effective_browse_url("", "fandom", profile.tag)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.path == "/works"
    assert query["tag_id"] == [profile.tag]
    assert query["work_search[excluded_tag_names]"] == ["Hard No"]
    assert query["commit"] == ["Sort and Filter"]


def test_fandom_filter_url_normalizes_words_and_flexible_dates() -> None:
    url = AO3BrowseService.resolve_fandom_filter_url(
        "Fandom",
        {
            "sort_column": "revised_at",
            "words_from": "10k",
            "words_to": "1.2m",
            "date_from": "12april1999",
            "date_to": "05/12/1999",
            "language_id": "en",
        },
    )

    assert "work_search%5Bwords_from%5D=10000" in url
    assert "work_search%5Bwords_to%5D=1200000" in url
    assert "work_search%5Bdate_from%5D=1999-04-12" in url
    assert "work_search%5Bdate_to%5D=1999-05-12" in url
    assert normalize_word_count_filter("10,000") == "10000"
    assert normalize_ao3_date_filter("April 12 1999") == "1999-04-12"


def test_work_block_and_author_block_are_separate(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom"), tag="Fandom", display_name="Fandom")
    container.fandom_service.save_profile(profile)
    author_url = "https://archiveofourown.org/users/example/pseuds/example"
    first = Work(
        "blocked-work",
        "https://archiveofourown.org/works/blocked-work",
        title="Blocked Work",
        author_name="example",
        author_url=author_url,
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    second = Work(
        "same-author",
        "https://archiveofourown.org/works/same-author",
        title="Same Author",
        author_name="example",
        author_url=author_url,
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(first)
    container.work_repo.upsert(second)

    assert container.work_repo.get("blocked-work").author_key == normalize_author_key("example", author_url)

    result = container.work_library_service.block_work("blocked-work", profile.fandom_key)

    assert result.ok
    assert container.work_library_service.visible_work_ids(["blocked-work", "same-author"]) == ["same-author"]
    assert container.work_library_service.list_blocked_authors() == []

    author_result = container.work_library_service.block_author_for_work("same-author", profile.fandom_key)

    assert author_result.ok
    assert container.work_library_service.visible_work_ids(["blocked-work", "same-author"]) == []
    assert container.work_library_service.list_blocked_authors()[0].display_name == "example"


def test_blocked_author_groups_and_standalone_blocked_work_views(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom"), tag="Fandom", display_name="Fandom")
    container.fandom_service.save_profile(profile)
    author_url = "https://archiveofourown.org/users/example/pseuds/example"
    first = Work(
        "blocked-work",
        "https://archiveofourown.org/works/blocked-work",
        title="Blocked Work With A Fairly Long Title",
        author_name="example",
        author_url=author_url,
        summary_text="This is the work that was explicitly blocked.",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    second = Work(
        "same-author",
        "https://archiveofourown.org/works/same-author",
        title="Same Author Work",
        author_name="example",
        author_url=author_url,
        summary_text="This is hidden by the author block only.",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(first)
    container.work_repo.upsert(second)

    container.work_library_service.block_work(first.work_id, profile.fandom_key)
    container.work_library_service.block_author_for_work(first.work_id, profile.fandom_key)

    groups = container.work_library_service.blocked_author_groups()
    assert len(groups) == 1
    assert groups[0].author.display_name == "example"
    assert {work.work_id for work in groups[0].works} == {"blocked-work", "same-author"}
    assert groups[0].explicit_work_ids == {"blocked-work"}
    assert [view.block.work_id for view in container.work_library_service.standalone_blocked_work_views()] == ["blocked-work"]

    assert container.work_library_service.unblock_many_authors([groups[0].author.author_key]) == 1

    standalone = container.work_library_service.standalone_blocked_work_views()
    assert [view.block.work_id for view in standalone] == ["blocked-work"]
    assert standalone[0].work.title == "Blocked Work With A Fairly Long Title"

    assert container.work_library_service.unblock_many_works(["blocked-work"]) == 1
    assert container.work_library_service.standalone_blocked_work_views() == []


def test_blocked_work_views_are_scoped_to_selected_fandom(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    life_is_strange = FandomProfile(fandom_key=fandom_key("Life is Strange"), tag="Life is Strange", display_name="Life is Strange")
    mass_effect = FandomProfile(fandom_key=fandom_key("Mass Effect"), tag="Mass Effect", display_name="Mass Effect")
    container.fandom_service.save_profile(life_is_strange)
    container.fandom_service.save_profile(mass_effect)
    work = Work(
        "lis-blocked-work",
        "https://archiveofourown.org/works/lis-blocked-work",
        title="Life Is Strange Blocked Work",
        author_name="example",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(work)
    container.work_library_service.block_work(work.work_id, life_is_strange.fandom_key)

    assert [view.block.work_id for view in container.work_library_service.standalone_blocked_work_views(fandom_key=life_is_strange.fandom_key)] == [
        work.work_id
    ]
    assert container.work_library_service.standalone_blocked_work_views(fandom_key=mass_effect.fandom_key) == []


def test_blocked_work_views_cluster_by_author(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom"), tag="Fandom", display_name="Fandom")
    container.fandom_service.save_profile(profile)
    works = [
        Work("a-2", "https://archiveofourown.org/works/a-2", title="Second A", author_name="Author A", last_scraped_at="2026-01-01T00:00:00Z"),
        Work("b-1", "https://archiveofourown.org/works/b-1", title="Only B", author_name="Author B", last_scraped_at="2026-01-01T00:00:00Z"),
        Work("a-1", "https://archiveofourown.org/works/a-1", title="First A", author_name="Author A", last_scraped_at="2026-01-01T00:00:00Z"),
    ]
    for work in works:
        container.work_repo.upsert(work)
        container.work_library_service.block_work(work.work_id, profile.fandom_key)

    views = container.work_library_service.standalone_blocked_work_views(fandom_key=profile.fandom_key)

    assert [view.block.work_id for view in views] == ["a-1", "a-2", "b-1"]


def test_blocked_tags_hide_matching_works_and_restore(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    work = Work(
        "tag-blocked",
        "https://archiveofourown.org/works/tag-blocked",
        title="Tag Blocked",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)
    container.tag_repo.replace_for_work(work.work_id, [WorkTag(work.work_id, TagType.FREEFORM, "Hard No")])
    container.work_library_service.collect(work.work_id, profile.fandom_key)

    result = container.work_library_service.block_tag(profile.fandom_key, TagType.FREEFORM, "Hard No")

    assert result.ok
    assert container.work_library_service.visible_work_ids([work.work_id]) == []
    assert container.work_library_service.list_blocked_tags(fandom_key=profile.fandom_key)[0].tag_text == "Hard No"
    assert container.work_library_service.is_collected(work.work_id) is False

    assert container.work_library_service.unblock_many_tags([(TagType.FREEFORM, "Hard No")]) == 1
    assert container.work_library_service.visible_work_ids([work.work_id]) == [work.work_id]


def test_blocked_tag_fetch_stores_metadata_for_later_restore(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.ensure_default()
    container.work_library_service.block_tag(profile.fandom_key, TagType.FREEFORM, "Hard No")
    work = Work(
        "fresh-tag-blocked",
        "https://archiveofourown.org/works/fresh-tag-blocked",
        title="Fresh Tag Blocked",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    tag = WorkTag(work.work_id, TagType.FREEFORM, "Hard No")
    parsed = ParsedBrowsePage("https://archiveofourown.org/tags/test/works", [WorkSummary(work, [tag])])

    result = container.browse_service._store_parsed_browse(parsed, parsed.source_url, "fandom", profile.fandom_key)

    assert result.ok
    assert result.works == []
    assert container.work_repo.get(work.work_id) is not None
    assert container.tag_repo.list_for_work(work.work_id)[0].tag_text == "Hard No"
    assert container.work_library_service.visible_work_ids([work.work_id]) == []

    container.work_library_service.unblock_many_tags([(TagType.FREEFORM, "Hard No")])
    assert container.work_library_service.visible_work_ids([work.work_id]) == [work.work_id]


def test_browse_cache_policy_defaults_and_round_trip(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")

    assert container.work_library_service.browse_cache_policy() == {"auto_purge_enabled": False, "max_cached_works": 120}

    saved = container.work_library_service.save_browse_cache_policy({"auto_purge_enabled": True, "max_cached_works": "42"})

    assert saved == {"auto_purge_enabled": True, "max_cached_works": 42}
    assert container.work_library_service.browse_cache_policy()["max_cached_works"] == 42


def test_auto_purge_runs_only_when_enabled_and_over_threshold(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    for work_id in ["keep", "trash"]:
        container.work_repo.upsert(
            Work(
                work_id,
                f"https://archiveofourown.org/works/{work_id}",
                title=work_id,
                last_scraped_at="2026-01-01T00:00:00Z",
            )
        )

    assert container.work_library_service.maybe_auto_purge_cache(["keep"]) is None
    assert container.work_repo.get("trash") is not None

    container.work_library_service.save_browse_cache_policy({"auto_purge_enabled": True, "max_cached_works": 1})
    result = container.work_library_service.maybe_auto_purge_cache(["keep"])

    assert result is not None
    assert result.ok
    assert container.work_repo.get("keep") is not None
    assert container.work_repo.get("trash") is None


def test_collection_and_blocklist_separate_browse_cache_from_kept_works(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(
        fandom_key=fandom_key("Fandom"),
        tag="Fandom",
        display_name="Fandom",
        color="#ff66aa",
    )
    container.fandom_service.save_profile(profile)
    work = Work(
        work_id="999",
        ao3_url="https://archiveofourown.org/works/999",
        title="Browsing Cache Only",
        last_scraped_at="2026-01-01T00:00:00Z",
        scrape_version="test",
    )
    container.work_repo.upsert(work)

    assert container.work_library_service.cache_count() == 1
    assert container.work_library_service.count() == 0

    assert container.work_library_service.collect("999", profile.fandom_key).ok
    assert container.work_library_service.count() == 1
    assert container.work_library_service.list_collected()[0].work_id == "999"

    container.work_library_service.block_work("999", profile.fandom_key)
    assert container.work_library_service.is_blocked("999")
    assert container.work_library_service.count() == 0


def test_collected_works_order_by_reader_activity_not_queue_activity(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    identity = container.identity_service.bootstrap()
    for work_id in ["old-read", "queued-only", "new-read"]:
        container.work_repo.upsert(
            Work(
                work_id,
                f"https://archiveofourown.org/works/{work_id}",
                title=work_id,
                last_scraped_at="2026-01-01T00:00:00Z",
            )
        )
        container.work_library_service.collect(work_id)

    container.reading_repo.upsert(
        ReadingState(
            "old-read",
            identity.local_user_id,
            ReadingStatus.READING,
            last_opened_at="2026-01-01T00:00:00Z",
        )
    )
    container.reading_repo.upsert(
        ReadingState(
            "queued-only",
            identity.local_user_id,
            ReadingStatus.QUEUED,
            last_opened_at="2030-01-01T00:00:00Z",
        )
    )
    container.reading_repo.upsert(
        ReadingState(
            "new-read",
            identity.local_user_id,
            ReadingStatus.READING,
            last_opened_at="2026-02-01T00:00:00Z",
        )
    )

    assert [work.work_id for work in container.work_library_service.list_collected()] == [
        "new-read",
        "old-read",
        "queued-only",
    ]


def test_queue_enqueue_does_not_create_reader_activity_timestamp(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    identity = container.identity_service.bootstrap()
    container.work_repo.upsert(
        Work(
            "queued-only",
            "https://archiveofourown.org/works/queued-only",
            title="Queued Only",
            last_scraped_at="2026-01-01T00:00:00Z",
        )
    )

    container.queue_service.enqueue("queued-only")

    state = container.reading_repo.get("queued-only", identity.local_user_id)
    assert state is not None
    assert state.state is ReadingStatus.QUEUED
    assert state.last_opened_at is None


def test_fandom_tag_catalog_is_cached_per_fandom(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(
        fandom_key=fandom_key("Life is Strange"),
        tag="Life is Strange",
        display_name="Life is Strange",
        color="#58a6ff",
    )
    container.fandom_service.save_profile(profile)
    html = Path("tests/snapshots/ao3_fandom_tag_sample.html").read_text(encoding="utf-8")
    items = parse_fandom_tag_catalog(html, "https://archiveofourown.org/tags/Life", profile.fandom_key)

    container.tag_catalog_repo.replace_for_fandom(profile.fandom_key, items)

    assert container.fandom_service.tag_catalog_count(profile.fandom_key) == len(items)
    suggestions = container.fandom_service.tag_suggestions(profile.fandom_key, "Chloe", 10)
    assert any(item.tag_text == 'Maxine "Max" Caulfield/Chloe Price' for item in suggestions)
    assert all(item.fandom_key == profile.fandom_key for item in suggestions)


def test_character_reader_style_round_trips_through_sqlite(tmp_path) -> None:
    db_path = tmp_path / "ao3.sqlite"
    container = build_container(db_path)
    profile = FandomProfile(
        fandom_key=fandom_key("Life is Strange"),
        tag="Life is Strange",
        display_name="Life is Strange",
        color="#58a6ff",
    )
    container.fandom_service.save_profile(profile)

    result = container.fandom_service.save_character(
        fandom_key=profile.fandom_key,
        name="Max",
        full_name="Maxine Caulfield",
        color="#58a6ff",
        reader_style={
            "font_family": "'Newsreader', serif",
            "custom_font_enabled": True,
            "font_size": 21.5,
            "font_size_enabled": True,
        },
    )

    assert result.ok
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 14
        columns = {row[1] for row in conn.execute("PRAGMA table_info(character_profiles)").fetchall()}
    assert "reader_style_json" in columns
    [character] = container.fandom_service.list_characters(profile.fandom_key)
    assert character.reader_style == {
        "font_family": "'Newsreader', serif",
        "custom_font_enabled": True,
        "font_size": 21.5,
        "font_size_enabled": True,
    }


def test_work_sets_and_favorite_tags_round_trip(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom"), tag="Fandom", display_name="Fandom")
    container.fandom_service.save_profile(profile)
    work = Work("111", "https://archiveofourown.org/works/111", title="Set Work", last_scraped_at="2026-01-01T00:00:00Z")
    container.work_repo.upsert(work)

    state = {"fandom": "Fandom", "sort_column": "word_count", "page": 2, "language_id": "en"}
    work_set = WorkSet(
        id="set-1",
        fandom_key=profile.fandom_key,
        name="Long English",
        filter_state=state,
        filter_signature=filter_signature(state),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    container.work_set_repo.save(work_set)
    container.work_set_repo.record_page("set-1", 2, "https://example.test/page=2", ["111"], "2026-01-01T00:00:00Z")
    container.work_library_service.favorite_tag(profile.fandom_key, TagType.CHARACTER, "Maxine Caulfield", "#ff66aa")
    color_result = container.work_library_service.set_tag_color(profile.fandom_key, TagType.FREEFORM, "Toxic Vibes", "#aa00ff")

    assert container.work_set_repo.get_by_name(profile.fandom_key, "Long English").filter_signature == filter_signature(state)
    assert container.work_set_repo.list_pages("set-1")[0].work_ids == ["111"]
    assert container.work_set_repo.list_work_ids("set-1") == ["111"]
    assert container.work_library_service.favorite_tags_for_fandom(profile.fandom_key)[0].tag_text == "Maxine Caulfield"
    assert color_result.ok
    assert container.work_library_service.tag_colors_for_fandom(profile.fandom_key)[0].tag_text == "Toxic Vibes"
    assert [favorite.tag_text for favorite in container.work_library_service.favorite_tags_for_fandom(profile.fandom_key)] == ["Maxine Caulfield"]


def test_fandom_backup_zip_exports_deletes_and_imports_scoped_data(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = container.fandom_service.save_profile(
        FandomProfile(
            fandom_key=fandom_key("Fandom Backup"),
            tag="Fandom Backup",
            display_name="Fandom Backup",
            color="#58a6ff",
            avatar_url="/fandom-avatars/fandom_backup.png",
            default_filter={"fandom": "Fandom Backup", "sort_column": "revised_at"},
        )
    )
    container.fandom_service.select(profile.fandom_key)
    work = Work("backup-work", "https://archiveofourown.org/works/backup-work", title="Backup Work", last_scraped_at="2026-01-01T00:00:00Z")
    container.work_repo.upsert(work)
    container.tag_repo.replace_for_work("backup-work", [WorkTag("backup-work", TagType.FANDOM, "Fandom Backup")])
    container.reader_asset_repo.replace_document(
        ReaderAsset(
            work_id="backup-work",
            source_format="html",
            source_url=work.ao3_url,
            download_url="https://archiveofourown.org/downloads/backup-work.html",
            content_hash="abc",
            downloaded_chapter_count=1,
            known_ao3_chapter_count=1,
            downloaded_at="2026-01-01T00:00:00Z",
            last_checked_at="2026-01-01T00:00:00Z",
        ),
        [ReaderChapter("backup-work", 1, "One", work.ao3_url, "chapter-1", "<p>Backup text.</p>", "h")],
    )
    container.fandom_service.save_character(
        fandom_key=profile.fandom_key,
        character_id="backup-character",
        name="Max",
        full_name="Maxine Caulfield",
        color="#58a6ff",
        avatar_url="/character-avatars/character_backup.png",
    )
    state = {"fandom": "Fandom Backup", "page": 1}
    work_set = WorkSet(
        id="backup-set",
        fandom_key=profile.fandom_key,
        name="Backup Set",
        filter_state=state,
        filter_signature=filter_signature(state),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    container.work_set_repo.save(work_set)
    container.work_set_repo.add_items(work_set.id, [work.work_id])
    container.batch_repo.save(
        EvaluationBatch(
            id="backup-batch",
            work_set_id=work_set.id,
            fandom_key=profile.fandom_key,
            schema_key="local_default_v1",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )
    container.queue_repo.add(
        EvaluationQueueItem(
            id="backup-queue",
            work_id=work.work_id,
            priority=100,
            queue_status=QueueStatus.QUEUED,
            requested_at="2026-01-01T00:00:00Z",
            batch_id="backup-batch",
            schema_key="local_default_v1",
        )
    )
    local_id = container.identity_service.bootstrap().local_user_id
    container.evaluation_repo.save(
        Evaluation(
            id="backup-eval",
            work_id=work.work_id,
            local_user_id=local_id,
            schema_key="local_default_v1",
            schema_version="1.0.0",
            scores={"craft": 8},
            status=EvaluationStatus.COMPLETE,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    )

    filename, payload = container.fandom_service.export_fandom_backup(profile.fandom_key)

    assert filename.endswith(".ao3fandom.zip")
    with ZipFile(io.BytesIO(payload), "r") as archive:
        assert {"manifest.json", "fandom.sqlite"} <= set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["fandom_key"] == profile.fandom_key
        assert manifest["work_count"] == 1

    result = container.fandom_service.delete_fandoms_after_backup([profile.fandom_key])
    assert result.ok
    assert container.fandom_repo.get(profile.fandom_key) is None
    assert container.work_repo.get(work.work_id) is None

    restored = container.fandom_service.import_fandom_backup(payload)

    assert restored.fandom_key == profile.fandom_key
    assert container.work_repo.get(work.work_id).title == "Backup Work"
    assert container.reader_asset_repo.get_asset(work.work_id).content_hash == "abc"
    assert container.work_set_repo.list_work_ids(work_set.id) == [work.work_id]
    assert container.queue_repo.get("backup-queue").work_id == work.work_id
    assert container.evaluation_repo.latest_for_work(work.work_id, local_id, "local_default_v1").scores == {"craft": 8}
    assert container.fandom_service.list_characters(profile.fandom_key)[0].name == "Max"


def test_reader_asset_and_position_round_trip(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work("reader", "https://archiveofourown.org/works/reader", title="Reader Work", chapters_current=2, last_scraped_at="2026-01-01T00:00:00Z")
    container.work_repo.upsert(work)
    asset = ReaderAsset(
        work_id="reader",
        source_format="html",
        source_url=work.ao3_url,
        download_url="https://archiveofourown.org/downloads/reader.html",
        content_hash="abc",
        downloaded_chapter_count=2,
        known_ao3_chapter_count=2,
        downloaded_at="2026-01-01T00:00:00Z",
        last_checked_at="2026-01-01T00:00:00Z",
    )
    chapters = [
        ReaderChapter("reader", 1, "One", work.ao3_url, "chapter-1", "<p>Max arrives.</p>", "h1"),
        ReaderChapter("reader", 2, "Two", work.ao3_url, "chapter-2", "<p>Chloe waits.</p>", "h2"),
    ]
    container.reader_asset_repo.replace_document(asset, chapters)

    container.reader_service.set_position("reader", 2, 0.5, "chapter-2")
    result = container.reader_service.open_work("reader", auto_download=False)

    assert result.ok
    assert result.freshness == "current"
    assert result.active_chapter_index == 2
    assert result.scroll_percent == 0.5
    assert [chapter.title for chapter in result.chapters] == ["One", "Two"]


class _FakeReaderClient:
    def fetch_reader_document(self, url: str) -> ReaderDocument:
        work = Work("remote-reader", url, title="Remote Reader", chapters_current=2, last_scraped_at="2026-01-01T00:00:00Z")
        return ReaderDocument(
            work=work,
            source_url=url,
            download_url="https://archiveofourown.org/downloads/remote-reader.html",
            content_hash="hash",
            chapters=[
                ReaderChapter("remote-reader", 1, "One", url, "chapter-1", "<p>One</p>", "one"),
                ReaderChapter("remote-reader", 2, "Two", url, "chapter-2", "<p>Two</p>", "two"),
            ],
        )


class _FailingReaderClient:
    def fetch_reader_document(self, url: str) -> ReaderDocument:
        raise RuntimeError("network unavailable")


class _FakeQueueModelProvider:
    def __init__(self) -> None:
        self.loaded: list[tuple[str, int | None]] = []
        self.unloaded: list[str] = []
        self.evaluated: list[str] = []

    def available_models(self) -> list[str]:
        return ["fake-model"]

    def available_model_details(self) -> list[dict[str, object]]:
        return [{"type": "llm", "key": "fake-model", "display_name": "Fake Model", "loaded_instances": []}]

    def loaded_instance_id(self, model: str) -> str | None:
        return None

    def load_model(self, model: str, context_length: int | None = None) -> dict[str, object]:
        self.loaded.append((model, context_length))
        return {"instance_id": "fake-instance", "status": "loaded"}

    def unload_model(self, instance_id: str) -> dict[str, object]:
        self.unloaded.append(instance_id)
        return {"instance_id": instance_id}

    def evaluate_work(self, **kwargs) -> dict[str, object]:
        return self.evaluate_sampled_work(**kwargs)

    def evaluate_sampled_work(self, **kwargs) -> dict[str, object]:
        work = kwargs["work"]
        self.evaluated.append(work.work_id)
        return {
            "scores": {"story_fit": 8, "craft": 7, "emotional_pull": 9},
            "notes_markdown": "Evaluated.",
            "evidence": {"work_id": work.work_id},
            "model_name": "fake-model",
        }


def test_reader_service_download_preserves_position(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    container.reader_service.ao3_client = _FakeReaderClient()
    work = Work("remote-reader", "https://archiveofourown.org/works/remote-reader", title="Remote Reader", chapters_current=1, last_scraped_at="2026-01-01T00:00:00Z")
    container.work_repo.upsert(work)
    container.reader_service.set_position("remote-reader", 2, 0.25, "chapter-2")

    result = container.reader_service.refresh_work("remote-reader")

    assert result.ok
    assert result.active_chapter_index == 2
    assert result.scroll_percent == 0.25
    assert container.reader_asset_repo.get_asset("remote-reader").downloaded_chapter_count == 2


def test_queue_sampling_uses_configured_chapters_without_marking_read(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        "sample-reader",
        "https://archiveofourown.org/works/sample-reader",
        title="Sample Reader",
        chapters_current=4,
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(work)
    container.reader_asset_repo.replace_document(
        ReaderAsset(
            work_id=work.work_id,
            source_format="html",
            source_url=work.ao3_url,
            download_url="https://archiveofourown.org/downloads/sample-reader.html",
            content_hash="sample-hash",
            downloaded_chapter_count=4,
            known_ao3_chapter_count=4,
            downloaded_at="2026-01-01T00:00:00Z",
        ),
        [
            ReaderChapter(work.work_id, 1, "One", work.ao3_url, "chapter-1", "<p>opening words are intentionally ignored here</p>", "h1"),
            ReaderChapter(work.work_id, 2, "Two", work.ao3_url, "chapter-2", "<p>   </p>", "h2"),
            ReaderChapter(work.work_id, 3, "Three", work.ao3_url, "chapter-3", "<p>alpha beta gamma delta epsilon</p>", "h3"),
            ReaderChapter(work.work_id, 4, "Four", work.ao3_url, "chapter-4", "<p>zeta eta theta iota kappa lambda</p>", "h4"),
        ],
    )
    identity = container.identity_service.bootstrap()

    result = container.queue_runner_service.sample_work(
        work.work_id,
        QueueEvaluationConfig(
            include_metadata=True,
            include_tags=False,
            start_chapter=2,
            chapter_window=2,
            target_words=6,
            max_words=8,
            skip_empty_chapters=True,
        ),
    )

    assert result.ok
    sample = result.payload
    assert sample.chapter_scope["actual_start_chapter"] == 3
    assert sample.chapter_scope["skipped_empty_chapters"] == [2]
    assert sample.chapter_scope["sampled_words"] <= 8
    assert "Chapter 3" in sample.text
    assert "Chapter 4" in sample.text
    assert "Chapter 1" not in sample.text
    assert container.reading_repo.get(work.work_id, identity.local_user_id) is None


def test_queue_runner_continues_after_work_failure_and_unloads_owned_model(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    provider = _FakeQueueModelProvider()
    container.evaluation_service.model_provider = provider
    container.local_model_service.provider = provider
    container.reader_service.ao3_client = _FailingReaderClient()
    container.local_model_service.save_config(
        base_url="http://localhost:1234/v1",
        model="fake-model",
        timeout_seconds=30,
        temperature=0.2,
        context_length=4096,
    )
    container.queue_runner_service.save_config(
        {
            "include_metadata": True,
            "include_tags": True,
            "start_chapter": 1,
            "chapter_window": 1,
            "target_words": 4,
            "max_words": 12,
            "skip_empty_chapters": True,
        }
    )
    active = container.fandom_service.ensure_default()
    work_ids = ["runner-a", "runner-b", "runner-c"]
    for work_id in work_ids:
        container.work_repo.upsert(
            Work(
                work_id=work_id,
                ao3_url=f"https://archiveofourown.org/works/{work_id}",
                title=work_id,
                chapters_current=1,
                last_scraped_at="2026-01-01T00:00:00Z",
            )
        )
    for work_id in ["runner-a", "runner-c"]:
        container.reader_asset_repo.replace_document(
            ReaderAsset(
                work_id=work_id,
                source_format="html",
                source_url=f"https://archiveofourown.org/works/{work_id}",
                download_url=f"https://archiveofourown.org/downloads/{work_id}.html",
                content_hash=f"{work_id}-hash",
                downloaded_chapter_count=1,
                known_ao3_chapter_count=1,
                downloaded_at="2026-01-01T00:00:00Z",
            ),
            [ReaderChapter(work_id, 1, "One", f"https://archiveofourown.org/works/{work_id}", "chapter-1", "<p>one two three four</p>", "h")],
        )
    result = container.queue_service.save_page_as_evaluation_queue(
        fandom_key=active.fandom_key,
        name="Runner Queue",
        filter_state={"fandom": active.tag, "page": 1},
        source_url="https://example.test",
        work_ids=work_ids,
        page_number=1,
    )
    batch = result.payload["batch"]

    run = container.queue_runner_service.run_batch(batch.id, work_order=["runner-a", "runner-b", "runner-c"])

    assert run.ok
    assert provider.loaded == [("fake-model", 4096)]
    assert provider.unloaded == ["fake-instance"]
    assert provider.evaluated == ["runner-a", "runner-c"]
    rows = {row.work_id: row for row in container.queue_repo.list(batch_id=batch.id)}
    assert rows["runner-a"].queue_status is QueueStatus.DONE
    assert rows["runner-b"].queue_status is QueueStatus.FAILED
    assert rows["runner-c"].queue_status is QueueStatus.DONE
    assert container.evaluation_service.latest_for_work("runner-a").chapter_scope["sampled_words"] == 4
    assert container.evaluation_service.latest_for_work("runner-b") is None
    assert container.evaluation_service.latest_for_work("runner-c").scores["craft"] == 7


def test_active_schema_selection_is_persisted(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    schema = container.schema_service.active_schema()
    schema.schema_key = "alternate"
    schema.name = "Alternate"
    schema.is_active = False
    container.schema_service.save_schema(schema)

    result = container.schema_service.set_active_schema("alternate")

    assert result.ok
    assert container.schema_service.active_schema().schema_key == "alternate"


def test_smart_purge_keeps_all_protected_work_categories(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom"), tag="Fandom", display_name="Fandom")
    container.fandom_service.save_profile(profile)
    ids = ["pinned", "set", "queued", "evaluated", "reading", "favorite", "blocked", "trash"]
    for work_id in ids:
        container.work_repo.upsert(
            Work(
                work_id,
                f"https://archiveofourown.org/works/{work_id}",
                title="Blocked Work" if work_id == "blocked" else work_id,
                summary_text="Blocked summary stays visible." if work_id == "blocked" else "",
                last_scraped_at="2026-01-01T00:00:00Z",
            )
        )
    container.work_library_service.collect("pinned", profile.fandom_key)
    state = {"fandom": "Fandom", "sort_column": "revised_at", "page": 1}
    container.work_set_repo.save(
        WorkSet("set-a", profile.fandom_key, "Set A", state, filter_signature(state), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    container.work_set_repo.record_page("set-a", 1, "https://example.test", ["set"], "2026-01-01T00:00:00Z")
    container.queue_service.enqueue("queued")
    container.evaluation_service.save_manual(
        work_id="evaluated",
        schema_key=container.schema_service.active_schema().schema_key,
        scores={"story_fit": 7, "craft": 7, "emotional_pull": 7},
        status=EvaluationStatus.COMPLETE,
    )
    identity = container.identity_service.bootstrap()
    container.reading_repo.upsert(ReadingState("reading", identity.local_user_id, ReadingStatus.READING))
    container.tag_repo.replace_for_work("favorite", [WorkTag("favorite", TagType.CHARACTER, "Favorite Character")])
    container.work_library_service.favorite_tag(profile.fandom_key, TagType.CHARACTER, "Favorite Character", "#ff66aa")
    container.work_library_service.block_work("blocked", profile.fandom_key)

    result = container.work_library_service.smart_purge_cache()

    assert result.ok
    assert container.work_repo.get("trash") is None
    for work_id in ids[:-1]:
        assert container.work_repo.get(work_id) is not None
    blocked_views = container.work_library_service.standalone_blocked_work_views(fandom_key=profile.fandom_key)
    assert len(blocked_views) == 1
    assert blocked_views[0].work is not None
    assert blocked_views[0].work.title == "Blocked Work"
    assert blocked_views[0].work.summary_text == "Blocked summary stays visible."


class _FakeBrowseClient:
    def __init__(self, work_id: str = "live", *, fail: bool = False) -> None:
        self.work_id = work_id
        self.fail = fail
        self.calls = 0

    def fetch_browse(self, url: str) -> ParsedBrowsePage:
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline")
        work = Work(self.work_id, f"https://archiveofourown.org/works/{self.work_id}", title=self.work_id, last_scraped_at="2026-01-01T00:00:00Z")
        return ParsedBrowsePage(url, [WorkSummary(work)], context_type="fandom", context_key="Fandom", page_number=1, sort_mode="revised_at")


def test_browse_fetch_is_live_first_even_with_exact_cache(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    state = {"fandom": "Fandom", "sort_column": "revised_at", "page": 1}
    url = AO3BrowseService.resolve_fandom_filter_url("Fandom", state)
    container.work_repo.upsert(Work("cached", "https://archiveofourown.org/works/cached", title="cached", last_scraped_at="2026-01-01T00:00:00Z"))
    container.snapshot_repo.add(BrowseSnapshot("snap", url, "fandom", "Fandom", "2026-01-01T00:00:00Z", 1, "revised_at", ["cached"]))
    fake = _FakeBrowseClient("live")
    service = AO3BrowseService(container.work_repo, container.tag_repo, container.snapshot_repo, fake, container.blocked_repo)

    result = service.fetch_fandom("Fandom", state)

    assert result.ok
    assert fake.calls == 1
    assert [work.work_id for work in result.works] == ["live"]


def test_browse_fetch_falls_back_only_to_exact_usable_cache(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    state = {"fandom": "Fandom", "sort_column": "revised_at", "page": 1}
    url = AO3BrowseService.resolve_fandom_filter_url("Fandom", state)
    container.work_repo.upsert(Work("cached", "https://archiveofourown.org/works/cached", title="cached", last_scraped_at="2026-01-01T00:00:00Z"))
    container.snapshot_repo.add(BrowseSnapshot("snap", url, "fandom", "Fandom", "2026-01-01T00:00:00Z", 1, "revised_at", ["cached"]))
    service = AO3BrowseService(container.work_repo, container.tag_repo, container.snapshot_repo, _FakeBrowseClient(fail=True), container.blocked_repo)

    result = service.fetch_fandom("Fandom", state)

    assert result.ok
    assert [work.work_id for work in result.works] == ["cached"]
    assert "showing exact cached page" in result.message


def test_stale_snapshot_with_missing_work_is_not_used_as_cache(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    state = {"fandom": "Fandom", "sort_column": "revised_at", "page": 1}
    url = AO3BrowseService.resolve_fandom_filter_url("Fandom", state)
    container.snapshot_repo.add(BrowseSnapshot("snap", url, "fandom", "Fandom", "2026-01-01T00:00:00Z", 1, "revised_at", ["missing"]))
    service = AO3BrowseService(container.work_repo, container.tag_repo, container.snapshot_repo, _FakeBrowseClient(fail=True), container.blocked_repo)

    result = service.fetch_fandom("Fandom", state)

    assert not result.ok
    assert container.snapshot_repo.latest_for_url(url) is None


def test_style_override_precedence_and_font_wheel_targets_fandom(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom"), tag="Fandom", display_name="Fandom", color="#ff66aa")
    container.fandom_service.save_profile(profile)

    global_style = container.style_service.save_global_settings({"reader_font_size": 18, "font_wheel_step_px": 1.0})
    container.style_service.save_fandom_override(profile.fandom_key, False, {"reader_font_size": 22, "font_wheel_step_px": 0.5})

    assert global_style["reader_font_size"] == 18
    assert container.style_service.effective_settings(profile.fandom_key)["reader_font_size"] == 18

    container.style_service.save_fandom_override(profile.fandom_key, True, {"reader_font_size": 22, "font_wheel_step_px": 0.5})
    assert container.style_service.effective_settings(profile.fandom_key)["reader_font_size"] == 22

    container.style_service.adjust_font_size(profile.fandom_key, 1)

    assert container.style_service.effective_settings(profile.fandom_key)["reader_font_size"] == 22.5
    assert container.style_service.global_settings()["reader_font_size"] == 18


def test_style_override_sections_are_independent_and_font_wheel_respects_font_section(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    profile = FandomProfile(fandom_key=fandom_key("Fandom Sections"), tag="Fandom Sections", display_name="Fandom Sections", color="#58a6ff")
    container.fandom_service.save_profile(profile)

    container.style_service.save_global_settings(
        {
            "preview_font_family": "'Source Code Pro', monospace",
            "reader_font_size": 18,
            "font_wheel_step_px": 1.0,
            "border_thickness": 1,
            "gradient_border_enabled": False,
        }
    )
    container.style_service.save_fandom_override(
        profile.fandom_key,
        True,
        {
            "preview_font_family": "'Recursive', monospace",
            "reader_font_size": 22,
            "font_wheel_step_px": 0.5,
            "border_thickness": 4,
            "gradient_border_enabled": True,
            STYLE_OVERRIDE_SECTIONS_KEY: {"font": True, "rarity": False},
        },
    )

    font_only = container.style_service.effective_settings(profile.fandom_key)
    assert font_only["preview_font_family"] == "'Recursive', monospace"
    assert font_only["reader_font_size"] == 22
    assert font_only["border_thickness"] == 1
    assert font_only["gradient_border_enabled"] is False

    container.style_service.save_fandom_override(
        profile.fandom_key,
        True,
        {
            "preview_font_family": "'Recursive', monospace",
            "reader_font_size": 22,
            "font_wheel_step_px": 0.5,
            "border_thickness": 4,
            "gradient_border_enabled": True,
            STYLE_OVERRIDE_SECTIONS_KEY: {"font": False, "rarity": True},
        },
    )

    rarity_only = container.style_service.effective_settings(profile.fandom_key)
    assert rarity_only["preview_font_family"] == "'Source Code Pro', monospace"
    assert rarity_only["reader_font_size"] == 18
    assert rarity_only["border_thickness"] == 4
    assert rarity_only["gradient_border_enabled"] is True

    container.style_service.adjust_font_size(profile.fandom_key, 1)

    after_global_wheel = container.style_service.effective_settings(profile.fandom_key)
    assert container.style_service.global_settings()["reader_font_size"] == 19
    assert after_global_wheel["reader_font_size"] == 19
    assert after_global_wheel["border_thickness"] == 4
    assert container.style_service.override_sections(container.style_service.fandom_override(profile.fandom_key)) == {"font": False, "rarity": True}


def test_fandom_directory_cache_defaults_incremental_suggestions_and_delete(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")

    sources = container.fandom_service.ensure_fandom_directory_sources()
    by_key = {source.media_key: source for source in sources}
    assert by_key["Movies"].enabled is True
    assert by_key["TV Shows"].enabled is True
    assert by_key["Video Games"].color == "#7ee787"
    assert by_key["Anime *a* Manga"].label == "Anime & Manga"
    assert by_key["Books *a* Literature"].enabled is True
    assert by_key["Cartoons *a* Comics *a* Graphic Novels"].label == "Cartoons & Comics & Graphic Novels"
    assert by_key["Cartoons *a* Comics *a* Graphic Novels"].enabled is True

    container.fandom_repo.cache_directory_fandoms(
        "Video Games",
        [
            FandomSuggestion(
                tag="Life is Strange (Video Games 2015 2017 2024 2026)",
                label="Life is Strange (Video Games 2015 2017 2024 2026)",
                url="https://archiveofourown.org/tags/Life%20is%20Strange%20(Video%20Games%202015%202017%202024%202026)/works",
            ),
            FandomSuggestion(
                tag="Portal",
                label="Portal",
                url="https://archiveofourown.org/tags/Portal/works",
            ),
        ],
    )
    container.fandom_repo.cache_directory_fandoms(
        "Video Games",
        [
            FandomSuggestion(
                tag="Portal",
                label="Portal",
                url="https://archiveofourown.org/tags/Portal/works",
            ),
            FandomSuggestion(
                tag="search",
                label="Tags",
                url="https://archiveofourown.org/tags/search",
            ),
            FandomSuggestion(
                tag="Mass Effect Trilogy",
                label="Mass Effect Trilogy",
                url="https://archiveofourown.org/tags/Mass%20Effect%20Trilogy/works",
            ),
        ],
    )

    suggestions = container.fandom_service.suggest_fandoms("life strange", 10)
    assert len(suggestions) == 1
    assert suggestions[0].tag == "Life is Strange (Video Games 2015 2017 2024 2026)"
    assert suggestions[0].media_label == "Video Games"
    assert suggestions[0].color == "#7ee787"

    assert container.fandom_service.suggest_fandoms("portal", 10)[0].tag == "Portal"
    assert container.fandom_service.suggest_fandoms("search", 10) == []
    assert container.fandom_service.delete_fandom_directory_cache("Video Games").ok
    assert container.fandom_service.suggest_fandoms("portal", 10) == []


def test_fandom_directory_service_caches_selected_sources_with_fake_ao3(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    container.fandom_repo.upsert_directory_source(
        FandomDirectorySource(
            media_key="Custom Type",
            label="Custom Type",
            url="https://archiveofourown.org/media/Custom/fandoms",
            color="#abcdef",
            enabled=True,
        )
    )

    class FakeAO3Client:
        def fetch_media_fandoms(self, media_key: str, label: str, url: str, color: str):
            assert media_key == "Custom Type"
            assert label == "Custom Type"
            assert color == "#abcdef"
            return [
                FandomSuggestion(
                    tag="Custom Fandom",
                    label="Custom Fandom",
                    url="https://archiveofourown.org/tags/Custom%20Fandom/works",
                    media_key=media_key,
                    media_label=label,
                    color=color,
                )
            ]

    container.fandom_service.ao3_client = FakeAO3Client()

    result = container.fandom_service.cache_fandom_directory_sources(["Custom Type"])

    assert result.ok
    [suggestion] = container.fandom_service.suggest_fandoms("custom", 5)
    assert suggestion.tag == "Custom Fandom"
    assert suggestion.media_key == "Custom Type"
    assert suggestion.color == "#abcdef"


def test_left_summary_counts_are_scoped_to_active_fandom(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    life = container.fandom_service.ensure_default()
    titanic = container.fandom_service.save_profile(
        FandomProfile(
            fandom_key=fandom_key("Titanic (1997)"),
            tag="Titanic (1997)",
            display_name="Titanic",
            color="#58a6ff",
        )
    )
    orphan = Work(
        "orphan",
        "https://archiveofourown.org/works/orphan",
        title="Orphan Cache",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    life_work = Work(
        "life-count",
        "https://archiveofourown.org/works/life-count",
        title="Life Count",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    titanic_work = Work(
        "titanic-count",
        "https://archiveofourown.org/works/titanic-count",
        title="Titanic Count",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    for work in [orphan, life_work, titanic_work]:
        container.work_repo.upsert(work)
    container.tag_repo.replace_for_work(life_work.work_id, [WorkTag(life_work.work_id, TagType.FANDOM, life.tag)])
    container.tag_repo.replace_for_work(titanic_work.work_id, [WorkTag(titanic_work.work_id, TagType.FANDOM, titanic.tag)])
    container.work_library_service.collect(life_work.work_id, life.fandom_key)
    container.evaluation_service.save_manual(
        work_id=life_work.work_id,
        schema_key=container.schema_service.active_schema().schema_key,
        scores={"story_fit": 8, "craft": 8, "emotional_pull": 8},
    )
    container.evaluation_service.save_manual(
        work_id=titanic_work.work_id,
        schema_key=container.schema_service.active_schema().schema_key,
        scores={"story_fit": 7, "craft": 7, "emotional_pull": 7},
    )
    container.queue_service.enqueue(titanic_work.work_id, fandom_key_value=titanic.fandom_key)

    assert container.work_library_service.count() == 1
    assert container.work_library_service.cache_count() == 3
    assert container.evaluation_service.count() == 2
    assert len(container.queue_service.list(QueueStatus.QUEUED)) == 1

    assert container.work_library_service.count_for_fandom(life) == 1
    assert container.work_library_service.cache_count_for_fandom(life) == 1
    assert container.evaluation_service.count_for_fandom(life) == 1
    assert container.queue_service.count_for_fandom(life.fandom_key) == 0

    assert container.work_library_service.count_for_fandom(titanic) == 0
    assert container.work_library_service.cache_count_for_fandom(titanic) == 1
    assert container.evaluation_service.count_for_fandom(titanic) == 1
    assert container.queue_service.count_for_fandom(titanic.fandom_key) == 1


def test_rarity_computed_manual_override_and_best_is_manual_only(tmp_path) -> None:
    container = build_container(tmp_path / "ao3.sqlite")
    work = Work(
        "rarity-work",
        "https://archiveofourown.org/works/rarity-work",
        title="Rarity Work",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(work)

    assert not container.rarity_service.has_assigned_rarity(work.work_id)

    container.rarity_service.set_manual(work.work_id, RarityTier.COMMON)
    assert container.rarity_service.has_assigned_rarity(work.work_id)
    container.rarity_service.set_manual(work.work_id, None)
    assert not container.rarity_service.has_assigned_rarity(work.work_id)

    result = container.evaluation_service.save_manual(
        work_id=work.work_id,
        schema_key=container.schema_service.active_schema().schema_key,
        scores={"story_fit": 9, "craft": 9, "emotional_pull": 9},
        status=EvaluationStatus.COMPLETE,
    )

    assert result.ok
    stored = container.rarity_service.get(work.work_id)
    assert stored.computed_quality_score == 9
    assert stored.computed_rarity is RarityTier.LEGENDARY
    assert stored.effective_rarity is RarityTier.LEGENDARY
    assert container.rarity_service.tier_for_quality(10) is RarityTier.LEGENDARY

    container.rarity_service.set_manual(work.work_id, RarityTier.BEST)
    assert container.rarity_service.effective_tier(work.work_id) is RarityTier.BEST

    container.rarity_service.set_manual(work.work_id, None)
    assert container.rarity_service.effective_tier(work.work_id) is RarityTier.LEGENDARY

    common_work = Work(
        "computed-common",
        "https://archiveofourown.org/works/computed-common",
        title="Computed Common",
        last_scraped_at="2026-01-01T00:00:00Z",
    )
    container.work_repo.upsert(common_work)
    result = container.evaluation_service.save_manual(
        work_id=common_work.work_id,
        schema_key=container.schema_service.active_schema().schema_key,
        scores={"story_fit": 1, "craft": 1, "emotional_pull": 1},
        status=EvaluationStatus.COMPLETE,
    )

    assert result.ok
    assert container.rarity_service.get(common_work.work_id).computed_rarity is RarityTier.COMMON
    assert container.rarity_service.has_assigned_rarity(common_work.work_id)
