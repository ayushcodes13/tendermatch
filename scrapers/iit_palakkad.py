# scrapers/iit_palakkad.py

import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://iitpkd.ac.in"
URL = f"{BASE_URL}/tenders"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def scrape_iit_palakkad():
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=20
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    tenders = []

    table = soup.find("table")
    if not table:
        return tenders

    rows = table.find_all("tr")[1:]  # skip header

    for row in rows:
        cells = row.find_all("td")

        if len(cells) < 6:
            continue

        tender_no = cells[0].get_text(strip=True)
        title = cells[1].get_text(strip=True)
        open_date = cells[2].get_text(strip=True)
        close_date = cells[3].get_text(strip=True)

        # collect ALL document links
        doc_links = cells[4].find_all("a", href=True)
        all_docs = []

        for link in doc_links:
            href = link["href"]

            full_url = (
                BASE_URL + href
                if href.startswith("/")
                else href
            )

            all_docs.append(full_url)

        remarks = cells[5].get_text(" ", strip=True)

        tenders.append({
            "tender_id": tender_no,
            "title": title,
            "organization": "IIT Palakkad",
            "published_date": open_date,
            "closing_date": close_date,
            "source_url": all_docs[0] if all_docs else None,
            "document_links": all_docs,
            "raw_text": f"{title} {remarks}",
            "source_type": "iit_palakkad",
            "source_portal": "iit_palakkad",
            "scraped_at": datetime.now().isoformat()
        })

    return tenders


if __name__ == "__main__":
    tenders = scrape_iit_palakkad()

    print(len(tenders))
    for t in tenders[:3]:
        print(t)