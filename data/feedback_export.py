"""Export feedback into a human adjudication queue, never directly into metrics."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from data.db import get_connection, init_db

_DIRECT_LABELS = {
    "relevant": "relevant",
    "not_relevant": "not_relevant",
    "missing_technical_evidence": "insufficient_information",
}


def build_feedback_review_queue(conn: sqlite3.Connection) -> dict:
    """Join feedback with current tender context and mark all items pending review."""
    rows = conn.execute(
        """SELECT f.id, f.tender_identity_key, f.tender_version,
                  f.manufacturer_id, f.label, f.reason, f.reviewer, f.reviewed_at,
                  t.tender_id, t.title, t.raw_text, t.source_url, t.source_portal, t.closing_date,
                  v.snapshot_json
           FROM salesperson_feedback AS f
           LEFT JOIN tenders AS t ON t.identity_key = f.tender_identity_key
           LEFT JOIN tender_versions AS v
             ON v.tender_identity_key = f.tender_identity_key
            AND v.content_fingerprint = f.tender_version
           ORDER BY f.id"""
    ).fetchall()
    items = []
    for row in rows:
        (
            feedback_id, identity_key, version, manufacturer_id, label, reason,
            reviewer, reviewed_at, tender_id, title, raw_text, source_url, source_portal,
            current_closing_date, snapshot_json,
        ) = row
        snapshot_status = "tender_record_missing"
        if snapshot_json:
            snapshot = json.loads(snapshot_json)
            content = snapshot.get("content") or {}
            tender_id = snapshot.get("tender_id")
            title = content.get("title")
            raw_text = content.get("raw_text")
            source_url = snapshot.get("source_url")
            source_portal = snapshot.get("source_portal")
            snapshot_status = "feedback_version_snapshot"
        elif title is not None:
            snapshot_status = "current_tender_fallback"
        items.append({
            "feedback_record_id": feedback_id,
            "tender_identity_key": identity_key,
            "tender_version": version,
            "tender_reference": tender_id,
            "title": title,
            "description": raw_text or title or "",
            "closing_date": content.get("closing_date") if snapshot_json else current_closing_date,
            "source_url": source_url,
            "source_portal": source_portal,
            "tender_context_status": snapshot_status,
            "manufacturer_id": manufacturer_id,
            "feedback_label": label,
            "suggested_evaluation_label": _DIRECT_LABELS.get(label),
            "reason": reason,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "review_status": "pending_adjudication",
        })
    return {
        "schema_version": 1,
        "export_kind": "salesperson_feedback_review_queue",
        "eligible_for_metrics": False,
        "items": items,
    }


def write_feedback_review_queue(conn: sqlite3.Connection, output_path: str | Path) -> int:
    """Write a private, non-overwriting JSON export for human adjudication."""
    target = Path(output_path)
    payload = json.dumps(build_feedback_review_queue(conn), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return len(json.loads(payload)["items"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export salesperson feedback for human evaluation-dataset adjudication")
    parser.add_argument("--output", required=True, help="New output file path; existing files are never overwritten")
    args = parser.parse_args(argv)
    conn = get_connection()
    try:
        init_db(conn)
        count = write_feedback_review_queue(conn, args.output)
        print(f"Exported {count} feedback records for human adjudication; not eligible for metrics.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
