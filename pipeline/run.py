"""         run.py
        (orchestrator)
        /     |     \
       /      |      \
 cppp.py   db.py   filter.py
(scrape)  (dedup) (classify)
"""

from scrapers.cppp import scrape_all

from data.db import (
    get_connection,
    init_db,
    process_tender,
    update_flags,
    get_high_signal_matches,
    insert_match,
    mark_as_emailed,
    is_already_emailed
)

from matching.filter import classify_tender

import json
import re
from matching.embedder import ManufacturerEmbedder
from matching.matcher import TenderMatcher

# EMAIL
from digest.formatter import format_email
from digest.sender import send_email


def run_pipeline():

    conn = get_connection()
    init_db(conn)

    tenders = scrape_all(max_pages=10, cutoff_hours=24)

    processed = []
    duplicates = 0

    # stats
    blocked = 0
    low_signal = 0
    high_signal = 0
    explore_count = 0

    # dedup
    seen_titles = set()

    # email collections
    high_tenders = []
    low_tenders = []
    explore_tenders = []

    # ✅ PORTAL LINKS
    PORTAL_LINKS = {
        "central": "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
        "state": "https://eprocure.gov.in/cppp/latestactivetendersnew/mmpdata",
        "gem": "https://eprocure.gov.in/cppp/latestactivetendersnew/gemdata"
    }

    # Load manufacturers
    with open("data/manufacturers.json") as f:
        manufacturers = json.load(f)

    # Build embeddings
    embedder = ManufacturerEmbedder()
    embedder.load_manufacturers(manufacturers)
    embedder.build_embeddings()

    matcher = TenderMatcher(embedder)

    for t in tenders:
        new_t = process_tender(conn, t)

        if not new_t:
            duplicates += 1
            continue

        # normalized title dedup
        title = new_t.get("title") or ""
        normalized_title = re.sub(r'[^a-z0-9 ]', '', title.lower()).strip()

        if normalized_title in seen_titles:
            continue

        seen_titles.add(normalized_title)

        processed.append(new_t)

        result = classify_tender(new_t)

        # DEBUG
        print(f"\n--- CLASSIFICATION ---")
        print(f"TITLE: {new_t['title']}")
        print(f"CATEGORY: {result['category']}")
        print(f"REASON: {result['reason']}")
        print("----------------------")

        content_hash = new_t["content_hash"]

        # skip if already emailed
        if is_already_emailed(conn, content_hash):
            continue

        # ✅ safer portal link
        portal = (new_t.get("source_portal") or "").lower()
        new_t["portal_link"] = PORTAL_LINKS.get(
            portal,
            "https://eprocure.gov.in"
        )

        # -------------------------
        # MATCH + STORE + EMAIL COLLECT
        # -------------------------
        if result["category"] == "high_signal":

            matches = matcher.match(new_t)

            print("\n=== MATCHES ===")
            print(f"TENDER: {new_t['title']}")
            print(f"ORG: {new_t['organization']}")

            for m in matches:
                print(f"- {m['manufacturer_name']} ({m['score']})")

                insert_match(conn, content_hash, m)

            print(f"LINK: {new_t['portal_link']}")
            print("================\n")

            new_t["matches"] = matches
            high_tenders.append(new_t)

            mark_as_emailed(conn, content_hash)

        elif result["category"] == "low_signal":
            low_tenders.append(new_t)

        elif result["category"] == "explore":
            explore_tenders.append(new_t)

        # -------------------------
        # UPDATE FLAGS
        # -------------------------
        update_flags(
            conn,
            content_hash,
            result["is_blocked"],
            result["has_signal"]
        )

        # -------------------------
        # STATS
        # -------------------------
        if result["category"] == "blocked":
            blocked += 1

        elif result["category"] == "low_signal":
            low_signal += 1

        elif result["category"] == "high_signal":
            high_signal += 1

        elif result["category"] == "explore":
            explore_count += 1

    # commit everything
    conn.commit()

    # -------------------------
    # SUMMARY
    # -------------------------
    print(f"\nTotal scraped: {len(tenders)}")
    print(f"New tenders: {len(processed)}")
    print(f"Duplicates skipped: {duplicates}")

    print("\nFILTER RESULTS:")
    print({
        "blocked": blocked,
        "low_signal": low_signal,
        "high_signal": high_signal,
        "explore": explore_count
    })

    # -------------------------
    # EVALUATION
    # -------------------------
    evaluation = {
        "total": len(tenders),
        "high": high_signal,
        "explore": explore_count,
        "low": low_signal,
        "blocked": blocked
    }

    print("\n📊 EVALUATION:")
    print(evaluation)

    # -------------------------
    # EMAIL
    # -------------------------
    if high_tenders or low_tenders or explore_tenders:

        stats = {
            "total": len(tenders),
            "high": high_signal,
            "explore": explore_count,
            "low": low_signal
        }

        subject, body = format_email(
            high_tenders,
            explore_tenders,
            low_tenders,
            stats
        )

        send_email(subject, body, "devayushrout@gmail.com")

        print("\n📩 Email sent.")

    else:
        print("\n📭 No relevant tenders. Email skipped.")

    # -------------------------
    # DB CHECK
    # -------------------------
    print("\n🔥 TOP MATCHES FROM DB:")
    results = get_high_signal_matches(conn)

    for r in results:
        print(r)


if __name__ == "__main__":
    run_pipeline()