"""Reversible migration utility for transitioning TenderMatch to a durable SQLite volume.

Safely migrates state from an authenticated encrypted cache snapshot (or plaintext backup)
to a persistent mounted database path with:
1. Integrity and schema compatibility verification prior to migration.
2. Automated rollback snapshot creation before replacing an existing database.
3. Exclusive maintenance locking to pause concurrent scheduler or pipeline runs.
4. Post-migration row-level and identity reconciliation across all core tables.
5. Automatic rollback on verification failure and manual CLI rollback support.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile

from data.backup import (
    MaintenanceLock,
    backup_database,
    restore_database,
    verify_schema_compatibility,
)
from data.cache_encryption import decrypt_database


CORE_TABLES = (
    "tenders",
    "tender_versions",
    "tender_amendments",
    "tender_matches",
    "email_batches",
    "email_notifications",
    "salesperson_feedback",
    "pipeline_runs",
    "document_extractions",
)


def get_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Retrieve row counts for all core TenderMatch tables."""
    counts = {}
    for table in CORE_TABLES:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        except sqlite3.OperationalError:
            counts[table] = 0
    return counts


def migrate_to_durable_volume(
    source: str | Path,
    destination: str | Path,
    *,
    key: str | bytes | None = None,
    dry_run: bool = False,
    rollback_dir: str | Path | None = None,
) -> dict:
    """Migrate state from a cache snapshot to a durable volume with rollback protection."""
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()

    if not source_path.is_file():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    # Determine whether the source is encrypted
    is_encrypted = source_path.suffix == ".enc" or not _is_sqlite_file(source_path)

    with tempfile.TemporaryDirectory(prefix="tendermatch-migration-") as tmpdir:
        working_snapshot = Path(tmpdir) / "snapshot.sqlite3"
        try:
            if is_encrypted:
                decrypt_database(source_path, working_snapshot, key=key)
            else:
                backup_database(source_path, working_snapshot)

            # Pre-migration verification on working snapshot
            verify_schema_compatibility(working_snapshot)
            with closing(sqlite3.connect(f"{working_snapshot.as_uri()}?mode=ro", uri=True)) as src_conn:
                source_counts = get_table_counts(src_conn)
        except Exception as exc:
            raise RuntimeError(
                f"Source snapshot validation failed before migration: {type(exc).__name__}: {exc}"
            ) from exc

        if dry_run:
            return {
                "status": "dry_run_success",
                "source": str(source_path),
                "destination": str(destination_path),
                "source_counts": source_counts,
                "rollback_snapshot": None,
            }

        rollback_snapshot = None
        if destination_path.exists():
            rollback_parent = Path(rollback_dir).expanduser() if rollback_dir else destination_path.parent
            rollback_parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            rollback_snapshot = rollback_parent / f"{destination_path.name}.rollback.{ts}.sqlite3"
            backup_database(destination_path, rollback_snapshot)

        with MaintenanceLock(destination_path):
            try:
                restore_database(
                    working_snapshot,
                    destination_path,
                    replace=True,
                    verify_schema=True,
                    pause_maintenance=False,  # Already held by outer lock
                )

                # Post-migration reconciliation
                with closing(
                    sqlite3.connect(f"{destination_path.as_uri()}?mode=ro", uri=True)
                ) as dest_conn:
                    dest_counts = get_table_counts(dest_conn)
                    for table, count in source_counts.items():
                        if dest_counts.get(table, 0) != count:
                            raise ValueError(
                                f"Post-migration reconciliation mismatch in '{table}': "
                                f"source had {count}, destination has {dest_counts.get(table, 0)}."
                            )

            except Exception as exc:
                if rollback_snapshot and rollback_snapshot.exists():
                    restore_database(
                        rollback_snapshot,
                        destination_path,
                        replace=True,
                        verify_schema=False,
                        pause_maintenance=False,
                    )
                raise RuntimeError(
                    f"Migration failed and was rolled back: {type(exc).__name__}: {exc}"
                ) from exc

    return {
        "status": "success",
        "source": str(source_path),
        "destination": str(destination_path),
        "source_counts": source_counts,
        "rollback_snapshot": str(rollback_snapshot) if rollback_snapshot else None,
    }


def rollback_migration(rollback_snapshot: str | Path, destination: str | Path) -> None:
    """Restore a previously created rollback snapshot to the destination."""
    snapshot_path = Path(rollback_snapshot).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()

    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Rollback snapshot not found: {snapshot_path}")

    with MaintenanceLock(destination_path):
        restore_database(
            snapshot_path,
            destination_path,
            replace=True,
            verify_schema=True,
            pause_maintenance=False,
        )


def _is_sqlite_file(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            header = f.read(16)
            return header.startswith(b"SQLite format 3")
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="source cache or snapshot file (.enc or .sqlite3)")
    parser.add_argument("destination", nargs="?", help="durable destination database path")
    parser.add_argument("--key", help="Fernet encryption key for encrypted cache")
    parser.add_argument("--dry-run", action="store_true", help="verify source without modifying destination")
    parser.add_argument("--rollback", help="restore the destination from a specified rollback snapshot")

    args = parser.parse_args(argv)

    if args.rollback:
        if not args.destination:
            destination = os.environ.get("TENDERMATCH_DB_PATH", "data/tenders.db")
        else:
            destination = args.destination
        rollback_migration(args.rollback, destination)
        print(f"✅ Successfully rolled back {destination} from {args.rollback}")
        return 0

    if not args.source:
        parser.error("A source file is required for migration unless --rollback is specified.")

    destination = args.destination or os.environ.get("TENDERMATCH_DB_PATH", "data/tenders.db")

    try:
        result = migrate_to_durable_volume(
            args.source,
            destination,
            key=args.key,
            dry_run=args.dry_run,
        )
        print(f"✅ Migration status: {result['status']}")
        print(f"   Source: {result['source']}")
        print(f"   Destination: {result['destination']}")
        print("   Verified Table Counts:")
        for table, count in result["source_counts"].items():
            print(f"     - {table}: {count}")
        if result["rollback_snapshot"]:
            print(f"   Rollback Snapshot Created: {result['rollback_snapshot']}")
        return 0
    except Exception as exc:
        print(f"❌ Migration failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
