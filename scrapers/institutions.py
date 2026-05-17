"""
Generic scraper for academic and research institution portals.

Pipeline role:
Acts as a fallback/generalized crawler for institutions that do not have 
a high-frequency API or complex HTML structure. Uses heuristic link analysis 
to identify likely tender documents.

Key responsibilities:
- Crawling a list of predefined institutional tender pages.
- Heuristic identification of 'tender-like' anchor tags.
- Normalizing diverse portal data into the unified tender schema.

Inputs:
- Static URLs from INSTITUTION_PORTALS dictionary.

Outputs:
- Normalized tender dictionaries (title, org, source_url, etc.).

Notes:
- Uses a simple keyword-in-text approach for link discovery.
- Normalization focuses on capturing the tender title and a valid 
  absolute URL for document retrieval.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

INSTITUTION_PORTALS = {
    "iit_bombay": "https://www.iitb.ac.in/tenders",
    "iit_madras": "https://www.iitm.ac.in/tenders",
    "iit_goa": "https://www.iitgoa.ac.in/tenders",
    "iit_palakkad": "https://iitpkd.ac.in/tenders",
    "isro": "https://www.isro.gov.in/tenders.html",
    "tifr": "https://www.tifr.res.in/tenders",
    "csir": "https://www.csir.res.in/tenders",
    "icmr": "https://main.icmr.nic.in/tenders",
    "npl": "https://www.nplindia.org/tenders",
    "ncl": "https://www.ncl-india.org/tenders",
    "cgcri": "https://www.cgcri.res.in/tenders",
    "nal": "https://www.nal.res.in/tenders"
}


def scrape_institution_page(url):
    """
    Fetches the HTML content of an institution's tender page.

    Args:
        url (str): Target URL.

    Returns:
        BeautifulSoup: Parsed HTML object, or None if the request fails.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return None


def parse_generic_links(soup, source_name, source_url):
    """
    Heuristically extracts tender links from a BeautifulSoup object.

    Args:
        soup (BeautifulSoup): Parsed HTML of the portal.
        source_name (str): Human-readable name of the institution.
        source_url (str): Base URL for resolving relative links.

    Returns:
        list: Collection of localized tender dictionaries.

    Notes:
        - Filters for links containing 'tender' or 'bid' in the anchor text.
        - Skips short or trivial text fragments (<15 chars).
    """
    tenders = []

    if not soup:
        return tenders

    links = soup.find_all("a", href=True)

    for link in links:
        text = link.get_text(strip=True)

        if not text or len(text) < 15:
            continue

        if "tender" not in text.lower() and "bid" not in text.lower():
            continue

        tender_url = link["href"]

        if not tender_url.startswith("http"):
            tender_url = source_url.rstrip("/") + "/" + tender_url.lstrip("/")

        tenders.append({
            "tender_id": f"{source_name}_{hash(text)}",
            "title": text,
            "organization": source_name,
            "published_date": None,
            "closing_date": None,
            "source_url": tender_url,
            "source_portal": source_name,
            "raw_text": text,
            "scraped_at": datetime.now().isoformat()
        })

    return tenders


def scrape_institution(source_name):
    """
    Main entry point for scraping a single institution.

    Args:
        source_name (str): Key matching INSTITUTION_PORTALS.

    Returns:
        list: Normalized tenders for that institution.
    """
    url = INSTITUTION_PORTALS[source_name]

    print(f"Scraping {source_name}...")

    soup = scrape_institution_page(url)

    return parse_generic_links(soup, source_name, url)


def scrape_all_institutions():
    """
    Orchestrates the scraping of all configured institution portals.

    Returns:
        list: Aggregated list of tenders from all sources.
    """
    all_tenders = []

    for source_name in INSTITUTION_PORTALS.keys():
        tenders = scrape_institution(source_name)
        all_tenders.extend(tenders)

    return all_tenders