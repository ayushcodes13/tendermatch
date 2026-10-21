import hashlib
import importlib
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from data.db import init_db
from data.documents import DocumentResult, fetch_official_pdf, record_document_result, retrieve_candidate_documents


URL = "https://docs.example.gov/tenders/spec.pdf"
PDF = b"%PDF-1.7\nsynthetic fixture\n"


def test_document_retrieval_configuration_is_disabled_by_default(monkeypatch):
    monkeypatch.setitem(sys.modules, "dotenv", SimpleNamespace(load_dotenv=lambda: None))
    import config

    monkeypatch.delenv("TENDERMATCH_DOCUMENT_HOSTS", raising=False)
    monkeypatch.delenv("TENDERMATCH_DOCUMENT_DIR", raising=False)
    importlib.reload(config)
    assert config.DOCUMENT_ALLOWED_HOSTS == frozenset()
    assert config.DOCUMENT_STORAGE_DIR is None

    monkeypatch.setenv("TENDERMATCH_DOCUMENT_HOSTS", " docs.example.gov,files.example.gov ")
    monkeypatch.setenv("TENDERMATCH_DOCUMENT_DIR", "/srv/tendermatch/docs")
    importlib.reload(config)
    assert config.DOCUMENT_ALLOWED_HOSTS == {"docs.example.gov", "files.example.gov"}
    assert config.DOCUMENT_STORAGE_DIR == "/srv/tendermatch/docs"
    monkeypatch.delenv("TENDERMATCH_DOCUMENT_HOSTS")
    monkeypatch.delenv("TENDERMATCH_DOCUMENT_DIR")
    importlib.reload(config)


class Response:
    def __init__(self, status=200, body=PDF, content_type="application/pdf", headers=None):
        self.status_code = status
        self.headers = headers or {"Content-Type": content_type}
        self.body = body
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


class Http:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return self.response


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr("data.documents.socket.getaddrinfo", lambda *args: [(None, None, None, None, ("8.8.8.8", 0))])


def test_downloads_pdf_atomically_and_hashes_content(tmp_path):
    http = Http(Response())
    result = fetch_official_pdf(URL, allowed_hosts={"docs.example.gov"}, storage_dir=tmp_path, http=http)

    expected = hashlib.sha256(PDF).hexdigest()
    assert result.status == "downloaded"
    assert result.content_fingerprint == expected
    assert result.source_url == URL
    assert (tmp_path / f"{expected}.pdf").read_bytes() == PDF
    assert (tmp_path / f"{expected}.pdf").stat().st_mode & 0o777 == 0o600
    assert http.kwargs["allow_redirects"] is False
    assert http.kwargs["timeout"] == (5, 20)


def test_requires_explicit_host_allowlist_and_https(tmp_path):
    blocked = fetch_official_pdf(URL, storage_dir=tmp_path, http=Http(Response()))
    insecure = fetch_official_pdf("http://docs.example.gov/spec.pdf", allowed_hosts={"docs.example.gov"}, storage_dir=tmp_path)
    assert blocked.status == "blocked"
    assert blocked.error_type == "HostNotAllowed"
    assert insecure.status == "unavailable"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "response, expected_status, expected_error",
    [
        (Response(status=302, headers={"Location": "https://elsewhere.example/spec.pdf"}), "blocked", "RedirectNotFollowed"),
        (Response(body=b"not a pdf"), "unsupported", "InvalidPDF"),
        (Response(content_type="text/html"), "unsupported", "UnsupportedContentType"),
        (Response(headers={"Content-Type": "application/pdf", "Content-Length": "1000"}), "rejected", "FileTooLarge"),
    ],
)
def test_rejects_redirects_invalid_types_and_oversize(tmp_path, response, expected_status, expected_error):
    result = fetch_official_pdf(URL, allowed_hosts={"docs.example.gov"}, storage_dir=tmp_path, max_bytes=100, http=Http(response))
    assert result.status == expected_status
    assert result.error_type == expected_error
    assert not list(tmp_path.iterdir())


def test_bounds_streamed_size_even_without_content_length(tmp_path):
    result = fetch_official_pdf(
        URL,
        allowed_hosts={"docs.example.gov"},
        storage_dir=tmp_path,
        max_bytes=10,
        http=Http(Response(headers={"Content-Type": "application/pdf"})),
    )
    assert result.status == "rejected"
    assert result.error_type == "FileTooLarge"
    assert not list(tmp_path.iterdir())


def test_records_each_document_observation_and_version(tmp_path):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    first = DocumentResult(URL, "downloaded", "a" * 64, str(tmp_path / "a.pdf"), "application/pdf", 20, "2026-10-22T00:00:00+00:00")
    second = DocumentResult(URL, "unavailable", fetched_at="2026-10-23T00:00:00+00:00", error_type="HTTP404")

    record_document_result(conn, "tender-1", first)
    record_document_result(conn, "tender-1", second)
    rows = conn.execute(
        "SELECT source_url, content_fingerprint, status, error_type FROM tender_documents ORDER BY id"
    ).fetchall()
    assert rows == [(URL, "a" * 64, "downloaded", None), (URL, None, "unavailable", "HTTP404")]
    conn.close()


def test_retrieval_only_visits_bounded_promising_candidates(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    calls = []

    def fake_fetch(url, **kwargs):
        calls.append(url)
        return DocumentResult(url, "blocked", error_type="HostNotAllowed")

    monkeypatch.setattr("data.documents.fetch_official_pdf", fake_fetch)
    candidates = [
        {"category": "low_signal", "tender_identity_key": "skip", "document_links": ["https://x.test/a.pdf"]},
        {"classification": {"category": "high_signal"}, "identity_key": "one", "document_links": ["https://x.test/1.pdf", "https://x.test/2.pdf", "https://x.test/3.pdf"]},
        {"category": "agent_review", "tender_identity_key": "two", "document_links": ["https://x.test/4.pdf"]},
        {"classification": {"category": "explore"}, "identity_key": "three", "document_links": ["https://x.test/5.pdf"]},
        *[
            {"category": "high_signal", "tender_identity_key": str(index), "document_links": [f"https://x.test/{index}.pdf"]}
            for index in range(20)
        ],
    ]

    results = retrieve_candidate_documents(
        conn, candidates, storage_dir=tmp_path, max_candidates=3, max_documents_per_candidate=2
    )

    assert calls == ["https://x.test/1.pdf", "https://x.test/2.pdf", "https://x.test/4.pdf", "https://x.test/5.pdf"]
    assert len(results) == 4
    assert conn.execute("SELECT COUNT(*) FROM tender_documents").fetchone()[0] == 4
    conn.close()
