from datetime import datetime
import requests
from bs4 import BeautifulSoup

from matching.filter import classify_tender
from matching.embedder import build_matcher

URL = "https://iisc.ac.in/all-tenders/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


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


def scrape_first_100_iisc():
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

        tender = {
            "tender_id": f"iisc_{abs(hash(line))}",
            "title": line,
            "organization": "Indian Institute of Science Bangalore",
            "published_date": None,
            "closing_date": None,
            "source_url": URL,
            "source_portal": "iisc",
            "raw_text": line,
            "scraped_at": datetime.now().isoformat()
        }

        tenders.append(tender)

        if len(tenders) >= 100:
            break

    return tenders


def test_iisc_first_100():
    print("=" * 80)
    print("IISC FIRST 100 PIPELINE TEST")
    print("=" * 80)

    tenders = scrape_first_100_iisc()
    matcher = build_matcher()

    print(f"\nTOTAL CHECKED: {len(tenders)}\n")

    for i, tender in enumerate(tenders, 1):
        print("=" * 80)
        print(f"TENDER {i}")
        print("=" * 80)
        print(f"TITLE: {tender['title']}")

        result = classify_tender(tender)

        print("\n[CLASSIFICATION]")
        print(result)

        if result["category"] == "high_signal":
            matches = matcher.match(tender)

            print("\n[MATCHES]")
            if matches:
                for idx, match in enumerate(matches, 1):
                    print(f"{idx}. {match}")
            else:
                print("No matches found")

        print()


if __name__ == "__main__":
    test_iisc_first_100()