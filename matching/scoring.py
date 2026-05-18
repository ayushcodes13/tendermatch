
"""
Tender scoring.

Converts extracted evidence into a transparent score.
"""

def score_tender(tender, signals, concepts, manufacturer_candidates=None):
    manufacturer_candidates = manufacturer_candidates or []

    score = 0
    breakdown = {}

    concept_score = min(concepts.get("concept_score", 0), 80)
    breakdown["technical_concept_score"] = concept_score
    score += concept_score

    manufacturer_score = score_manufacturer_candidates(manufacturer_candidates)
    breakdown["manufacturer_score"] = manufacturer_score
    score += manufacturer_score

    soft_risk_penalty = -10 * len(signals.get("soft_risk_terms", []))
    soft_risk_penalty = max(soft_risk_penalty, -25)
    breakdown["soft_risk_penalty"] = soft_risk_penalty
    score += soft_risk_penalty

    contextual_penalty = -18 * len(signals.get("contextual_negative_hits", []))
    contextual_penalty = max(contextual_penalty, -35)
    breakdown["contextual_negative_penalty"] = contextual_penalty
    score += contextual_penalty

    buyer_prior_penalty = -8 if signals.get("buyer_priors") else 0
    breakdown["buyer_prior_penalty"] = buyer_prior_penalty
    score += buyer_prior_penalty

    hard_junk_penalty = score_hard_junk(signals)
    breakdown["hard_junk_penalty"] = hard_junk_penalty
    score += hard_junk_penalty

    rescue_bonus = score_rescue(signals, concepts, manufacturer_candidates)
    breakdown["rescue_bonus"] = rescue_bonus
    score += rescue_bonus

    source_bonus = score_source_prior(tender)
    breakdown["source_bonus"] = source_bonus
    score += source_bonus

    final_score = max(0, min(100, score))

    return {
        "score": final_score,
        "raw_score": score,
        "breakdown": breakdown,
    }


def score_manufacturer_candidates(candidates):
    if not candidates:
        return 0

    top = candidates[0]
    top_score = top.get("score", 0) or 0
    keyword_hits = top.get("keyword_hits", []) or []

    points = 0

    # Raw embedding scores are not calibrated, so use broad bands.
    if top_score >= 0.75:
        points += 30
    elif top_score >= 0.60:
        points += 22
    elif top_score >= 0.45:
        points += 14
    else:
        points += 8

    if top.get("rank") == 1:
        points += 5

    if keyword_hits:
        points += min(15, 3 * len(keyword_hits))

    return min(points, 45)


def score_hard_junk(signals):
    clusters = signals.get("hard_junk_clusters", [])

    if not clusters:
        return 0

    strong_count = sum(1 for c in clusters if c.get("strength") == "strong")
    medium_count = sum(1 for c in clusters if c.get("strength") == "medium")

    penalty = -(35 * strong_count + 20 * medium_count)

    return max(penalty, -70)


def score_rescue(signals, concepts, manufacturer_candidates):
    has_real_negative = bool(
        signals.get("hard_junk_clusters")
        or signals.get("contextual_negative_hits")
        or has_strong_soft_risk(signals)
    )

    has_rescue_term = signals.get("has_rescue", False)
    has_concept = concepts.get("has_technical_concept", False)

    top_manufacturer = manufacturer_candidates[0] if manufacturer_candidates else None
    has_manufacturer_evidence = bool(
        top_manufacturer
        and (
            top_manufacturer.get("score", 0) >= 0.45
            or top_manufacturer.get("keyword_hits")
        )
    )

    if has_real_negative and (has_rescue_term or has_concept or has_manufacturer_evidence):
        return 25

    return 0


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


def score_source_prior(tender):
    source = (
        tender.get("source_portal")
        or tender.get("source_type")
        or tender.get("organization")
        or ""
    ).lower()

    priority_sources = [
        "iisc",
        "iitm",
        "iit madras",
        "iit_goa",
        "iit palakkad",
        "iit_palakkad",
    ]

    if any(src in source for src in priority_sources):
        return 8

    return 0