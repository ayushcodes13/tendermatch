"""
Persistence layer for tender and match data using SQLite.

Pipeline role:
Handles all I/O operations for tenders, classification flags, and manufacturer matches. 
Ensures data integrity and implements the deduplication logic used to prevent 
re-processing of known tenders.

Key responsibilities:
- Schema management and database initialization.
- Content-based hashing for tender deduplication (title + organization).
- CRUD operations for tender records and manufacturer match results.
- State management for email dispatch tracking.

Inputs:
- Raw or processed tender dictionaries.
- Manufacturer match dictionaries.

Outputs:
- SQLite connection objects.
- Result sets for email formatting and pipeline statistics.

Notes:
- Uses an MD5 hash of 'title_organization' as the primary uniqueness constraint 
  to handle the same tender appearing across different portals with different IDs.
"""
import sqlite3
import hashlib
import re

DB_PATH = "data/tenders.db"


def get_connection():
    """
    Establishes a connection to the local SQLite database.

    Returns:
        sqlite3.Connection: An active database connection object.
    """
    return sqlite3.connect(DB_PATH)


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
    )
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # -------- UNIQUE INDEX --------
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_match
    ON tender_matches (tender_hash, manufacturer_id)
    """)

    conn.commit()


# -------- HASH --------
def generate_hash(tender):
    """
    Generates a deterministic content hash for a tender.

    Args:
        tender (dict): Dictionary containing 'title' and 'organization'.

    Returns:
        str: MD5 hexadecimal hash representing the tender identity.

    Notes:
        - Logic: MD5(lowercase(title)_lowercase(org)). 
        - This is the core of the project's cross-portal deduplication strategy.
    """
    title = (tender.get("title") or "").strip().lower()
    organization = (tender.get("organization") or "").strip().lower()

    base = f"{title}_{organization}"

    return hashlib.md5(base.encode()).hexdigest()


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
def insert_tender(conn, tender, content_hash):
    """
    Inserts a new tender record into the database.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender (dict): Normalized tender data.
        content_hash (str): Generated content hash.

    Notes:
        - Stores both the portal ID and the global content hash.
        - Captures full metadata including source URL and raw text for future analysis.
    """
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO tenders (
        tender_id,
        content_hash,
        title,
        organization,
        published_date,
        closing_date,
        source_url,
        source_portal,
        raw_text,
        scraped_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tender.get("tender_id"),
        content_hash,
        tender.get("title"),
        tender.get("organization"),
        tender.get("published_date"),
        tender.get("closing_date"),
        tender.get("source_url"),
        tender.get("source_portal"),
        tender.get("raw_text"),
        tender.get("scraped_at")
    ))


# -------- INSERT MATCH --------
def insert_match(conn, tender_hash, match):
    """
    Records a manufacturer match for a specific tender.

    Args:
        conn (sqlite3.Connection): Active connection.
        tender_hash (str): Content hash of the tender.
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
            confidence
        ) VALUES (?, ?, ?, ?, ?)
    """, (
        tender_hash,
        match["manufacturer_id"],
        match["manufacturer_name"],
        match["score"],
        match["confidence"]
    ))


# -------- UPDATE FLAGS --------
def update_flags(conn, content_hash, is_blocked, has_signal):
    """
    Updates classification flags for an existing tender record.

    Args:
        conn (sqlite3.Connection): Active connection.
        content_hash (str): Content hash of the target tender.
        is_blocked (bool): Whether the tender was filtered by the blocklist.
        has_signal (bool): Whether the tender is high-value for matching.
    """
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tenders
        SET is_blocked=?, has_signal=?
        WHERE content_hash=?
    """, (int(is_blocked), int(has_signal), content_hash))


# -------- MAIN PROCESS --------
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
    content_hash = generate_hash(tender)

    if tender_exists(conn, tender.get("tender_id"), content_hash):
        return None  # duplicate

    insert_tender(conn, tender, content_hash)
    tender["content_hash"] = content_hash
    return tender


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
        ON t.content_hash = m.tender_hash
    WHERE t.has_signal = 1
    AND m.created_at >= datetime('now', '-30 minutes')
    ORDER BY m.score DESC
    """)

    return cursor.fetchall()

def mark_as_emailed(conn, content_hash):
    """
    Sets the 'emailed' flag for a tender to prevent inclusion in future digests.

    Args:
        conn (sqlite3.Connection): Active connection.
        content_hash (str): Target tender hash.
    """
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tenders
        SET emailed = 1
        WHERE content_hash = ?
    """, (content_hash,))
    conn.commit()


def is_already_emailed(conn, content_hash):
    """
    Checks if a tender has already been sent in an email digest.

    Args:
        conn (sqlite3.Connection): Active connection.
        content_hash (str): Target tender hash.

    Returns:
        bool: True if the emailed flag is set, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT emailed FROM tenders
        WHERE content_hash = ?
        LIMIT 1
    """, (content_hash,))
    
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