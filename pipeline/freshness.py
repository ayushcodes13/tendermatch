"""
Tender freshness filtering.

Prevents old tenders from being emailed just because they appear in a scrape.
"""

from datetime import datetime, timedelta, timezone
import re


DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d %B %Y",
]


def is_recent_tender(tender, max_age_hours=24):
    """
    Returns True only if the tender has a recent publish/update date.

    Strict behavior:
    - If date is missing: False
    - If date cannot be parsed: False
    - If latest detected date is older than max_age_hours: False
    """
    latest_dt = get_latest_tender_datetime(tender)

    if not latest_dt:
        return False

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)

    return latest_dt >= cutoff


def get_latest_tender_datetime(tender):
    """
    Extracts the latest meaningful date from tender fields.

    Important for IISc-style titles:
    "Tender name (24/12/2025) Corrigendum (14/01/2026)"

    In that case, use 14/01/2026 as latest date.
    """
    candidates = []

    fields = [
        tender.get("published_date"),
        tender.get("updated_date"),
        tender.get("corrigendum_date"),
        tender.get("title"),
        tender.get("raw_text"),
    ]

    for value in fields:
        candidates.extend(extract_dates(value))

    if not candidates:
        return None

    return max(candidates)


def extract_dates(value):
    if not value:
        return []

    text = str(value)

    date_strings = []

    # 24/12/2025, 24-12-2025, 24.12.2025
    date_strings.extend(
        re.findall(r"\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{4}\b", text)
    )

    # 24 Dec 2025, 24 December 2025
    date_strings.extend(
        re.findall(
            r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
            r"January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{4}\b",
            text,
            flags=re.IGNORECASE,
        )
    )

    parsed = []

    for date_str in date_strings:
        dt = parse_date(date_str)
        if dt:
            parsed.append(dt)

    return parsed


def parse_date(value):
    text = str(value).strip()

    # Normalize Sept -> Sep
    text = re.sub(r"\bSept\b", "Sep", text, flags=re.IGNORECASE)

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None