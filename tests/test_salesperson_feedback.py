import sqlite3
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from data.db import init_db
from data.feedback import capture_feedback, main


REVIEWERS = {"Sales.Reviewer@example.com"}


@pytest.fixture
def feedback_db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


def test_captures_feedback_with_reviewer_timestamp_and_tender_version(feedback_db):
    feedback_id = capture_feedback(
        feedback_db,
        tender_identity_key="tender:42",
        tender_version="sha256:abc",
        manufacturer_id="maker-1",
        label="relevant",
        reviewer="sales.reviewer@example.com",
        trusted_reviewers=REVIEWERS,
        reason="Technical fit looks promising",
    )

    row = feedback_db.execute(
        "SELECT id, tender_identity_key, tender_version, manufacturer_id, label, reason, reviewer, reviewed_at "
        "FROM salesperson_feedback"
    ).fetchone()
    assert feedback_id == 1
    assert row[:7] == (
        1,
        "tender:42",
        "sha256:abc",
        "maker-1",
        "relevant",
        "Technical fit looks promising",
        "Sales.Reviewer@example.com",
    )
    timestamp = datetime.fromisoformat(row[7])
    assert timestamp.tzinfo == timezone.utc


def test_feedback_is_append_only_and_new_labels_preserve_history(feedback_db):
    common = dict(
        tender_identity_key="tender:42",
        manufacturer_id="maker-1",
        reviewer="Sales.Reviewer@example.com",
        trusted_reviewers=REVIEWERS,
    )
    capture_feedback(feedback_db, label="relevant", **common)
    capture_feedback(feedback_db, label="already_known", **common)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        feedback_db.execute("UPDATE salesperson_feedback SET label='not_relevant' WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        feedback_db.execute("DELETE FROM salesperson_feedback WHERE id=1")
    assert feedback_db.execute("SELECT label FROM salesperson_feedback ORDER BY id").fetchall() == [
        ("relevant",),
        ("already_known",),
    ]


@pytest.mark.parametrize(
    "overrides, exception, message",
    [
        ({"reviewer": "outsider@example.com"}, PermissionError, "not in"),
        ({"label": "invented"}, ValueError, "unsupported"),
        ({"tender_identity_key": "  "}, ValueError, "identity"),
        ({"reason": "x" * 1001}, ValueError, "characters or fewer"),
    ],
)
def test_rejects_untrusted_or_invalid_feedback(feedback_db, overrides, exception, message):
    values = {
        "tender_identity_key": "tender:42",
        "manufacturer_id": "maker-1",
        "label": "relevant",
        "reviewer": "Sales.Reviewer@example.com",
        "trusted_reviewers": REVIEWERS,
        "reason": None,
    }
    values.update(overrides)
    with pytest.raises(exception, match=message):
        capture_feedback(feedback_db, **values)
    assert feedback_db.execute("SELECT COUNT(*) FROM salesperson_feedback").fetchone()[0] == 0


def test_cli_uses_configured_reviewer_allowlist_and_persistent_connection(feedback_db, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(FEEDBACK_REVIEWERS=REVIEWERS))
    monkeypatch.setattr("data.feedback.get_connection", lambda: feedback_db)

    result = main([
        "--tender-identity-key", "tender:42",
        "--tender-version", "v1",
        "--manufacturer-id", "maker-1",
        "--label", "wrong_manufacturer",
        "--reviewer", "Sales.Reviewer@example.com",
        "--reason", "Another profile is a better fit",
    ])

    assert result == 0
    assert "Recorded feedback #1 (wrong_manufacturer)" in capsys.readouterr().out


def test_cli_requires_a_configured_reviewer_allowlist(feedback_db, monkeypatch):
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(FEEDBACK_REVIEWERS=frozenset()))
    with pytest.raises(SystemExit) as exc:
        main([
            "--tender-identity-key", "tender:42",
            "--manufacturer-id", "maker-1",
            "--label", "relevant",
            "--reviewer", "Sales.Reviewer@example.com",
        ])
    assert exc.value.code == 2
    assert feedback_db.execute("SELECT COUNT(*) FROM salesperson_feedback").fetchone()[0] == 0
