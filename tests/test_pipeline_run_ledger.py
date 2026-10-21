import sqlite3
import json
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


def test_collection_keeps_safe_outcome_for_each_scraper(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "scrape_cppp", lambda: [{"title": "Tender"}])
    monkeypatch.setattr(pipeline, "scrape_iitm", lambda: [])
    monkeypatch.setattr(pipeline, "scrape_iit_palakkad", lambda: (_ for _ in ()).throw(RuntimeError("private")))
    monkeypatch.setattr(pipeline, "scrape_iit_goa", lambda: [])
    monkeypatch.setattr(pipeline, "scrape_iisc", lambda: [])

    tenders = pipeline.collect_all_tenders()
    assert len(tenders) == 1
    assert tenders.source_results["cppp"] == {"status": "ok", "tenders": 1}
    assert tenders.source_results["iit_palakkad"] == {
        "status": "failed", "error_type": "RuntimeError"
    }
    assert "private" not in capsys.readouterr().out


def test_completed_run_persists_safe_summary_and_source_outcomes(monkeypatch, tmp_path):
    path = tmp_path / "runs.sqlite3"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(path))
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [])
    monkeypatch.setattr(pipeline, "build_matcher", lambda: object())
    monkeypatch.setattr(pipeline, "deliver_due_batches", lambda *args: 0)
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "")

    pipeline.run_pipeline()

    conn = sqlite3.connect(path)
    run = conn.execute(
        "SELECT status, started_at, completed_at, duration_seconds, "
        "source_results_json, summary_json, error_type FROM pipeline_runs"
    ).fetchone()
    conn.close()
    assert run[0] == "completed"
    assert run[1] and run[2]
    assert run[3] >= 0
    assert run[4] == "{}"
    summary = json.loads(run[5])
    assert summary["total_scraped"] == 0
    assert summary["needs_review"] == 0
    assert summary["email_delivery"] == "skipped_no_opportunities"
    assert run[6] is None


def test_failed_run_records_exception_type_without_payload(monkeypatch, tmp_path, capsys):
    path = tmp_path / "failed-runs.sqlite3"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(path))
    monkeypatch.setattr(
        pipeline, "deliver_due_batches",
        lambda *args: (_ for _ in ()).throw(RuntimeError("secret-bearing failure details")),
    )

    with pytest.raises(RuntimeError):
        pipeline.run_pipeline()

    output = capsys.readouterr().out
    assert "RuntimeError" in output
    assert "secret-bearing failure details" not in output
    conn = sqlite3.connect(path)
    run = conn.execute(
        "SELECT status, completed_at, duration_seconds, error_type FROM pipeline_runs"
    ).fetchone()
    conn.close()
    assert run[0] == "failed"
    assert run[1]
    assert run[2] >= 0
    assert run[3] == "RuntimeError"


def test_failed_run_rolls_back_partial_tender_processing(monkeypatch, tmp_path):
    path = tmp_path / "rollback-runs.sqlite3"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(path))
    monkeypatch.setattr(pipeline, "deliver_due_batches", lambda *args: 0)
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [{
        "tender_id": "ROLLBACK-1", "title": "Lab equipment",
        "organization": "Agency", "published_date": "2026-10-21",
        "source_portal": "cppp", "raw_text": "Supply of lab equipment",
    }])
    monkeypatch.setattr(pipeline, "is_recent_tender", lambda *args, **kwargs: True)

    class BrokenMatcher:
        def match_topk(self, *args, **kwargs):
            raise RuntimeError("matching failed")

    monkeypatch.setattr(pipeline, "build_matcher", lambda: BrokenMatcher())
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "")

    with pytest.raises(RuntimeError):
        pipeline.run_pipeline()

    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM pipeline_runs").fetchone()[0] == "failed"
    conn.close()
