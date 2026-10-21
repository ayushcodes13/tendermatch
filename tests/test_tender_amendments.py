import json
import sqlite3

import pytest

from data.amendments import compare_tender_versions
from data.db import get_tender_amendments, init_db, upsert_or_get_tender


def snapshot(**content):
    return {"content": {
        "title": "Supply of equipment",
        "organization": "Agency",
        "published_date": "2026-10-01",
        "updated_date": None,
        "corrigendum_date": None,
        "closing_date": "2026-11-01",
        "raw_text": "Supply of equipment",
        **content,
    }}


@pytest.mark.parametrize(
    ("old_text", "new_text", "expected", "status"),
    [
        ("Quantity: 10 units", "Quantity: 12 units", "quantity_changed", "meaningful"),
        ("Technical specification: flow rate 2 L/min", "Technical specification: flow rate 3 L/min", "technical_specification_changed", "meaningful"),
        ("ISO certificate required", "ISO certificate and test report required", "certification_requirement_changed", "meaningful"),
        ("Eligibility: 3 years experience", "Eligibility: 5 years experience", "eligibility_requirement_changed", "meaningful"),
        ("Tender open for bids", "Tender cancelled by authority", "cancellation_or_withdrawal", "needs_review"),
    ],
)
def test_text_amendment_categories_require_reviewable_evidence(old_text, new_text, expected, status):
    result = compare_tender_versions(snapshot(raw_text=old_text), snapshot(raw_text=new_text))
    assert result["status"] == status
    assert expected in result["change_types"]
    assert "raw_text" in result["evidence"]


def test_deadline_extension_and_corrigendum_are_reported_with_values():
    result = compare_tender_versions(
        snapshot(closing_date="01/11/2026"),
        snapshot(closing_date="2026-11-20", corrigendum_date="2026-10-20"),
    )
    assert result["status"] == "meaningful"
    assert "deadline_extended" in result["change_types"]
    assert "corrigendum_date_changed" in result["change_types"]
    assert result["evidence"]["closing_date"] == {
        "from": "01/11/2026", "to": "2026-11-20"
    }


def test_unparseable_deadline_change_is_not_reported_as_extension_or_shortening():
    result = compare_tender_versions(
        snapshot(closing_date="To be announced"),
        snapshot(closing_date="31/12/2026"),
    )
    assert result["status"] == "meaningful"
    assert "deadline_changed" in result["change_types"]
    assert "deadline_extended" not in result["change_types"]
    assert "deadline_shortened" not in result["change_types"]


def test_deadline_shortening_is_directionally_reported():
    result = compare_tender_versions(
        snapshot(closing_date="2026-11-20"),
        snapshot(closing_date="2026-11-10"),
    )
    assert result["status"] == "meaningful"
    assert "deadline_shortened" in result["change_types"]


def test_formatting_only_text_changes_are_not_meaningful():
    result = compare_tender_versions(
        snapshot(raw_text="Supply   of\nequipment"),
        snapshot(raw_text="supply of equipment"),
    )
    assert result == {"status": "formatting_only", "change_types": [], "evidence": {}}


def test_date_display_format_change_is_not_a_deadline_amendment():
    result = compare_tender_versions(
        snapshot(closing_date="01/11/2026", published_date="01/10/2026"),
        snapshot(closing_date="2026-11-01", published_date="2026-10-01"),
    )
    assert result["status"] == "formatting_only"
    assert result["change_types"] == []


def test_unclassified_substantive_change_is_routed_to_review():
    result = compare_tender_versions(
        snapshot(raw_text="Supply of equipment at Building A"),
        snapshot(raw_text="Supply of equipment at Building B"),
    )
    assert result["status"] == "needs_review"
    assert result["change_types"] == ["unclassified_content_change"]


def test_unchanged_technical_text_does_not_label_an_unrelated_change_as_specification():
    old_text = "Technical specification: flow rate 2 L/min\nDelivery location: Building A"
    new_text = "Technical specification: flow rate 2 L/min\nDelivery location: Building B"
    result = compare_tender_versions(
        snapshot(raw_text=old_text), snapshot(raw_text=new_text)
    )
    assert result["status"] == "needs_review"
    assert result["change_types"] == ["unclassified_content_change"]


def test_mixed_categorized_and_uncategorized_lines_require_review():
    old_text = "Technical specification: flow rate 2 L/min\nContact: old office"
    new_text = "Technical specification: flow rate 3 L/min\nContact: new office"
    result = compare_tender_versions(
        snapshot(raw_text=old_text), snapshot(raw_text=new_text)
    )
    assert result["status"] == "needs_review"
    assert "technical_specification_changed" in result["change_types"]
    assert "unclassified_content_change" in result["change_types"]


def test_upsert_persists_comparison_between_adjacent_content_versions():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    tender = {
        "tender_id": "REF-10",
        "title": "Pump procurement",
        "organization": "Agency",
        "closing_date": "2026-11-01",
        "source_portal": "cppp",
        "source_url": "https://example.test/tender/REF-10",
        "raw_text": "Technical specification: flow rate 2 L/min",
    }
    stored, _ = upsert_or_get_tender(conn, tender)
    updated, is_new = upsert_or_get_tender(conn, {
        **tender,
        "closing_date": "2026-11-20",
        "raw_text": "Technical specification: flow rate 3 L/min",
    })

    changes = get_tender_amendments(conn, stored["identity_key"])
    assert not is_new
    assert updated["version_fingerprint"] != stored["version_fingerprint"]
    assert len(changes) == 1
    assert changes[0]["status"] == "meaningful"
    assert changes[0]["from_fingerprint"] == stored["version_fingerprint"]
    assert changes[0]["to_fingerprint"] == updated["version_fingerprint"]
    assert {"deadline_extended", "technical_specification_changed"} <= set(changes[0]["change_types"])
    json.dumps(changes[0]["evidence"])
