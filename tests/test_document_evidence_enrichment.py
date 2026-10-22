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
    assert evidence["completeness"] == "coverage_not_assessed"
    assert "requirement coverage not assessed" in evidence["summary"]
    lifecycle = evidence["extraction_lifecycle"]
    assert lifecycle["pdf_downloaded"] is True
    assert lifecycle["native_text_extracted"] is True
    assert lifecycle["ocr_required"] is False
    assert lifecycle["extraction_truncated"] is False
    assert lifecycle["requirement_coverage_evaluated"] is False
    assert lifecycle["technical_compatibility_evaluated"] is True
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
            "completeness": "coverage_not_assessed",
            "summary": "Official PDF native text extracted across 4 page(s); requirement coverage not assessed.",
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
    assert "Document review: Official PDF native text extracted across 4 page(s); requirement coverage not assessed." in body
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
    assert "Document review: Official PDF native text extracted across 1 page(s); requirement coverage not assessed." in body


# ==============================================================================
# P0 Verification Semantics Tests: Numerical, Domains, Claims, and Scope
# ==============================================================================

def test_numerical_parameter_mismatch_creates_explicit_conflict():
    """Tender requiring 1500 C temperature when manufacturer max is 1100 C triggers explicit conflict."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX deposition system"],
            "known_limitations": ["Maximum process temperature is 1100 C"],
        }
    ]
    tender = {
        "title": "Ultra High Temperature Annealing System",
        "category": "high_signal",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Must support substrate heating up to 1500 C in high vacuum",
                    "evidence": {"page": 1, "quote": "Must support substrate heating up to 1500 C in high vacuum"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    evidence = enriched["document_evidence"]
    assert len(evidence["conflicts"]) == 1
    conflict = evidence["conflicts"][0]
    assert conflict["technical_compatibility"] == "explicit_conflict"
    assert "1500 °C" in conflict["conflict_reason"]
    assert "1100 °C" in conflict["conflict_reason"]
    assert enriched["category"] == "explore"


def test_incompatible_equipment_family_creates_explicit_conflict():
    """Tender requiring gas chromatography when manufacturer makes PVD triggers explicit conflict."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX PVD system"],
            "negative_keywords": ["gas chromatography", "medical infusion"],
        }
    ]
    tender = {
        "title": "Gas Chromatography System Procurement",
        "category": "high_signal",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Supply of dual-channel gas chromatography system with flame detector",
                    "evidence": {"page": 1, "quote": "Supply of dual-channel gas chromatography system with flame detector"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    assert len(enriched["document_evidence"]["conflicts"]) == 1
    assert "Incompatible equipment domain" in enriched["document_evidence"]["conflicts"][0]["conflict_reason"]


def test_source_scope_contradiction_does_not_create_false_conflict():
    """Tender explicitly excluding civil work from contractor scope must not trigger civil work conflict."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX deposition system", "thin film deposition"],
            "negative_keywords": ["civil construction"],
        }
    ]
    tender = {
        "title": "Thin Film Sputtering Unit",
        "category": "high_signal",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}, {"page": 2}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Civil construction works and foundation laying are strictly excluded from bidder scope; vendor only supplies deposition system",
                    "evidence": {"page": 2, "quote": "Civil construction works and foundation laying are strictly excluded from bidder scope"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    # The negative keyword 'civil construction' is excluded from bidder scope, so no conflict is raised
    assert len(enriched["document_evidence"]["conflicts"]) == 0
    assert enriched.get("has_document_conflicts") is not True


def test_missing_technical_specifications_flags_insufficient_evidence():
    """Generic equipment terms lacking technical specs must not become verified matches."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX deposition system"],
            "keywords": ["vacuum"],
        }
    ]
    tender = {
        "title": "Laboratory Procurement",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "technical_specifications": [
                {
                    "value": "vacuum pump",
                    "evidence": {"page": 1, "quote": "Item 1: vacuum pump"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    evidence = enriched["document_evidence"]
    assert len(evidence["verified_requirements"]) == 0
    assert "vacuum pump" in evidence["insufficient_evidence"]


def test_service_only_tender_against_equipment_maker_flags_conflict():
    """Third-party maintenance tenders against equipment manufacturers trigger conflict."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX PVD system"],
            "offered_services": ["training on HEX systems only"],
        }
    ]
    tender = {
        "title": "Third-Party AMC Tender",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Comprehensive annual maintenance contract for multi-vendor laboratory balances",
                    "evidence": {"page": 1, "quote": "Comprehensive annual maintenance contract for multi-vendor laboratory balances"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    assert len(enriched["document_evidence"]["conflicts"]) == 1
    assert "Service scope mismatch" in enriched["document_evidence"]["conflicts"][0]["conflict_reason"]


def test_model_specific_capability_mismatch_creates_conflict():
    """Tender requiring e-beam evaporation against sputtering-only platform creates conflict."""
    catalog = [
        {
            "id": "teer",
            "name": "Teer Coatings Limited",
            "products": ["UDP magnetron sputtering system"],
            "known_limitations": ["Platform is sputtering only; no e-beam evaporation supported"],
        }
    ]
    tender = {
        "title": "E-beam Evaporation System",
        "matches": [{"manufacturer_id": "teer", "manufacturer_name": "Teer Coatings Limited"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Must include electron beam evaporation source with 6-pocket turret",
                    "evidence": {"page": 1, "quote": "Must include electron beam evaporation source with 6-pocket turret"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    assert len(enriched["document_evidence"]["conflicts"]) == 1
    assert "Model capability mismatch" in enriched["document_evidence"]["conflicts"][0]["conflict_reason"]


def test_lexical_keyword_overlap_remains_candidate_not_promoted_to_verified():
    """General auxiliary keyword overlap without substantiated product capability remains lexical candidate."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX deposition system"],
            "keywords": ["vacuum chamber", "high precision", "mounting flange"],
        }
    ]
    tender = {
        "title": "Custom Metal Fabrication",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "technical_specifications": [
                {
                    "value": "High precision custom apparatus with vacuum chamber and mounting flange",
                    "evidence": {"page": 1, "quote": "High precision custom apparatus with vacuum chamber and mounting flange"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    evidence = enriched["document_evidence"]
    # Does NOT become verified requirement!
    assert len(evidence["verified_requirements"]) == 0
    # Remains in lexical candidates
    assert len(evidence["lexical_candidates"]) == 1
    candidate = evidence["lexical_candidates"][0]
    assert candidate["technical_compatibility"] == "lexical_candidate"
    assert "Lexical keyword overlap detected" in candidate["notes"]


def test_human_disposition_surfaced_on_assessed_requirements():
    """Salesperson adjudication feedback is tracked under human_disposition."""
    catalog = [
        {
            "id": "korvus",
            "name": "Korvus Technology",
            "products": ["HEX deposition system", "thin film deposition"],
        }
    ]
    tender = {
        "title": "Thin Film Research System",
        "matches": [{"manufacturer_id": "korvus", "manufacturer_name": "Korvus Technology"}],
        "feedback": [
            {
                "manufacturer_id": "korvus",
                "label": "worth_pursuing",
                "reviewer": "sales-lead@example.com",
            }
        ],
    }
    extraction = {
        "status": "extracted",
        "pages": [{"page": 1}],
        "fields": {
            "mandatory_requirements": [
                {
                    "value": "Modular thin film deposition system for educational research",
                    "evidence": {"page": 1, "quote": "Modular thin film deposition system for educational research"},
                }
            ]
        },
    }
    enriched = enrich_tender_with_document_evidence(tender, extraction, catalog)
    evidence = enriched["document_evidence"]
    assert len(evidence["verified_requirements"]) == 1
    req = evidence["verified_requirements"][0]
    assert req["human_disposition"] == "reviewed_worth_pursuing"
    assert req["technical_compatibility"] == "technical_match_supported"
    assert req["source_extraction_validity"] == "source_verified"
