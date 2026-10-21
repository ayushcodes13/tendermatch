"""Isolated startup, persistence, and scheduler smoke checks; no live services."""
import sqlite3
import sys
from types import ModuleType

import pytest


def _stub_if_unavailable(name, **attributes):
    if name in sys.modules:
        return
    try:
        __import__(name)
    except ImportError:
        module = ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        sys.modules[name] = module


_stub_if_unavailable("dotenv", load_dotenv=lambda: None)
_stub_if_unavailable("bs4", BeautifulSoup=object)
_stub_if_unavailable("sentence_transformers", SentenceTransformer=object)

import pipeline.run as pipeline
import scheduler


class EmptyMatcher:
    def match_topk(self, tender, top_k=5):
        return []


def test_synthetic_pipeline_startup_persists_two_runs_without_live_services(monkeypatch, tmp_path):
    database = tmp_path / "smoke.sqlite3"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(database))
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())
    monkeypatch.setattr(pipeline, "deliver_due_batches", lambda *args: 0)
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "")
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda *args, **kwargs: True)
    monkeypatch.setattr(pipeline, "classify_tender", lambda *args, **kwargs: {
        "is_blocked": False,
        "has_signal": False,
        "category": "low_signal",
        "decision": "low_signal",
        "score": 20,
        "reason": "isolated smoke fixture",
        "agent_review_required": False,
    })

    collection = pipeline.TenderCollection()
    collection.append({
        "tender_id": "SMOKE-1",
        "title": "Synthetic smoke tender",
        "organization": "Fixture Agency",
        "published_date": "2026-10-22",
        "source_portal": "fixture",
        "raw_text": "Synthetic test data only",
    })
    collection.source_results["fixture"] = {"status": "ok", "tenders": 1}
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: collection)

    pipeline.run_pipeline()
    pipeline.run_pipeline()

    conn = sqlite3.connect(database)
    runs = conn.execute(
        "SELECT status, source_results_json, summary_json FROM pipeline_runs ORDER BY started_at"
    ).fetchall()
    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1
    conn.close()
    assert len(runs) == 2
    assert all(row[0] == "completed" for row in runs)
    assert all('"fixture": {"status": "ok", "tenders": 1}' in row[1] for row in runs)
    assert all('"total_scraped": 1' in row[2] for row in runs)


def test_scheduler_executes_a_cycle_before_waiting(monkeypatch):
    calls = []

    class StopAfterOneCycle(Exception):
        pass

    monkeypatch.setattr(scheduler, "run_pipeline", lambda: calls.append("run"))

    def stop_after_wait(_seconds):
        raise StopAfterOneCycle()

    monkeypatch.setattr(scheduler.time, "sleep", stop_after_wait)
    with pytest.raises(StopAfterOneCycle):
        scheduler.start_scheduler()
    assert calls == ["run"]
