
"""
Decision trace builder.

Standardizes classification output for DB/email/debugging.
"""

from datetime import datetime


PIPELINE_VERSION = "matching_v2_0"


def build_trace(tender, signals, concepts, scoring, decision, manufacturer_candidates=None):
    manufacturer_candidates = manufacturer_candidates or []

    return {
        "pipeline_version": PIPELINE_VERSION,
        "created_at": datetime.now().isoformat(),
        "tender_id": tender.get("tender_id"),
        "title": tender.get("title"),
        "organization": tender.get("organization"),

        "decision": decision["decision"],
        "score": scoring["score"],
        "raw_score": scoring["raw_score"],
        "score_breakdown": scoring["breakdown"],
        "reason_codes": decision["reason_codes"],
        "agent_review_required": decision.get("agent_review_required", False),

        "signals": signals,
        "concepts": concepts,
        "manufacturer_candidates": manufacturer_candidates[:5],
    }