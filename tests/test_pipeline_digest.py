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
