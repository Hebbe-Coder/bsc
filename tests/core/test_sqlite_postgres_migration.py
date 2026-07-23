from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from uuid import uuid4
from urllib.parse import urlencode

import pytest

from app.core.database import SQLiteBackend, init_database
from app.core.sqlite_postgres_migration import (
    SQLitePostgresMigrationError,
    migrate_sqlite_to_postgres,
    write_migration_report,
)
from app.knowledge.growth_repository import GrowthRepository
from app.knowledge.wiki_contracts import SourceRecord, SourceStatus


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL is required")
def test_migrates_sqlite_runtime_rows_with_backup_and_report(tmp_path: Path):
    psycopg2 = pytest.importorskip("psycopg2")
    source_path = tmp_path / "runtime.sqlite"
    source_backend = SQLiteBackend(str(source_path))
    init_database(source_backend)
    source_repository = GrowthRepository(backend=source_backend)
    project_id = f"migration-{uuid4().hex[:10]}"
    source_repository.configure_vault(project_id, f"projects/{project_id}", "migration-test")
    source_repository.create_source(
        SourceRecord(
            id=f"source-{project_id}",
            project_id=project_id,
            source_type="migration-test",
            content_hash="a" * 64,
            raw_content="Durable evidence survives the database cutover.",
            trust_level="trusted",
            status=SourceStatus.ELIGIBLE,
        )
    )
    source_repository.close()

    schema = f"migration_{uuid4().hex[:16]}"
    base_url = os.environ["TEST_POSTGRES_URL"]
    target_url = _schema_url(base_url, schema)
    with psycopg2.connect(base_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA "{schema}"')
    try:
        dry_run = migrate_sqlite_to_postgres(source_path, target_url)
        assert dry_run.applied is False
        assert any(item.table == "knowledge_sources" and item.source_rows == 1 for item in dry_run.migrated_tables)

        report = migrate_sqlite_to_postgres(
            source_path,
            target_url,
            apply=True,
            backup_dir=tmp_path / "backups",
        )
        assert report.applied is True
        assert report.backup_path and Path(report.backup_path).is_file()
        backup_connection = sqlite3.connect(report.backup_path)
        try:
            assert backup_connection.execute("SELECT COUNT(*) FROM knowledge_sources").fetchone()[0] == 1
        finally:
            backup_connection.close()
        assert "schema_migrations" in report.skipped_source_tables
        assert any(item.table == "knowledge_sources" and item.target_rows == 1 for item in report.migrated_tables)

        report_path = write_migration_report(report, tmp_path / "migration-report.json")
        assert '"applied": true' in report_path.read_text(encoding="utf-8")

        with pytest.raises(SQLitePostgresMigrationError, match="already contains"):
            migrate_sqlite_to_postgres(source_path, target_url, apply=True)
    finally:
        with psycopg2.connect(base_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def _schema_url(base_url: str, schema: str) -> str:
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'options': f'-csearch_path={schema}'})}"
