import json
import sqlite3
from datetime import datetime, timezone

import pytest

from data.db import init_db
from data.feedback import capture_feedback
from data.feedback_export import build_feedback_review_queue, main, write_feedback_review_queue


@pytest.fixture
def feedback_db():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    conn.execute(
        """INSERT INTO tenders
           (identity_key, tender_id, title, raw_text, source_url, source_portal,
            version_fingerprint)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("tender:42", "REF-CURRENT", "Current title", "Current tender text",
         "https://source.example/current", "portal", "current-version"),
    )
    yield conn
    conn.close()


def add_feedback(conn, *, label="relevant", version="feedback-version"):
    return capture_feedback(
        conn,
        tender_identity_key="tender:42",
        tender_version=version,
        manufacturer_id="maker-1",
        label=label,
        reviewer="reviewer@example.com",
        trusted_reviewers={"reviewer@example.com"},
        reason="Reviewed against the listed requirement",
    )


def test_export_uses_the_reviewed_tender_version_and_keeps_provenance(feedback_db):
    feedback_id = add_feedback(feedback_db)
    feedback_db.execute(
        """INSERT INTO tender_versions
           (tender_identity_key, content_fingerprint, snapshot_json, first_seen_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            "tender:42",
            "feedback-version",
            json.dumps({
                "tender_id": "REF-OLD",
                "source_portal": "old-portal",
                "source_url": "https://source.example/version-1",
                "content": {
                    "title": "Reviewed historical tender title",
                    "raw_text": "Reviewed requirement text",
                    "closing_date": "2026-11-30",
                },
            }),
            "2026-10-01T00:00:00+00:00",
            "2026-10-01T00:00:00+00:00",
        ),
    )
    feedback_db.commit()

    queue = build_feedback_review_queue(feedback_db)
    item = queue["items"][0]

    assert queue["eligible_for_metrics"] is False
    assert queue["export_kind"] == "salesperson_feedback_review_queue"
    assert item["feedback_record_id"] == feedback_id
    assert item["tender_reference"] == "REF-OLD"
    assert item["title"] == "Reviewed historical tender title"
    assert item["description"] == "Reviewed requirement text"
    assert item["closing_date"] == "2026-11-30"
    assert item["source_url"] == "https://source.example/version-1"
    assert item["tender_context_status"] == "feedback_version_snapshot"
    assert item["feedback_label"] == "relevant"
    assert item["suggested_evaluation_label"] == "relevant"
    assert item["reviewer"] == "reviewer@example.com"
    assert datetime.fromisoformat(item["reviewed_at"]).tzinfo == timezone.utc
    assert item["review_status"] == "pending_adjudication"


def test_only_direct_feedback_labels_get_suggestions(feedback_db):
    add_feedback(feedback_db, label="worth_pursuing", version="v1")
    add_feedback(feedback_db, label="eligibility_not_met", version="v2")
    add_feedback(feedback_db, label="missing_technical_evidence", version="v3")

    items = build_feedback_review_queue(feedback_db)["items"]

    assert [item["suggested_evaluation_label"] for item in items] == [
        None,
        None,
        "insufficient_information",
    ]
    assert all(item["tender_context_status"] == "current_tender_fallback" for item in items)
    assert all(item["closing_date"] is None for item in items)


def test_export_is_private_and_refuses_to_overwrite_existing_file(feedback_db, tmp_path):
    add_feedback(feedback_db)
    output = tmp_path / "review-queue.json"

    assert write_feedback_review_queue(feedback_db, output) == 1
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["eligible_for_metrics"] is False
    with pytest.raises(FileExistsError):
        write_feedback_review_queue(feedback_db, output)


def test_export_cli_writes_review_queue_and_reports_metric_gate(feedback_db, tmp_path, monkeypatch, capsys):
    add_feedback(feedback_db, label="worth_pursuing")
    monkeypatch.setattr("data.feedback_export.get_connection", lambda: feedback_db)
    output = tmp_path / "review-queue.json"

    assert main(["--output", str(output)]) == 0
    assert "not eligible for metrics" in capsys.readouterr().out
    assert json.loads(output.read_text())["items"][0]["suggested_evaluation_label"] is None
