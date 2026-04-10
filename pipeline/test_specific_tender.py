from matching.filter import classify_tender
from matching.embedder import build_matcher


def test_specific_tender():
    tender = {
        "title": "Global Tender for Maskless laser lithography system",
        "organization": "Indian Institute of Science",
        "published_date": "08/04/2026",
        "raw_text": "Global Tender for Maskless laser lithography system"
    }

    print("\n" + "=" * 60)
    print("TESTING SPECIFIC TENDER")
    print("=" * 60)
    print("Title:", tender["title"])
    print("Organization:", tender["organization"])

    # -----------------------
    # CLASSIFICATION
    # -----------------------
    classification = classify_tender(tender)

    print("\n[CLASSIFICATION RESULT]")
    print(classification)

    if classification["category"] == "blocked":
        print("\n❌ Tender blocked")
        return

    # -----------------------
    # MATCHING
    # -----------------------
    matcher = build_matcher()
    matches = matcher.match(tender)

    print("\n[MATCHING RESULT]")
    if not matches:
        print("❌ No manufacturer matches found")
    else:
        for i, match in enumerate(matches, 1):
            print(f"{i}. {match}")


if __name__ == "__main__":
    test_specific_tender()