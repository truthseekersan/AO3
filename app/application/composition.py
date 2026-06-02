from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.application.services import (
    AdminRemoteService,
    AO3BrowseService,
    AO3WorkFetchService,
    EvaluationQueueService,
    QueueEvaluationRunnerService,
    EvaluationService,
    FandomService,
    IdentityService,
    LocalModelService,
    MergeService,
    ModeService,
    PreferencesService,
    RarityService,
    ReaderService,
    SchemaService,
    SharedOverlayService,
    StyleService,
    SyncService,
    WorkLibraryService,
)
from app.infrastructure.ao3.client import AO3Client
from app.infrastructure.lmstudio import LMStudioEvaluationProvider
from app.infrastructure.remote_stub.client import RemoteStubClient
from app.infrastructure.sqlite.database import SQLiteDatabase
from app.infrastructure.sqlite.repositories import (
    SQLiteBlockedAuthorRepository,
    SQLiteBlockedTagRepository,
    SQLiteBlockedWorkRepository,
    SQLiteBrowseSnapshotRepository,
    SQLiteCharacterProfileRepository,
    SQLiteEvaluationBatchRepository,
    SQLiteEvaluationQueueRepository,
    SQLiteEvaluationRepository,
    SQLiteEvaluationSchemaRepository,
    SQLiteFandomRepository,
    SQLiteFandomStyleRepository,
    SQLiteFandomTagCatalogRepository,
    SQLiteFavoriteTagRepository,
    SQLiteIdentityRepository,
    SQLiteRarityRepository,
    SQLiteReaderAssetRepository,
    SQLiteReadingStateRepository,
    SQLiteSettingsRepository,
    SQLiteSharedOverlayRepository,
    SQLiteSyncRepository,
    SQLiteTagColorRepository,
    SQLiteTagRepository,
    SQLiteWorkCollectionRepository,
    SQLiteWorkRepository,
    SQLiteWorkSetRepository,
)


@dataclass(slots=True)
class ApplicationContainer:
    db: SQLiteDatabase
    settings_repo: SQLiteSettingsRepository
    identity_repo: SQLiteIdentityRepository
    work_repo: SQLiteWorkRepository
    tag_repo: SQLiteTagRepository
    snapshot_repo: SQLiteBrowseSnapshotRepository
    evaluation_repo: SQLiteEvaluationRepository
    batch_repo: SQLiteEvaluationBatchRepository
    queue_repo: SQLiteEvaluationQueueRepository
    schema_repo: SQLiteEvaluationSchemaRepository
    reading_repo: SQLiteReadingStateRepository
    reader_asset_repo: SQLiteReaderAssetRepository
    sync_repo: SQLiteSyncRepository
    overlay_repo: SQLiteSharedOverlayRepository
    fandom_repo: SQLiteFandomRepository
    character_repo: SQLiteCharacterProfileRepository
    collection_repo: SQLiteWorkCollectionRepository
    blocked_repo: SQLiteBlockedWorkRepository
    blocked_author_repo: SQLiteBlockedAuthorRepository
    blocked_tag_repo: SQLiteBlockedTagRepository
    tag_catalog_repo: SQLiteFandomTagCatalogRepository
    fandom_style_repo: SQLiteFandomStyleRepository
    work_set_repo: SQLiteWorkSetRepository
    favorite_tag_repo: SQLiteFavoriteTagRepository
    tag_color_repo: SQLiteTagColorRepository
    rarity_repo: SQLiteRarityRepository
    identity_service: IdentityService
    mode_service: ModeService
    preferences_service: PreferencesService
    fandom_service: FandomService
    style_service: StyleService
    rarity_service: RarityService
    schema_service: SchemaService
    evaluation_service: EvaluationService
    queue_service: EvaluationQueueService
    queue_runner_service: QueueEvaluationRunnerService
    browse_service: AO3BrowseService
    work_fetch_service: AO3WorkFetchService
    reader_service: ReaderService
    work_library_service: WorkLibraryService
    shared_overlay_service: SharedOverlayService
    sync_service: SyncService
    merge_service: MergeService
    admin_service: AdminRemoteService
    lmstudio_provider: LMStudioEvaluationProvider
    local_model_service: LocalModelService


def build_container(database_path: Path | None = None) -> ApplicationContainer:
    db = SQLiteDatabase(database_path)
    settings_repo = SQLiteSettingsRepository(db)
    identity_repo = SQLiteIdentityRepository(db, settings_repo)
    work_repo = SQLiteWorkRepository(db)
    tag_repo = SQLiteTagRepository(db)
    snapshot_repo = SQLiteBrowseSnapshotRepository(db)
    evaluation_repo = SQLiteEvaluationRepository(db)
    batch_repo = SQLiteEvaluationBatchRepository(db)
    queue_repo = SQLiteEvaluationQueueRepository(db)
    schema_repo = SQLiteEvaluationSchemaRepository(db)
    reading_repo = SQLiteReadingStateRepository(db)
    reader_asset_repo = SQLiteReaderAssetRepository(db)
    sync_repo = SQLiteSyncRepository(db)
    overlay_repo = SQLiteSharedOverlayRepository(db)
    fandom_repo = SQLiteFandomRepository(db)
    character_repo = SQLiteCharacterProfileRepository(db)
    collection_repo = SQLiteWorkCollectionRepository(db)
    blocked_repo = SQLiteBlockedWorkRepository(db)
    blocked_author_repo = SQLiteBlockedAuthorRepository(db)
    blocked_tag_repo = SQLiteBlockedTagRepository(db)
    tag_catalog_repo = SQLiteFandomTagCatalogRepository(db)
    fandom_style_repo = SQLiteFandomStyleRepository(db)
    work_set_repo = SQLiteWorkSetRepository(db)
    favorite_tag_repo = SQLiteFavoriteTagRepository(db)
    tag_color_repo = SQLiteTagColorRepository(db)
    rarity_repo = SQLiteRarityRepository(db)
    ao3_client = AO3Client()
    remote_client = RemoteStubClient()
    lmstudio_provider = LMStudioEvaluationProvider(settings_repo)

    identity_service = IdentityService(identity_repo)
    mode_service = ModeService(settings_repo, identity_repo)
    preferences_service = PreferencesService(settings_repo)
    fandom_service = FandomService(fandom_repo, character_repo, tag_catalog_repo, settings_repo, ao3_client)
    style_service = StyleService(settings_repo, fandom_style_repo)
    rarity_service = RarityService(rarity_repo, identity_repo, style_service)
    schema_service = SchemaService(schema_repo)
    evaluation_service = EvaluationService(
        evaluation_repo,
        schema_repo,
        identity_repo,
        work_repo,
        tag_repo,
        model_provider=lmstudio_provider,
        rarity_service=rarity_service,
    )
    queue_service = EvaluationQueueService(
        queue_repo,
        batch_repo,
        work_set_repo,
        work_repo,
        tag_repo,
        evaluation_repo,
        schema_repo,
        reading_repo,
        identity_repo,
        fandom_repo,
    )
    work_library_service = WorkLibraryService(
        work_repo,
        tag_repo,
        collection_repo,
        blocked_repo,
        blocked_author_repo,
        blocked_tag_repo,
        work_set_repo,
        favorite_tag_repo,
        tag_color_repo,
        snapshot_repo,
        settings_repo,
        reading_repo,
        identity_repo,
    )
    shared_overlay_service = SharedOverlayService(overlay_repo)
    browse_service = AO3BrowseService(work_repo, tag_repo, snapshot_repo, ao3_client, blocked_repo, blocked_author_repo, blocked_tag_repo)
    work_fetch_service = AO3WorkFetchService(work_repo, tag_repo, ao3_client)
    reader_service = ReaderService(work_repo, reader_asset_repo, reading_repo, identity_repo, ao3_client)
    sync_service = SyncService(mode_service, overlay_repo, sync_repo, remote_client)
    merge_service = MergeService(work_repo, evaluation_repo, overlay_repo, identity_repo, mode_service)
    admin_service = AdminRemoteService(mode_service, remote_client)
    local_model_service = LocalModelService(settings_repo, lmstudio_provider)
    queue_runner_service = QueueEvaluationRunnerService(
        settings=settings_repo,
        queue_service=queue_service,
        reader_service=reader_service,
        evaluation_service=evaluation_service,
        local_model_service=local_model_service,
        queue=queue_repo,
        batches=batch_repo,
        work_sets=work_set_repo,
        works=work_repo,
        tags=tag_repo,
        evaluations=evaluation_repo,
        identities=identity_repo,
    )

    identity_service.bootstrap()
    fandom_service.ensure_default()
    schema_service.ensure_default_schema()

    return ApplicationContainer(
        db=db,
        settings_repo=settings_repo,
        identity_repo=identity_repo,
        work_repo=work_repo,
        tag_repo=tag_repo,
        snapshot_repo=snapshot_repo,
        evaluation_repo=evaluation_repo,
        batch_repo=batch_repo,
        queue_repo=queue_repo,
        schema_repo=schema_repo,
        reading_repo=reading_repo,
        reader_asset_repo=reader_asset_repo,
        sync_repo=sync_repo,
        overlay_repo=overlay_repo,
        fandom_repo=fandom_repo,
        character_repo=character_repo,
        collection_repo=collection_repo,
        blocked_repo=blocked_repo,
        blocked_author_repo=blocked_author_repo,
        blocked_tag_repo=blocked_tag_repo,
        tag_catalog_repo=tag_catalog_repo,
        fandom_style_repo=fandom_style_repo,
        work_set_repo=work_set_repo,
        favorite_tag_repo=favorite_tag_repo,
        tag_color_repo=tag_color_repo,
        rarity_repo=rarity_repo,
        identity_service=identity_service,
        mode_service=mode_service,
        preferences_service=preferences_service,
        fandom_service=fandom_service,
        style_service=style_service,
        rarity_service=rarity_service,
        schema_service=schema_service,
        evaluation_service=evaluation_service,
        queue_service=queue_service,
        queue_runner_service=queue_runner_service,
        browse_service=browse_service,
        work_fetch_service=work_fetch_service,
        reader_service=reader_service,
        work_library_service=work_library_service,
        shared_overlay_service=shared_overlay_service,
        sync_service=sync_service,
        merge_service=merge_service,
        admin_service=admin_service,
        lmstudio_provider=lmstudio_provider,
        local_model_service=local_model_service,
    )
