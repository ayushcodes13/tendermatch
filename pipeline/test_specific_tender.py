from matching.classifier import classify_tender

def test_specific_tender():
    tender = {
        "title": "Global Tender for Maskless laser lithography system",
        "organization": "Indian Institute of Science",
        "published_date": "08/04/2026",
        "raw_text": "Global Tender for Maskless laser lithography system"
    }

    result = classify_tender(tender)

    print("\n--- TEST RESULT ---")
    print("Title:", tender["title"])
    print("Result:", result)

if __name__ == "__main__":
    test_specific_tender()