import importlib
import sys
from types import ModuleType
from datetime import datetime, timezone

import pytest

from pipeline.freshness import (
    assess_tender_freshness,
    get_latest_tender_datetime,
    get_tender_date_status,
    parse_date,
    should_process_tender,
)
from scrapers.iisc_dates import extract_iisc_date_fields


NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value",
    [
        "21/10/2026",
        "21-10-2026",
        "2026-10-21",
        "21.10.2026",
        "21-Oct-2026 05:30 PM",
        "21-Oct-2026 05:30 PM IST",
        "2026-10-21T17:30:00+05:30",
        "2026-10-21T12:00:00Z",
    ],
)
def test_parses_supported_date_only_and_timezone_formats(value):
    assert parse_date(value) is not None


def test_naive_portal_datetime_uses_india_timezone_and_offsets_are_normalized():
    assert parse_date("2026-10-21T17:30") == parse_date("2026-10-21T12:00:00Z")


def test_recent_publication_update_open_and_expired_dates_are_distinguished():
    assert assess_tender_freshness(
        {"published_date": "2026-10-21T16:00:00+05:30"}, now=NOW
    ) == "recently_published"
    assert assess_tender_freshness(
        {"published_date": "2026-10-01", "corrigendum_date": "2026-10-21"},
        now=NOW,
    ) == "recently_updated"
    assert assess_tender_freshness(
        {"published_date": "2026-10-01", "closing_date": "22/10/2026"},
        now=NOW,
    ) == "still_open"
    assert assess_tender_freshness(
        {"published_date": "2026-10-21", "closing_date": "20/10/2026"},
        now=NOW,
    ) == "expired"
    assert get_tender_date_status(
        {"published_date": "2026-10-21", "closing_date": "22/10/2026"}, now=NOW
    ) == {"activity": "recently_published", "lifecycle": "still_open"}


def test_unknown_and_missing_dates_are_preserved_for_review():
    assert assess_tender_freshness({"published_date": "not a date"}, now=NOW) == "unknown"
    assert should_process_tender({"published_date": None}, now=NOW)
    assert assess_tender_freshness(
        {"published_date": "2026-10-01", "closing_date": "deadline TBD"}, now=NOW
    ) == "unknown"
    assert should_process_tender(
        {"published_date": "2026-10-01", "closing_date": "deadline TBD"}, now=NOW
    )


def test_definitely_stale_publication_without_open_deadline_is_not_fresh():
    tender = {"published_date": "2026-10-01", "title": "Tender (21/10/2026)"}
    assert assess_tender_freshness(tender, now=NOW) == "stale"
    assert get_latest_tender_datetime(tender) == parse_date("2026-10-01")
    assert not should_process_tender(tender, now=NOW)


def test_date_only_closing_date_remains_open_through_local_calendar_day():
    tender = {"published_date": "2026-10-01", "closing_date": "21/10/2026"}
    assert assess_tender_freshness(tender, now=NOW) == "still_open"
    assert should_process_tender(tender, now=NOW)


def test_cppp_timestamp_format_is_parsed_as_india_local_time():
    parsed = parse_date("21-Oct-2026 05:30 PM")
    assert parsed is not None
    assert parsed.utcoffset().total_seconds() == 0


@pytest.mark.parametrize(
    "source,publication,closing",
    [
        ("cppp", "21-Oct-2026 05:00 PM", "22-Oct-2026 05:00 PM"),
        ("iitm", "2026-10-21T17:00", "2026-10-22T17:00"),
        ("iisc", "21/10/2026", None),
        ("iit_goa", "21/10/2026", "22/10/2026"),
        ("iit_palakkad", "21/10/2026", "22/10/2026"),
    ],
)
def test_source_date_fixtures_are_classified_without_false_staleness(
    source, publication, closing
):
    tender = {"source_portal": source, "published_date": publication, "closing_date": closing}
    assert assess_tender_freshness(tender, now=NOW) == "recently_published"


def test_cppp_and_iitm_source_filters_keep_unknown_and_open_opportunities(monkeypatch):
    if "scrapers.cppp" not in sys.modules:
        bs4_stub = ModuleType("bs4")
        bs4_stub.BeautifulSoup = object
        monkeypatch.setitem(sys.modules, "bs4", bs4_stub)
    cppp = importlib.import_module("scrapers.cppp")
    iitm = importlib.import_module("scrapers.iitm")

    assert cppp.parse_date("21-Oct-2026 05:30 PM").utcoffset().total_seconds() == 0
    assert cppp.is_new_tender({"published_date": "unrecognized"})
    assert not cppp.is_new_tender(
        {"published_date": "21-Oct-2026 05:00 PM", "closing_date": "20-Oct-2026"}
    )
    assert iitm.is_recent_tender("not a date")
    assert iitm.is_recent_tender("2026-10-01", closing_date="2026-10-22")


def test_iisc_date_roles_do_not_turn_corrigendum_only_listing_into_new_publication():
    corrigendum_only = extract_iisc_date_fields("Corrigendum issued (21/10/2026)")
    assert corrigendum_only["published_date"] is None
    assert corrigendum_only["corrigendum_date"] == parse_date("21/10/2026")

    publication_and_corrigendum = extract_iisc_date_fields(
        "Supply notice (01/10/2026). Corrigendum issued (21/10/2026)"
    )
    assert publication_and_corrigendum["published_date"] == parse_date("01/10/2026")
    assert publication_and_corrigendum["corrigendum_date"] == parse_date("21/10/2026")


def test_recent_amendment_after_scraped_deadline_is_retained_for_review():
    tender = {
        "published_date": "2026-10-01",
        "corrigendum_date": "2026-10-21",
        "closing_date": "20/10/2026",
    }
    assert get_tender_date_status(tender, now=NOW) == {
        "activity": "recently_updated",
        "lifecycle": "unknown",
    }
    assert assess_tender_freshness(tender, now=NOW) == "recently_updated"
    assert should_process_tender(tender, now=NOW)
