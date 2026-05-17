"""
Tender scraper for Indian Institute of Technology (IIT) Madras.

Pipeline role:
Fetches structured tender data from the IITM API. This is one of the 
fastest scrapers in the pipeline due to the direct JSON access.

Key responsibilities:
- Consuming the IITM Tender API.
- Filtering for 'recent' tenders within a 24-hour window by default.
- Constructing valid deep-links to tender detail pages.

Inputs:
- IITM API endpoint.

Outputs:
- Normalized tender dictionaries.
"""

import requests
from datetime import datetime, timedelta

API_URL = "https://tenders.iitm.ac.in/tenderapi/listtender"


def is_recent_tender(opening_date, cutoff_hours=24):
    """
    Checks if an IITM tender is within the freshness cutoff.

    Args:
        opening_date (str): Date string in format "%Y-%m-%dT%H:%M".
        cutoff_hours (int): Sliding window duration in hours.

    Returns:
        bool: True if newer than the cutoff.
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
    """
    Main entry point for scraping IIT Madras tenders.

    Args:
        cutoff_hours (int): Time window for filtering.

    Returns:
        list: Normalized tender dictionaries.
    """
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