"""
Manual debugger for the IISc Bangalore tender scraper.

Purpose:
Executes the IISc scraper in isolation and provides a detailed console breakdown 
of each scraped tender to verify parsing correctness on live HTML.
"""
from scrapers.iisc import scrape_iisc

def main():
    print("=" * 80)
    print("LIVE IISc SCRAPE DEBUG")
    print("=" * 80)

    tenders = scrape_iisc()

    print(f"\nTotal tenders scraped: {len(tenders)}\n")

    if not tenders:
        print("No tenders returned from scraper.")
        return

    found_target = False
    target_phrase = "maskless laser lithography"

    for idx, tender in enumerate(tenders, 1):
        title = tender.get("title", "")
        org = tender.get("organization", "")
        date = tender.get("published_date", tender.get("date", "N/A"))
        url = tender.get("source_url", "N/A")

        print(f"[{idx}]")
        print(f"Title: {title}")
        print(f"Organization: {org}")
        print(f"Date: {date}")
        print(f"URL: {url}")
        print("-" * 80)

        if target_phrase in title.lower():
            found_target = True

    print("\n" + "=" * 80)
    print("TARGET CHECK")
    print("=" * 80)

    if found_target:
        print("FOUND: Maskless laser lithography tender is being scraped.")
    else:
        print("NOT FOUND: scraper is missing the tender.")
        print("This means the issue is in scrapers/iisc.py, not matching/email.")

if __name__ == "__main__":
    main()