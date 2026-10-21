import sys
from types import ModuleType

import pytest
import requests


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

from pipeline import run as pipeline
from scheduler import start_scheduler
from scrapers import cppp, institutions


SECRET_URL = "https://user:password@portal.example/tenders?token=super-secret-token"


def test_pipeline_scraper_failure_logs_only_source_and_exception_type(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "scrape_cppp", lambda: (_ for _ in ()).throw(requests.ConnectionError(SECRET_URL)))
    monkeypatch.setattr(pipeline, "scrape_iitm", lambda: [])
    monkeypatch.setattr(pipeline, "scrape_iit_palakkad", lambda: [])
    monkeypatch.setattr(pipeline, "scrape_iit_goa", lambda: [])
    monkeypatch.setattr(pipeline, "scrape_iisc", lambda: [])

    assert pipeline.collect_all_tenders() == []
    output = capsys.readouterr().out
    assert "[SCRAPER FAILED] cppp: ConnectionError" in output
    assert "super-secret-token" not in output
    assert "password" not in output


def test_cppp_retry_logging_omits_url_and_exception_payload(monkeypatch, capsys):
    monkeypatch.setattr(cppp.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError(SECRET_URL)))
    monkeypatch.setattr(cppp.time, "sleep", lambda _: None)

    assert cppp.scrape_page("https://portal.example/tenders?token=super-secret-token", 2, retries=1) is None
    output = capsys.readouterr().out
    assert "request failed (ConnectionError)" in output
    assert "super-secret-token" not in output
    assert "password" not in output


def test_institution_scraper_failure_does_not_log_url_or_exception_payload(monkeypatch, capsys):
    monkeypatch.setattr(institutions.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError(SECRET_URL)))

    assert institutions.scrape_institution_page(SECRET_URL) is None
    output = capsys.readouterr().out
    assert "[INSTITUTION SCRAPER FAILED] ConnectionError" in output
    assert "super-secret-token" not in output
    assert "password" not in output


def test_scheduler_failure_logs_type_without_traceback_or_payload(monkeypatch, capsys):
    class StopLoop(Exception):
        pass

    monkeypatch.setattr("scheduler.run_pipeline", lambda: (_ for _ in ()).throw(RuntimeError(SECRET_URL)))

    def stop_after_first_run(_):
        raise StopLoop()

    monkeypatch.setattr("scheduler.time.sleep", stop_after_first_run)
    with pytest.raises(StopLoop):
        start_scheduler()
    output = capsys.readouterr().out
    assert "Pipeline run failed (RuntimeError)" in output
    assert "super-secret-token" not in output
    assert "Traceback" not in output
    assert "password" not in output
