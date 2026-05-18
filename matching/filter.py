"""
Evidence-based tender classifier.

Pipeline role:
Acts as the decision layer for tender relevance classification.

v2 design:
- Does not hard-block tenders just because one risky word appears.
- Separates signal detection from final decision.
- Supports manufacturer candidates from matcher.match_topk().
- Returns legacy-compatible fields so pipeline/run.py does not break yet.
- Produces decision traces and reason codes for debugging, DB storage, and email output.

Classification flow:
1. detect_signals()    -> negative/risk/rescue evidence
2. detect_concepts()   -> technical concept evidence
3. score_tender()      -> transparent scoring
4. decide_tender()     -> final bucket
5. build_trace()       -> full explainability object

Inputs:
- Normalized tender dictionary.
- Optional manufacturer candidates from TenderMatcher.match_topk().

Outputs:
- Classification dictionary containing category, decision, score, reason codes, and trace.
"""

from matching.signals import detect_signals
from matching.concepts import detect_concepts
from matching.scoring import score_tender
from matching.decision import decide_tender
from matching.trace import build_trace


SIGNAL_DECISIONS = {
    "high_signal",
    "explore",
    "rescued",
    "agent_review",
}


BLOCKED_DECISIONS = {
    "reject_hard",
    "reject_soft",
    "low_signal",
}


def classify_tender(tender, manufacturer_candidates=None):
    """
    Classifies one tender using the v2 evidence-based classifier.

    Args:
        tender (dict):
            Normalized tender data.

        manufacturer_candidates (list[dict] | None):
            Optional top-k manufacturer candidates from TenderMatcher.match_topk().
            This is optional for now so the old pipeline does not break.

    Returns:
        dict:
            Legacy-compatible + v2 classification result.
    """
    manufacturer_candidates = manufacturer_candidates or []

    signals = detect_signals(tender)
    concepts = detect_concepts(tender)

    scoring = score_tender(
        tender=tender,
        signals=signals,
        concepts=concepts,
        manufacturer_candidates=manufacturer_candidates,
    )

    decision = decide_tender(
        signals=signals,
        concepts=concepts,
        scoring=scoring,
        manufacturer_candidates=manufacturer_candidates,
    )

    trace = build_trace(
        tender=tender,
        signals=signals,
        concepts=concepts,
        scoring=scoring,
        decision=decision,
        manufacturer_candidates=manufacturer_candidates,
    )

    final_decision = decision["decision"]
    category = map_decision_to_legacy_category(final_decision)

    return {
        # legacy fields used by current pipeline/email code
        "is_blocked": final_decision in BLOCKED_DECISIONS,
        "has_signal": final_decision in SIGNAL_DECISIONS,
        "category": category,
        "reason": build_short_reason(decision.get("reason_codes", []), scoring.get("score")),

        # new v2 fields
        "decision": final_decision,
        "score": scoring["score"],
        "raw_score": scoring["raw_score"],
        "score_breakdown": scoring["breakdown"],
        "reason_codes": decision.get("reason_codes", []),
        "agent_review_required": decision.get("agent_review_required", False),
        "trace": trace,
    }


def map_decision_to_legacy_category(decision):
    """
    Maps v2 decision buckets to old categories.

    This prevents pipeline/run.py and email formatting from breaking immediately.
    Later, we should update the pipeline to use `decision` directly.
    """
    if decision == "high_signal":
        return "high_signal"

    if decision in {"explore", "rescued", "agent_review"}:
        return "explore"

    if decision == "low_signal":
        return "low_signal"

    return "blocked"


def build_short_reason(reason_codes, score):
    """
    Builds a compact reason string for current logs/emails.

    Full trace remains available in result["trace"].
    """
    if not reason_codes:
        return f"score: {score}"

    top_reasons = reason_codes[:5]
    return f"score: {score}; reasons: {', '.join(top_reasons)}"