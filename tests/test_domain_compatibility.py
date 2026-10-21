"""Contextual domain collisions must stay reviewable, not auto-rejected."""

import pytest

from matching.filter import classify_tender
from matching.signals import detect_domain_review_hits


@pytest.mark.parametrize(
    ("title", "rule_id"),
    [
        (
            "Procurement of medical infusion pumps with patient dose controls and an industrial water transfer pump for the cooling loop",
            "PUMP_MEDICAL_INDUSTRIAL_COLLISION",
        ),
        (
            "Supply of a high-vacuum laboratory chamber and commercial vacuum cleaners for floor cleaning",
            "LAB_VACUUM_CLEANING_COLLISION",
        ),
        (
            "Procurement of a PVD deposition chamber with a 33 kV substation extension and cable line shifting",
            "PROCESS_EQUIPMENT_ELECTRICAL_INFRASTRUCTURE_COLLISION",
        ),
        (
            "Research magnetron sputtering PVD system; mandatory clause says no vacuum and prohibits deposition sources",
            "CONFLICTING_PROCESS_SPECIFICATIONS",
        ),
    ],
)
def test_conflicting_domains_and_specifications_go_to_review(title, rule_id):
    result = classify_tender({"title": title})

    assert result["decision"] == "agent_review"
    assert result["agent_review_required"] is True
    assert f"DOMAIN_COMPATIBILITY_REVIEW_{rule_id}" in result["reason_codes"]
    assert len(result["reason_codes"]) == len(set(result["reason_codes"]))


@pytest.mark.parametrize(
    "title",
    [
        "Supply of medical infusion pumps with patient dose controls for hospital wards",
        "Supply of an industrial water transfer pump for a manufacturing cooling loop",
        "Purchase of a commercial vacuum cleaner for office floor cleaning",
        "Procurement of a research PVD deposition chamber",
    ],
)
def test_single_domain_does_not_trigger_a_cross_domain_conflict(title):
    assert detect_domain_review_hits(title.lower()) == []


def test_new_equipment_purchase_survives_separate_existing_asset_amc():
    result = classify_tender({
        "title": "Purchase of a new research PVD sputtering system; annual maintenance is for a separate existing chamber"
    })

    assert result["decision"] == "high_signal"
    assert "SOFT_RISK_RESCUED_HIGH_CONFIDENCE" in result["reason_codes"]
