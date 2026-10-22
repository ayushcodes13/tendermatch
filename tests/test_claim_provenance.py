"""Tests for manufacturer claim-level provenance tracking, validation, and matching integration."""

import pytest

from matching.claim_provenance import (
    assess_candidate_claims,
    load_claims,
    validate_claims,
    VALID_CLAIM_TYPES,
    VALID_VALIDATION_STATES,
)
from matching.decision import decide_tender
from matching.matcher import TenderMatcher


@pytest.fixture
def sample_profiles():
    return [
        {
            "id": "korvus_technology",
            "name": "Korvus Technology",
            "country": "United Kingdom",
            "active": True,
            "website": "https://korvustech.com/",
            "embedding_text": "Korvus modular PVD systems.",
            "product_categories": ["thin film deposition systems", "PVD systems"],
            "products": ["HEX Series PVD systems"],
            "industries_served": ["material science"],
            "keywords": ["PVD", "sputtering"],
            "concepts": ["thin_film_deposition", "pvd"],
            "negative_keywords": [],
            "service_keywords": ["thin-film training"],
            "source_links": [
                "https://korvustech.com/pvd-systems/",
                "https://korvustech.com/pvd-teaching-and-training/",
            ],
            "profile_version": "1.0",
            "profile_last_updated": "2026-10-22",
        },
        {
            "id": "nippon_instruments",
            "name": "Nippon Instruments Corporation",
            "country": "Japan",
            "active": True,
            "website": "https://www.hg-nic.com/",
            "embedding_text": "NIC mercury analyzers.",
            "product_categories": ["mercury analyzers"],
            "products": ["MA Series direct mercury analyzers"],
            "industries_served": ["environmental testing"],
            "keywords": ["mercury analyzer"],
            "concepts": ["mercury_analysis"],
            "negative_keywords": [],
            "service_keywords": ["customer support"],
            "source_links": [
                "https://www.hg-nic.com/products/",
                "https://www.hg-nic.com/industries-application/",
            ],
            "profile_version": "1.0",
            "profile_last_updated": "2026-10-22",
        },
    ]


@pytest.fixture
def sample_claims():
    return [
        {
            "claim_id": "KORVUS-PVD-001",
            "manufacturer_id": "korvus_technology",
            "claim_type": "product",
            "claim_text": "HEX Series modular PVD systems supporting sputtering and evaporation.",
            "claim_term": "HEX Series PVD systems",
            "source_url": "https://korvustech.com/pvd-systems/",
            "source_locator": "Overview Section",
            "supporting_quote": "HEX Series modular research PVD systems.",
            "validation_state": "validated_capability",
            "last_verified_date": "2026-10-22",
            "known_limitations": ["Requires turbo-molecular pump package"],
        },
        {
            "claim_id": "KORVUS-TRAIN-001",
            "manufacturer_id": "korvus_technology",
            "claim_type": "service",
            "claim_text": "Thin-film and PVD training modules.",
            "claim_term": "thin-film training",
            "source_url": "https://korvustech.com/pvd-teaching-and-training/",
            "source_locator": "Training Section",
            "supporting_quote": "Korvus publishes teaching and training resources.",
            "validation_state": "conditional_service",
            "last_verified_date": "2026-10-22",
            "known_limitations": ["On-site training requires separate quotation"],
        },
    ]


def test_canonical_claims_file_validates_without_errors():
    """Verify that the checked-in data/manufacturer_claims.json is completely valid."""
    import json
    from pathlib import Path

    claims = load_claims()
    assert len(claims) >= 14, "Expected claim provenance records across all catalog manufacturers"

    profiles = json.loads(Path("data/manufacturers.json").read_text(encoding="utf-8"))
    issues = validate_claims(claims, profiles)
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    assert not errors, f"Canonical claims registry has errors: {errors}"
    assert not warnings, f"Canonical claims registry has warnings: {warnings}"


def test_claim_validation_detects_structural_and_semantic_errors(sample_profiles, sample_claims):
    # 1. Invalid claim_id pattern
    bad_id = dict(sample_claims[0], claim_id="bad id with spaces")
    issues = validate_claims([bad_id], sample_profiles)
    assert any(i["code"] == "invalid_claim_id" for i in issues)

    # 2. Duplicate claim_id
    duplicate = [sample_claims[0], sample_claims[0]]
    issues = validate_claims(duplicate, sample_profiles)
    assert any(i["code"] == "duplicate_claim_id" for i in issues)

    # 3. Unknown manufacturer
    bad_mfr = dict(sample_claims[0], manufacturer_id="nonexistent_maker")
    issues = validate_claims([bad_mfr], sample_profiles)
    assert any(i["code"] == "unknown_manufacturer" for i in issues)

    # 4. Invalid validation state
    bad_state = dict(sample_claims[0], validation_state="definitely_super_true")
    issues = validate_claims([bad_state], sample_profiles)
    assert any(i["code"] == "invalid_validation_state" for i in issues)

    # 5. Invalid date
    bad_date = dict(sample_claims[0], last_verified_date="2026-99-99")
    issues = validate_claims([bad_date], sample_profiles)
    assert any(i["code"] in {"invalid_date", "invalid_calendar_date"} for i in issues)

    # 6. Unregistered source link produces warning
    unregistered_url = dict(sample_claims[0], source_url="https://other-domain.org/doc.pdf")
    issues = validate_claims([unregistered_url], sample_profiles)
    assert any(i["code"] == "unregistered_source_url" for i in issues)


def test_assess_candidate_claims_categorization(sample_claims):
    # Candidate with verified product hit
    candidate = {
        "manufacturer_id": "korvus_technology",
        "product_hits": ["HEX Series PVD systems"],
        "service_hits": [],
    }
    assessment = assess_candidate_claims(candidate, sample_claims)
    assert assessment["claim_status"] == "fully_verified"
    assert len(assessment["verified_claims"]) == 1
    assert assessment["verified_claims"][0]["claim_id"] == "KORVUS-PVD-001"
    assert len(assessment["claim_warnings"]) == 1
    assert "turbo-molecular pump" in assessment["claim_warnings"][0]

    # Candidate with conditional service hit
    candidate_service = {
        "manufacturer_id": "korvus_technology",
        "product_hits": [],
        "service_hits": ["thin-film training"],
    }
    assessment_service = assess_candidate_claims(candidate_service, sample_claims)
    assert assessment_service["claim_status"] == "unverified"
    assert len(assessment_service["uncertain_claims"]) == 1
    assert "Uncertain claim" in assessment_service["claim_warnings"][0]


def test_unsupported_claim_conflict_forces_agent_review(sample_claims):
    # Add an unsupported claim
    conflicting_claims = list(sample_claims) + [
        {
            "claim_id": "KORVUS-OLED-001",
            "manufacturer_id": "korvus_technology",
            "claim_type": "capability",
            "claim_text": "Industrial OLED display mass production line.",
            "claim_term": "OLED mass production",
            "source_url": "https://korvustech.com/pvd-systems/",
            "source_locator": "Scope Notice",
            "supporting_quote": "HEX systems are intended for laboratory research, not industrial mass production.",
            "validation_state": "unsupported",
            "last_verified_date": "2026-10-22",
            "known_limitations": ["Industrial mass production unsupported"],
        }
    ]

    candidate = {
        "manufacturer_id": "korvus_technology",
        "product_hits": ["OLED mass production"],
        "keyword_hits": [],
    }
    assessment = assess_candidate_claims(candidate, conflicting_claims)
    assert assessment["claim_status"] == "has_conflicts"
    assert len(assessment["unsupported_claims"]) == 1

    # In decide_tender, a candidate with claim conflict must require agent_review
    signals = {}
    concepts = {"has_rescue_concept": True}
    scoring = {"score": 95}  # Would normally be clean high_signal
    manufacturer_candidates = [
        {
            "manufacturer_id": "korvus_technology",
            "score": 0.92,
            "keyword_hits": ["OLED mass production"],
            "claim_provenance": assessment,
        }
    ]

    decision = decide_tender(
        signals=signals,
        concepts=concepts,
        scoring=scoring,
        manufacturer_candidates=manufacturer_candidates,
    )

    assert decision["decision"] == "agent_review"
    assert decision["agent_review_required"] is True
    assert "UNSUPPORTED_MANUFACTURER_CLAIM_CONFLICT" in decision["reason_codes"]
