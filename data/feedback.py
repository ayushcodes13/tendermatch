"""Append-only, allowlist-gated capture of salesperson relevance feedback."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone

from data.db import get_connection, init_db

FEEDBACK_LABELS = frozenset({
    "relevant",
    "not_relevant",
    "already_known",
    "worth_pursuing",
    "wrong_manufacturer",
    "incorrect_product_category",
    "missing_technical_evidence",
    "eligibility_not_met",
})
MAX_REASON_LENGTH = 1_000


def capture_feedback(
    conn: sqlite3.Connection,
    *,
    tender_identity_key: str,
    manufacturer_id: str,
    label: str,
    reviewer: str,
    trusted_reviewers: set[str] | frozenset[str],
    reason: str | None = None,
    tender_version: str | None = None,
) -> int:
    """Append one human label, preserving earlier submissions as history."""
    tender_identity_key = (tender_identity_key or "").strip()
    manufacturer_id = (manufacturer_id or "").strip()
    reviewer = (reviewer or "").strip()
    if not tender_identity_key or not manufacturer_id:
        raise ValueError("tender identity and manufacturer id are required")
    if label not in FEEDBACK_LABELS:
        raise ValueError(f"unsupported feedback label: {label}")
    allowed = {item.casefold(): item for item in trusted_reviewers if item.strip()}
    canonical_reviewer = allowed.get(reviewer.casefold())
    if not canonical_reviewer:
        raise PermissionError("reviewer is not in TENDERMATCH_FEEDBACK_REVIEWERS")
    reason = (reason or "").strip() or None
    if reason and len(reason) > MAX_REASON_LENGTH:
        raise ValueError(f"feedback reason must be {MAX_REASON_LENGTH} characters or fewer")
    timestamp = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """INSERT INTO salesperson_feedback
           (tender_identity_key, tender_version, manufacturer_id, label,
            reason, reviewer, reviewed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            tender_identity_key,
            (tender_version or "").strip() or None,
            manufacturer_id,
            label,
            reason,
            canonical_reviewer,
            timestamp,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Append salesperson feedback for a tender/manufacturer match")
    parser.add_argument("--tender-identity-key", required=True)
    parser.add_argument("--tender-version")
    parser.add_argument("--manufacturer-id", required=True)
    parser.add_argument("--label", required=True, choices=sorted(FEEDBACK_LABELS))
    parser.add_argument("--reviewer", required=True, help="Must match an operator-configured reviewer")
    parser.add_argument("--reason", default=None)
    args = parser.parse_args(argv)
    from config import FEEDBACK_REVIEWERS

    trusted_reviewers = FEEDBACK_REVIEWERS
    if not trusted_reviewers:
        parser.error("Set TENDERMATCH_FEEDBACK_REVIEWERS before capturing feedback")

    conn = get_connection()
    try:
        init_db(conn)
        try:
            feedback_id = capture_feedback(
                conn,
                tender_identity_key=args.tender_identity_key,
                tender_version=args.tender_version,
                manufacturer_id=args.manufacturer_id,
                label=args.label,
                reviewer=args.reviewer,
                trusted_reviewers=trusted_reviewers,
                reason=args.reason,
            )
        except (ValueError, PermissionError) as exc:
            parser.error(str(exc))
        print(f"Recorded feedback #{feedback_id} ({args.label}) for {args.tender_identity_key}.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
