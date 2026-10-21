import sqlite3
import threading
from datetime import datetime, timezone, timedelta

from data.db import init_db, is_already_emailed, upsert_or_get_tender
from digest.outbox import (
    deliver_batch,
    deliver_due_batches,
    due_batch_ids,
    notification_exists,
    recipient_has_notification,
    queue_digest,
)


def make_db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    return conn


def make_tender(conn):
    tender, _ = upsert_or_get_tender(conn, {
        "tender_id": "REF-OUTBOX-1",
        "title": "Supply of a spectrometer",
        "organization": "Research Institute",
        "published_date": "2026-10-21",
        "closing_date": "2026-11-01",
        "source_url": "https://portal.example/tender/REF-OUTBOX-1",
        "source_portal": "cppp",
        "raw_text": "Supply of a spectrometer",
    })
    return tender


def test_digest_is_persisted_before_smtp_and_failure_retries_with_backoff(capsys):
    conn = make_db()
    tender = make_tender(conn)
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    batch_id = queue_digest(
        conn, "sales@example.com", "Tender digest", "body", [tender], now=now
    )
    observed = {}

    def failing_sender(subject, body, recipient):
        observed["state_during_send"] = conn.execute(
            "SELECT state FROM email_batches WHERE id=?", (batch_id,)
        ).fetchone()[0]
        raise RuntimeError("sensitive transport detail must not be persisted")

    assert not deliver_batch(conn, batch_id, failing_sender, now=now)
    batch = conn.execute(
        "SELECT state, attempt_count, last_error_type, next_attempt_at FROM email_batches WHERE id=?",
        (batch_id,),
    ).fetchone()
    notification = conn.execute(
        "SELECT state, attempt_count FROM email_notifications WHERE batch_id=?", (batch_id,)
    ).fetchone()

    assert observed["state_during_send"] == "sending"
    assert batch == ("failed", 1, "RuntimeError", "2026-10-21T12:30:00Z")
    assert notification == ("failed", 1)
    assert not is_already_emailed(conn, tender["identity_key"])
    assert "sensitive transport detail" not in capsys.readouterr().out
    assert due_batch_ids(conn, now=now + timedelta(minutes=29)) == []
    assert due_batch_ids(conn, now=now + timedelta(minutes=30)) == [batch_id]

    sent = []
    results = deliver_due_batches(
        conn,
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
        now=now + timedelta(minutes=30),
    )

    assert results == [(batch_id, True)]
    assert sent == [("Tender digest", "body", "sales@example.com")]
    assert is_already_emailed(conn, tender["identity_key"])
    assert conn.execute(
        "SELECT state, attempt_count FROM email_notifications WHERE batch_id=?", (batch_id,)
    ).fetchone() == ("sent", 2)


def test_same_tender_version_is_idempotent_but_new_version_can_be_notified():
    conn = make_db()
    tender = make_tender(conn)
    first = queue_digest(conn, "sales@example.com", "Subject", "Body", [tender])

    assert first is not None
    assert queue_digest(conn, "sales@example.com", "Subject", "Body", [tender]) is None
    assert notification_exists(conn, "sales@example.com", tender)

    revised = {**tender, "raw_text": "Revised technical specification"}
    second = queue_digest(conn, "sales@example.com", "Subject", "Body", [revised])

    assert second is not None and second != first
    assert conn.execute("SELECT COUNT(*) FROM email_batches").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM email_notifications").fetchone()[0] == 2


def test_stale_sending_attempt_is_retried_after_process_interruption():
    conn = make_db()
    tender = make_tender(conn)
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    batch_id = queue_digest(conn, "sales@example.com", "Subject", "Body", [tender], now=now)
    conn.execute(
        "UPDATE email_batches SET state='sending', attempt_count=1, updated_at=? WHERE id=?",
        ("2026-10-21T11:40:00Z", batch_id),
    )
    conn.execute(
        "UPDATE email_notifications SET state='sending', attempt_count=1 WHERE batch_id=?",
        (batch_id,),
    )
    conn.commit()

    assert due_batch_ids(conn, now=now) == [batch_id]
    assert deliver_due_batches(conn, lambda *args: None, now=now) == [(batch_id, True)]


def test_outbox_batch_survives_database_reopen_after_interrupted_send(tmp_path):
    database_path = tmp_path / "tenders.sqlite3"
    conn = sqlite3.connect(database_path)
    init_db(conn)
    tender = make_tender(conn)
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    batch_id = queue_digest(conn, "sales@example.com", "Subject", "Stored body", [tender], now=now)
    conn.execute(
        "UPDATE email_batches SET state='sending', attempt_count=1, updated_at=? WHERE id=?",
        ("2026-10-21T11:40:00Z", batch_id),
    )
    conn.commit()
    conn.close()

    recovered = sqlite3.connect(database_path)
    init_db(recovered)
    sent = []
    results = deliver_due_batches(
        recovered,
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
        now=now,
    )

    assert results == [(batch_id, True)]
    assert sent == [("Subject", "Stored body", "sales@example.com")]
    assert recovered.execute(
        "SELECT state FROM email_batches WHERE id=?", (batch_id,)
    ).fetchone()[0] == "sent"
    recovered.close()


def test_concurrent_queueing_creates_one_batch_with_valid_notification_links(tmp_path):
    database_path = tmp_path / "concurrent-queue.sqlite3"
    setup = sqlite3.connect(database_path)
    init_db(setup)
    tender = make_tender(setup)
    setup.commit()
    setup.close()

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def queue():
        conn = sqlite3.connect(database_path, timeout=10)
        try:
            barrier.wait(timeout=5)
            results.append(queue_digest(conn, "sales@example.com", "Subject", "Body", [tender]))
        except Exception as exc:  # surfaced as an assertion in the parent thread
            errors.append(exc)
        finally:
            conn.close()

    workers = [threading.Thread(target=queue) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert not errors
    assert all(not worker.is_alive() for worker in workers)
    assert len([batch_id for batch_id in results if batch_id is not None]) == 1
    check = sqlite3.connect(database_path)
    assert check.execute("SELECT COUNT(*) FROM email_batches").fetchone()[0] == 1
    assert check.execute("SELECT COUNT(*) FROM email_notifications").fetchone()[0] == 1
    assert check.execute(
        "SELECT COUNT(*) FROM email_notifications n JOIN email_batches b ON b.id=n.batch_id"
    ).fetchone()[0] == 1
    check.close()


def test_concurrent_delivery_claims_batch_only_once(tmp_path):
    database_path = tmp_path / "concurrent-send.sqlite3"
    setup = sqlite3.connect(database_path)
    init_db(setup)
    tender = make_tender(setup)
    batch_id = queue_digest(setup, "sales@example.com", "Subject", "Body", [tender])
    setup.close()

    entered_sender = threading.Event()
    release_sender = threading.Event()
    sends = []
    results = []
    errors = []

    def sender(*args):
        sends.append(args)
        entered_sender.set()
        assert release_sender.wait(timeout=5)

    def first_delivery():
        conn = sqlite3.connect(database_path, timeout=10)
        try:
            results.append(deliver_batch(conn, batch_id, sender))
        except Exception as exc:
            errors.append(exc)
        finally:
            conn.close()

    first = threading.Thread(target=first_delivery)
    first.start()
    assert entered_sender.wait(timeout=5)
    second_conn = sqlite3.connect(database_path, timeout=10)
    second_result = deliver_batch(second_conn, batch_id, sender)
    second_conn.close()
    release_sender.set()
    first.join(timeout=10)

    assert not errors
    assert not first.is_alive()
    assert second_result is False
    assert results == [True]
    assert sends == [("Subject", "Body", "sales@example.com")]


def test_recipient_delivery_history_is_scoped_per_recipient():
    conn = make_db()
    tender = make_tender(conn)
    batch_id = queue_digest(conn, "first@example.com", "Subject", "Body", [tender])

    assert recipient_has_notification(conn, "first@example.com", tender["identity_key"])
    assert not recipient_has_notification(conn, "second@example.com", tender["identity_key"])
    assert batch_id is not None
