from scrapers.cppp import scrape_all
from matching.filter import classify_tender
from matching.embedder import build_matcher

TARGET = "sputter deposition"

matcher = build_matcher()

tenders = scrape_all()

print(f"\nTOTAL SCRAPED: {len(tenders)}\n")

found = False

for t in tenders:
    title = (t.get("title") or "").lower()

    if TARGET in title:
        found = True

        print("=" * 80)
        print("FOUND TARGET TENDER")
        print("=" * 80)

        print("TITLE:")
        print(t["title"])

        print("\nORG:")
        print(t["organization"])

        print("\nRAW:")
        print(t["raw_text"][:1500])

        result = classify_tender(t)

        print("\nCLASSIFICATION:")
        print(result)

        matches = matcher.match(t)

        print("\nMATCHES:")
        for m in matches:
            print(m)

if not found:
    print("TARGET TENDER NOT FOUND IN CPPP SCRAPE")