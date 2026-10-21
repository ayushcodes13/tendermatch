"""Promote explicitly human-adjudicated feedback into a separate eval dataset."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

VALID_EVALUATION_LABELS = {
    "relevant",
    "not_relevant",
    "potentially_relevant_needs_review",
    "insufficient_information",
}


def build_adjudicated_dataset(review_queue: dict, *, trusted_adjudicators: set[str] | frozenset[str]) -> dict:
    """Build evaluation cases only from entries with explicit human adjudication."""
    if not isinstance(review_queue, dict):
        raise ValueError("review queue must be an object")
    if review_queue.get("export_kind") != "salesperson_feedback_review_queue":
        raise ValueError("input is not a TenderMatch salesperson feedback review queue")
    if review_queue.get("eligible_for_metrics") is not False:
        raise ValueError("review queue must remain marked ineligible for metrics before adjudication")
    items = review_queue.get("items")
    if not isinstance(items, list):
        raise ValueError("review queue items must be a list")

    cases = []
    seen_feedback_ids = set()
    seen_pairs = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each review queue item must be an object")
        if item.get("review_status") != "human_adjudicated":
            continue
        feedback_id = item.get("feedback_record_id")
        if type(feedback_id) is not int or feedback_id <= 0:
            raise ValueError("adjudicated items require a positive feedback_record_id")
        if feedback_id in seen_feedback_ids:
            raise ValueError(f"duplicate adjudicated feedback record: {feedback_id}")
        seen_feedback_ids.add(feedback_id)

        label = item.get("adjudicated_label")
        if not isinstance(label, str):
            raise ValueError(f"unsupported adjudicated evaluation label for feedback {feedback_id}")
        if label not in VALID_EVALUATION_LABELS:
            raise ValueError(f"unsupported adjudicated evaluation label for feedback {feedback_id}")
        text_fields = (
            "tender_identity_key", "manufacturer_id", "description",
            "adjudication_reason", "adjudicator", "adjudicated_at",
        )
        if any(not isinstance(item.get(field), str) for field in text_fields):
            raise ValueError(f"adjudicated feedback {feedback_id} is missing required text context")
        tender_id = item["tender_identity_key"].strip()
        manufacturer_id = item["manufacturer_id"].strip()
        description = item["description"].strip()
        reason = item["adjudication_reason"].strip()
        adjudicator = item["adjudicator"].strip()
        adjudicated_at = item["adjudicated_at"].strip()
        source_url = item.get("source_url")
        tender_version = item.get("tender_version")
        if tender_version is not None and (not isinstance(tender_version, str) or not tender_version.strip()):
            raise ValueError(f"tender_version for feedback {feedback_id} must be a non-empty string or null")
        if isinstance(tender_version, str):
            tender_version = tender_version.strip()
        allowed_adjudicators = {value.casefold() for value in trusted_adjudicators if value.strip()}
        if adjudicator.casefold() not in allowed_adjudicators:
            raise ValueError(f"adjudicator for feedback {feedback_id} is not allowlisted")
        if len(description) > 50_000:
            raise ValueError(f"description for feedback {feedback_id} exceeds 50000 characters")
        if not all((tender_id, manufacturer_id, description, reason, adjudicator, adjudicated_at)):
            raise ValueError(f"adjudicated feedback {feedback_id} is missing required context")
        try:
            timestamp = datetime.fromisoformat(adjudicated_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError
        except ValueError:
            raise ValueError(f"adjudicated_at for feedback {feedback_id} must be an ISO-8601 timezone-aware timestamp") from None
        try:
            if not isinstance(source_url, str):
                raise ValueError
            parsed = urlsplit(source_url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError
        except ValueError:
            raise ValueError(f"adjudicated feedback {feedback_id} requires a valid HTTP(S) source URL") from None

        pair = (tender_id, tender_version, manufacturer_id)
        if pair in seen_pairs:
            raise ValueError(f"multiple adjudicated feedback records for tender/version/manufacturer pair {pair}")
        seen_pairs.add(pair)
        evaluation_tender_id = f"{tender_id}@{tender_version}" if tender_version else tender_id

        technical_evidence = item.get("technical_evidence", [])
        known_exclusions = item.get("known_exclusions", [])
        if not isinstance(technical_evidence, list) or not all(isinstance(value, str) for value in technical_evidence):
            raise ValueError(f"technical_evidence for feedback {feedback_id} must be a string list")
        if not isinstance(known_exclusions, list) or not all(isinstance(value, str) for value in known_exclusions):
            raise ValueError(f"known_exclusions for feedback {feedback_id} must be a string list")

        cases.append({
            "case_id": f"feedback-{feedback_id}",
            "tender_id": evaluation_tender_id,
            "description": description,
            "manufacturer_id": manufacturer_id,
            "label": label,
            "reason": reason,
            "technical_evidence": technical_evidence,
            "known_exclusions": known_exclusions,
            "provenance": {
                "type": "human_reviewed_feedback",
                "source": f"salesperson feedback record {feedback_id}",
                "review_status": "human_adjudicated",
                "feedback_label": item.get("feedback_label"),
                "feedback_reviewer": item.get("reviewer"),
                "feedback_reviewed_at": item.get("reviewed_at"),
                "adjudicator": adjudicator,
                "adjudicated_at": adjudicated_at,
                "tender_identity_key": tender_id,
                "tender_reference": item.get("tender_reference"),
                "tender_version": tender_version,
                "source_url": source_url,
                "source_portal": item.get("source_portal"),
                "tender_context_status": item.get("tender_context_status"),
            },
        })

    if not cases:
        raise ValueError("no human-adjudicated feedback items were found")
    canonical = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    dataset_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return {
        "dataset_id": f"tendermatch-human-feedback-{dataset_hash}",
        "description": "Human-adjudicated feedback cases; separate from synthetic regression cases.",
        "human_reviewed_case_count": len(cases),
        "synthetic_case_count": 0,
        "ranking_complete_tender_ids": [],
        "cases": cases,
    }


def write_adjudicated_dataset(
    review_queue_path: str | Path,
    output_path: str | Path,
    *,
    trusted_adjudicators: set[str] | frozenset[str],
) -> int:
    queue = json.loads(Path(review_queue_path).read_text(encoding="utf-8"))
    dataset = build_adjudicated_dataset(queue, trusted_adjudicators=trusted_adjudicators)
    payload = json.dumps(dataset, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return len(dataset["cases"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create a separate evaluation dataset from human-adjudicated feedback")
    parser.add_argument("--review-queue", required=True)
    parser.add_argument("--output", required=True, help="New output file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        from config import EVALUATION_ADJUDICATORS

        if not EVALUATION_ADJUDICATORS:
            raise ValueError("Set TENDERMATCH_EVALUATION_ADJUDICATORS before importing adjudicated cases")
        count = write_adjudicated_dataset(
            args.review_queue,
            args.output,
            trusted_adjudicators=EVALUATION_ADJUDICATORS,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"Cannot create adjudicated dataset: {type(exc).__name__}: {exc}")
    print(f"Created separate human-reviewed dataset with {count} cases; inspect it before evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
