"""
Tender scraper for Indian Institute of Technology (IIT) Goa.

Pipeline role:
Extracts tender information from the structured HTML tables of the 
IIT Goa portal. Captures regional and niche research requirements.

Key responsibilities:
- Scraping HTML tables from the IIT Goa portal.
- Normalizing table cells into standardized tender fields.
- Handling insecure SSL requests (required by some institution portals).

Notes:
- Disables insecure request warnings due to SSL configuration issues 
  on the target portal.
"""
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://iitgoa.ac.in/tenders/"


def scrape_iit_goa():
    """
    Main entry point for scraping IIT Goa tenders.

    Returns:
        list: Normalized tender dictionaries.
    """
    response = requests.get(
        URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
        verify=False
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")[1:]  # skip header

    tenders = []

    for row in rows:
        cells = row.find_all("td")

        if len(cells) < 4:
            continue

        published_date = cells[0].get_text(strip=True)
        title = cells[1].get_text(" ", strip=True)
        category = cells[2].get_text(strip=True)
        closing_date = cells[3].get_text(strip=True)

        link_tag = cells[1].find("a", href=True)
        doc_url = link_tag["href"] if link_tag else None

        tenders.append({
            "tender_id": title[:50],
            "title": title,
            "organization": "IIT Goa",
            "published_date": published_date,
            "closing_date": closing_date,
            "source_url": doc_url,
            "raw_text": f"{title} {category}",
            "source_type": "iit_goa",
            "source_portal": "iit_goa",
            "scraped_at": datetime.now().isoformat()
        })

    return tenders


if __name__ == "__main__":
    tenders = scrape_iit_goa()
    print(len(tenders))
    print(tenders[:3])