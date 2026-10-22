import os
import subprocess
import sqlite3
import stat
from pathlib import Path
import sys

import pytest

from data.backup import backup_database, restore_database


def _create_database(path, rows=("original",)):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS records (value TEXT NOT NULL)")
        conn.executemany("INSERT INTO records(value) VALUES (?)", [(row,) for row in rows])


def _rows(path):
    with sqlite3.connect(path) as conn:
        return [row[0] for row in conn.execute("SELECT value FROM records ORDER BY rowid")]


def test_backup_captures_committed_wal_data_and_is_private(tmp_path):
    database = tmp_path / "tenders.sqlite3"
    backup = tmp_path / "backups" / "tenders.sqlite3"
    backup.parent.mkdir()
    _create_database(database)

    writer = sqlite3.connect(database)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("INSERT INTO records(value) VALUES ('wal-committed')")
    writer.commit()

    assert backup_database(database, backup) == backup.resolve()
    assert _rows(backup) == ["original", "wal-committed"]
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    writer.close()


def test_backup_refuses_missing_same_and_existing_paths(tmp_path):
    database = tmp_path / "tenders.sqlite3"
    _create_database(database)
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "missing.sqlite3", tmp_path / "backup.sqlite3")
    with pytest.raises(ValueError, match="differ"):
        backup_database(database, database)
    existing = tmp_path / "existing.sqlite3"
    _create_database(existing, rows=("keep",))
    with pytest.raises(FileExistsError, match="already exists"):
        backup_database(database, existing)
    assert _rows(existing) == ["keep"]


def test_backup_rejects_corrupt_source_and_leaves_no_partial_snapshot(tmp_path):
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not a sqlite database")
    backup = tmp_path / "backup.sqlite3"

    with pytest.raises(sqlite3.DatabaseError):
        backup_database(corrupt, backup)
    assert not backup.exists()
    assert list(tmp_path.glob(".backup.sqlite3.*.tmp")) == []


def test_restore_is_atomic_private_and_requires_explicit_replace(tmp_path):
    database = tmp_path / "tenders.sqlite3"
    backup = tmp_path / "snapshot.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    _create_database(database, rows=("snapshot-value",))
    backup_database(database, backup)

    assert restore_database(backup, restored) == restored.resolve()
    assert _rows(restored) == ["snapshot-value"]
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600

    _create_database(restored, rows=("existing-value",))
    with pytest.raises(FileExistsError, match="replace=True"):
        restore_database(backup, restored)
    assert _rows(restored) == ["snapshot-value", "existing-value"]

    restore_database(backup, restored, replace=True)
    assert _rows(restored) == ["snapshot-value"]


def test_restore_rejects_corrupt_backup_and_same_source_destination(tmp_path):
    backup = tmp_path / "corrupt.sqlite3"
    backup.write_bytes(b"not a sqlite database")
    destination = tmp_path / "restored.sqlite3"

    with pytest.raises(sqlite3.DatabaseError):
        restore_database(backup, destination)
    assert not destination.exists()
    with pytest.raises(ValueError, match="differ"):
        restore_database(backup, backup)


def test_restore_refuses_destination_with_wal_sidecars(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    _create_database(source)
    _create_database(destination)
    backup_database(source, backup)
    Path(f"{destination}-wal").write_bytes(b"active wal marker")

    with pytest.raises(RuntimeError, match="WAL sidecars"):
        restore_database(backup, destination, replace=True)
    assert _rows(destination) == ["original"]


@pytest.mark.skipif(os.name != "posix", reason="owner-only SQLite file mode is POSIX-specific")
def test_restore_replace_publishes_owner_only_file(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    target = tmp_path / "target.sqlite3"
    _create_database(source)
    backup_database(source, backup)
    _create_database(target, rows=("old",))

    restore_database(backup, target, replace=True)

    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_backup_and_restore_cli_round_trip(tmp_path):
    source = tmp_path / "source.sqlite3"
    snapshot = tmp_path / "snapshot.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    _create_database(source, rows=("cli-value",))

    backup_result = subprocess.run(
        [sys.executable, "-m", "data.backup", "backup", str(source), str(snapshot)],
        check=True,
        capture_output=True,
        text=True,
    )
    restore_result = subprocess.run(
        [sys.executable, "-m", "data.backup", "restore", str(snapshot), str(restored)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "integrity check passed" in backup_result.stdout
    assert "integrity check passed" in restore_result.stdout
    assert _rows(restored) == ["cli-value"]
