"""
Persistence layer for tender and match data using SQLite.

Pipeline role:
Handles all I/O operations for tenders, classification flags, and manufacturer matches. 
Ensures data integrity and implements the deduplication logic used to prevent 
re-processing of known tenders.

Key responsibilities:
- Schema management and backward-compatible database initialization.
- Stable source-identity hashing with title/date fallback for tender deduplication.
- CRUD operations for tender records and manufacturer match results.
- State management for email dispatch tracking.

Inputs:
- Raw or processed tender dictionaries.
- Manufacturer match dictionaries.

Outputs:
- SQLite connection objects.
- Result sets for email formatting and pipeline statistics.

Notes:
- Uses SHA-256 source identity keys for tender state and manufacturer matches.
- Retains the former title/organization digest for migration compatibility only.
"""
import sqlite3
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from data.amendments import compare_tender_versions
from pipeline.freshness import parse_date

DB_PATH = "data/tenders.db"


def get_connection():
    """
    Establishes a connection to the local SQLite database.

    Returns:
        sqlite3.Connection: An active database connection object.
    """
    configured_path = os.environ.get("TENDERMATCH_DB_PATH")
    database_path = configured_path or DB_PATH
    if configured_path and configured_path != ":memory:":
        parent = Path(database_path).parent
        if not parent.is_dir():
            raise FileNotFoundError(
                "The directory configured by TENDERMATCH_DB_PATH does not exist; "
                "mount or create the storage directory before starting TenderMatch."
            )
    return sqlite3.connect(database_path, timeout=30)


def init_db(conn):
    """
    Initializes the database schema if it doesn't already exist.

    Args:
        conn (sqlite3.Connection): Active database connection.

    Notes:
        - Creates 'tenders' table for storing metadata and classification state.
        - Creates 'tender_matches' table for storing many-to-many relationships 
          between tenders and manufacturers.
        - Sets up unique indices for efficient lookups and duplicate prevention.
    """
    cursor = conn.cursor()

    # -------- TENDERS TABLE --------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tenders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_id TEXT,
        content_hash TEXT,
        identity_key TEXT,
        title TEXT,
        organization TEXT,
        published_date TEXT,
        updated_date TEXT,
        corrigendum_date TEXT,
        closing_date TEXT,
        source_url TEXT,
        source_portal TEXT,
        raw_text TEXT,
        scraped_at TEXT,
        version_fingerprint TEXT,

        is_blocked INTEGER DEFAULT 0,
        has_signal INTEGER DEFAULT 0,
        emailed INTEGER DEFAULT 0,

        UNIQUE(tender_id, content_hash)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tender_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_identity_key TEXT NOT NULL,
        content_fingerprint TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        UNIQUE(tender_identity_key, content_fingerprint)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tender_amendments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_identity_key TEXT NOT NULL,
        from_fingerprint TEXT NOT NULL,
        to_fingerprint TEXT NOT NULL,
        change_status TEXT NOT NULL,
        change_types_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        UNIQUE(tender_identity_key, from_fingerprint, to_fingerprint)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tender_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_identity_key TEXT NOT NULL,
        source_url TEXT NOT NULL,
        content_fingerprint TEXT,
        storage_path TEXT,
        status TEXT NOT NULL,
        content_type TEXT,
        byte_size INTEGER,
        fetched_at TEXT NOT NULL,
        error_type TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_extractions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_url TEXT NOT NULL,
        content_fingerprint TEXT NOT NULL,
        extraction_status TEXT NOT NULL,
        result_json TEXT NOT NULL,
        error_type TEXT,
        extracted_at TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS salesperson_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_identity_key TEXT NOT NULL,
        tender_version TEXT,
        manufacturer_id TEXT NOT NULL,
        label TEXT NOT NULL,
        reason TEXT,
        reviewer TEXT NOT NULL,
        reviewed_at TEXT NOT NULL
    )
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS salesperson_feedback_no_update
        BEFORE UPDATE ON salesperson_feedback
        BEGIN
            SELECT RAISE(ABORT, 'salesperson feedback records are immutable');
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS salesperson_feedback_no_delete
        BEFORE DELETE ON salesperson_feedback
        BEGIN
            SELECT RAISE(ABORT, 'salesperson feedback records are immutable');
        END
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tender_amendment_version
        ON tender_amendments (tender_identity_key, to_fingerprint)
    """)

    # -------- MATCHES TABLE --------
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tender_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tender_hash TEXT,
        manufacturer_id TEXT,
        manufacturer_name TEXT,
        score REAL,
        confidence TEXT,
        tender_identity_key TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        digest_key TEXT NOT NULL UNIQUE,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT,
        last_error_type TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        sent_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        duration_seconds REAL,
        source_results_json TEXT NOT NULL DEFAULT '{}',
        summary_json TEXT,
        error_type TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL,
        recipient TEXT NOT NULL,
        tender_identity_key TEXT NOT NULL,
        tender_version TEXT NOT NULL,
        notification_type TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        sent_at TEXT,
        UNIQUE(recipient, tender_identity_key, tender_version, notification_type)
    )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_email_batches_due
        ON email_batches (state, next_attempt_at)
    """)

    _ensure_column(conn, "tenders", "identity_key", "TEXT")
    _ensure_column(conn, "tenders", "updated_date", "TEXT")
    _ensure_column(conn, "tenders", "corrigendum_date", "TEXT")
    _ensure_column(conn, "tenders", "version_fingerprint", "TEXT")
    _ensure_column(conn, "tender_matches", "tender_identity_key", "TEXT")

    _migrate_tender_identity_keys(conn)
    _migrate_match_identity_keys(conn)
    _backfill_tender_versions(conn)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_tender_identity
        ON tenders (identity_key)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_match_identity
        ON tender_matches (tender_identity_key, manufacturer_id)
        WHERE tender_identity_key IS NOT NULL
    """)

    # -------- LEGACY UNIQUE INDEX --------
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_match
    ON tender_matches (tender_hash, manufacturer_id)
    """)

    conn.commit()


def _ensure_column(conn, table, column, definition):
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_tender_identity_keys(conn):
    """Backfill stable keys without deleting or merging historical tender rows."""
    rows = conn.execute("SELECT * FROM tenders ORDER BY id").fetchall()
    columns = [description[0] for description in conn.execute(
        "SELECT * FROM tenders LIMIT 0"
    ).description]
    used = set()
    for row in rows:
        tender = dict(zip(columns, row))
        identity_key = tender.get("identity_key") or generate_hash(tender)
        if identity_key in used:
            # Retain duplicate historical rows as distinct records. Future
            # writes resolve through the canonical key to the first row.
            identity_key = hashlib.sha256(
                f"{identity_key}:legacy-row:{tender['id']}".encode("utf-8")
            ).hexdigest()
        used.add(identity_key)
        conn.execute(
            "UPDATE tenders SET identity_key=? WHERE id=?",
            (identity_key, tender["id"]),
        )


def _migrate_match_identity_keys(conn):
    """Attach legacy matches to identities while retaining every old match row."""
    matches = conn.execute(
        "SELECT id, tender_hash, manufacturer_id, manufacturer_name, score, confidence, created_at "
        "FROM tender_matches WHERE tender_identity_key IS NULL ORDER BY id"
    ).fetchall()
    for match in matches:
        match_id, tender_hash, manufacturer_id, manufacturer_name, score, confidence, created_at = match
        tenders = conn.execute(
            "SELECT identity_key FROM tenders WHERE content_hash=? ORDER BY id",
            (tender_hash,),
        ).fetchall()
        if len(tenders) == 1:
            conn.execute(
                "UPDATE tender_matches SET tender_identity_key=? WHERE id=?",
                (tenders[0][0], match_id),
            )
        # An old title+organization digest may refer to several distinct
        # notices. Keep the historical match intact but unlinked; assigning it
        # to every candidate would invent match evidence the old schema lacked.


# -------- HASH --------
def generate_hash(tender):
    """
    Generates a SHA-256 key for a tender's stable source identity.

    Args:
        tender (dict): Dictionary containing 'title' and 'organization'.

    Returns:
        str: SHA-256 hexadecimal identity key.

    Notes:
        - Prefer the official tender reference and organization, which survives
          title edits and can identify the same official tender across portals.
        - Fall back to the detail URL, then typed source/title/date fields.
    """
    title = _normalize_identity_text(tender.get("title"))
    organization = _normalize_identity_text(tender.get("organization"))
    portal = _normalize_identity_text(tender.get("source_portal"))
    tender_id = _normalize_identity_text(tender.get("tender_id"))
    source_url = _normalize_url(tender.get("source_url"))

    if tender_id and not (portal == "iisc" and tender_id.startswith("iisc_")):
        identity = ["official_id", organization, tender_id]
    elif source_url and not _is_listing_url(source_url):
        identity = ["detail_url", source_url]
    elif portal == "iisc":
        # IISc has no exposed notice ID; its previous scraper-generated Python
        # hash was process-random. Stable text identity preserves repeat runs.
        identity = ["iisc_listing_text", organization, title]
    else:
        identity = [
            "fallback", portal, title, organization,
            _normalize_identity_date(tender.get("published_date")),
            _normalize_identity_date(tender.get("closing_date")),
        ]
    payload = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_identity_text(value):
    return " ".join(str(value or "").casefold().split())


def _normalize_identity_date(value):
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else _normalize_identity_text(value)


def _normalize_url(value):
    if not value:
        return ""
    parts = urlsplit(str(value).strip())
    if not parts.scheme or not parts.netloc:
        return str(value).strip().rstrip("/")
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _is_listing_url(url):
    path = urlsplit(url).path.rstrip("/").casefold()
    return path in {"", "/tenders", "/all-tenders", "/latestactivetendersnew"}


def generate_legacy_content_hash(tender):
    """Preserve the former title/organization digest for historical compatibility."""
    title = _normalize_identity_text(tender.get("title"))
    organization = _normalize_identity_text(tender.get("organization"))
    return hashlib.md5(f"{title}_{organization}".encode("utf-8")).hexdigest()


VERSION_CONTENT_FIELDS = (
    "title",
    "organization",
    "published_date",
    "updated_date",
    "corrigendum_date",
    "closing_date",
    "raw_text",
)


def _tender_snapshot(tender):
    """Return a stable, JSON-safe snapshot separating content from provenance."""
    content = {}
    for field in VERSION_CONTENT_FIELDS:
        value = tender.get(field)
        if isinstance(value, str):
            value = value.replace("\r\n", "\n").replace("\r", "\n")
        content[field] = value
    return {
        "tender_id": tender.get("tender_id"),
        "source_portal": tender.get("source_portal"),
        "source_url": tender.get("source_url"),
        "content": content,
    }


def generate_content_fingerprint(tender):
    """Return a SHA-256 fingerprint for tender content, independent of identity."""
    snapshot = _tender_snapshot(tender)
    canonical_content = json.dumps(
        snapshot["content"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()


def _record_tender_version(conn, tender):
    identity_key = tender["identity_key"]
    snapshot = _tender_snapshot(tender)
    fingerprint = generate_content_fingerprint(tender)
    snapshot_json = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    observed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    previous = conn.execute(
        "SELECT content_fingerprint, snapshot_json FROM tender_versions "
        "WHERE tender_identity_key=? ORDER BY last_seen_at DESC, id DESC LIMIT 1",
        (identity_key,),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO tender_versions (
            tender_identity_key, content_fingerprint, snapshot_json, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(tender_identity_key, content_fingerprint) DO UPDATE SET
            last_seen_at=excluded.last_seen_at
        """,
        (identity_key, fingerprint, snapshot_json, observed_at, observed_at),
    )
    if previous and previous[0] != fingerprint:
        comparison = compare_tender_versions(previous[1], snapshot_json)
        conn.execute(
            """
            INSERT OR IGNORE INTO tender_amendments (
                tender_identity_key, from_fingerprint, to_fingerprint, change_status,
                change_types_json, evidence_json, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity_key, previous[0], fingerprint, comparison["status"],
                json.dumps(comparison["change_types"], sort_keys=True),
                json.dumps(comparison["evidence"], ensure_ascii=False, sort_keys=True),
                observed_at,
            ),
        )
    conn.execute(
        "UPDATE tenders SET version_fingerprint=? WHERE identity_key=?",
        (fingerprint, identity_key),
    )
    return fingerprint


def get_tender_amendments(conn, identity_key):
    """Return stored version comparisons in observation order."""
    rows = conn.execute(
        "SELECT from_fingerprint, to_fingerprint, change_status, change_types_json, "
        "evidence_json, observed_at FROM tender_amendments "
        "WHERE tender_identity_key=? ORDER BY id",
        (identity_key,),
    ).fetchall()
    return [
        {
            "from_fingerprint": row[0],
            "to_fingerprint": row[1],
            "status": row[2],
            "change_types": json.loads(row[3]),
            "evidence": json.loads(row[4]),
            "observed_at": row[5],
        }
        for row in rows
    ]


def get_tender_amendment(conn, identity_key, version_fingerprint):
    """Return the comparison that produced a given tender content version."""
    row = conn.execute(
        "SELECT from_fingerprint, to_fingerprint, change_status, change_types_json, "
        "evidence_json, observed_at FROM tender_amendments "
        "WHERE tender_identity_key=? AND to_fingerprint=? ORDER BY id DESC LIMIT 1",
        (identity_key, version_fingerprint),
    ).fetchone()
    if row is None:
        return None
    return {
        "from_fingerprint": row[0],
        "to_fingerprint": row[1],
        "status": row[2],
        "change_types": json.loads(row[3]),
        "evidence": json.loads(row[4]),
        "observed_at": row[5],
    }


def _backfill_tender_versions(conn):
    """Seed one version row for existing records without rewriting their history."""
    rows = conn.execute(
        "SELECT * FROM tenders WHERE version_fingerprint IS NULL ORDER BY id"
    ).fetchall()
    columns = [column[0] for column in conn.execute("SELECT * FROM tenders LIMIT 0").description]
    for row in rows:
        tender = dict(zip(columns, row))
        # Existing records have no historical version trail. Seed their current
        # persisted content as the earliest version available to this schema.
        _record_tender_version(conn, tender)


# -------- DUP CHECK --------
def tender_exists(conn, tender_id, content_hash):
    """
    Checks if a tender has already been recorded in the database.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender_id (str): Portal-specific unique ID.
        content_hash (str): Global content-based hash.

    Returns:
        bool: True if a matching record exists, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM tenders WHERE tender_id=? AND content_hash=? LIMIT 1",
        (tender_id, content_hash)
    )
    return cursor.fetchone() is not None


# -------- INSERT TENDER --------
def insert_tender(conn, tender, identity_key):
    """
    Inserts a new tender record into the database.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender (dict): Normalized tender data.
        identity_key (str): Generated stable source identity key.

    Notes:
        - Stores both the portal ID and the global content hash.
        - Captures full metadata including source URL and raw text for future analysis.
    """
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO tenders (
        tender_id,
        content_hash,
        identity_key,
        title,
        organization,
        published_date,
        updated_date,
        corrigendum_date,
        closing_date,
        source_url,
        source_portal,
        raw_text,
        scraped_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tender.get("tender_id"),
        generate_legacy_content_hash(tender),
        identity_key,
        tender.get("title"),
        tender.get("organization"),
        tender.get("published_date"),
        tender.get("updated_date"),
        tender.get("corrigendum_date"),
        tender.get("closing_date"),
        tender.get("source_url"),
        tender.get("source_portal"),
        tender.get("raw_text"),
        tender.get("scraped_at")
    ))


# -------- INSERT MATCH --------
def insert_match(conn, tender_hash, match):
    """
    Records a manufacturer match for a specific tender identity.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender_hash (str): Stable SHA-256 identity key of the tender.
        match (dict): Metadata about the match (manufacturer_id, score, confidence).
    
    Notes:
        - Uses 'INSERT OR IGNORE' to prevent duplicate match records.
    """
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO tender_matches (
            tender_hash,
            manufacturer_id,
            manufacturer_name,
            score,
            confidence,
            tender_identity_key
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        tender_hash,
        match["manufacturer_id"],
        match["manufacturer_name"],
        match["score"],
        match["confidence"],
        tender_hash,
    ))


# -------- UPDATE FLAGS --------
def update_flags(conn, identity_key, is_blocked, has_signal):
    """
    Updates classification flags for an existing tender record.

    Args:
        conn (sqlite3.Connection): Active connection.
        identity_key (str): Stable identity key of the target tender.
        is_blocked (bool): Whether the tender was filtered by the blocklist.
        has_signal (bool): Whether the tender is high-value for matching.
    """
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tenders
        SET is_blocked=?, has_signal=?
        WHERE identity_key=?
    """, (int(is_blocked), int(has_signal), identity_key))


# -------- MAIN PROCESS --------
def get_tender_by_hash(conn, content_hash):
    """
    Retrieves an existing tender from the database by its content hash.
    
    Args:
        conn (sqlite3.Connection): Active connection.
        content_hash (str): Target tender hash.
        
    Returns:
        dict: The tender record if found, else None.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM tenders
        WHERE content_hash = ?
        LIMIT 1
    """, (content_hash,))
    
    # We want to return a dict, so we can access columns by name
    columns = [col[0] for col in cursor.description]
    row = cursor.fetchone()
    
    if row:
        return dict(zip(columns, row))
    return None


def get_tender_by_identity(conn, identity_key):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenders WHERE identity_key=? LIMIT 1", (identity_key,))
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip((col[0] for col in cursor.description), row))


def upsert_or_get_tender(conn, tender):
    """
    Handles insertion or retrieval of a tender, enabling reprocessing.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender (dict): Raw tender data from scraper.

    Returns:
        tuple (dict, bool): 
            - dict: The merged tender (if existing) or new tender (if new).
            - bool: True if the tender is NEW, False if it EXISTING_NOT_EMAILED (or already emailed).

    Notes:
        - Replaces the hard gate in process_tender.
    """
    identity_key = generate_hash(tender)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO tenders (
            tender_id, content_hash, identity_key, title, organization,
            published_date, updated_date, corrigendum_date, closing_date,
            source_url, source_portal, raw_text, scraped_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tender.get("tender_id"), generate_legacy_content_hash(tender), identity_key,
        tender.get("title"), tender.get("organization"), tender.get("published_date"),
        tender.get("updated_date"), tender.get("corrigendum_date"),
        tender.get("closing_date"), tender.get("source_url"),
        tender.get("source_portal"), tender.get("raw_text"), tender.get("scraped_at"),
    ))
    is_new = cursor.rowcount == 1
    cursor.execute("""
        UPDATE tenders SET
            tender_id=COALESCE(NULLIF(?, ''), tender_id),
            title=COALESCE(NULLIF(?, ''), title),
            organization=COALESCE(NULLIF(?, ''), organization),
            published_date=COALESCE(NULLIF(?, ''), published_date),
            updated_date=COALESCE(NULLIF(?, ''), updated_date),
            corrigendum_date=COALESCE(NULLIF(?, ''), corrigendum_date),
            closing_date=COALESCE(NULLIF(?, ''), closing_date),
            source_url=COALESCE(NULLIF(?, ''), source_url),
            source_portal=COALESCE(NULLIF(?, ''), source_portal),
            raw_text=COALESCE(NULLIF(?, ''), raw_text),
            scraped_at=COALESCE(NULLIF(?, ''), scraped_at)
        WHERE identity_key=?
    """, (
        tender.get("tender_id"), tender.get("title"), tender.get("organization"),
        tender.get("published_date"), tender.get("updated_date"),
        tender.get("corrigendum_date"), tender.get("closing_date"),
        tender.get("source_url"), tender.get("source_portal"), tender.get("raw_text"),
        tender.get("scraped_at"), identity_key,
    ))
    existing = get_tender_by_identity(conn, identity_key)
    version_fingerprint = _record_tender_version(conn, existing)
    merged = {**tender, **existing}
    merged["identity_key"] = identity_key
    merged["version_fingerprint"] = version_fingerprint
    merged["emailed"] = existing.get("emailed", 0)
    return merged, is_new


def process_tender(conn, tender):
    """
    Main entry point for persisting a scraped tender.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender (dict): Raw tender data from scraper.

    Returns:
        dict: The updated tender dict with 'content_hash' added, or None if it's a duplicate.

    Notes:
        - Orchestrates hashing, duplicate checking, and insertion.
    """
    result, is_new = upsert_or_get_tender(conn, tender)
    return result if is_new else None


# -------- QUERY FOR EMAIL --------
def get_high_signal_matches(conn):
    """
    Retrieves recent high-value matches for the hourly/daily digest.

    Args:
        conn (sqlite3.Connection): Active connection.

    Returns:
        list: List of sqlite3.Row or tuples containing joined tender and match data.

    Notes:
        - Currently filtered to matches created within the last 30 minutes.
    """
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        t.title,
        t.organization,
        m.manufacturer_name,
        m.score,
        m.confidence
    FROM tenders t
    JOIN tender_matches m
        ON t.identity_key = m.tender_identity_key
    WHERE t.has_signal = 1
    AND m.created_at >= datetime('now', '-30 minutes')
    ORDER BY m.score DESC
    """)

    return cursor.fetchall()

def mark_as_emailed(conn, identity_key):
    """
    Sets the 'emailed' flag for a tender to prevent inclusion in future digests.

    Args:
        conn (sqlite3.Connection): Active connection.
        identity_key (str): Stable target tender identity.
    """
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tenders
        SET emailed = 1
        WHERE identity_key = ?
    """, (identity_key,))
    conn.commit()


def is_already_emailed(conn, identity_key):
    """
    Checks if a tender has already been sent in an email digest.

    Args:
        conn (sqlite3.Connection): Active connection.
        identity_key (str): Stable target tender identity.

    Returns:
        bool: True if the emailed flag is set, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT emailed FROM tenders
        WHERE identity_key = ?
        LIMIT 1
    """, (identity_key,))
    
    row = cursor.fetchone()
    return row and row[0] == 1

def normalize_title(title):
    """
    Strips special characters and whitespace from a tender title for robust comparison.

    Args:
        title (str): Raw tender title.

    Returns:
        str: Alphanumeric-only lowercase string.
    """
    return re.sub(r'[^a-z0-9 ]', '', (title or "").lower()).strip()
