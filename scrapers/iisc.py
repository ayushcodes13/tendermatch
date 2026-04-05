"""
IISc Bangalore tender scraper
Static webpage + strict 24 hour freshness
"""

import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

URL = "https://iisc.ac.in/all-tenders/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def extract_date(text):
    """
    Extract first tender publish date from line
    Example: (04/04/2026)
    """
    match = re.search(r"\((\d{2}/\d{2}/\d{4})\)", text)

    if not match:
        return None

    try:
        return datetime.strptime(match.group(1), "%d/%m/%Y")
    except ValueError:
        return None


def is_fresh_24h(dt):
    if not dt:
        return False

    return datetime.now() - dt <= timedelta(hours=24)


def looks_like_tender(line):
    keywords = [
        "tender",
        "rfq",
        "rfb",
        "eoi",
        "quotation",
        "bid"
    ]

    line_lower = line.lower()

    return any(k in line_lower for k in keywords)


def scrape_iisc():
    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    lines = soup.get_text("\n", strip=True).split("\n")

    tenders = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if not looks_like_tender(line):
            continue

        published_date = extract_date(line)

        # STRICT 24H FILTER
        if not is_fresh_24h(published_date):
            continue

        tender = {
            "tender_id": f"iisc_{abs(hash(line))}",
            "title": line,
            "organization": "Indian Institute of Science Bangalore",
            "published_date": published_date.isoformat(),
            "closing_date": None,
            "source_url": URL,
            "source_portal": "iisc",
            "raw_text": line,
            "scraped_at": datetime.now().isoformat()
        }

        tenders.append(tender)

    print(f"IISc fresh tenders (24h): {len(tenders)}")

    return tenders


if __name__ == "__main__":
    tenders = scrape_iisc()

    print(len(tenders))
    for t in tenders[:5]:
        print(t["title"])