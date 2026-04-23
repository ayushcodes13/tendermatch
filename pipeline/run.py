"""
Central orchestrator for the tender intelligence pipeline.

Pipeline role:
Coordinates the end-to-end flow: scraping from multiple portals, deduplication 
via database hashing, classification of tender relevance, semantic matching 
against manufacturer profiles, and generation of digest emails.

Key responsibilities:
- Aggregating data from across CPPP and specific institution scrapers.
- Managing tender lifecycle (New -> Classified -> Matched -> Emailed).
- Maintaining pipeline stats and triggering failure alerts.

Inputs:
- Portal URLs and API endpoints (via scrapers).
- Persistence state (via data/tenders.db).
- Manufacturer profiles (via data/manufacturers.json).

Outputs:
- Classified and matched tenders in the database.
- Multi-section HTML/Text digest emails for stakeholders.

Notes:
- Uses a title+organization normalization strategy to handle cross-portal duplicates.
- Semantic matching is only triggered for 'high_signal' tenders to optimize resource usage.
"""

from scrapers.cppp import scrape_all as scrape_cppp, PORTAL_LINKS
from scrapers.iitm import scrape_iitm
from scrapers.iit_palakkad import scrape_iit_palakkad
from scrapers.iit_goa import scrape_iit_goa
from scrapers.iisc import scrape_iisc

from data.db import (
    get_connection,
    init_db,
    process_tender,
    update_flags,
    insert_match,
    mark_as_emailed,
    is_already_emailed,
    normalize_title
)

from matching.filter import classify_tender
from matching.embedder import build_matcher

from digest.formatter import format_email
from digest.sender import send_email


def collect_all_tenders():
    """
    Aggregates tender data from all configured scraping sources.

    Returns:
        list: A consolidated list of raw tender dictionaries from various portals.

    Notes:
        - Sources include CPPP (Central, State, GeM) and specific Tier-1 institutions.
        - No deduplication is performed at this stage.
    """
    tenders = []

    # CPPP ecosystem
    tenders.extend(scrape_cppp())

    # institute sources
    tenders.extend(scrape_iitm())
    tenders.extend(scrape_iit_palakkad())
    tenders.extend(scrape_iit_goa())
    tenders.extend(scrape_iisc())

    return tenders


def run_pipeline():
    """
    Executes the main pipeline logic for tender processing and matching.

    Side Effects:
        - Initializes/updates SQLite database.
        - Triggers web scraping requests.
        - Sends digest emails if relevant tenders are found.
        - Updates persistence flags for emailed/processed status.

    Notes:
        - Implements a multi-stage duplicate check: (1) DB check via content hash, 
          (2) Runtime check via normalized title set.
        - Classification results determine whether a tender enters the 
          computational intensive matching phase.
    """
    conn = get_connection()
    init_db(conn)

    tenders = collect_all_tenders()

    processed = []
    duplicates = 0

    blocked = 0
    low_signal = 0
    high_signal = 0
    explore_count = 0

    seen_titles = set()

    high_tenders = []
    low_tenders = []
    explore_tenders = []

    matcher = build_matcher()

    for t in tenders:
        new_t = process_tender(conn, t)

        if not new_t:
            duplicates += 1
            continue

        title = new_t.get("title") or ""
        normalized_title = normalize_title(title)

        if normalized_title in seen_titles:
            duplicates += 1
            continue

        seen_titles.add(normalized_title)

        content_hash = new_t["content_hash"]

        # skip if already emailed
        if is_already_emailed(conn, content_hash):
            continue

        # only count truly processable tenders
        processed.append(new_t)

        result = classify_tender(new_t)

        print(f"\n--- CLASSIFICATION ---")
        print(f"TITLE: {new_t['title']}")
        print(f"CATEGORY: {result['category']}")
        print(f"REASON: {result['reason']}")
        print("----------------------")

        portal = (new_t.get("source_portal") or "").lower()
        new_t["portal_link"] = PORTAL_LINKS.get(
            portal,
            new_t.get("source_url", "https://eprocure.gov.in")
        )

        # -------------------------
        # MATCH + STORE + EMAIL COLLECT
        # -------------------------
        if result["category"] == "high_signal":
            matches = matcher.match(new_t)

            if not matches:
                continue

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

        try:
            send_email(subject, body, "devayushrout@gmail.com")

            for t in high_tenders:
                mark_as_emailed(conn, t["content_hash"])

            for t in low_tenders:
                mark_as_emailed(conn, t["content_hash"])

            for t in explore_tenders:
                mark_as_emailed(conn, t["content_hash"])

            conn.commit()

            print("\n📩 Email sent.")

        except Exception as e:
            print(f"\n❌ Email failed: {e}")

    else:
        print("\n📭 No relevant tenders. Email skipped.")


if __name__ == "__main__":
    run_pipeline()