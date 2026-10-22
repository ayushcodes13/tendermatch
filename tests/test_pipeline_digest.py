from datetime import date, timedelta
import json
import sqlite3
import sys
from types import ModuleType


def install_import_stub(module_name, **attributes):
    if module_name not in sys.modules:
        try:
            __import__(module_name)
        except ImportError:
            module = ModuleType(module_name)
            for name, value in attributes.items():
                setattr(module, name, value)
            sys.modules[module_name] = module


install_import_stub("dotenv", load_dotenv=lambda: None)
install_import_stub("bs4", BeautifulSoup=object)
install_import_stub("sentence_transformers", SentenceTransformer=object)

import pipeline.run as pipeline
from data.db import init_db, upsert_or_get_tender
from digest.outbox import queue_digest


class EmptyMatcher:
    def match_topk(self, tender, top_k=5):
        return []


def test_pipeline_generates_digest_with_its_statistics_schema(monkeypatch):
    sent = {}
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(":memory:"))
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [{
        "tender_id": "T-1",
        "title": "Supply of a spectrometer",
        "organization": "Research Institute",
        "published_date": "2026-10-21",
        "source_portal": "unknown",
        "raw_text": "Supply of a spectrometer",
    }])
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda tender, max_age_hours: True)
    monkeypatch.setattr(pipeline, "classify_tender", lambda tender, manufacturer_candidates: {
        "is_blocked": False,
        "has_signal": True,
        "category": "high_signal",
        "decision": "high_signal",
        "score": 80,
        "reason": "test fixture",
    })
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(
        pipeline,
        "send_email",
        lambda subject, body, recipient: sent.update(
            subject=subject, body=body, recipient=recipient
        ),
    )

    pipeline.run_pipeline()

    assert sent["recipient"] == "sales@example.com"
    assert sent["subject"] == "Tender Intelligence Report | 1 High-Signal Opportunity"
    assert "Total scraped: 1" in sent["body"]
    assert "Fresh tenders processed: 1" in sent["body"]
    assert "High-signal opportunities: 1" in sent["body"]


def test_pipeline_reports_missing_recipient_without_attempting_email(
    monkeypatch, tmp_path, capsys
):
    database_path = tmp_path / "missing-recipient.sqlite3"
    today = date.today().isoformat()
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [{
        "tender_id": "REF-MISSING-RECIPIENT",
        "title": "Relevant procurement",
        "organization": "Research Institute",
        "published_date": today,
        "source_portal": "cppp",
        "raw_text": "New procurement",
    }])
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda *args, **kwargs: True)
    monkeypatch.setattr(pipeline, "classify_tender", lambda *args, **kwargs: {
        "is_blocked": False,
        "has_signal": True,
        "category": "high_signal",
        "decision": "high_signal",
        "score": 80,
        "reason": "controlled missing-recipient fixture",
    })
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "")
    monkeypatch.setattr(
        pipeline,
        "send_email",
        lambda *args: (_ for _ in ()).throw(AssertionError("email must not be sent")),
    )

    pipeline.run_pipeline()

    output = capsys.readouterr().out
    assert "Cannot queue a new digest: RECEIVER_EMAIL is missing." in output
    conn = sqlite3.connect(database_path)
    summary_json = conn.execute(
        "SELECT summary_json FROM pipeline_runs"
    ).fetchone()[0]
    conn.close()
    assert json.loads(summary_json)["email_delivery"] == "skipped_missing_recipient"


def test_pipeline_digest_reports_counts_for_mixed_tender_outcomes(monkeypatch, tmp_path, capsys):
    database_path = tmp_path / "mixed-digest.sqlite3"
    sent = []
    today = date.today().isoformat()
    stale_date = (date.today() - timedelta(days=90)).isoformat()
    previously_notified = {
        "tender_id": "REF-PREVIOUSLY-EMAILED",
        "title": "Previously notified tender",
        "organization": "Research Institute",
        "published_date": today,
        "source_portal": "cppp",
        "raw_text": "Existing opportunity",
    }

    seed = sqlite3.connect(database_path)
    init_db(seed)
    saved, _ = upsert_or_get_tender(seed, previously_notified)
    batch_id = queue_digest(
        seed, "sales@example.com", "Previous digest", "Previous body", [saved]
    )
    seed.execute("UPDATE email_batches SET state='sent' WHERE id=?", (batch_id,))
    seed.execute(
        "UPDATE email_notifications SET state='sent' WHERE batch_id=?", (batch_id,)
    )
    seed.commit()
    seed.close()

    tenders = [
        previously_notified,
        {
            "tender_id": "REF-STALE",
            "title": "Stale tender",
            "organization": "Research Institute",
            "published_date": stale_date,
            "source_portal": "cppp",
            "raw_text": "Old opportunity",
        },
        {
            "tender_id": "REF-EXPIRED",
            "title": "Expired tender",
            "organization": "Research Institute",
            "published_date": today,
            "closing_date": (date.today() - timedelta(days=1)).isoformat(),
            "source_portal": "cppp",
            "raw_text": "Expired opportunity",
        },
        {
            "tender_id": "REF-HIGH",
            "title": "High-signal tender",
            "organization": "Research Institute",
            "published_date": today,
            "source_portal": "cppp",
            "raw_text": "New opportunity",
        },
        {
            "tender_id": "REF-HIGH",
            "title": "High-signal tender",
            "organization": "Research Institute",
            "published_date": today,
            "source_portal": "cppp",
            "raw_text": "New opportunity",
        },
        {
            "tender_id": "REF-EXPLORE",
            "title": "Exploration tender",
            "organization": "Research Institute",
            "published_date": today,
            "source_portal": "cppp",
            "raw_text": "Potential opportunity",
        },
        {
            "tender_id": "REF-BLOCKED",
            "title": "Blocked tender",
            "organization": "Research Institute",
            "published_date": today,
            "source_portal": "cppp",
            "raw_text": "Irrelevant opportunity",
        },
        {
            "tender_id": "REF-LOW",
            "title": "Low-signal tender",
            "organization": "Research Institute",
            "published_date": today,
            "source_portal": "cppp",
            "raw_text": "Low signal opportunity",
        },
    ]
    categories = {
        "High-signal tender": "high_signal",
        "Exploration tender": "explore",
        "Blocked tender": "blocked",
        "Low-signal tender": "low_signal",
    }

    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: tenders)
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(
        pipeline,
        "is_recent_tender",
        lambda tender, max_age_hours: tender["title"] not in {"Stale tender", "Expired tender"},
    )
    monkeypatch.setattr(
        pipeline,
        "classify_tender",
        lambda tender, manufacturer_candidates: {
            "is_blocked": categories[tender["title"]] == "blocked",
            "has_signal": categories[tender["title"]] in {"high_signal", "explore"},
            "category": categories[tender["title"]],
            "decision": categories[tender["title"]],
            "score": 80,
            "reason": "controlled digest statistics fixture",
        },
    )
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(pipeline, "deliver_due_batches", lambda *args: 0)
    monkeypatch.setattr(
        pipeline,
        "send_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )

    pipeline.run_pipeline()

    assert len(sent) == 1
    _, body, recipient = sent[0]
    assert recipient == "sales@example.com"
    assert "Total scraped: 8" in body
    assert "Fresh tenders processed: 4" in body
    assert "High-signal opportunities: 1" in body
    assert "Exploration candidates: 1" in body
    assert "Low-signal tenders: 1" in body
    assert "Blocked tenders: 1" in body
    assert "Stale tenders skipped: 1" in body
    assert "Expired tenders skipped: 1" in body
    assert "Duplicates skipped: 1" in body
    assert "Previously emailed skipped: 1" in body
    assert "Expired skipped: 1" in capsys.readouterr().out

    conn = sqlite3.connect(database_path)
    summary_json = conn.execute(
        "SELECT summary_json FROM pipeline_runs"
    ).fetchone()[0]
    conn.close()
    assert json.loads(summary_json)["expired_skipped"] == 1


def test_pipeline_does_not_suppress_distinct_tenders_with_the_same_title(monkeypatch):
    classified = []
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(":memory:"))
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [
        {
            "tender_id": "REF-1", "title": "Supply of a spectrometer",
            "organization": "Research Institute", "published_date": "2026-10-21",
            "source_portal": "cppp", "raw_text": "First procurement",
        },
        {
            "tender_id": "REF-2", "title": "Supply of a spectrometer",
            "organization": "Research Institute", "published_date": "2026-10-21",
            "source_portal": "cppp", "raw_text": "Second procurement",
        },
    ])
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda tender, max_age_hours: True)
    monkeypatch.setattr(pipeline, "classify_tender", lambda tender, manufacturer_candidates: (
        classified.append(tender["raw_text"]) or {
            "is_blocked": False,
            "has_signal": True,
            "category": "high_signal",
            "decision": "high_signal",
            "score": 80,
            "reason": "test fixture",
        }
    ))
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(pipeline, "send_email", lambda *args: None)

    pipeline.run_pipeline()

    assert classified == ["First procurement", "Second procurement"]


def test_pipeline_sends_legacy_emailed_tender_to_new_recipient(monkeypatch):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    tender, _ = upsert_or_get_tender(conn, {
        "tender_id": "REF-RECIPIENT-1",
        "title": "Supply of a spectrometer",
        "organization": "Research Institute",
        "published_date": "2026-10-21",
        "source_portal": "cppp",
        "raw_text": "New procurement for lab instrumentation",
    })
    conn.execute(
        "UPDATE tenders SET emailed=1 WHERE identity_key=?", (tender["identity_key"],)
    )
    previous_batch = queue_digest(conn, "previous@example.com", "Old digest", "Old body", [tender])
    conn.execute("UPDATE email_batches SET state='sent' WHERE id=?", (previous_batch,))
    conn.execute("UPDATE email_notifications SET state='sent' WHERE batch_id=?", (previous_batch,))
    conn.commit()
    sent = []

    monkeypatch.setattr(pipeline, "get_connection", lambda: conn)
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [{
        "tender_id": "REF-RECIPIENT-1",
        "title": "Supply of a spectrometer",
        "organization": "Research Institute",
        "published_date": "2026-10-21",
        "source_portal": "cppp",
        "raw_text": "New procurement for lab instrumentation",
    }])
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda tender, max_age_hours: True)
    monkeypatch.setattr(pipeline, "classify_tender", lambda tender, manufacturer_candidates: {
        "is_blocked": False,
        "has_signal": True,
        "category": "high_signal",
        "decision": "high_signal",
        "score": 80,
        "reason": "test fixture",
    })
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "new@example.com")
    monkeypatch.setattr(pipeline, "send_email", lambda subject, body, recipient: sent.append(recipient))

    pipeline.run_pipeline()

    assert sent == ["new@example.com"]


def test_pipeline_sends_meaningful_amendment_to_existing_recipient(monkeypatch, tmp_path):
    database_path = tmp_path / "amendment.sqlite3"
    sent = []
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda tender, max_age_hours: True)
    def classify(tender, manufacturer_candidates):
        return {
            "is_blocked": False,
            "has_signal": True,
            "category": "high_signal",
            "decision": "high_signal",
            "score": 80,
            "reason": "test fixture",
        }
    monkeypatch.setattr(pipeline, "classify_tender", classify)
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(
        pipeline, "send_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )

    first = {
        "tender_id": "REF-AMEND-1",
        "title": "Pump procurement",
        "organization": "Agency",
        "published_date": "2026-10-21",
        "closing_date": "2026-11-01",
        "source_portal": "cppp",
        "source_url": "https://agency.example/tenders/REF-AMEND-1",
        "raw_text": "Technical specification: flow rate 2 L/min",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [first])
    pipeline.run_pipeline()

    revised = {
        **first,
        "closing_date": "2026-11-20",
        "raw_text": "Technical specification: flow rate 3 L/min",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [revised])
    pipeline.run_pipeline()

    assert len(sent) == 2
    subject, body, recipient = sent[1]
    assert recipient == "sales@example.com"
    assert subject == "Tender Intelligence Update | 1 Updated"
    assert "UPDATED TENDERS" in body
    assert "Closing date extended from 2026-11-01 to 2026-11-20." in body
    assert "https://agency.example/tenders/REF-AMEND-1" in body
    conn = sqlite3.connect(database_path)
    assert conn.execute(
        "SELECT notification_type FROM email_notifications ORDER BY id"
    ).fetchall() == [("new_opportunity",), ("amendment_update",)]
    conn.close()


def test_pipeline_suppresses_blocked_amendment_for_existing_recipient(monkeypatch, tmp_path):
    database_path = tmp_path / "amendment-blocked.sqlite3"
    sent = []
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda tender, max_age_hours: True)

    def classify(tender, manufacturer_candidates):
        if "flow rate 3" in tender["raw_text"]:
            return {
                "is_blocked": True,
                "has_signal": False,
                "category": "blocked",
                "decision": "blocked",
                "score": 0,
                "reason": "amended text is blocked",
            }
        return {
            "is_blocked": False,
            "has_signal": True,
            "category": "high_signal",
            "decision": "high_signal",
            "score": 80,
            "reason": "initial opportunity matched",
        }

    monkeypatch.setattr(pipeline, "classify_tender", classify)
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(
        pipeline, "send_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )

    first = {
        "tender_id": "REF-AMEND-BLOCKED",
        "title": "Pump procurement",
        "organization": "Agency",
        "published_date": "2026-10-21",
        "closing_date": "2026-11-01",
        "source_portal": "cppp",
        "source_url": "https://agency.example/tenders/REF-AMEND-BLOCKED",
        "raw_text": "Technical specification: flow rate 2 L/min",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [first])
    pipeline.run_pipeline()

    revised = {
        **first,
        "closing_date": "2026-11-20",
        "raw_text": "Technical specification: flow rate 3 L/min",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [revised])
    pipeline.run_pipeline()

    # Initial opportunity sent, but blocked amendment must NOT be emailed
    assert len(sent) == 1
    conn = sqlite3.connect(database_path)
    assert conn.execute(
        "SELECT notification_type FROM email_notifications ORDER BY id"
    ).fetchall() == [("new_opportunity",)]
    conn.close()


def test_pipeline_suppresses_stale_or_expired_amendment_for_existing_recipient(monkeypatch, tmp_path):
    database_path = tmp_path / "amendment-expired.sqlite3"
    sent = []
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())

    # Initially fresh; on second run marked not recent (expired / stale)
    recent_flags = [True, False]
    monkeypatch.setattr(
        pipeline, "is_recent_tender",
        lambda tender, max_age_hours: recent_flags.pop(0) if recent_flags else False,
    )
    monkeypatch.setattr(pipeline, "classify_tender", lambda tender, *args, **kwargs: {
        "is_blocked": False,
        "has_signal": True,
        "category": "high_signal",
        "decision": "high_signal",
        "score": 80,
        "reason": "test fixture",
    })
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(
        pipeline, "send_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )

    first = {
        "tender_id": "REF-AMEND-EXPIRED",
        "title": "Equipment procurement",
        "organization": "Agency",
        "published_date": "2026-10-21",
        "closing_date": "2026-11-01",
        "source_portal": "cppp",
        "source_url": "https://agency.example/tenders/REF-AMEND-EXPIRED",
        "raw_text": "Quantity: 10 units",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [first])
    pipeline.run_pipeline()

    revised = {
        **first,
        "closing_date": "2026-10-01",  # Past / expired date
        "raw_text": "Quantity: 15 units",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [revised])
    pipeline.run_pipeline()

    # Expired amendment must NOT be emailed
    assert len(sent) == 1
    conn = sqlite3.connect(database_path)
    assert conn.execute(
        "SELECT notification_type FROM email_notifications ORDER BY id"
    ).fetchall() == [("new_opportunity",)]
    conn.close()


def test_pipeline_does_not_resend_formatting_only_content_change(monkeypatch, tmp_path):
    database_path = tmp_path / "formatting.sqlite3"
    sent = []
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda tender, max_age_hours: True)
    monkeypatch.setattr(pipeline, "classify_tender", lambda tender, manufacturer_candidates: {
        "is_blocked": False,
        "has_signal": True,
        "category": "high_signal",
        "decision": "high_signal",
        "score": 80,
        "reason": "test fixture",
    })
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(pipeline, "send_email", lambda *args: sent.append(args))
    first = {
        "tender_id": "REF-FORMAT-1",
        "title": "Lab equipment",
        "organization": "Agency",
        "published_date": "2026-10-21",
        "source_portal": "cppp",
        "raw_text": "Supply of equipment",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [first])
    pipeline.run_pipeline()
    monkeypatch.setattr(
        pipeline, "collect_all_tenders",
        lambda: [{**first, "raw_text": "supply   of\nequipment"}],
    )
    pipeline.run_pipeline()

    assert len(sent) == 1
    conn = sqlite3.connect(database_path)
    assert conn.execute("SELECT COUNT(*) FROM email_notifications").fetchone()[0] == 1
    conn.close()
