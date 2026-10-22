"""Create and restore integrity-checked SQLite snapshots for TenderMatch."""

from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timezone
import os
import sqlite3
import tempfile
from pathlib import Path


def _database_path(value: str | Path, *, must_exist: bool) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise ValueError("Database paths must not be symbolic links.")
    if must_exist and not path.is_file():
        raise FileNotFoundError("The database file does not exist or is not a regular file.")
    if not must_exist and not path.parent.is_dir():
        raise FileNotFoundError("The destination directory does not exist.")
    return path.resolve(strict=must_exist)


def _open_existing(path: Path) -> sqlite3.Connection:
    # mode=rw prevents SQLite from silently creating an empty source database.
    uri = f"{path.as_uri()}?mode=rw"
    return sqlite3.connect(uri, uri=True, timeout=30)


def _integrity_check(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise sqlite3.DatabaseError("SQLite integrity check failed.")


def _require_private_file_permissions() -> None:
    if os.name != "posix":
        raise OSError("SQLite backups require a POSIX filesystem for owner-only file permissions.")


def _fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _snapshot(source: Path, temporary_destination: Path) -> None:
    with closing(_open_existing(source)) as source_conn:
        with closing(sqlite3.connect(temporary_destination, timeout=30)) as destination_conn:
            source_conn.backup(destination_conn, pages=256, sleep=0.01)
            _integrity_check(destination_conn)
            destination_conn.commit()
    os.chmod(temporary_destination, 0o600)
    with temporary_destination.open("rb") as snapshot_file:
        os.fsync(snapshot_file.fileno())


def backup_database(source: str | Path, destination: str | Path) -> Path:
    """Write an atomic, owner-readable SQLite snapshot; refuse to overwrite."""
    _require_private_file_permissions()
    source_path = _database_path(source, must_exist=True)
    destination_path = _database_path(destination, must_exist=False)
    if source_path == destination_path:
        raise ValueError("The backup destination must differ from the source database.")
    if destination_path.exists():
        raise FileExistsError("The backup destination already exists; choose a new path.")

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.", suffix=".tmp", dir=destination_path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        _snapshot(source_path, temporary_path)
        # link() is an atomic no-clobber publish because temp and destination
        # are in the same directory. It also avoids replacing a path created
        # concurrently after the initial existence check.
        os.link(temporary_path, destination_path)
        temporary_path.unlink()
        _fsync_directory(destination_path.parent)
        return destination_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


REQUIRED_SCHEMA_TABLES = (
    "tenders",
    "tender_versions",
    "tender_amendments",
    "tender_matches",
    "email_batches",
    "email_notifications",
    "salesperson_feedback",
    "pipeline_runs",
)


def verify_schema_compatibility(conn_or_path: sqlite3.Connection | str | Path) -> bool:
    """Validate that the SQLite database contains all required TenderMatch core tables."""
    if isinstance(conn_or_path, (str, Path)):
        path = _database_path(conn_or_path, must_exist=True)
        with closing(_open_existing(path)) as conn:
            return verify_schema_compatibility(conn)

    cursor = conn_or_path.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    existing_tables = {row[0] for row in cursor.fetchall()}
    missing = [table for table in REQUIRED_SCHEMA_TABLES if table not in existing_tables]
    if missing:
        raise ValueError(
            f"Database schema compatibility check failed: missing required table(s): {', '.join(sorted(missing))}."
        )
    return True


class MaintenanceLock:
    """Context manager acquiring an exclusive maintenance lock during restore/migration."""

    def __init__(self, database_path: str | Path, timeout_seconds: int = 300):
        self.database_path = Path(database_path).expanduser()
        self.lock_path = Path(f"{self.database_path}.maintenance")
        self.timeout_seconds = timeout_seconds
        self._acquired = False

    def __enter__(self):
        if self.lock_path.exists():
            try:
                mtime = self.lock_path.stat().st_mtime
                if (datetime.now(timezone.utc).timestamp() - mtime) > self.timeout_seconds:
                    self.lock_path.unlink(missing_ok=True)
                else:
                    raise RuntimeError(
                        f"Maintenance lock active at {self.lock_path}; restore/migration already in progress."
                    )
            except FileNotFoundError:
                pass

        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self.lock_path, flags, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(f"pid={os.getpid()}\ntimestamp={datetime.now(timezone.utc).isoformat()}\n")
            self._acquired = True
        except FileExistsError:
            raise RuntimeError(
                f"Maintenance lock active at {self.lock_path}; restore/migration already in progress."
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._acquired:
            self.lock_path.unlink(missing_ok=True)


def is_maintenance_active(database_path: str | Path, timeout_seconds: int = 300) -> bool:
    """Return True if a maintenance lock exists for the specified database and is fresh."""
    path = Path(database_path).expanduser()
    lock_path = Path(f"{path}.maintenance")
    if not lock_path.exists():
        return False
    try:
        mtime = lock_path.stat().st_mtime
        if (datetime.now(timezone.utc).timestamp() - mtime) > timeout_seconds:
            # Stale lock
            return False
        return True
    except FileNotFoundError:
        return False


def prune_old_backups(
    directory: str | Path, pattern: str = "*.sqlite3", keep_count: int = 7
) -> list[Path]:
    """Prune old backups in a directory, keeping the newest keep_count snapshots."""
    dir_path = Path(directory).expanduser()
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Backup directory not found: {dir_path}")
    backups = sorted(
        [p for p in dir_path.glob(pattern) if p.is_file() and not p.name.startswith(".")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    pruned = []
    for old_backup in backups[keep_count:]:
        old_backup.unlink()
        pruned.append(old_backup)
    if pruned:
        _fsync_directory(dir_path)
    return pruned


def restore_database(
    backup: str | Path,
    destination: str | Path,
    *,
    replace: bool = False,
    verify_schema: bool = False,
    pause_maintenance: bool = True,
) -> Path:
    """Restore an integrity-checked snapshot atomically to a SQLite path."""
    _require_private_file_permissions()
    backup_path = _database_path(backup, must_exist=True)
    destination_path = _database_path(destination, must_exist=False)
    if backup_path == destination_path:
        raise ValueError("The restore destination must differ from the backup file.")
    if destination_path.exists() and not replace:
        raise FileExistsError("The restore destination exists; pass replace=True to replace it.")
    if destination_path.exists() and any(
        Path(f"{destination_path}{suffix}").exists() for suffix in ("-wal", "-shm")
    ):
        raise RuntimeError(
            "The destination has SQLite WAL sidecars; stop all database users and "
            "checkpoint or remove stale sidecars before restoring."
        )

    lock_ctx = MaintenanceLock(destination_path) if pause_maintenance else nullcontext()
    with lock_ctx:
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.", suffix=".tmp", dir=destination_path.parent
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        try:
            os.chmod(temporary_path, 0o600)
            _snapshot(backup_path, temporary_path)
            if verify_schema:
                verify_schema_compatibility(temporary_path)
            if replace:
                os.replace(temporary_path, destination_path)
            else:
                os.link(temporary_path, destination_path)
                temporary_path.unlink()
            _fsync_directory(destination_path.parent)
            return destination_path
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup", help="create an SQLite snapshot")
    backup_parser.add_argument("database", help="existing TenderMatch SQLite database")
    backup_parser.add_argument("snapshot", help="new snapshot path in a protected directory")

    restore_parser = subparsers.add_parser("restore", help="restore an SQLite snapshot")
    restore_parser.add_argument("snapshot", help="integrity-checked SQLite snapshot")
    restore_parser.add_argument("database", help="restore destination database path")
    restore_parser.add_argument(
        "--replace", action="store_true", help="replace an existing destination database"
    )
    restore_parser.add_argument(
        "--verify-schema",
        action="store_true",
        help="verify TenderMatch core tables before completing restore",
    )

    prune_parser = subparsers.add_parser("prune", help="prune old backups keeping newest N snapshots")
    prune_parser.add_argument("directory", help="directory containing backups")
    prune_parser.add_argument(
        "--keep", type=int, default=7, help="number of snapshots to retain (default: 7)"
    )

    args = parser.parse_args()
    if args.command == "backup":
        backup_database(args.database, args.snapshot)
        print("SQLite backup created; integrity check passed.")
    elif args.command == "restore":
        restore_database(
            args.snapshot,
            args.database,
            replace=args.replace,
            verify_schema=args.verify_schema,
        )
        print("SQLite restore completed; integrity check passed.")
    elif args.command == "prune":
        pruned = prune_old_backups(args.directory, keep_count=args.keep)
        print(f"Pruned {len(pruned)} old backup snapshot(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
