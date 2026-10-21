"""SQLite-backed, retryable email delivery for TenderMatch digests."""

import hashlib
import json
from datetime import datetime, timedelta, timezone


NEW_OPPORTUNITY = "new_opportunity"
SENDING_RECOVERY_MINUTES = 15
MAX_RETRY_MINUTES = 24 * 60


def _timestamp(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tender_version(tender):
    """Return a deterministic fingerprint for the tender fields used in email."""
    version_fields = {
        key: tender.get(key)
        for key in (
            "title", "organization", "published_date", "updated_date",
            "corrigendum_date", "closing_date", "source_url", "raw_text",
        )
    }
    payload = json.dumps(version_fields, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def notification_exists(conn, recipient, tender, notification_type=NEW_OPPORTUNITY):
    cursor = conn.execute(
        """SELECT 1 FROM email_notifications
           WHERE recipient=? AND tender_identity_key=? AND tender_version=?
             AND notification_type=? LIMIT 1""",
        (recipient, tender["identity_key"], tender_version(tender), notification_type),
    )
    return cursor.fetchone() is not None


def recipient_has_notification(conn, recipient, identity_key):
    cursor = conn.execute(
        """SELECT 1 FROM email_notifications
           WHERE recipient=? AND tender_identity_key=? LIMIT 1""",
        (recipient, identity_key),
    )
    return cursor.fetchone() is not None


def queue_digest(conn, recipient, subject, body, tenders, now=None):
    """Persist the exact email and its tender associations before SMTP delivery."""
    timestamp = _timestamp(now)
    # Lock before checking uniqueness so concurrent callers cannot both decide
    # that the same recipient/tender/version is eligible.
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    eligible = [
        tender for tender in tenders
        if not notification_exists(conn, recipient, tender)
    ]
    if not eligible:
        conn.commit()
        return None

    notification_refs = sorted(
        f"{tender['identity_key']}:{tender_version(tender)}" for tender in eligible
    )
    digest_key = hashlib.sha256(
        f"{recipient}\0{subject}\0{body}\0{json.dumps(notification_refs)}".encode("utf-8")
    ).hexdigest()
    batch_cursor = conn.execute(
        """INSERT OR IGNORE INTO email_batches
           (digest_key, recipient, subject, body, state, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
        (digest_key, recipient, subject, body, timestamp, timestamp),
    )
    created_batch = batch_cursor.rowcount == 1
    batch_id = conn.execute(
        "SELECT id FROM email_batches WHERE digest_key=?", (digest_key,)
    ).fetchone()[0]

    inserted = 0
    for tender in eligible:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO email_notifications
               (batch_id, recipient, tender_identity_key, tender_version,
                notification_type, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (
                batch_id, recipient, tender["identity_key"], tender_version(tender),
                NEW_OPPORTUNITY, timestamp, timestamp,
            ),
        )
        inserted += cursor.rowcount

    if inserted == 0:
        if created_batch:
            conn.execute("DELETE FROM email_batches WHERE id=?", (batch_id,))
        conn.commit()
        return None

    conn.commit()
    return batch_id


def _set_batch_state(conn, batch_id, state, *, now, error_type=None, next_attempt_at=None):
    timestamp = _timestamp(now)
    sent_at = timestamp if state == "sent" else None
    conn.execute(
        """UPDATE email_batches SET state=?, updated_at=?, sent_at=?,
           last_error_type=?, next_attempt_at=? WHERE id=?""",
        (state, timestamp, sent_at, error_type, next_attempt_at, batch_id),
    )
    conn.execute(
        """UPDATE email_notifications SET state=?, updated_at=?, sent_at=?
           WHERE batch_id=?""",
        (state, timestamp, sent_at, batch_id),
    )


def deliver_batch(conn, batch_id, send_email, now=None):
    """Attempt one persisted batch, recording state before and after SMTP."""
    now = now or datetime.now(timezone.utc)
    timestamp = _timestamp(now)
    stale_sending = _timestamp(now - timedelta(minutes=SENDING_RECOVERY_MINUTES))
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    batch = conn.execute(
        """SELECT recipient, subject, body, state, attempt_count,
                  next_attempt_at, updated_at
           FROM email_batches WHERE id=?""",
        (batch_id,),
    ).fetchone()
    if batch is None:
        conn.commit()
        return False

    state, next_attempt_at, updated_at = batch[3], batch[5], batch[6]
    if state == "sent":
        conn.commit()
        return True
    if state == "sending" and updated_at > stale_sending:
        conn.commit()
        return False
    if state == "failed" and (not next_attempt_at or next_attempt_at > timestamp):
        conn.commit()
        return False
    if state not in {"pending", "failed", "sending"}:
        conn.commit()
        return False

    recipient, subject, body, _, previous_attempts, _, _ = batch
    attempt_count = previous_attempts + 1
    conn.execute(
        "UPDATE email_batches SET state='sending', attempt_count=?, updated_at=?, "
        "next_attempt_at=NULL, last_error_type=NULL WHERE id=?",
        (attempt_count, timestamp, batch_id),
    )
    conn.execute(
        "UPDATE email_notifications SET state='sending', attempt_count=?, updated_at=? WHERE batch_id=?",
        (attempt_count, timestamp, batch_id),
    )
    conn.commit()

    try:
        send_email(subject, body, recipient)
    except Exception as exc:
        retry_minutes = min(30 * (2 ** min(attempt_count - 1, 10)), MAX_RETRY_MINUTES)
        retry_at = now + timedelta(minutes=retry_minutes)
        _set_batch_state(
            conn, batch_id, "failed", now=now,
            error_type=type(exc).__name__, next_attempt_at=_timestamp(retry_at),
        )
        conn.execute(
            "UPDATE email_batches SET next_attempt_at=? WHERE id=?",
            (_timestamp(retry_at), batch_id),
        )
        conn.commit()
        print(
            f"[EMAIL OUTBOX] Batch {batch_id} failed ({type(exc).__name__}); "
            f"retry scheduled in {retry_minutes} minutes."
        )
        return False

    _set_batch_state(conn, batch_id, "sent", now=now)
    conn.execute(
        """UPDATE tenders SET emailed=1
           WHERE identity_key IN (
               SELECT tender_identity_key FROM email_notifications WHERE batch_id=?
           )""",
        (batch_id,),
    )
    conn.commit()
    return True


def due_batch_ids(conn, now=None):
    now = now or datetime.now(timezone.utc)
    timestamp = _timestamp(now)
    stale_sending = _timestamp(now - timedelta(minutes=SENDING_RECOVERY_MINUTES))
    rows = conn.execute(
        """SELECT id FROM email_batches
           WHERE (state='pending')
              OR (state='failed' AND next_attempt_at<=?)
              OR (state='sending' AND updated_at<=?)
           ORDER BY id""",
        (timestamp, stale_sending),
    ).fetchall()
    return [row[0] for row in rows]


def deliver_due_batches(conn, send_email, now=None):
    """Retry queued or due notifications, including stale in-progress attempts."""
    return [
        (batch_id, deliver_batch(conn, batch_id, send_email, now=now))
        for batch_id in due_batch_ids(conn, now=now)
    ]
