import sqlite3
import threading

from data.db import (
    generate_hash,
    get_high_signal_matches,
    init_db,
    insert_match,
    is_already_emailed,
    mark_as_emailed,
    upsert_or_get_tender,
    update_flags,
)


def tender(**overrides):
    value = {
        "tender_id": "REF-100",
        "title": "Supply of a spectrometer",
        "organization": "Research Institute",
        "published_date": "2026-10-21",
        "closing_date": "2026-11-01",
        "source_portal": "cppp",
        "source_url": "https://portal.example/tender/REF-100",
        "raw_text": "Supply of a spectrometer",
    }
    return {**value, **overrides}


def db():
    connection = sqlite3.connect(":memory:")
    init_db(connection)
    return connection


def test_different_official_tender_ids_do_not_collapse_same_title_and_organization():
    conn = db()
    first, first_new = upsert_or_get_tender(conn, tender(tender_id="REF-100"))
    second, second_new = upsert_or_get_tender(conn, tender(tender_id="REF-101"))

    assert first_new and second_new
    assert first["identity_key"] != second["identity_key"]
    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 2


def test_same_official_reference_across_portals_updates_one_persisted_record():
    conn = db()
    first, is_new = upsert_or_get_tender(conn, tender())
    update_flags(conn, first["identity_key"], False, True)
    mark_as_emailed(conn, first["identity_key"])

    refreshed, second_is_new = upsert_or_get_tender(
        conn,
        tender(
            title="Updated spectrometer procurement",
            source_portal="institution",
            source_url="https://institution.example/notice/REF-100",
            updated_date="2026-10-21",
            raw_text="Updated specification for the same official reference",
        ),
    )

    assert is_new and not second_is_new
    assert first["identity_key"] == refreshed["identity_key"]
    assert refreshed["title"] == "Updated spectrometer procurement"
    assert refreshed["updated_date"] == "2026-10-21"
    assert refreshed["emailed"] == 1
    assert refreshed["has_signal"] == 1
    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1
    assert is_already_emailed(conn, refreshed["identity_key"])


def test_missing_tender_id_uses_detail_url_and_persists_refreshes():
    conn = db()
    original = tender(tender_id=None)
    first, is_new = upsert_or_get_tender(conn, original)
    second, second_is_new = upsert_or_get_tender(
        conn,
        tender(tender_id=None, title="Renamed notice", raw_text="New detail text"),
    )

    assert is_new and not second_is_new
    assert first["identity_key"] == second["identity_key"]
    assert second["title"] == "Renamed notice"
    assert second["raw_text"] == "New detail text"
    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1


def test_fallback_identity_separates_same_title_when_dates_differ():
    first = tender(tender_id=None, source_url=None, source_portal="iit_goa")
    second = tender(
        tender_id=None,
        source_url=None,
        source_portal="iit_goa",
        published_date="2026-10-20",
    )
    assert generate_hash(first) != generate_hash(second)


def test_iisc_identity_uses_detail_url_and_survives_title_or_scraper_id_changes():
    original = tender(
        tender_id="iisc_123456",
        source_portal="iisc",
        source_url="https://iisc.ac.in/tenders/notice-123",
        published_date="2026-10-21T00:00:00",
    )
    refreshed = tender(
        tender_id="iisc_abcdef",
        source_portal="iisc",
        source_url="https://iisc.ac.in/tenders/notice-123",
        published_date="2026-10-20T18:30:00+00:00",
    )
    assert generate_hash(original) == generate_hash(refreshed)


def test_iisc_detail_urls_separate_distinct_notices():
    first = tender(tender_id="iisc_a", source_portal="iisc", source_url="https://iisc.ac.in/tenders/1")
    second = tender(tender_id="iisc_b", source_portal="iisc", source_url="https://iisc.ac.in/tenders/2")
    assert generate_hash(first) != generate_hash(second)


def test_repeated_manufacturer_match_is_idempotent():
    conn = db()
    stored, _ = upsert_or_get_tender(conn, tender())
    match = {
        "manufacturer_id": "maker-1",
        "manufacturer_name": "Maker One",
        "score": 0.8,
        "confidence": "high_signal",
    }

    insert_match(conn, stored["identity_key"], match)
    insert_match(conn, stored["identity_key"], match)

    assert conn.execute("SELECT COUNT(*) FROM tender_matches").fetchone()[0] == 1
    assert conn.execute(
        "SELECT tender_identity_key FROM tender_matches"
    ).fetchone()[0] == stored["identity_key"]


def test_legacy_schema_migration_preserves_rows_and_leaves_ambiguous_matches_unlinked():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id TEXT,
            content_hash TEXT,
            title TEXT,
            organization TEXT,
            published_date TEXT,
            closing_date TEXT,
            source_url TEXT,
            source_portal TEXT,
            raw_text TEXT,
            scraped_at TEXT,
            is_blocked INTEGER DEFAULT 0,
            has_signal INTEGER DEFAULT 0,
            emailed INTEGER DEFAULT 0,
            UNIQUE(tender_id, content_hash)
        );
        CREATE TABLE tender_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_hash TEXT,
            manufacturer_id TEXT,
            manufacturer_name TEXT,
            score REAL,
            confidence TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX idx_unique_match
        ON tender_matches (tender_hash, manufacturer_id);
    """)
    legacy_hash = "old-title-org-hash"
    conn.execute(
        "INSERT INTO tenders (tender_id, content_hash, title, organization, emailed, has_signal) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("REF-1", legacy_hash, "Same title", "Same organization", 1, 1),
    )
    conn.execute(
        "INSERT INTO tenders (tender_id, content_hash, title, organization, emailed, has_signal) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("REF-2", legacy_hash, "Same title", "Same organization", 0, 1),
    )
    conn.execute(
        "INSERT INTO tender_matches (tender_hash, manufacturer_id, manufacturer_name, score, confidence) "
        "VALUES (?, ?, ?, ?, ?)",
        (legacy_hash, "maker-1", "Maker One", 0.8, "high_signal"),
    )
    conn.commit()

    init_db(conn)

    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM tender_matches").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(DISTINCT identity_key) FROM tenders").fetchone()[0] == 2
    assert conn.execute("SELECT emailed FROM tenders ORDER BY id").fetchall() == [(1,), (0,)]
    assert conn.execute(
        "SELECT tender_identity_key FROM tender_matches"
    ).fetchone()[0] is None
    assert get_high_signal_matches(conn) == []

    # Re-running initialization is safe and does not duplicate migrated rows.
    init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM tender_matches").fetchone()[0] == 1


def test_concurrent_upserts_create_one_row_for_the_same_identity(tmp_path):
    path = tmp_path / "shared.sqlite3"
    setup = sqlite3.connect(path)
    init_db(setup)
    setup.close()
    barrier = threading.Barrier(2)
    outcomes = []
    errors = []

    def write_tender():
        conn = sqlite3.connect(path, timeout=10)
        try:
            barrier.wait(timeout=5)
            result, is_new = upsert_or_get_tender(conn, tender())
            conn.commit()
            outcomes.append((result["identity_key"], is_new))
        except Exception as exc:  # surfaced below as a test failure
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=write_tender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    check = sqlite3.connect(path)
    assert not errors
    assert len(outcomes) == 2
    assert sum(is_new for _, is_new in outcomes) == 1
    assert check.execute("SELECT COUNT(*) FROM tenders").fetchone()[0] == 1
    check.close()
