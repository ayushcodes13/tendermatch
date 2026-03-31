"""
scrape_all
    → scrape central portal  (scrape_source)
        → open page 1         (scrape_page)
            → read 10 rows    (parse_tenders)
                → read 1 row  (parse_cppp_row)
        → open page 2
        → old tender found, stop
    → scrape state portal
    → scrape gem portal
    → combine everything → 1 big list
"""

import sys
import os
from pathlib import Path

# Add project root to sys.path to allow imports from other directories
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time


BASE_URLS = {
    "central": "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
    "state": "https://eprocure.gov.in/cppp/latestactivetendersnew/mmpdata",
    "gem": "https://eprocure.gov.in/cppp/latestactivetendersnew/gemdata"
}


def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%d-%b-%Y %I:%M %p")
    except:
        return None


def is_new_tender(tender, cutoff_hours=24):
    published = parse_date(tender.get("published_date", ""))
    if not published:
        return True
    cutoff = datetime.now() - timedelta(hours=cutoff_hours)
    return published >= cutoff


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def scrape_page(url, page, retries=3):
    full_url = f"{url}?page={page}"

    for attempt in range(retries):
        try:
            response = requests.get(full_url, headers=HEADERS, timeout=10)
            response.raise_for_status()

            time.sleep(0.5)

            soup = BeautifulSoup(response.content, "html.parser")
            return soup

        except requests.exceptions.RequestException as e:
            print(f"[Retry {attempt+1}] Error on {full_url}: {e}")
            time.sleep(1.5)

    print(f"[FAILED] Skipping page {page} after retries.")
    return None


def parse_cppp_row(cells, link):
    raw = cells[4].strip() if len(cells) > 4 else ""
    match = re.search(r'(GEM/\d{4}|[\w]+/\d{4}[_/])', raw)

    if match:
        title = raw[:match.start()].strip().rstrip("/").strip()
        tender_id = raw[match.start():].strip()
    else:
        title = raw
        tender_id = raw

    organization = cells[5].strip() if len(cells) > 5 else None

    raw_text = f"{title} {organization}" if organization else title

    return {
        "tender_id": tender_id,
        "title": title,
        "organization": organization,
        "published_date": cells[1].strip() if len(cells) > 1 else None,
        "closing_date": cells[2].strip() if len(cells) > 2 else None,
        "source_url": link,
        "raw_text": raw_text,
        "product_category": None,
        "source_type": "cppp"
    }


def parse_gem_row(cells, link):
    tender_id = cells[3].strip() if len(cells) > 3 else None
    product_category = cells[4].strip() if len(cells) > 4 else None
    organization = cells[5].strip() if len(cells) > 5 else None
    department = cells[6].strip() if len(cells) > 6 else None

    title = product_category

    raw_text_parts = [title, product_category, organization, department]
    raw_text = " ".join([part for part in raw_text_parts if part])

    return {
        "tender_id": tender_id,
        "title": title,
        "organization": organization,
        "published_date": cells[1].strip() if len(cells) > 1 else None,
        "closing_date": cells[2].strip() if len(cells) > 2 else None,
        "source_url": link,
        "raw_text": raw_text,
        "product_category": product_category,
        "source_type": "gem"
    }


def parse_tenders(soup, source):
    tenders = []
    table = soup.find("table")
    if not table:
        return tenders

    rows = table.find_all("tr")[1:]

    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) < 5:
            continue

        link_tag = row.find("a", href=True)
        href = link_tag["href"] if link_tag else None
        tender_url = href if href and href.startswith("http") else "https://eprocure.gov.in" + href if href else None

        if source == "gem":
            tender = parse_gem_row(cells, tender_url)
        else:
            tender = parse_cppp_row(cells, tender_url)

        tender["source_portal"] = source
        tender["scraped_at"] = datetime.now().isoformat()
        tenders.append(tender)

    return tenders


def scrape_source(source_key, max_pages=50, cutoff_hours=24):
    url = BASE_URLS[source_key]
    all_tenders = []

    for page in range(1, max_pages + 1):
        print(f"Scraping {source_key} page {page}...")

        soup = scrape_page(url, page)

        if not soup:
            print(f"[WARN] Skipping page {page} due to fetch failure.")
            continue

        tenders = parse_tenders(soup, source_key)

        if not tenders:
            break

        new_tenders = []
        stop = False

        for t in tenders:
            if is_new_tender(t, cutoff_hours):
                new_tenders.append(t)
            else:
                stop = True
                break

        all_tenders.extend(new_tenders)

        if stop:
            print(f"Reached old tenders at page {page}, stopping.")
            break

    return all_tenders


def scrape_all(max_pages=50, cutoff_hours=24):
    all_tenders = []
    for source in BASE_URLS.keys():
        tenders = scrape_source(source, max_pages=max_pages, cutoff_hours=cutoff_hours)
        all_tenders.extend(tenders)
    return all_tenders