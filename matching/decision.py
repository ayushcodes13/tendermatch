"""
Final tender decision logic.

Only this module should assign final buckets.

Decision buckets:
- reject_hard
- reject_soft
- low_signal
- explore
- rescued
- high_signal
- agent_review
"""

from matching.thresholds import resolve_thresholds


def decide_tender(signals, concepts, scoring, manufacturer_candidates=None, thresholds=None):
    manufacturer_candidates = manufacturer_candidates or []
    thresholds = resolve_thresholds(thresholds)

    score = scoring["score"]

    hard_junk_clusters = signals.get("hard_junk_clusters", [])
    soft_risks = signals.get("soft_risk_terms", [])
    contextual_negatives = signals.get("contextual_negative_hits", [])
    domain_review_hits = signals.get("domain_review_hits", [])

    has_rescue = has_real_rescue_evidence(signals, concepts, manufacturer_candidates, thresholds)
    has_support_only = concepts.get("has_support_only_concepts", False)
    has_rescue_concept = concepts.get("has_rescue_concept", False)
    has_mfr_evidence = has_strong_manufacturer_evidence(manufacturer_candidates, thresholds)

    reason_codes = build_reason_codes(
        signals=signals,
        concepts=concepts,
        manufacturer_candidates=manufacturer_candidates,
        thresholds=thresholds,
    )

    # Conflicting domain/specification evidence is ambiguous and must remain
    # visible to a person, even when no current manufacturer has a strong hit.
    if domain_review_hits:
        return {
            "decision": "agent_review",
            "reason_codes": reason_codes,
            "agent_review_required": True,
        }

    # --------------------------------------------------
    # 1. Hard junk gates
    # --------------------------------------------------
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

    # --------------------------------------------------
    # 2. Contextual negative gates
    # --------------------------------------------------
    if contextual_negatives and not has_rescue:
        return {
            "decision": "reject_soft",
            "reason_codes": reason_codes + ["CONTEXT_NEGATIVE_WITHOUT_RESCUE"],
            "agent_review_required": False,
        }

    if contextual_negatives and has_rescue:
        return {
            "decision": "agent_review",
            "reason_codes": reason_codes + ["CONTEXT_NEGATIVE_WITH_RESCUE_CONFLICT"],
            "agent_review_required": True,
        }

    # --------------------------------------------------
    # 3. Soft-risk rescue gate
    # --------------------------------------------------
    if has_strong_soft_risk(signals) and has_rescue:
        if score >= thresholds["soft_risk_high_signal"] and (has_rescue_concept or has_mfr_evidence):
            return {
                "decision": "high_signal",
                "reason_codes": reason_codes + ["SOFT_RISK_RESCUED_HIGH_CONFIDENCE"],
                "agent_review_required": False,
            }

        if score >= thresholds["soft_risk_rescued"]:
            return {
                "decision": "rescued",
                "reason_codes": reason_codes + ["SOFT_RISK_RESCUED"],
                "agent_review_required": score < thresholds["soft_risk_review_below"],
            }

    # --------------------------------------------------
    # 4. Clean high-signal gate
    # --------------------------------------------------
    top_candidate = manufacturer_candidates[0] if manufacturer_candidates else None
    top_claim_status = (
        top_candidate.get("claim_provenance", {}).get("claim_status")
        if top_candidate else None
    )

    if score >= thresholds["high_signal"] and (has_rescue_concept or has_mfr_evidence):
        if top_claim_status == "has_conflicts":
            return {
                "decision": "agent_review",
                "reason_codes": reason_codes + ["UNSUPPORTED_MANUFACTURER_CLAIM_CONFLICT"],
                "agent_review_required": True,
            }
        return {
            "decision": "high_signal",
            "reason_codes": reason_codes + ["SCORE_HIGH_SIGNAL"],
            "agent_review_required": False,
        }

    # --------------------------------------------------
    # 5. Strong manufacturer match without concept
    # --------------------------------------------------
    if score >= thresholds["manufacturer_explore"] and has_mfr_evidence:
        return {
            "decision": "explore",
            "reason_codes": reason_codes + ["MANUFACTURER_EVIDENCE_EXPLORE"],
            "agent_review_required": False,
        }

    # --------------------------------------------------
    # 6. Rescue concept but borderline score
    # --------------------------------------------------
    if has_rescue_concept and thresholds["rescue_concept_review_min"] <= score < thresholds["rescue_concept_review_max_exclusive"]:
        return {
            "decision": "agent_review",
            "reason_codes": reason_codes + ["RESCUE_CONCEPT_BORDERLINE_SCORE"],
            "agent_review_required": True,
        }

    # --------------------------------------------------
    # 7. Support-only concepts
    # --------------------------------------------------
    if has_support_only and not has_rescue_concept and not has_mfr_evidence:
        if score >= thresholds["support_review"]:
            return {
                "decision": "agent_review",
                "reason_codes": reason_codes + ["SUPPORT_ONLY_CONCEPT_REVIEW"],
                "agent_review_required": True,
            }

        return {
            "decision": "low_signal",
            "reason_codes": reason_codes + ["SUPPORT_ONLY_CONCEPT_LOW_SIGNAL"],
            "agent_review_required": False,
        }

    # --------------------------------------------------
    # 8. Explore / borderline
    # --------------------------------------------------
    if score >= thresholds["explore"]:
        return {
            "decision": "explore",
            "reason_codes": reason_codes + ["SCORE_EXPLORE"],
            "agent_review_required": False,
        }

    if score >= thresholds["review"]:
        return {
            "decision": "agent_review",
            "reason_codes": reason_codes + ["BORDERLINE_SCORE"],
            "agent_review_required": True,
        }

    # --------------------------------------------------
    # 9. Negative low-score fallback
    # --------------------------------------------------
    if soft_risks or contextual_negatives:
        return {
            "decision": "reject_soft",
            "reason_codes": reason_codes + ["LOW_SCORE_WITH_NEGATIVE_SIGNALS"],
            "agent_review_required": False,
        }

    # --------------------------------------------------
    # 10. No evidence fallback
    # --------------------------------------------------
    if not has_rescue and not has_support_only and not has_mfr_evidence:
        return {
            "decision": "reject_soft",
            "reason_codes": reason_codes + ["NO_POSITIVE_EVIDENCE"],
            "agent_review_required": False,
        }

    return {
        "decision": "low_signal",
        "reason_codes": reason_codes + ["LOW_EVIDENCE"],
        "agent_review_required": False,
    }


def build_reason_codes(signals, concepts, manufacturer_candidates, thresholds=None):
    thresholds = resolve_thresholds(thresholds)
    reason_codes = []

    for cluster in signals.get("hard_junk_clusters", []):
        reason_codes.append(f"HARD_JUNK_{cluster['cluster_id'].upper()}")

    for term in signals.get("soft_risk_terms", []):
        reason_codes.append(f"SOFT_RISK_{normalize_reason(term)}")

    for hit in signals.get("contextual_negative_hits", []):
        reason_codes.append(f"CONTEXT_NEGATIVE_{hit['rule_id']}")

    for hit in signals.get("domain_review_hits", []):
        reason_codes.append(f"DOMAIN_COMPATIBILITY_REVIEW_{hit['rule_id']}")

    for concept in concepts.get("matched_concepts", []):
        reason_codes.append(concept["reason_code"])

    if has_strong_manufacturer_evidence(manufacturer_candidates, thresholds):
        reason_codes.append("MANUFACTURER_EVIDENCE_PRESENT")

    return dedupe_preserve_order(reason_codes)


def has_real_rescue_evidence(signals, concepts, manufacturer_candidates, thresholds=None):
    """
    Real rescue evidence means:
    - rescue concept from active concepts
    - strong manufacturer evidence

    Important:
    signals["has_rescue"] is intentionally NOT used here.

    Why?
    Because signals may contain broad/static rescue terms like XRD.
    If the concept is not active and no manufacturer strongly matches,
    it should not rescue the tender.
    """
    return bool(
        concepts.get("has_rescue_concept", False)
        or has_strong_manufacturer_evidence(manufacturer_candidates, thresholds)
    )


def has_strong_manufacturer_evidence(candidates, thresholds=None):
    thresholds = resolve_thresholds(thresholds)
    if not candidates:
        return False

    top = candidates[0]
    top_score = top.get("score", 0) or 0

    keyword_hits = top.get("keyword_hits", []) or []
    product_hits = top.get("product_hits", []) or []
    category_hits = top.get("category_hits", []) or []
    concept_hits = top.get("concept_hits", []) or []
    alias_hits = top.get("alias_hits", []) or []

    evidence_count = (
        len(keyword_hits)
        + len(product_hits)
        + len(category_hits)
        + len(concept_hits)
        + len(alias_hits)
    )

    # Concrete evidence + acceptable semantic score.
    with_evidence_min = thresholds["manufacturer_semantic_with_evidence_min_percent"] / 100
    semantic_only_min = thresholds["manufacturer_semantic_only_min_percent"] / 100
    if evidence_count >= 1 and top_score >= with_evidence_min:
        return True

    # Very high semantic score can count, but only at a stricter threshold.
    if top_score >= semantic_only_min:
        return True

    return False


def has_strong_soft_risk(signals):
    strong_soft_terms = {
        "amc",
        "annual maintenance",
        "maintenance",
        "repair",
        "rectification",
        "upgradation",
        "service contract",
        "warranty extension",
        "replacement",
    }

    soft_terms = {
        str(term).lower()
        for term in signals.get("soft_risk_terms", [])
    }

    return bool(soft_terms.intersection(strong_soft_terms))


def normalize_reason(text):
    return (
        str(text)
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
    )


def dedupe_preserve_order(items):
    seen = set()
    out = []

    for item in items:
        key = str(item)
        if key not in seen:
            seen.add(key)
            out.append(item)

    return out
