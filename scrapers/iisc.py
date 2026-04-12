"""
IISc Bangalore tender scraper
HTML structure based scraper
"""

import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://iisc.ac.in/all-tenders/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def extract_date(text):
    match = re.search(r"\((\d{2}/\d{2}/\d{4})\)", text)

    if not match:
        return None

    try:
        return datetime.strptime(match.group(1), "%d/%m/%Y")
    except:
        return None


def looks_like_tender(text):
    keywords = [
        "tender",
        "rfq",
        "rfb",
        "eoi",
        "quotation",
        "bid"
    ]

    text_lower = text.lower()

    return any(k in text_lower for k in keywords)


def scrape_iisc():
    response = requests.get(URL, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    tenders = []

    # CRITICAL FIX: scrape list items directly
    list_items = soup.find_all("li")

    for item in list_items:
        text = item.get_text(" ", strip=True)

        if not text:
            continue

        if not looks_like_tender(text):
            continue

        published_date = extract_date(text)

        tender = {
            "tender_id": f"iisc_{abs(hash(text))}",
            "title": text,
            "organization": "Indian Institute of Science Bangalore",
            "published_date": published_date.isoformat() if published_date else None,
            "closing_date": None,
            "source_url": URL,
            "source_portal": "iisc",
            "raw_text": text,
            "scraped_at": datetime.now().isoformat()
        }

        tenders.append(tender)

    print(f"IISc total tenders scraped: {len(tenders)}")

    return tenders


if __name__ == "__main__":
    tenders = scrape_iisc()

    print(f"\nTotal: {len(tenders)}")

    for t in tenders[:20]:
        print(t["title"])