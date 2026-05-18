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
- Semantic matching is integrated into the classification phase to ensure strong manufacturer relevance can rescue borderline tenders.
"""

from config import RECEIVER_EMAIL
from scrapers.cppp import scrape_all as scrape_cppp, PORTAL_LINKS
from scrapers.iitm import scrape_iitm
from scrapers.iit_palakkad import scrape_iit_palakkad
from scrapers.iit_goa import scrape_iit_goa
from scrapers.iisc import scrape_iisc

from pipeline.freshness import is_recent_tender

from data.db import (
    get_connection,
    init_db,
    process_tender,
    update_flags,
    insert_match,
    mark_as_emailed,
    is_already_emailed,
    normalize_title,
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
        - Implements a multi-stage duplicate check:
          (1) DB check via content hash,
          (2) Runtime check via normalized title set.
        - Classification results determine whether a tender enters the
          computational intensive matching phase.
    """
    conn = get_connection()
    init_db(conn)

    tenders = collect_all_tenders()

    processed = []
    duplicates = 0
    stale_skipped = 0
    already_emailed = 0

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

        # -------------------------
        # FRESHNESS GATE
        # -------------------------
        # This prevents old archive tenders from being emailed just because
        # they appeared in the latest scrape.
        if not is_recent_tender(new_t, max_age_hours=24):
            stale_skipped += 1
            print(
                f"Skipping stale tender: {new_t.get('title')} | "
                f"published_date={new_t.get('published_date')} | "
                f"updated_date={new_t.get('updated_date')} | "
                f"corrigendum_date={new_t.get('corrigendum_date')}"
            )
            continue

        # -------------------------
        # RUNTIME TITLE DEDUPE
        # -------------------------
        title = new_t.get("title") or ""
        normalized_title = normalize_title(title)

        if normalized_title in seen_titles:
            duplicates += 1
            continue

        seen_titles.add(normalized_title)

        content_hash = new_t["content_hash"]

        # -------------------------
        # EMAIL DEDUPE
        # -------------------------
        if is_already_emailed(conn, content_hash):
            already_emailed += 1
            continue

        # only count truly processable fresh tenders
        processed.append(new_t)

        manufacturer_candidates = matcher.match_topk(new_t, top_k=5)

        result = classify_tender(
            new_t,
            manufacturer_candidates=manufacturer_candidates,
        )

        portal = (new_t.get("source_portal") or "").lower()
        new_t["portal_link"] = PORTAL_LINKS.get(
            portal,
            new_t.get("source_url", "https://eprocure.gov.in"),
        )

        new_t["classification"] = result

        print("\n--- CLASSIFICATION ---")
        print(f"TITLE: {new_t.get('title')}")
        print(f"DECISION: {result.get('decision')}")
        print(f"CATEGORY: {result.get('category')}")
        print(f"SCORE: {result.get('score')}")
        print(f"REASON: {result.get('reason')}")
        print("----------------------")

        update_flags(
            conn,
            content_hash,
            result["is_blocked"],
            result["has_signal"],
        )

        decision = result.get("decision")
        category = result.get("category")

        if category == "blocked":
            blocked += 1
            continue

        if category == "low_signal":
            low_signal += 1
            continue

        if category == "high_signal":
            high_signal += 1

        elif category == "explore":
            explore_count += 1

        else:
            continue

        matches = [
            m for m in manufacturer_candidates
            if (
                m.get("score", 0) >= 0.60
                or m.get("keyword_hits")
                or m.get("product_hits")
                or m.get("category_hits")
                or m.get("concept_hits")
            )
        ]

        for m in matches:
            insert_match(conn, content_hash, m)

        new_t["matches"] = matches

        if category == "high_signal":
            high_tenders.append(new_t)

        elif category == "explore":
            explore_tenders.append(new_t)

    conn.commit()

    # -------------------------
    # SUMMARY
    # -------------------------
    print(f"\nTotal scraped: {len(tenders)}")
    print(f"Fresh processed: {len(processed)}")
    print(f"Duplicates skipped: {duplicates}")
    print(f"Stale skipped: {stale_skipped}")
    print(f"Already emailed skipped: {already_emailed}")

    stats = {
        "total_scraped": len(tenders),
        "fresh_processed": len(processed),
        "duplicates_skipped": duplicates,
        "stale_skipped": stale_skipped,
        "already_emailed_skipped": already_emailed,
        "high": high_signal,
        "explore": explore_count,
        "low": low_signal,
        "blocked": blocked,
    }

    print("\n📊 EVALUATION:")
    print(stats)

    # -------------------------
    # EMAIL
    # -------------------------
    if high_tenders or explore_tenders:
        subject, body = format_email(
            high_tenders,
            explore_tenders,
            stats,
        )

        try:
            if not RECEIVER_EMAIL:
                raise ValueError("RECEIVER_EMAIL is missing")

            send_email(subject, body, RECEIVER_EMAIL)

            for t in high_tenders + explore_tenders:
                mark_as_emailed(conn, t["content_hash"])

            conn.commit()

            print("\n📩 Email sent.")

        except Exception as e:
            print(f"\n❌ Email failed: {e}")

    else:
        print("\n📭 No relevant fresh tenders. Email skipped.")

    conn.close()


if __name__ == "__main__":
    run_pipeline()