import os
import sqlite3
import stat

import pytest
from cryptography.fernet import Fernet

from data.cache_encryption import decrypt_database, encrypt_database
from data.db import init_db


def _create_database(path):
    with sqlite3.connect(path) as connection:
        init_db(connection)
        connection.execute(
            """INSERT INTO salesperson_feedback
               (tender_identity_key, manufacturer_id, label, reason, reviewer, reviewed_at)
               VALUES ('tender-1', 'maker-1', 'relevant', 'confidential reason',
                       'reviewer@example.test', '2026-10-22T00:00:00Z')"""
        )
        connection.execute(
            """INSERT INTO email_batches
               (digest_key, recipient, subject, body, state, created_at, updated_at)
               VALUES ('digest-1', 'recipient@example.test', 'subject', 'private body',
                       'pending', '2026-10-22T00:00:00Z', '2026-10-22T00:00:00Z')"""
        )


def _sensitive_values(path):
    with sqlite3.connect(path) as connection:
        return (
            connection.execute("SELECT reviewer, reason FROM salesperson_feedback").fetchone(),
            connection.execute("SELECT recipient, body FROM email_batches").fetchone(),
        )


def test_encrypted_cache_hides_sensitive_rows_and_restores_integrity(tmp_path):
    database = tmp_path / "tenders.db"
    cache = tmp_path / "tenders.db.enc"
    restored = tmp_path / "restored.db"
    key = Fernet.generate_key()
    _create_database(database)

    encrypt_database(database, cache, key)
    ciphertext = cache.read_bytes()

    assert b"reviewer@example.test" not in ciphertext
    assert b"confidential reason" not in ciphertext
    assert b"recipient@example.test" not in ciphertext
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600

    decrypt_database(cache, restored, key)
    assert _sensitive_values(restored) == _sensitive_values(database)


def test_wrong_key_or_corrupt_ciphertext_never_restores_plaintext(tmp_path):
    database = tmp_path / "tenders.db"
    cache = tmp_path / "tenders.db.enc"
    restored = tmp_path / "restored.db"
    key = Fernet.generate_key()
    _create_database(database)
    encrypt_database(database, cache, key)

    with pytest.raises(ValueError, match="failed authentication"):
        decrypt_database(cache, restored, Fernet.generate_key())
    assert not restored.exists()

    cache.write_bytes(cache.read_bytes()[:-8] + os.urandom(8))
    with pytest.raises(ValueError, match="failed authentication"):
        decrypt_database(cache, restored, key)
    assert not restored.exists()


def test_restore_refuses_to_replace_existing_database(tmp_path):
    database = tmp_path / "tenders.db"
    cache = tmp_path / "tenders.db.enc"
    destination = tmp_path / "existing.db"
    _create_database(database)
    _create_database(destination)
    encrypt_database(database, cache, Fernet.generate_key())

    with pytest.raises(FileExistsError, match="refusing to replace"):
        decrypt_database(cache, destination, Fernet.generate_key())
