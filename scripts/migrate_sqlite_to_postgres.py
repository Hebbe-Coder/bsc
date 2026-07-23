"""CLI entry point for the guarded BSC SQLite to PostgreSQL migration."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.sqlite_postgres_migration import (
    SQLitePostgresMigrationError,
    migrate_sqlite_to_postgres,
    write_migration_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate durable BSC SQLite data into PostgreSQL safely.")
    parser.add_argument("--source", required=True, help="Path to the SQLite database file")
    parser.add_argument("--target-url", default=os.getenv("DB_URL", ""), help="PostgreSQL DB_URL")
    parser.add_argument("--backup-dir", default="", help="Directory for the pre-migration SQLite backup")
    parser.add_argument("--report", required=True, help="Path for the JSON migration report")
    parser.add_argument("--apply", action="store_true", help="Perform the copy; omitted means dry run")
    parser.add_argument("--allow-nonempty-target", action="store_true", help="Allow additive retry into an existing target")
    args = parser.parse_args()

    try:
        report = migrate_sqlite_to_postgres(
            args.source,
            args.target_url,
            apply=args.apply,
            backup_dir=args.backup_dir or None,
            allow_nonempty_target=args.allow_nonempty_target,
        )
        report_path = write_migration_report(report, Path(args.report))
    except SQLitePostgresMigrationError as exc:
        parser.error(str(exc))
    print(f"migration_report={report_path}")
    print(f"applied={report.applied} tables={len(report.migrated_tables)} skipped={len(report.skipped_source_tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
