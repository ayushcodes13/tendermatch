from data.db import (
    get_connection,
    init_db,
    process_tender,
    update_flags
)

from matching.filter import classify_tender
from matching.embedder import build_matcher

from digest.formatter import format_email
from digest.sender import send_email

from .testsynthetic import generate_tenders


def test_pipeline():

    conn = get_connection()
    init_db(conn)

    tenders = generate_tenders(100)

    matcher = build_matcher()

    stats = {
        "blocked": 0,
        "low": 0,
        "high": 0,
        "explore": 0
    }

    high_tenders = []
    low_tenders = []
    explore_tenders = []

    for t in tenders:
        new_t = process_tender(conn, t)

        if not new_t:
            continue

        result = classify_tender(new_t)

        content_hash = new_t["content_hash"]

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

            new_t["matches"] = matches
            high_tenders.append(new_t)

        elif result["category"] == "explore":
            stats["explore"] += 1
            explore_tenders.append(new_t)

        elif result["category"] == "low_signal":
            stats["low"] += 1
            low_tenders.append(new_t)

        else:
            stats["blocked"] += 1

    print("\n📊 FINAL STATS:")
    print(stats)

    if high_tenders or low_tenders or explore_tenders:

        email_stats = {
            "total": len(tenders),
            "high": stats["high"],
            "explore": stats["explore"],
            "low": stats["low"]
        }

        subject, body = format_email(
            high_tenders,
            explore_tenders,
            low_tenders,
            email_stats
        )

        send_email(subject, body, "devayushrout@gmail.com")

        print("\n📩 Test email sent.")

    else:
        print("\n📭 No email sent.")


if __name__ == "__main__":
    test_pipeline()