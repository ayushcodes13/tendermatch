
"""
Final tender decision logic.

Only this module should assign final buckets.
"""

def decide_tender(signals, concepts, scoring, manufacturer_candidates=None):
    manufacturer_candidates = manufacturer_candidates or []

    score = scoring["score"]

    hard_junk_clusters = signals.get("hard_junk_clusters", [])
    soft_risks = signals.get("soft_risk_terms", [])
    contextual_negatives = signals.get("contextual_negative_hits", [])

    has_rescue = (
        signals.get("has_rescue", False)
        or concepts.get("has_technical_concept", False)
        or has_manufacturer_evidence(manufacturer_candidates)
    )

    reason_codes = []

    for cluster in hard_junk_clusters:
        reason_codes.append(f"HARD_JUNK_{cluster['cluster_id'].upper()}")

    for term in soft_risks:
        reason_codes.append(f"SOFT_RISK_{normalize_reason(term)}")

    for hit in contextual_negatives:
        reason_codes.append(f"CONTEXT_NEGATIVE_{hit['rule_id']}")

    for concept in concepts.get("matched_concepts", []):
        reason_codes.append(concept["reason_code"])

    if has_manufacturer_evidence(manufacturer_candidates):
        reason_codes.append("MANUFACTURER_EVIDENCE_PRESENT")

    if hard_junk_clusters and not has_rescue:
        return {
            "decision": "reject_hard",
            "reason_codes": reason_codes + ["NO_RESCUE_EVIDENCE"],
            "agent_review_required": False,
        }

    if hard_junk_clusters and has_rescue:
        return {
            "decision": "agent_review",
            "reason_codes": reason_codes + ["HARD_JUNK_WITH_RESCUE_CONFLICT"],
            "agent_review_required": True,
        }

    if soft_risks and has_rescue and score >= 45:
        return {
            "decision": "rescued",
            "reason_codes": reason_codes + ["SOFT_RISK_RESCUED"],
            "agent_review_required": score < 65,
        }

    if score >= 75:
        return {
            "decision": "high_signal",
            "reason_codes": reason_codes + ["SCORE_HIGH_SIGNAL"],
            "agent_review_required": False,
        }

    if score >= 50:
        return {
            "decision": "explore",
            "reason_codes": reason_codes + ["SCORE_EXPLORE"],
            "agent_review_required": False,
        }

    if score >= 35:
        return {
            "decision": "agent_review",
            "reason_codes": reason_codes + ["BORDERLINE_SCORE"],
            "agent_review_required": True,
        }

    if soft_risks or contextual_negatives:
        return {
            "decision": "reject_soft",
            "reason_codes": reason_codes + ["LOW_SCORE_WITH_NEGATIVE_SIGNALS"],
            "agent_review_required": False,
        }

    return {
        "decision": "low_signal",
        "reason_codes": reason_codes + ["LOW_EVIDENCE"],
        "agent_review_required": False,
    }


def has_manufacturer_evidence(candidates):
    if not candidates:
        return False

    top = candidates[0]

    return bool(
        top.get("score", 0) >= 0.50
        or top.get("keyword_hits")
    )


def normalize_reason(text):
    return (
        str(text)
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )