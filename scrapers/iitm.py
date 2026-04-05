"""
IIT Madras tender scraper
    → fetch JSON api
    → filter recent tenders by opening date
    → normalize tenders
    → return structured list
"""

import requests
from datetime import datetime, timedelta

API_URL = "https://tenders.iitm.ac.in/tenderapi/listtender"


def is_recent_tender(opening_date, cutoff_hours=24):
    """
    IITM uses format: 2026-03-25T14:00
    """
    if not opening_date:
        return True

    try:
        published = datetime.strptime(
            opening_date,
            "%Y-%m-%dT%H:%M"
        )
    except Exception:
        return True

    cutoff = datetime.now() - timedelta(hours=cutoff_hours)

    return published >= cutoff


def scrape_iitm(cutoff_hours=24):
    response = requests.get(API_URL, timeout=20)
    response.raise_for_status()

    data = response.json()

    tenders = []

    for tender in data:
        opening_date = tender.get("openingdatevalue")

        # freshness filter
        if not is_recent_tender(opening_date, cutoff_hours):
            continue

        tenders.append({
            "tender_id": tender.get("referencenumber"),
            "title": tender.get("tendertitle"),
            "organization": "Indian Institute of Technology Madras",
            "published_date": opening_date,
            "closing_date": tender.get("closingdatevalue"),
            "source_url": (
                "https://tenders.iitm.ac.in/viewnewtender.html"
                f"?formid={tender.get('formid')}"
            ),
            "source_portal": "iitm",
            "raw_text": (
                f"{tender.get('tendertitle', '')} "
                f"{tender.get('tenderdescription', '')} "
                f"{tender.get('keywords', '')}"
            ).strip(),
            "scraped_at": datetime.now().isoformat()
        })

    return tenders