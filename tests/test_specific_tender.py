"""Deterministic regression coverage for the previously debugged tender."""

from matching.filter import classify_tender


def test_thermovac_sputter_tender_is_retained_for_review():
    tender = {
        "title": "Thermal and Vacuum Cycling Chamber (Thermovac)",
        "organization": "Thermal and Vacuum Cycling Chamber (Thermovac)",
        "published_date": "08/04/2026",
        "raw_text": "Sputter Deposition Setupt",
    }

    result = classify_tender(tender)

    assert result["decision"] == "agent_review"
    assert result["agent_review_required"] is True
    assert "TECH_CONCEPT_SPUTTERING" in result["reason_codes"]
