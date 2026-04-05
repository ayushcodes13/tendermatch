from scrapers.cppp import scrape_all as scrape_cppp
from scrapers.iitm import scrape_iitm
from scrapers.iit_palakkad import scrape_iit_palakkad
from scrapers.iit_goa import scrape_iit_goa

def test_scrapers():

    all_tenders = []

    sources = {
        "cppp": scrape_cppp,
        "iitm": scrape_iitm,
        "iit_palakkad": scrape_iit_palakkad,
        "iit_goa": scrape_iit_goa
    }

    for name, scraper in sources.items():
        try:
            tenders = scraper()

            print(f"\n=== {name.upper()} ===")
            print(f"COUNT: {len(tenders)}")

            for t in tenders[:3]:
                print(
                    f"{t.get('source_portal')} | "
                    f"{t.get('title')}"
                )

            all_tenders.extend(tenders)

        except Exception as e:
            print(f"\n❌ {name} FAILED")
            print(e)

    print("\n======================")
    print("TOTAL SCRAPED:", len(all_tenders))


if __name__ == "__main__":
    test_scrapers()