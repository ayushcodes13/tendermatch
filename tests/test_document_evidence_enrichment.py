"""Tests for source-grounded document evidence enrichment and matching integration."""

from datetime import date, timedelta
import json
import sqlite3
import sys
from types import ModuleType

import pytest


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

from digest.formatter import format_email
from matching.document_enrichment import (
    enrich_tender_with_document_evidence,
    format_document_evidence_lines,
)
import pipeline.run as pipeline


SAMPLE_CATALOG = [
    {
        "id": "korvus",
        "name": "Korvus Technology",
        "products": ["HEX deposition system", "CVD system", "thin film deposition"],
        "offered_services": ["thin film training", "system installation"],
        "keywords": ["chemical vapor deposition", "vacuum chamber"],
        "negative_keywords": ["medical infusion", "civil construction"],
        "known_limitations": ["no high-pressure autoclaves"],
    }
]


def test_enrich_tender_without_document_discloses_no_document():
    tender = {
        "title": "Supply of laboratory evaporator",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    enriched = enrich_tender_with_document_evidence(tender, None, SAMPLE_CATALOG)
    assert enriched["document_evidence"]["completeness"] == "no_document"
    assert "No official tender PDF was retrieved" in enriched["document_evidence"]["summary"]


def test_enrich_tender_with_scanned_pdf_flags_needs_ocr():
    tender = {
        "title": "Procurement of specialized deposition system",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "needs_ocr",
        "error_type": None,
        "pages": [{"page": 1, "status": "no_text"}, {"page": 2, "status": "no_text"}],
        "fields": {},
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, SAMPLE_CATALOG)
    assert enriched["document_evidence"]["completeness"] == "needs_ocr"
    assert "OCR or manual review required" in enriched["document_evidence"]["summary"]


def test_enrich_tender_with_extracted_requirements_matches_capabilities():
    tender = {
        "title": "Procurement of advanced thin film deposition system",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "error_type": None,
        "pages": [{"page": 1}, {"page": 2}, {"page": 3}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Must include high precision chemical vapor deposition module with vacuum chamber",
                    "evidence": {
                        "source_url": "https://eprocure.gov.in/doc1.pdf",
                        "page": 2,
                        "quote": "Mandatory requirement: Must include high precision chemical vapor deposition module with vacuum chamber",
                    },
                }
            ],
            "technical_specifications": [
                {
                    "value": "Custom glass substrate stage with temperature controller",
                    "evidence": {
                        "source_url": "https://eprocure.gov.in/doc1.pdf",
                        "page": 3,
                        "quote": "Specifications: Custom glass substrate stage with temperature controller",
                    },
                }
            ],
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, SAMPLE_CATALOG)
    evidence = enriched["document_evidence"]
    assert evidence["completeness"] == "verified"
    assert evidence["pages_reviewed"] == 3
    assert len(evidence["verified_requirements"]) >= 1

    matched = evidence["verified_requirements"][0]
    assert matched["manufacturer"] == "Korvus Technology"
    assert matched["page"] == 2
    assert "chemical vapor deposition" in matched["capability"]

    # Unknown technical specification is retained in unverified requirements
    assert any("Custom glass substrate stage" in req for req in evidence["unverified_requirements"])


def test_enrich_tender_with_conflict_demotes_and_flags_review():
    tender = {
        "title": "Hospital medical infusion equipment",
        "category": "high_signal",
        "decision": "high_signal",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Medical infusion ward monitoring and delivery apparatus",
                    "evidence": {
                        "source_url": "https://hospital.gov.in/tender.pdf",
                        "page": 1,
                        "quote": "Mandatory: Medical infusion ward monitoring and delivery apparatus",
                    },
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, SAMPLE_CATALOG)
    assert enriched["has_document_conflicts"] is True
    assert enriched["agent_review_required"] is True
    assert enriched["category"] == "explore"  # Demoted from high_signal
    assert len(enriched["document_evidence"]["conflicts"]) == 1

    conflict = enriched["document_evidence"]["conflicts"][0]
    assert conflict["page"] == 1
    assert "medical infusion" in conflict["conflict_reason"]


def test_format_email_renders_document_review_and_conflict_disclosure():
    tender = {
        "title": "Deposition system tender",
        "organization": "National Laboratory",
        "document_evidence": {
            "completeness": "verified",
            "summary": "Official PDF verified natively across 4 page(s).",
            "conflicts": [
                {
                    "requirement": "Sterilization autoclave requirement",
                    "page": 3,
                    "conflict_reason": "Conflicts with Korvus limitation: 'no high-pressure autoclaves'",
                }
            ],
            "verified_requirements": [
                {
                    "requirement": "Chemical vapor deposition system",
                    "page": 1,
                    "manufacturer": "Korvus Technology",
                    "capability": "chemical vapor deposition",
                }
            ],
            "unverified_requirements": ["Specialized chiller unit (p. 4)"],
        },
        "matches": [
            {
                "manufacturer_name": "Korvus Technology",
                "product_hits": ["CVD system"],
                "concept_hits": ["chemical vapor deposition"],
            }
        ],
    }

    subject, body = format_email([tender], [], {})
    assert "Document review: Official PDF verified natively across 4 page(s)." in body
    assert "⚠️ Document conflicts detected:" in body
    assert "Sterilization autoclave requirement (p. 3)" in body
    assert "Verified document requirements:" in body
    assert "Chemical vapor deposition system (p. 1)" in body


def test_pipeline_executes_document_enrichment_end_to_end(monkeypatch, tmp_path):
    database_path = tmp_path / "doc_pipeline.sqlite3"
    storage_dir = tmp_path / "doc_storage"
    storage_dir.mkdir()

    sent = []
    monkeypatch.setattr(pipeline, "get_connection", lambda: sqlite3.connect(database_path))
    monkeypatch.setattr(pipeline, "RECEIVER_EMAIL", "sales@example.com")
    monkeypatch.setattr(
        pipeline, "send_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )
    monkeypatch.setattr(pipeline, "DOCUMENT_ALLOWED_HOSTS", frozenset(["allowed.example.com"]))
    monkeypatch.setattr(pipeline, "DOCUMENT_STORAGE_DIR", str(storage_dir))

    # Mock candidate document retrieval
    from data.documents import DocumentResult
    mock_pdf_path = storage_dir / "sample.pdf"
    mock_pdf_path.write_bytes(b"%PDF-1.4 dummy content")

    def mock_retrieve(*args, **kwargs):
        return [
            DocumentResult(
                source_url="https://allowed.example.com/spec.pdf",
                status="downloaded",
                storage_path=str(mock_pdf_path),
                content_fingerprint="abc123fingerprint",
            )
        ]

    def mock_extract(storage_path, **kwargs):
        return {
            "status": "extracted",
            "source_url": "https://allowed.example.com/spec.pdf",
            "content_fingerprint": "abc123fingerprint",
            "extracted_at": "2026-10-22T00:00:00Z",
            "pages": [{"page": 1}],
            "fields": {
                "mandatory_requirements": [
                    {
                        "value": "chemical vapor deposition apparatus",
                        "evidence": {"page": 1, "quote": "chemical vapor deposition apparatus"},
                    }
                ]
            },
        }

    class EmptyMatcher:
        def match_topk(self, *args, **kwargs):
            return []

    monkeypatch.setattr(pipeline, "retrieve_candidate_documents", mock_retrieve)
    monkeypatch.setattr(pipeline, "extract_pdf_requirements", mock_extract)
    monkeypatch.setattr(pipeline, "build_matcher", lambda: EmptyMatcher())

    tender = {
        "tender_id": "REF-DOC-1",
        "title": "Thin Film CVD System Procurement",
        "organization": "Advanced Physics Center",
        "published_date": date.today().isoformat(),
        "closing_date": (date.today() + timedelta(days=30)).isoformat(),
        "source_portal": "cppp",
        "source_url": "https://eprocure.gov.in/tenders/REF-DOC-1",
        "document_links": ["https://allowed.example.com/spec.pdf"],
        "raw_text": "Supply of CVD deposition system",
    }
    monkeypatch.setattr(pipeline, "collect_all_tenders", lambda: [tender])
    monkeypatch.setattr(pipeline, "classify_tender", lambda *args, **kwargs: {
        "is_blocked": False,
        "has_signal": True,
        "category": "high_signal",
        "decision": "high_signal",
        "score": 90,
        "reason": "high signal cvd",
    })

    pipeline.run_pipeline()

    assert len(sent) == 1
    subject, body, recipient = sent[0]
    assert "Document review: Official PDF verified natively across 1 page(s)." in body
