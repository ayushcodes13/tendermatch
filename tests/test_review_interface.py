"""Tests for the authenticated salesperson review interface and feedback lifecycle."""

import json
import os
import threading
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from config import FEEDBACK_REVIEWERS
from data.db import get_connection, init_db
from data.feedback import FEEDBACK_LABELS
from data.feedback_adjudication import build_adjudicated_dataset
from data.feedback_export import build_feedback_review_queue
from web.server import AUTH_TOKEN_ENV, TenderMatchReviewHandler


@pytest.fixture
def review_server(tmp_path, monkeypatch):
    """Start an ephemeral authenticated review HTTP server for testing."""
    test_db = tmp_path / "test_review.db"
    auth_token = "secret-test-token-xyz"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(test_db))
    monkeypatch.setenv(AUTH_TOKEN_ENV, auth_token)
    monkeypatch.setenv("TENDERMATCH_FEEDBACK_REVIEWERS", "sales-lead@example.com,sales-rep@example.com")

    conn = get_connection()
    try:
        init_db(conn)
        # Populate test tender
        conn.execute(
            """INSERT INTO tenders (
                tender_id, identity_key, version_fingerprint, title,
                organization, published_date, closing_date, source_url,
                source_portal, raw_text, emailed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "TENDER-2026-001",
                "identity-001",
                "fp-001",
                "Supply of Cryogenic High Vacuum Turbo Molecular Pump",
                "IISc Bangalore",
                "2026-10-20",
                "2026-11-15",
                "https://iisc.ac.in/tenders/001",
                "iisc",
                "Detailed tender specifications for cryogenic TMP with CF100 flange.",
                0,
            ),
        )
        # Populate match
        conn.execute(
            """INSERT INTO tender_matches (
                tender_identity_key, manufacturer_id, manufacturer_name, score, confidence
            ) VALUES (?, ?, ?, ?, ?)""",
            ("identity-001", "pfeiffer_vacuum", "Pfeiffer Vacuum", 0.92, "high"),
        )
        # Populate amendment
        conn.execute(
            """INSERT INTO tender_amendments (
                tender_identity_key, from_fingerprint, to_fingerprint,
                change_status, change_types_json, evidence_json, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "identity-001",
                "fp-000",
                "fp-001",
                "amended",
                json.dumps(["closing_date_extended"]),
                json.dumps({"old_closing_date": "2026-11-10", "new_closing_date": "2026-11-15"}),
                "2026-10-21T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    server = HTTPServer(("127.0.0.1", 0), TenderMatchReviewHandler)
    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    yield {
        "base_url": base_url,
        "token": auth_token,
        "db_path": str(test_db),
    }

    server.shutdown()
    server.server_close()


def _request(url: str, method: str = "GET", data: dict | None = None, headers: dict | None = None):
    req_headers = headers or {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = Request(url, data=body, headers=req_headers, method=method)
    return urlopen(req)


def test_static_asset_serving(review_server):
    base = review_server["base_url"]

    # Index HTML
    with _request(f"{base}/") as resp:
        assert resp.status == 200
        assert "text/html" in resp.headers.get("Content-Type")
        content = resp.read().decode("utf-8")
        assert "TenderMatch" in content
        assert "Salesperson Review" in content

    # CSS
    with _request(f"{base}/styles.css") as resp:
        assert resp.status == 200
        assert "text/css" in resp.headers.get("Content-Type")

    # JS
    with _request(f"{base}/app.js") as resp:
        assert resp.status == 200
        assert "javascript" in resp.headers.get("Content-Type")


def test_authentication_required(review_server):
    base = review_server["base_url"]

    # Unauthenticated GET
    with pytest.raises(HTTPError) as exc_info:
        _request(f"{base}/api/tenders")
    assert exc_info.value.code == 401

    # Unauthenticated POST
    with pytest.raises(HTTPError) as exc_info:
        _request(
            f"{base}/api/feedback",
            method="POST",
            data={"tender_identity_key": "identity-001", "label": "relevant"},
        )
    assert exc_info.value.code == 401

    # Invalid Bearer token
    with pytest.raises(HTTPError) as exc_info:
        _request(
            f"{base}/api/tenders",
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert exc_info.value.code == 401


TRUSTED_REVIEWERS = frozenset({"sales-lead@example.com", "sales-rep@example.com"})
PRIMARY_REVIEWER = "sales-lead@example.com"


def test_authenticated_endpoints_with_bearer_token(review_server):
    base = review_server["base_url"]
    headers = {"Authorization": f"Bearer {review_server['token']}"}

    # Auth check
    with _request(f"{base}/api/auth/check", headers=headers) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("authenticated") is True

    # Reviewers
    with _request(f"{base}/api/reviewers", headers=headers) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert set(data.get("reviewers", [])) == set(TRUSTED_REVIEWERS)

    # Labels
    with _request(f"{base}/api/labels", headers=headers) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert set(data.get("labels", [])) == set(FEEDBACK_LABELS)

    # Tenders listing
    with _request(f"{base}/api/tenders", headers=headers) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        tenders = data.get("tenders", [])
        assert len(tenders) == 1
        t = tenders[0]
        assert t["tender_id"] == "TENDER-2026-001"
        assert t["organization"] == "IISc Bangalore"
        assert len(t["matches"]) == 1
        assert t["matches"][0]["manufacturer_id"] == "pfeiffer_vacuum"
        assert t["amendment"]["status"] == "amended"


def test_authenticated_via_query_parameter(review_server):
    base = review_server["base_url"]
    token = review_server["token"]

    url = f"{base}/api/tenders?token={token}"
    with _request(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "tenders" in data


def test_post_feedback_success_and_history(review_server):
    base = review_server["base_url"]
    headers = {"Authorization": f"Bearer {review_server['token']}"}

    payload = {
        "tender_identity_key": "identity-001",
        "tender_version": "fp-001",
        "manufacturer_id": "pfeiffer_vacuum",
        "label": "worth_pursuing",
        "reviewer": PRIMARY_REVIEWER,
        "reason": "Direct specification match for Pfeiffer HiPace 300 series.",
    }

    with _request(f"{base}/api/feedback", method="POST", data=payload, headers=headers) as resp:
        assert resp.status == 201
        res = json.loads(resp.read().decode("utf-8"))
        assert res["status"] == "success"
        assert res["label"] == "worth_pursuing"
        assert res["reviewer"] == PRIMARY_REVIEWER
        assert "feedback_id" in res

    # Verify feedback shows up in subsequent GET /api/tenders
    with _request(f"{base}/api/tenders", headers=headers) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        fb_list = data["tenders"][0]["feedback"]
        assert len(fb_list) == 1
        assert fb_list[0]["label"] == "worth_pursuing"
        assert fb_list[0]["reviewer"] == PRIMARY_REVIEWER
        assert "HiPace 300" in fb_list[0]["reason"]


def test_post_feedback_validation_rejections(review_server):
    base = review_server["base_url"]
    headers = {"Authorization": f"Bearer {review_server['token']}"}

    # Untrusted reviewer
    payload_bad_reviewer = {
        "tender_identity_key": "identity-001",
        "manufacturer_id": "pfeiffer_vacuum",
        "label": "relevant",
        "reviewer": "unauthorized-intruder@example.com",
    }
    with pytest.raises(HTTPError) as exc_info:
        _request(f"{base}/api/feedback", method="POST", data=payload_bad_reviewer, headers=headers)
    assert exc_info.value.code == 400

    # Unsupported label
    payload_bad_label = {
        "tender_identity_key": "identity-001",
        "manufacturer_id": "pfeiffer_vacuum",
        "label": "invalid_label_xyz",
        "reviewer": PRIMARY_REVIEWER,
    }
    with pytest.raises(HTTPError) as exc_info:
        _request(f"{base}/api/feedback", method="POST", data=payload_bad_label, headers=headers)
    assert exc_info.value.code == 400

    # Excessive reason length
    payload_long_reason = {
        "tender_identity_key": "identity-001",
        "manufacturer_id": "pfeiffer_vacuum",
        "label": "relevant",
        "reviewer": PRIMARY_REVIEWER,
        "reason": "x" * 1500,
    }
    with pytest.raises(HTTPError) as exc_info:
        _request(f"{base}/api/feedback", method="POST", data=payload_long_reason, headers=headers)
    assert exc_info.value.code == 400


def test_feedback_to_adjudication_pipeline_integration(review_server):
    """Verify that feedback submitted via the UI flows through export and adjudication cleanly."""
    base = review_server["base_url"]
    headers = {"Authorization": f"Bearer {review_server['token']}"}

    # Submit feedback via review UI API
    payload = {
        "tender_identity_key": "identity-001",
        "tender_version": "fp-001",
        "manufacturer_id": "pfeiffer_vacuum",
        "label": "relevant",
        "reviewer": PRIMARY_REVIEWER,
        "reason": "Strong match confirmed by field sales.",
    }
    with _request(f"{base}/api/feedback", method="POST", data=payload, headers=headers) as resp:
        assert resp.status == 201

    conn = get_connection()
    try:
        # Build adjudication queue from feedback
        queue = build_feedback_review_queue(conn)
        assert len(queue["items"]) == 1
        item = queue["items"][0]
        assert item["tender_reference"] == "TENDER-2026-001"
        assert item["manufacturer_id"] == "pfeiffer_vacuum"
        assert item["feedback_label"] == "relevant"
        assert item["review_status"] == "pending_adjudication"

        # Adjudicate the queue item
        item["review_status"] = "human_adjudicated"
        item["adjudicated_label"] = "relevant"
        item["adjudication_reason"] = "Verified by technical sales lead."
        item["adjudicator"] = "lead-adjudicator@example.com"
        item["adjudicated_at"] = "2026-10-22T12:00:00+00:00"
        item["technical_evidence"] = ["Cryogenic turbo molecular pump requirement"]
        item["known_exclusions"] = []

        dataset = build_adjudicated_dataset(
            queue,
            trusted_adjudicators={"lead-adjudicator@example.com"},
        )
        assert dataset["human_reviewed_case_count"] == 1
        assert dataset["synthetic_case_count"] == 0
        case = dataset["cases"][0]
        assert case["label"] == "relevant"
        assert case["provenance"]["feedback_label"] == "relevant"
        assert case["provenance"]["feedback_reviewer"] == PRIMARY_REVIEWER
    finally:
        conn.close()

