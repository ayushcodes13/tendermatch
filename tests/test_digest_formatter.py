from digest.formatter import format_email


def test_format_email_uses_pipeline_stats_and_reports_all_skip_counts():
    stats = {
        "total_scraped": 12,
        "fresh_processed": 7,
        "duplicates_skipped": 1,
        "stale_skipped": 2,
        "expired_skipped": 3,
        "already_emailed_skipped": 1,
        "high": 1,
        "explore": 2,
        "low": 2,
        "blocked": 2,
    }
    high_tenders = [
        {
            "title": "Supply of a spectrometer",
            "organization": "Research Institute",
            "matches": [],
        }
    ]
    explore_tenders = [
        {
            "title": "Laboratory equipment",
            "organization": "Research Institute",
        }
    ]

    subject, body = format_email(high_tenders, explore_tenders, stats)

    assert subject == "Tender Intelligence Report | 1 High-Signal Opportunity"
    assert "Total scraped: 12" in body
    assert "Fresh tenders processed: 7" in body
    assert "High-signal opportunities: 1" in body
    assert "Exploration candidates: 2" in body
    assert "Low-signal tenders: 2" in body
    assert "Blocked tenders: 2" in body
    assert "Stale tenders skipped: 2" in body
    assert "Expired tenders skipped: 3" in body
    assert "Duplicates skipped: 1" in body
    assert "Previously emailed skipped: 1" in body
    assert "CONFIDENCE" not in body


def test_format_email_handles_empty_digest_and_missing_optional_stats():
    subject, body = format_email([], [], {})

    assert subject == "Tender Intelligence Report | 0 High-Signal Opportunities"
    assert "Total scraped: 0" in body
    assert "Expired tenders skipped: 0" in body
    assert "No high-signal opportunities identified." in body
    assert "EXPLORATION (REQUIRES REVIEW)" in body
    assert "No exploration candidates require review." in body


def test_format_email_renders_amendment_update_separately():
    subject, body = format_email([], [], {}, updated_tenders=[{
        "title": "Pump procurement",
        "organization": "Agency",
        "source_url": "https://agency.example/tender/1",
        "amendment": {
            "status": "meaningful",
            "change_types": ["deadline_extended"],
            "evidence": {"closing_date": {"from": "2026-11-01", "to": "2026-11-20"}},
        },
    }])

    assert subject == "Tender Intelligence Update | 1 Updated"
    assert "UPDATED TENDERS" in body
    assert "Closing date extended from 2026-11-01 to 2026-11-20." in body
    assert "https://agency.example/tender/1" in body


def test_actionable_digest_includes_evidence_concerns_and_next_steps_without_scores():
    tender = {
        "title": "Supply of an industrial vacuum system",
        "organization": "Research Institute",
        "tender_id": "REF-2026-17",
        "closing_date": "2026-11-30",
        "source_url": "https://procurement.example.gov/tender/REF-2026-17",
        "matches": [{
            "manufacturer_name": "Vacuum Maker",
            "score": 0.95,
            "product_hits": ["Dry screw vacuum pumps"],
            "category_hits": ["Industrial vacuum systems"],
            "concept_hits": ["vacuum generation"],
            "keyword_hits": ["dry screw"],
            "negative_hits": ["maintenance-only scope"],
        }],
        "classification": {
            "explanation": {
                "unverified_requirements": [
                    "Manufacturer eligibility is not verified.",
                    "Delivery capability is not established.",
                ],
                "negative_evidence": {"domain_review_hits": [{"rule_id": "maintenance_scope"}]},
            }
        },
    }

    _, body = format_email([tender], [], {})

    assert "Tender reference: REF-2026-17" in body
    assert "Status: New to this recipient's digest" in body
    assert "Closing date: 2026-11-30" in body
    assert "Vacuum Maker" in body
    assert "Product family: Dry screw vacuum pumps, Industrial vacuum systems" in body
    assert "Why it matched: vacuum generation, dry screw" in body
    assert "Known concerns: maintenance-only scope" in body
    assert "Manufacturer eligibility is not verified." in body
    assert "Suggested next action: Check the official requirements" in body
    assert "https://procurement.example.gov/tender/REF-2026-17" in body
    assert "0.95" not in body
    assert "confidence" not in body.lower()


def test_exploration_candidate_is_clearly_reviewable_and_invalid_link_is_not_rendered():
    _, body = format_email([], [{
        "title": "Possible laboratory instrument purchase",
        "organization": "Institute",
        "source_url": "javascript:alert(1)",
        "matches": [],
    }], {})

    assert "Potential opportunity; needs review" in body
    assert "Manufacturer/product fit: No manufacturer match details attached" in body
    assert "No valid HTTP(S) source link recorded" in body
    assert "javascript:" not in body
    assert "confirm product fit and eligibility before pursuing" in body


def test_manufacturer_profile_warning_is_rendered_as_evidence_to_confirm():
    _, body = format_email([{
        "title": "Laboratory instrument supply",
        "organization": "Institute",
        "matches": [{
            "manufacturer_name": "Instrument Supplier",
            "profile_warnings": ["Verify current regional authorization before relying on distributor support."],
        }],
    }], [], {})

    assert "Evidence to confirm: Verify current regional authorization" in body


def test_amendment_digest_includes_updated_opportunity_context_once():
    _, body = format_email([], [], {}, updated_tenders=[{
        "title": "Pump procurement",
        "organization": "Agency",
        "tender_id": "AG-21",
        "closing_date": "2026-11-20",
        "source_url": "https://agency.example/tender/AG-21",
        "amendment": {
            "status": "meaningful",
            "change_types": ["deadline_extended"],
            "evidence": {"closing_date": {"from": "2026-11-01", "to": "2026-11-20"}},
        },
    }])

    assert body.count("Pump procurement") == 1
    assert "Status: Updated opportunity" in body
    assert "Tender reference: AG-21" in body
    assert "Closing date: 2026-11-20" in body
    assert "Closing date extended from 2026-11-01 to 2026-11-20." in body
    assert "Review the amendment" in body
