"""Date parsing and conservative freshness decisions for scraped tenders."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import re


SOURCE_TIMEZONE = ZoneInfo("Asia/Kolkata")
DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y",
    "%d-%b-%Y", "%d %b %Y", "%d %B %Y",
    "%d-%b-%Y %I:%M %p", "%d-%b-%Y %I:%M:%S %p",
    "%d-%b-%Y %I:%M %p%z", "%d-%b-%Y %I:%M:%S %p%z",
    "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M%z", "%d/%m/%Y %H:%M:%S%z",
    "%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M%z", "%d-%m-%Y %H:%M:%S%z",
    "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
)


def parse_date(value, *, end_of_day=False):
    """Parse common tender dates, preserving offsets and assigning IST to naive values.

    Date-only closing dates are treated as inclusive through the end of that
    local calendar day. Unrecognized or absent values return ``None``.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time(23, 59, 59) if end_of_day else time.min)
    else:
        text = str(value).strip()
        if not text:
            return None
        normalized = re.sub(r"\bSept\b", "Sep", text, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+IST$", "+05:30", normalized, flags=re.IGNORECASE)
        normalized = re.sub(
            r"\s+(?:UTC|GMT)$", "+00:00", normalized, flags=re.IGNORECASE
        )
        iso_text = (
            normalized[:-1] + "+00:00"
            if normalized.endswith(("Z", "z"))
            else normalized
        )
        try:
            parsed = datetime.fromisoformat(iso_text)
        except ValueError:
            parsed = None
            for fmt in DATE_FORMATS:
                try:
                    parsed = datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    pass
            if parsed is None:
                # Some portals append a timezone offset separated by a space.
                match = re.fullmatch(r"(.+?)\s+([+-]\d{2}:?\d{2})", normalized)
                if match:
                    try:
                        parsed = datetime.fromisoformat(
                            f"{match.group(1)}{match.group(2)}"
                        )
                    except ValueError:
                        return None
                else:
                    return None
        if end_of_day and _is_date_only(normalized):
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=0)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SOURCE_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def _is_date_only(text):
    return not re.search(r"\d{1,2}:\d{2}", text)


def assess_tender_freshness(tender, max_age_hours=24, *, now=None):
    """Classify dates without treating unknown values as proof of staleness.

    Returns a stable status string: ``recently_published``, ``recently_updated``,
    ``still_open``, ``expired``, ``stale``, or ``unknown``.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=SOURCE_TIMEZONE)
    now = now.astimezone(timezone.utc)
    details = get_tender_date_status(tender, max_age_hours, now=now)
    lifecycle = details["lifecycle"]
    activity = details["activity"]
    if lifecycle == "expired":
        return "expired"
    if activity in {"recently_published", "recently_updated"}:
        return activity
    if lifecycle == "still_open":
        return "still_open"
    return activity


def get_tender_date_status(tender, max_age_hours=24, *, now=None):
    """Return independent recency and lifecycle classifications for auditability."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=SOURCE_TIMEZONE)
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)

    published = parse_date(tender.get("published_date"))
    raw_updates = [tender.get(key) for key in ("updated_date", "corrigendum_date")]
    parsed_updates = [parse_date(value) for value in raw_updates]
    updates = [value for value in parsed_updates if value is not None]
    raw_closing = tender.get("closing_date")
    closing = parse_date(raw_closing, end_of_day=True)

    if published is not None and published >= cutoff:
        activity = "recently_published"
    elif any(value >= cutoff for value in updates):
        activity = "recently_updated"
    elif published is not None or updates:
        activity = "stale"
    else:
        activity = "unknown"

    if closing is not None and closing < now:
        lifecycle = "expired"
    elif closing is not None:
        lifecycle = "still_open"
    else:
        lifecycle = "unknown"

    if (raw_closing and closing is None) or any(
        raw and parsed is None for raw, parsed in zip(raw_updates, parsed_updates)
    ):
        if lifecycle != "expired":
            lifecycle = "unknown"
        if activity == "stale":
            activity = "unknown"

    if closing is not None and closing < now and any(
        update is not None and update > closing for update in updates
    ):
        # The closing date predates an amendment. The scraped deadline may not
        # reflect an extension, so do not treat the tender as definitely closed.
        lifecycle = "unknown"
        if activity == "stale":
            activity = "unknown"

    return {"activity": activity, "lifecycle": lifecycle}


def should_process_tender(tender, max_age_hours=24, *, now=None):
    """Keep new, updated, open, and date-unknown tenders; exclude definite stale/expired."""
    return assess_tender_freshness(tender, max_age_hours, now=now) not in {
        "stale", "expired"
    }


def is_recent_tender(tender, max_age_hours=24):
    """Backward-compatible conservative predicate used by the pipeline."""
    return should_process_tender(tender, max_age_hours)


def get_latest_tender_datetime(tender):
    """Return latest explicitly typed publication/update/corrigendum date."""
    candidates = [
        parse_date(tender.get(key))
        for key in ("published_date", "updated_date", "corrigendum_date")
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    return max(candidates) if candidates else None


def extract_dates(value):
    """Compatibility helper returning parsed dates found inside free text."""
    if not value:
        return []
    text = str(value)
    candidates = re.findall(
        r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}\b|"
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
        r"January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{4}\b",
        text,
        flags=re.IGNORECASE,
    )
    return [parsed for item in candidates if (parsed := parse_date(item)) is not None]
