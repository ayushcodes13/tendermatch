"""Tests for durable SQLite persistence, schema verification, maintenance locks, and reversible migration."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import stat
import time

from cryptography.fernet import Fernet
import pytest

from data.backup import (
    MaintenanceLock,
    backup_database,
    is_maintenance_active,
    prune_old_backups,
    restore_database,
    verify_schema_compatibility,
)
from data.cache_encryption import encrypt_database
from data.db import init_db
from deploy.migrate_cache_to_durable import (
    get_table_counts,
    migrate_to_durable_volume,
    rollback_migration,
)
from digest.outbox import deliver_due_batches
import scheduler


def _populate_tendermatch_database(path: Path) -> dict:
    conn = sqlite3.connect(path)
    init_db(conn)

    # Insert sample records across all core tables
    conn.execute(
        """INSERT INTO tenders
           (tender_id, content_hash, identity_key, title, organization, published_date, closing_date, raw_text)
           VALUES ('T-1', 'hash-1', 'key-1', 'Test Tender', 'Org-1', '2026-10-22', '2026-11-01', 'Test')"""
    )
    conn.execute(
        """INSERT INTO tender_versions
           (tender_identity_key, content_fingerprint, snapshot_json, first_seen_at, last_seen_at)
           VALUES ('key-1', 'fp-1', '{"title": "Test Tender"}', '2026-10-22T00:00:00Z', '2026-10-22T00:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO tender_amendments
           (tender_identity_key, from_fingerprint, to_fingerprint, change_status, change_types_json, evidence_json, observed_at)
           VALUES ('key-1', 'fp-0', 'fp-1', 'meaningful', '["deadline"]', '{"deadline": "new"}', '2026-10-22T00:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO salesperson_feedback
           (tender_identity_key, manufacturer_id, label, reviewer, reviewed_at)
           VALUES ('key-1', 'mfg-1', 'relevant', 'sales@example.com', '2026-10-22T00:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO email_batches
           (digest_key, recipient, subject, body, state, created_at, updated_at)
           VALUES ('digest-1', 'sales@example.com', 'Subject 1', 'Body 1', 'pending', '2026-10-22T00:00:00Z', '2026-10-22T00:00:00Z')"""
    )
    batch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        """INSERT INTO email_notifications
           (batch_id, recipient, tender_identity_key, tender_version, notification_type, state, created_at, updated_at)
           VALUES (?, 'sales@example.com', 'key-1', 'fp-1', 'new_opportunity', 'pending', '2026-10-22T00:00:00Z', '2026-10-22T00:00:00Z')""",
        (batch_id,),
    )
    conn.execute(
        """INSERT INTO pipeline_runs
           (run_id, status, started_at, completed_at, duration_seconds)
           VALUES ('run-100', 'completed', '2026-10-22T00:00:00Z', '2026-10-22T00:00:10Z', 10.0)"""
    )
    conn.commit()
    counts = get_table_counts(conn)
    conn.close()
    return counts


def test_schema_compatibility_verification(tmp_path):
    valid_db = tmp_path / "valid.sqlite3"
    _populate_tendermatch_database(valid_db)
    assert verify_schema_compatibility(valid_db) is True

    incomplete_db = tmp_path / "incomplete.sqlite3"
    conn = sqlite3.connect(incomplete_db)
    conn.execute("CREATE TABLE tenders (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="missing required table"):
        verify_schema_compatibility(incomplete_db)


def test_maintenance_lock_pauses_scheduler(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "tenders.sqlite3"
    _populate_tendermatch_database(db_path)
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    executed = []
    monkeypatch.setattr(scheduler, "run_pipeline", lambda: executed.append("ran"))

    # When no maintenance is active, scheduler step runs
    assert is_maintenance_active(db_path) is False
    assert scheduler.run_scheduler_step() is True
    assert executed == ["ran"]

    # When maintenance lock is held, scheduler step pauses
    with MaintenanceLock(db_path):
        assert is_maintenance_active(db_path) is True
        assert scheduler.run_scheduler_step() is False
        assert executed == ["ran"]  # pipeline was not run

    out = capsys.readouterr().out
    assert "Maintenance in progress" in out
    assert is_maintenance_active(db_path) is False


def test_prune_old_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create 8 backup files with ascending timestamps
    created = []
    for i in range(8):
        f = backup_dir / f"backup_{i}.sqlite3"
        f.write_text("data")
        # Ensure distinct modification times
        os.utime(f, (1000 + i * 10, 1000 + i * 10))
        created.append(f)

    pruned = prune_old_backups(backup_dir, keep_count=5)
    assert len(pruned) == 3
    remaining = sorted(p.name for p in backup_dir.glob("*.sqlite3"))
    assert len(remaining) == 5
    # The 5 newest (index 3 to 7) remain
    assert remaining == [f"backup_{i}.sqlite3" for i in range(3, 8)]


def test_restore_database_with_verify_schema(tmp_path):
    valid_db = tmp_path / "valid.sqlite3"
    _populate_tendermatch_database(valid_db)
    snapshot = tmp_path / "snapshot.sqlite3"
    backup_database(valid_db, snapshot)

    restored = tmp_path / "restored.sqlite3"
    restore_database(snapshot, restored, verify_schema=True)
    assert restored.exists()
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600

    # Test restoring non-TenderMatch database with verify_schema=True
    arbitrary_db = tmp_path / "arbitrary.sqlite3"
    conn = sqlite3.connect(arbitrary_db)
    conn.execute("CREATE TABLE foo (bar TEXT)")
    conn.commit()
    conn.close()
    arbitrary_snapshot = tmp_path / "arbitrary_snapshot.sqlite3"
    backup_database(arbitrary_db, arbitrary_snapshot)

    arbitrary_target = tmp_path / "arbitrary_target.sqlite3"
    with pytest.raises(ValueError, match="missing required table"):
        restore_database(arbitrary_snapshot, arbitrary_target, verify_schema=True)
    assert not arbitrary_target.exists()


def test_migration_from_cache_to_durable_volume(tmp_path):
    key = Fernet.generate_key()
    source_db = tmp_path / "source.sqlite3"
    expected_counts = _populate_tendermatch_database(source_db)

    # Encrypt source database as if it were Actions cache
    encrypted_cache = tmp_path / "tenders.db.enc"
    encrypt_database(source_db, encrypted_cache, key=key)

    durable_dir = tmp_path / "var_lib_tendermatch"
    durable_dir.mkdir()
    durable_db = durable_dir / "tenders.db"

    # Pre-existing database on durable volume to verify rollback creation
    _populate_tendermatch_database(durable_db)

    result = migrate_to_durable_volume(
        encrypted_cache,
        durable_db,
        key=key,
    )
    assert result["status"] == "success"
    assert result["rollback_snapshot"] is not None
    assert Path(result["rollback_snapshot"]).exists()

    with sqlite3.connect(f"{durable_db.as_uri()}?mode=ro", uri=True) as conn:
        dest_counts = get_table_counts(conn)
    assert dest_counts == expected_counts
    assert stat.S_IMODE(durable_db.stat().st_mode) == 0o600


def test_migration_failure_triggers_automatic_rollback(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    durable_db = tmp_path / "durable.sqlite3"
    original_counts = _populate_tendermatch_database(durable_db)

    # 1. Invalid source cache is rejected before modifying target
    corrupt_cache = tmp_path / "corrupt.db.enc"
    corrupt_cache.write_bytes(b"not-encrypted-data")

    with pytest.raises(RuntimeError, match="Source snapshot validation failed before migration"):
        migrate_to_durable_volume(corrupt_cache, durable_db, key=key)

    with sqlite3.connect(f"{durable_db.as_uri()}?mode=ro", uri=True) as conn:
        assert get_table_counts(conn) == original_counts

    # 2. Simulated reconciliation failure during migration triggers automatic rollback
    source_db = tmp_path / "valid_source.sqlite3"
    _populate_tendermatch_database(source_db)
    valid_cache = tmp_path / "valid.db.enc"
    encrypt_database(source_db, valid_cache, key=key)

    # Monkeypatch get_table_counts on destination connection to simulate a mismatch
    import deploy.migrate_cache_to_durable as mig_mod
    orig_get_counts = mig_mod.get_table_counts
    call_count = [0]

    def failing_get_counts(conn):
        call_count[0] += 1
        counts = orig_get_counts(conn)
        # On second call (destination check), return corrupted count
        if call_count[0] > 1:
            counts["tenders"] = -999
        return counts

    monkeypatch.setattr(mig_mod, "get_table_counts", failing_get_counts)

    with pytest.raises(RuntimeError, match="Migration failed and was rolled back"):
        migrate_to_durable_volume(valid_cache, durable_db, key=key)

    # Verify destination was safely restored to original counts
    with sqlite3.connect(f"{durable_db.as_uri()}?mode=ro", uri=True) as conn:
        assert orig_get_counts(conn) == original_counts


def test_recovery_of_pending_notifications_after_restore(tmp_path):
    db_path = tmp_path / "outbox.sqlite3"
    _populate_tendermatch_database(db_path)

    # Snapshot and restore to a fresh environment
    snapshot = tmp_path / "outbox_snapshot.sqlite3"
    backup_database(db_path, snapshot)

    restored_db = tmp_path / "fresh_outbox.sqlite3"
    restore_database(snapshot, restored_db, verify_schema=True)

    sent_emails = []

    def mock_send_email(subject, body, recipient):
        sent_emails.append((subject, body, recipient))

    with sqlite3.connect(restored_db) as conn:
        results = deliver_due_batches(conn, mock_send_email)
        assert len(results) == 1
        batch_id, success = results[0]
        assert success is True
        # Verify batch state transitioned to sent
        batch_state = conn.execute(
            "SELECT state FROM email_batches WHERE id=?", (batch_id,)
        ).fetchone()[0]
        assert batch_state == "sent"

    assert len(sent_emails) == 1
    assert sent_emails[0][0] == "Subject 1"
    assert sent_emails[0][2] == "sales@example.com"
