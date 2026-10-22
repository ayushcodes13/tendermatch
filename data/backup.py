"""Create and restore integrity-checked SQLite snapshots for TenderMatch."""

from __future__ import annotations

import argparse
from contextlib import closing
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


def restore_database(
    backup: str | Path, destination: str | Path, *, replace: bool = False
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

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.", suffix=".tmp", dir=destination_path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        _snapshot(backup_path, temporary_path)
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

    args = parser.parse_args()
    if args.command == "backup":
        backup_database(args.database, args.snapshot)
        print("SQLite backup created; integrity check passed.")
    else:
        restore_database(args.snapshot, args.database, replace=args.replace)
        print("SQLite restore completed; integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
