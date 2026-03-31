import sqlite3
import hashlib

DB_PATH = "data/tenders.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db(conn):
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
    title = (tender.get("title") or "").strip().lower()
    organization = (tender.get("organization") or "").strip().lower()

    base = f"{title}_{organization}"

    return hashlib.md5(base.encode()).hexdigest()


# -------- DUP CHECK --------
def tender_exists(conn, tender_id, content_hash):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM tenders WHERE tender_id=? AND content_hash=? LIMIT 1",
        (tender_id, content_hash)
    )
    return cursor.fetchone() is not None


# -------- INSERT TENDER --------
def insert_tender(conn, tender, content_hash):
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
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tenders
        SET is_blocked=?, has_signal=?
        WHERE content_hash=?
    """, (int(is_blocked), int(has_signal), content_hash))


# -------- MAIN PROCESS --------
def process_tender(conn, tender):
    content_hash = generate_hash(tender)

    if tender_exists(conn, tender.get("tender_id"), content_hash):
        return None  # duplicate

    insert_tender(conn, tender, content_hash)
    tender["content_hash"] = content_hash
    return tender


# -------- QUERY FOR EMAIL --------
def get_high_signal_matches(conn):
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
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tenders
        SET emailed = 1
        WHERE content_hash = ?
    """, (content_hash,))
    conn.commit()


def is_already_emailed(conn, content_hash):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT emailed FROM tenders
        WHERE content_hash = ?
        LIMIT 1
    """, (content_hash,))
    
    row = cursor.fetchone()
    return row and row[0] == 1