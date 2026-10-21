from digest.formatter import format_email


def test_format_email_uses_pipeline_stats_and_reports_all_skip_counts():
    stats = {
        "total_scraped": 12,
        "fresh_processed": 7,
        "duplicates_skipped": 1,
        "stale_skipped": 2,
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
    assert "Duplicates skipped: 1" in body
    assert "Previously emailed skipped: 1" in body
    assert "CONFIDENCE" not in body


def test_format_email_handles_empty_digest_and_missing_optional_stats():
    subject, body = format_email([], [], {})

    assert subject == "Tender Intelligence Report | 0 High-Signal Opportunities"
    assert "Total scraped: 0" in body
    assert "No high-signal opportunities identified." in body
    assert "EXPLORATION (REQUIRES REVIEW)" in body


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
