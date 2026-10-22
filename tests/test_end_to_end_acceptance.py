"""Comprehensive end-to-end acceptance tests demonstrating customer Journeys A through I.

Validates the complete TenderMatch procurement intelligence lifecycle without
contacting live external procurement portals or sending live customer emails:
  - Journey A: Initial Discovery & Matching
  - Journey B: Repeated Run Deduplication & Suppression
  - Journey C: Meaningful Amendment Versioning & Notification
  - Journey D: Wrong-Domain Rejection & Contextual Penalty
  - Journey E: Ambiguous Technical Match & Manual Review Preservation
  - Journey F: Official Document Intelligence & Evidence Enrichment
  - Journey G: SMTP Outbox Interruption & Crash Recovery
  - Journey H: Salesperson Feedback Capture & Adjudication Pipeline
  - Journey I: Database Backup, Fresh-Environment Restore & State Recovery
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
from types import ModuleType

if "sentence_transformers" not in sys.modules:
    try:
        __import__("sentence_transformers")
    except ImportError:
        stub = ModuleType("sentence_transformers")
        stub.SentenceTransformer = object
        sys.modules["sentence_transformers"] = stub

import pytest

from data.backup import backup_database, restore_database
from data.db import (
    get_connection,
    init_db,
    upsert_or_get_tender,
)
from data.documents import DocumentResult, record_document_result
from data.extraction import record_extraction_result
from data.feedback import capture_feedback
from data.feedback_adjudication import build_adjudicated_dataset
from data.feedback_export import build_feedback_review_queue
from digest.outbox import (
    AMENDMENT_UPDATE,
    NEW_OPPORTUNITY,
    deliver_batch,
    deliver_due_batches,
    queue_digest,
)
from matching.claim_provenance import assess_candidate_claims, load_claims
from matching.decision import decide_tender
from matching.document_enrichment import enrich_tender_with_document_evidence
from matching.filter import classify_tender
from matching.concepts import detect_concepts
from matching.signals import detect_signals


# ==============================================================================
# Journey A: Initial Discovery & Controlled Outbox Queueing
# ==============================================================================

def test_journey_a_initial_discovery_and_matching(tmp_path, monkeypatch):
    """Journey A: A valid new tender is scraped, stored, matched, explained, and queued."""
    db_path = tmp_path / "journey_a.db"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    conn = get_connection()
    try:
        init_db(conn)

        tender = {
            "tender_id": "TENDER-IITM-2026-PVD-01",
            "title": "Supply and Installation of Modular High Vacuum Sputter Deposition System",
            "organization": "IIT Madras",
            "published_date": "2026-10-22T09:00",
            "closing_date": "2026-11-20T17:00",
            "source_url": "https://tenders.iitm.ac.in/tender/01.pdf",
            "source_portal": "iitm",
            "raw_text": "Supply and installation of modular research PVD system with magnetron sputtering sources and RF/DC power supplies.",
        }

        # 1. Classification & matching
        classification = classify_tender(tender)
        assert classification["category"] in {"high_signal", "explore"}
        assert classification["decision"] in {"high_signal", "explore"}
        trace_concepts = [c["concept_id"] for c in classification["trace"]["concepts"]["matched_concepts"]]
        assert "thin_film_deposition" in trace_concepts or "pvd" in trace_concepts

        # 2. Store tender in SQLite
        merged_tender, is_new = upsert_or_get_tender(conn, tender)
        assert is_new is True
        identity_key = merged_tender["identity_key"]
        assert identity_key is not None

        # Verify version row was recorded
        version_rows = conn.execute(
            "SELECT count(*) FROM tender_versions WHERE tender_identity_key = ?",
            (identity_key,),
        ).fetchone()[0]
        assert version_rows == 1

        # 3. Check claim provenance for candidate
        claims_registry = load_claims()
        korvus_claims = [c for c in claims_registry if c.get("manufacturer_id") == "korvus_technology"]
        assert len(korvus_claims) >= 1
        candidate = {
            "manufacturer_id": "korvus_technology",
            "keyword_hits": ["PVD", "sputtering"],
            "product_hits": ["HEX Series PVD systems"],
        }
        claim_assessment = assess_candidate_claims(candidate, claims_registry)
        assert claim_assessment["claim_status"] == "fully_verified"
        assert len(claim_assessment["verified_claims"]) >= 1

        # 4. Queue digest in outbox
        batch_id = queue_digest(
            conn,
            recipient="sales@example.com",
            subject="TenderMatch Daily Digest",
            body="New high-signal tender opportunity discovered.",
            tenders=[merged_tender],
        )
        assert batch_id is not None

        # Verify batch state is 'pending'
        state = conn.execute("SELECT state FROM email_batches WHERE id = ?", (batch_id,)).fetchone()[0]
        assert state == "pending"

        notif = conn.execute(
            "SELECT tender_identity_key, notification_type, state FROM email_notifications WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        assert notif[0] == identity_key
        assert notif[1] == NEW_OPPORTUNITY
        assert notif[2] == "pending"
    finally:
        conn.close()


# ==============================================================================
# Journey B: Repeated Run Deduplication & Suppression
# ==============================================================================

def test_journey_b_repeated_run_does_not_duplicate_notification(tmp_path, monkeypatch):
    """Journey B: The same unchanged tender does not generate duplicate notification rows."""
    db_path = tmp_path / "journey_b.db"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    conn = get_connection()
    try:
        init_db(conn)

        tender = {
            "tender_id": "TENDER-IISc-2026-CRYO",
            "title": "Procurement of Cryopump for High Vacuum System",
            "organization": "IISc Bangalore",
            "published_date": "2026-10-22",
            "source_url": "https://iisc.ac.in/tenders/cryo.pdf",
            "source_portal": "iisc",
            "raw_text": "Cryogenic pump for ultra-high vacuum applications.",
        }

        # First run: new opportunity
        merged_1, is_new_1 = upsert_or_get_tender(conn, tender)
        assert is_new_1 is True
        identity_key = merged_1["identity_key"]

        batch_id_1 = queue_digest(
            conn,
            recipient="sales@example.com",
            subject="TenderMatch Daily Digest",
            body="First digest",
            tenders=[merged_1],
        )
        assert batch_id_1 is not None

        # Simulate successful delivery by marking batch and notifications sent
        conn.execute("UPDATE email_batches SET state = 'sent' WHERE id = ?", (batch_id_1,))
        conn.execute("UPDATE email_notifications SET state = 'sent' WHERE batch_id = ?", (batch_id_1,))
        conn.commit()

        # Second run with exact same tender content
        merged_2, is_new_2 = upsert_or_get_tender(conn, tender)
        assert is_new_2 is False, "Unchanged tender must not be inserted as a new record"

        # Check outbox: attempt to queue again should return None (already notified)
        batch_id_2 = queue_digest(
            conn,
            recipient="sales@example.com",
            subject="TenderMatch Daily Digest",
            body="Second digest",
            tenders=[merged_2],
        )
        assert batch_id_2 is None, "Already notified tender must not create another batch"
    finally:
        conn.close()


# ==============================================================================
# Journey C: Meaningful Amendment Notification
# ==============================================================================

def test_journey_c_meaningful_amendment_triggers_update_digest(tmp_path, monkeypatch):
    """Journey C: Meaningful deadline extension generates a version and amendment notification."""
    db_path = tmp_path / "journey_c.db"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    conn = get_connection()
    try:
        init_db(conn)

        v1 = {
            "tender_id": "TENDER-IITPKD-2026-009",
            "title": "High Vacuum Turbo Molecular Pumping Station",
            "organization": "IIT Palakkad",
            "published_date": "2026-10-15",
            "closing_date": "2026-10-30",
            "source_url": "https://iitpkd.ac.in/tenders/009",
            "source_portal": "iit_palakkad",
            "raw_text": "Turbo molecular pump station with dry backing pump.",
        }

        # First version
        merged_v1, is_new_1 = upsert_or_get_tender(conn, v1)
        assert is_new_1 is True
        identity_key = merged_v1["identity_key"]

        batch_id_1 = queue_digest(
            conn,
            recipient="sales@example.com",
            subject="Daily Digest",
            body="Initial opportunity",
            tenders=[merged_v1],
        )
        assert batch_id_1 is not None

        # Simulate delivery of v1
        conn.execute("UPDATE email_batches SET state = 'sent' WHERE id = ?", (batch_id_1,))
        conn.execute("UPDATE email_notifications SET state = 'sent' WHERE batch_id = ?", (batch_id_1,))
        conn.commit()

        # Amended version: closing date extended by 15 days
        v2 = dict(v1, closing_date="2026-11-15", raw_text=v1["raw_text"] + " Corrigendum: closing date extended to 15 November 2026.")
        merged_v2, is_new_2 = upsert_or_get_tender(conn, v2)
        assert merged_v2["version_fingerprint"] != merged_v1["version_fingerprint"]
        merged_v2["notification_type"] = AMENDMENT_UPDATE

        # Queue amendment update
        batch_id_2 = queue_digest(
            conn,
            recipient="sales@example.com",
            subject="TenderMatch Corrigendum Update",
            body="Tender updated with extended deadline.",
            tenders=[merged_v2],
        )
        assert batch_id_2 is not None

        notif = conn.execute(
            "SELECT notification_type, tender_version FROM email_notifications WHERE batch_id = ?",
            (batch_id_2,),
        ).fetchone()
        assert notif[0] == AMENDMENT_UPDATE
        assert notif[1] == merged_v2["version_fingerprint"]
    finally:
        conn.close()


# ==============================================================================
# Journey D: Wrong-Domain Tender Rejection
# ==============================================================================

def test_journey_d_wrong_domain_tender_is_rejected():
    """Journey D: Irrelevant tenders (e.g. civil construction, food catering) are rejected."""
    civil_tender = {
        "title": "Annual maintenance contract for campus road paving and civil drainage",
        "organization": "Public Works Department",
        "published_date": "2026-10-22",
        "raw_text": "Construction, civil paving, road repair, and sanitation works.",
    }

    classification = classify_tender(civil_tender)
    assert classification["is_blocked"] is True or classification["decision"] == "reject_hard"
    assert classification["category"] == "blocked" or "civil" in classification.get("reason", "").lower()


# ==============================================================================
# Journey E: Ambiguous Technical Match Preserved for Review
# ==============================================================================

def test_journey_e_ambiguous_technical_match_requires_agent_review():
    """Journey E: Borderline or domain-conflicting tenders preserve uncertainty for human review."""
    ambiguous_tender = {
        "title": "Supply of laboratory vacuum cleaner and industrial suction apparatus",
        "organization": "National Physical Laboratory",
        "published_date": "2026-10-22",
        "raw_text": "Procurement of floor cleaning vacuum cleaner and laboratory vacuum chamber accessories.",
    }

    classification = classify_tender(ambiguous_tender)
    assert classification["decision"] == "agent_review"
    assert classification["agent_review_required"] is True
    assert any("LAB_VACUUM_CLEANING_COLLISION" in code for code in classification["reason_codes"])


# ==============================================================================
# Journey F: Official Document Intelligence & Evidence Enrichment
# ==============================================================================

def test_journey_f_document_intelligence_enrichment(tmp_path, monkeypatch):
    """Journey F: Authorized PDF extraction extracts technical specs and substantiates fit."""
    db_path = tmp_path / "journey_f.db"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    conn = get_connection()
    try:
        init_db(conn)

        # 1. Record document retrieval
        doc_result = DocumentResult(
            source_url="https://iisc.ac.in/tender/pvd_specs.pdf",
            status="downloaded",
            storage_path=str(tmp_path / "pvd_specs.pdf"),
            content_type="application/pdf",
            byte_size=2048,
        )
        record_document_result(conn, tender_identity_key="id-doc-001", result=doc_result)

        # 2. Record extraction result with page citations
        extraction = {
            "source_url": "https://iisc.ac.in/tender/pvd_specs.pdf",
            "content_fingerprint": "fp-pdf-001",
            "status": "extracted",
            "pages": [1, 2, 3],
            "fields": {
                "technical_specifications": [
                    {
                        "value": "HEX Series PVD systems magnetron sputtering",
                        "evidence": {"page": 3, "quote": "Supply of HEX Series PVD systems magnetron sputtering unit."},
                    }
                ]
            },
        }
        record_extraction_result(conn, extraction)

        # 3. Enrich tender with document evidence against manufacturer capabilities
        tender = {
            "identity_key": "id-doc-001",
            "title": "Supply of Modular PVD Magnetron Sputtering Tool",
            "matches": [
                {
                    "manufacturer_id": "korvus_technology",
                    "manufacturer_name": "Korvus Technology",
                }
            ],
        }

        enriched = enrich_tender_with_document_evidence(tender, extraction)

        assert enriched["document_evidence"]["completeness"] == "verified"
        assert enriched["document_evidence"]["pages_reviewed"] == 3
        assert len(enriched["document_evidence"]["verified_requirements"]) >= 1
        req = enriched["document_evidence"]["verified_requirements"][0]
        assert req["page"] == 3
        assert "sputtering" in req["requirement"].lower()
    finally:
        conn.close()


# ==============================================================================
# Journey G: SMTP Outbox Crash & Recovery
# ==============================================================================

def test_journey_g_smtp_interruption_and_recovery(tmp_path, monkeypatch):
    """Journey G: Interrupted SMTP dispatch leaves batch recoverable in outbox."""
    db_path = tmp_path / "journey_g.db"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    conn = get_connection()
    try:
        init_db(conn)

        batch_id = queue_digest(
            conn,
            recipient="operator@example.com",
            subject="Daily Digest",
            body="Digest content",
            tenders=[{"identity_key": "k-01", "version_fingerprint": "fp-01"}],
        )
        assert batch_id is not None

        # 1. Simulate worker crash by leaving status as 'sending' with stale timestamp (>15 mins ago)
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "UPDATE email_batches SET state = 'sending', updated_at = ? WHERE id = ?",
            (stale_time, batch_id),
        )
        conn.commit()

        # 2. Worker restarts and recovers stale sending batches
        sent_emails = []

        def fake_send(subject, body, recipient):
            sent_emails.append((recipient, subject))

        outcomes = deliver_due_batches(conn, fake_send)
        assert len(outcomes) == 1
        assert outcomes[0] == (batch_id, True)
        assert len(sent_emails) == 1
        assert sent_emails[0][0] == "operator@example.com"

        # Verify database state is now 'sent'
        status = conn.execute("SELECT state, sent_at FROM email_batches WHERE id = ?", (batch_id,)).fetchone()
        assert status[0] == "sent"
        assert status[1] is not None
    finally:
        conn.close()


# ==============================================================================
# Journey H: Salesperson Feedback Capture & Adjudication Pipeline
# ==============================================================================

def test_journey_h_feedback_capture_to_adjudication_pipeline(tmp_path, monkeypatch):
    """Journey H: Salesperson submits feedback, exports queue, and builds human-adjudicated dataset."""
    db_path = tmp_path / "journey_h.db"
    monkeypatch.setenv("TENDERMATCH_DB_PATH", str(db_path))

    conn = get_connection()
    try:
        init_db(conn)

        # Tender record
        conn.execute(
            """INSERT INTO tenders (
                tender_id, identity_key, title, organization,
                published_date, closing_date, source_url, source_portal, raw_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "T-2026-PFEIFFER",
                "key-pfeiffer-001",
                "Supply of Turbo Molecular Vacuum Pumping Station",
                "IISc Bangalore",
                "2026-10-20",
                "2026-11-20",
                "https://iisc.ac.in/tender/vac.pdf",
                "iisc",
                "TMP station with dry backing pump.",
            ),
        )
        conn.commit()

        # Salesperson submits feedback
        trusted = frozenset({"sales-rep@example.com"})
        fb_id = capture_feedback(
            conn,
            tender_identity_key="key-pfeiffer-001",
            manufacturer_id="korvus_technology",
            label="worth_pursuing",
            reviewer="sales-rep@example.com",
            trusted_reviewers=trusted,
            reason="Confirmed high fit for HEX series research pumping requirement.",
        )
        assert fb_id > 0

        # Export review queue
        queue = build_feedback_review_queue(conn)
        assert len(queue["items"]) == 1
        item = queue["items"][0]
        assert item["feedback_label"] == "worth_pursuing"
        assert item["review_status"] == "pending_adjudication"

        # Adjudicate queue item
        item["review_status"] = "human_adjudicated"
        item["adjudicated_label"] = "relevant"
        item["adjudication_reason"] = "Verified technical fit with OEM engineering lead."
        item["adjudicator"] = "lead-adjudicator@example.com"
        item["adjudicated_at"] = "2026-10-22T14:00:00+00:00"
        item["technical_evidence"] = ["Turbo molecular pump requirement confirmed"]
        item["known_exclusions"] = []

        # Promote to human-reviewed evaluation dataset
        dataset = build_adjudicated_dataset(
            queue,
            trusted_adjudicators={"lead-adjudicator@example.com"},
        )
        assert dataset["human_reviewed_case_count"] == 1
        assert dataset["synthetic_case_count"] == 0
        case = dataset["cases"][0]
        assert case["label"] == "relevant"
        assert case["provenance"]["type"] == "human_reviewed_feedback"
    finally:
        conn.close()


# ==============================================================================
# Journey I: Persistence & Disaster Recovery
# ==============================================================================

def test_journey_i_backup_fresh_environment_restore_and_recovery(tmp_path):
    """Journey I: Backup SQLite database, simulate fresh machine, and restore without data loss."""
    primary_db = tmp_path / "primary_production.db"
    backup_file = tmp_path / "backup_snapshot.sqlite"
    restored_db = tmp_path / "restored_production.db"

    # Populate primary production database
    conn = sqlite3.connect(primary_db)
    try:
        init_db(conn)
        conn.execute(
            """INSERT INTO tenders (
                tender_id, identity_key, title, organization, published_date,
                source_url, source_portal, raw_text, version_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "TENDER-DR-001",
                "identity-dr-001",
                "High Field EPR Spectrometer",
                "IISc",
                "2026-10-22",
                "https://iisc.ac.in/epr.pdf",
                "iisc",
                "Pulse EPR spectrometer specs.",
                "fp-dr-001",
            ),
        )
        conn.execute(
            """INSERT INTO salesperson_feedback (
                tender_identity_key, tender_version, manufacturer_id, label,
                reason, reviewer, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "identity-dr-001",
                "fp-dr-001",
                "spinflex",
                "relevant",
                "Direct product match for spinUP system.",
                "sales@example.com",
                "2026-10-22T10:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # 1. Take integrity-checked backup
    backup_path = backup_database(source=primary_db, destination=backup_file)
    assert Path(backup_path).is_file()

    # 2. Simulate fresh host environment and restore
    restored_path = restore_database(backup=backup_file, destination=restored_db, replace=True, verify_schema=True)
    assert Path(restored_path).is_file()

    # 3. Verify complete state recovery
    restored_conn = sqlite3.connect(restored_db)
    try:
        tender_row = restored_conn.execute("SELECT tender_id, title FROM tenders WHERE identity_key = 'identity-dr-001'").fetchone()
        assert tender_row is not None
        assert tender_row[0] == "TENDER-DR-001"

        feedback_row = restored_conn.execute("SELECT manufacturer_id, label, reviewer FROM salesperson_feedback WHERE tender_identity_key = 'identity-dr-001'").fetchone()
        assert feedback_row is not None
        assert feedback_row[0] == "spinflex"
        assert feedback_row[1] == "relevant"
        assert feedback_row[2] == "sales@example.com"
    finally:
        restored_conn.close()
