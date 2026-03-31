from data.db import get_connection, init_db, process_tender, update_flags, generate_hash
from matching.filter import classify_tender
from matching.embedder import ManufacturerEmbedder
from matching.matcher import TenderMatcher

import json
from .testsynthetic import generate_tenders

# ✅ NEW IMPORTS
from digest.formatter import format_email
from digest.sender import send_email


def test_pipeline():

    conn = get_connection()
    init_db(conn)

    tenders = generate_tenders(100)

    # Load manufacturers
    with open("data/manufacturers.json") as f:
        manufacturers = json.load(f)

    embedder = ManufacturerEmbedder()
    embedder.load_manufacturers(manufacturers)
    embedder.build_embeddings()

    matcher = TenderMatcher(embedder)

    stats = {
        "blocked": 0,
        "low": 0,
        "high": 0
    }

    # ✅ NEW: email collections
    high_tenders = []
    low_tenders = []

    for t in tenders:
        new_t = process_tender(conn, t)

        if not new_t:
            continue

        result = classify_tender(new_t)

        content_hash = generate_hash(new_t)

        update_flags(
            conn,
            content_hash,
            result["is_blocked"],
            result["has_signal"]
        )

        if result["category"] == "high_signal":
            stats["high"] += 1

            matches = matcher.match(new_t)

            print("\n🔥 HIGH SIGNAL")
            print(new_t["title"])

            for m in matches:
                print(f"→ {m['manufacturer_name']} ({m['score']})")

            # ✅ ADD FOR EMAIL
            new_t["matches"] = matches
            high_tenders.append(new_t)

        elif result["category"] == "low_signal":
            stats["low"] += 1
            low_tenders.append(new_t)

        else:
            stats["blocked"] += 1

    print("\n📊 FINAL STATS:")
    print(stats)

    # ✅ EMAIL SECTION
    if high_tenders or low_tenders:

        email_stats = {
            "total": len(tenders),
            "high": stats["high"],
            "low": stats["low"]
        }

        subject, body = format_email(high_tenders, low_tenders, email_stats)

        send_email(subject, body, "devayushrout@gmail.com")

        print("\n📩 Test email sent.")

    else:
        print("\n📭 No email sent (no signals).")


if __name__ == "__main__":
    test_pipeline()