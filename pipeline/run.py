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
- Uses stable tender identities for duplicate suppression and SQLite-backed email retries.
- Semantic matching is integrated into the classification phase to ensure strong manufacturer relevance can rescue borderline tenders.
"""

from config import DOCUMENT_ALLOWED_HOSTS, DOCUMENT_STORAGE_DIR, RECEIVER_EMAIL
from data.documents import retrieve_candidate_documents
from data.extraction import extract_pdf_requirements, record_extraction_result
from scrapers.cppp import scrape_all as scrape_cppp, PORTAL_LINKS
from scrapers.iitm import scrape_iitm
from scrapers.iit_palakkad import scrape_iit_palakkad
from scrapers.iit_goa import scrape_iit_goa
from scrapers.iisc import scrape_iisc

from pipeline.freshness import (
    assess_tender_freshness,
    get_tender_date_status,
    is_recent_tender,
)

from data.db import (
    get_connection,
    init_db,
    process_tender,
    upsert_or_get_tender,
    update_flags,
    insert_match,
    get_tender_amendment,
)

from matching.filter import classify_tender
from matching.embedder import build_matcher

from digest.formatter import format_email
from digest.sender import send_email
from digest.outbox import (
    deliver_batch,
    deliver_due_batches,
    notification_exists,
    recipient_has_notification,
    AMENDMENT_UPDATE,
    NEW_OPPORTUNITY,
    queue_digest,
)


def collect_all_tenders():
    """
    Aggregates tender data from all configured scraping sources.

    Returns:
        list: A consolidated list of raw tender dictionaries from various portals.

    Notes:
        - Sources include CPPP (Central, State, GeM) and specific Tier-1 institutions.
        - No deduplication is performed at this stage.
        - Individual scraper failures are isolated so other sources can still run.
    """
    tenders = []

    scraper_jobs = [
        ("cppp", scrape_cppp),
        ("iitm", scrape_iitm),
        ("iit_palakkad", scrape_iit_palakkad),
        ("iit_goa", scrape_iit_goa),
        ("iisc", scrape_iisc),
    ]

    for name, scraper_fn in scraper_jobs:
        try:
            results = scraper_fn() or []
            print(f"[SCRAPER OK] {name}: {len(results)} tenders")
            tenders.extend(results)
        except Exception as e:
            # Exception strings can include credential-bearing URLs or response data.
            print(f"[SCRAPER FAILED] {name}: {type(e).__name__}")
            continue

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
    deliver_due_batches(conn, send_email)

    tenders = collect_all_tenders()

    processed = []
    duplicates = 0
    stale_skipped = 0
    expired_skipped = 0
    unknown_date_count = 0
    still_open_count = 0
    already_emailed = 0

    blocked = 0
    low_signal = 0
    high_signal = 0
    explore_count = 0

    seen_identity_keys = set()

    high_tenders = []
    low_tenders = []
    explore_tenders = []
    updated_tenders = []
    document_candidates = []

    matcher = build_matcher()

    for t in tenders:
        new_t, is_new = upsert_or_get_tender(conn, t)
        identity_key = new_t["identity_key"]
        status_str = "NEW" if is_new else "EXISTING_NOT_EMAILED"
        new_t["portal_link"] = PORTAL_LINKS.get(
            (new_t.get("source_portal") or "").lower(),
            new_t.get("source_url", "https://eprocure.gov.in"),
        )

        # -------------------------
        # EMAIL DEDUPE
        # -------------------------
        notification_type = NEW_OPPORTUNITY
        if RECEIVER_EMAIL:
            already_notified = recipient_has_notification(
                conn, RECEIVER_EMAIL, identity_key
            )
            if already_notified:
                latest_amendment = get_tender_amendment(
                    conn, identity_key, new_t.get("version_fingerprint")
                )
                if (
                    latest_amendment is None
                    or latest_amendment["status"] == "formatting_only"
                    or notification_exists(conn, RECEIVER_EMAIL, new_t, AMENDMENT_UPDATE)
                ):
                    already_emailed += 1
                    print(f"[{status_str}] No new recipient-worthy tender update: {new_t.get('title')}")
                    continue
                notification_type = AMENDMENT_UPDATE
                new_t["amendment"] = latest_amendment
                new_t["notification_type"] = notification_type
                updated_tenders.append(new_t)
            elif notification_exists(conn, RECEIVER_EMAIL, new_t, NEW_OPPORTUNITY):
                already_emailed += 1
                print(f"[{status_str}] Skipping tender already notified to this recipient: {new_t.get('title')}")
                continue
        elif new_t.get("emailed"):
            already_emailed += 1
            print(f"[{status_str}] Skipping legacy emailed tender: {new_t.get('title')}")
            continue
        new_t.setdefault("notification_type", notification_type)

        print(f"[{status_str}] Processing tender: {new_t.get('title')}")

        # -------------------------
        # FRESHNESS GATE
        # -------------------------
        # This prevents old archive tenders from being emailed just because
        # they appeared in the latest scrape.
        freshness_status = assess_tender_freshness(new_t, max_age_hours=24)
        date_status = get_tender_date_status(new_t, max_age_hours=24)
        if "unknown" in date_status.values():
            unknown_date_count += 1
        if date_status["lifecycle"] == "still_open":
            still_open_count += 1

        if not is_recent_tender(new_t, max_age_hours=24):
            if freshness_status == "expired":
                expired_skipped += 1
            else:
                stale_skipped += 1
            print(
                f"[{status_str}] Skipping {freshness_status} tender: {new_t.get('title')} | "
                f"published_date={new_t.get('published_date')} | "
                f"updated_date={new_t.get('updated_date')} | "
                f"corrigendum_date={new_t.get('corrigendum_date')}"
            )
            continue

        # -------------------------
        # RUNTIME TITLE DEDUPE
        # -------------------------
        if identity_key in seen_identity_keys:
            duplicates += 1
            continue

        seen_identity_keys.add(identity_key)

        # only count truly processable fresh tenders
        processed.append(new_t)

        manufacturer_candidates = matcher.match_topk(new_t, top_k=5)

        result = classify_tender(
            new_t,
            manufacturer_candidates=manufacturer_candidates,
        )

        portal = (new_t.get("source_portal") or "").lower()
        new_t["portal_link"] = PORTAL_LINKS.get(
            portal, new_t.get("source_url", "https://eprocure.gov.in")
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
            identity_key,
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
            insert_match(conn, identity_key, m)

        new_t["matches"] = matches

        if new_t.get("document_links") and category in {"high_signal", "explore"}:
            document_candidates.append(new_t)

        if category == "high_signal":
            if notification_type != AMENDMENT_UPDATE:
                high_tenders.append(new_t)

        elif category == "explore":
            if notification_type != AMENDMENT_UPDATE:
                explore_tenders.append(new_t)

    if DOCUMENT_ALLOWED_HOSTS and DOCUMENT_STORAGE_DIR and document_candidates:
        retrievals = retrieve_candidate_documents(
            conn,
            document_candidates,
            allowed_hosts=DOCUMENT_ALLOWED_HOSTS,
            storage_dir=DOCUMENT_STORAGE_DIR,
            max_candidates=10,
            max_documents_per_candidate=2,
        )
        extracted_count = 0
        for document in retrievals:
            if document.status != "downloaded" or not document.storage_path:
                continue
            extraction = extract_pdf_requirements(
                document.storage_path,
                source_url=document.source_url,
                content_fingerprint=document.content_fingerprint,
            )
            record_extraction_result(conn, extraction)
            extracted_count += extraction["status"] == "extracted"
        print(
            f"[DOCUMENT RETRIEVAL] {len(retrievals)} linked files attempted; "
            f"{extracted_count} native-text extractions completed"
        )

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
        "expired_skipped": expired_skipped,
        "unknown_date_count": unknown_date_count,
        "still_open_count": still_open_count,
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
    if (high_tenders or explore_tenders or updated_tenders) and not RECEIVER_EMAIL:
        print("\n[EMAIL OUTBOX] Cannot queue a new digest: RECEIVER_EMAIL is missing.")
    elif high_tenders or explore_tenders or updated_tenders:
        eligible_high = [
            tender for tender in high_tenders
            if not notification_exists(
                conn, RECEIVER_EMAIL, tender, tender.get("notification_type", NEW_OPPORTUNITY)
            )
        ]
        eligible_explore = [
            tender for tender in explore_tenders
            if not notification_exists(
                conn, RECEIVER_EMAIL, tender, tender.get("notification_type", NEW_OPPORTUNITY)
            )
        ]
        eligible_updates = [
            tender for tender in updated_tenders
            if not notification_exists(conn, RECEIVER_EMAIL, tender, AMENDMENT_UPDATE)
        ]
        digest_tenders = eligible_high + eligible_explore + eligible_updates
        if not digest_tenders:
            print("\n[EMAIL OUTBOX] Matching opportunities already have a delivery record.")
        else:
            digest_stats = {
                **stats,
                "high": len(eligible_high),
                "explore": len(eligible_explore),
                "updated": len(eligible_updates),
            }
            subject, body = format_email(
                eligible_high,
                eligible_explore,
                digest_stats,
                updated_tenders=eligible_updates,
            )
            batch_id = queue_digest(
                conn,
                RECEIVER_EMAIL,
                subject,
                body,
                digest_tenders,
            )
            if batch_id is not None and deliver_batch(conn, batch_id, send_email):
                print("\n📩 Email sent and recorded.")
            elif batch_id is not None:
                print("\n[EMAIL OUTBOX] Digest stored for a later retry.")

    else:
        print("\n📭 No relevant fresh tenders. Email skipped.")

    conn.close()


if __name__ == "__main__":
    run_pipeline()
