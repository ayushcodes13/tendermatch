"""
Tender scoring.

Converts extracted evidence into a transparent score.

Important:
- This module does NOT assign the final decision.
- It only creates a transparent numeric score and score breakdown.
- Final bucketing belongs only in matching.decision.
"""

def score_tender(tender, signals, concepts, manufacturer_candidates=None):
    manufacturer_candidates = manufacturer_candidates or []

    score = 0
    breakdown = {}

    # --------------------------------------------------
    # 1. Technical concept score
    # --------------------------------------------------
    rescue_concept_score = min(concepts.get("rescue_concept_score", 0), 75)
    support_only_concept_score = min(concepts.get("support_only_concept_score", 0), 25)

    breakdown["rescue_concept_score"] = rescue_concept_score
    breakdown["support_only_concept_score"] = support_only_concept_score

    score += rescue_concept_score
    score += support_only_concept_score

    # --------------------------------------------------
    # 2. Manufacturer evidence score
    # --------------------------------------------------
    manufacturer_score = score_manufacturer_candidates(manufacturer_candidates)
    breakdown["manufacturer_score"] = manufacturer_score
    score += manufacturer_score

    # --------------------------------------------------
    # 3. Soft risk penalty
    # --------------------------------------------------
    soft_risk_penalty = score_soft_risks(signals)
    breakdown["soft_risk_penalty"] = soft_risk_penalty
    score += soft_risk_penalty

    # --------------------------------------------------
    # 4. Contextual negative penalty
    # --------------------------------------------------
    contextual_penalty = score_contextual_negatives(signals)
    breakdown["contextual_negative_penalty"] = contextual_penalty
    score += contextual_penalty

    # --------------------------------------------------
    # 5. Buyer prior score
    # --------------------------------------------------
    buyer_prior_score = score_buyer_prior(tender, signals)
    breakdown["buyer_prior_score"] = buyer_prior_score
    score += buyer_prior_score

    # --------------------------------------------------
    # 6. Hard junk penalty
    # --------------------------------------------------
    hard_junk_penalty = score_hard_junk(signals)
    breakdown["hard_junk_penalty"] = hard_junk_penalty
    score += hard_junk_penalty

    # --------------------------------------------------
    # 7. Rescue bonus
    # --------------------------------------------------
    rescue_bonus = score_rescue(signals, concepts, manufacturer_candidates)
    breakdown["rescue_bonus"] = rescue_bonus
    score += rescue_bonus

    # --------------------------------------------------
    # 8. Source / organization prior
    # --------------------------------------------------
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
    """
    Manufacturer score should not blindly trust embeddings.

    Strong manufacturer evidence:
    - high semantic score
    - OR keyword/product/category/concept evidence
    - OR multiple evidence channels together

    This prevents random semantic neighbors from boosting bad tenders.
    """
    if not candidates:
        return 0

    top = candidates[0]
    top_score = top.get("score", 0) or 0

    keyword_hits = top.get("keyword_hits", []) or []
    product_hits = top.get("product_hits", []) or []
    category_hits = top.get("category_hits", []) or []
    concept_hits = top.get("concept_hits", []) or []
    alias_hits = top.get("alias_hits", []) or []

    evidence_hit_count = (
        len(keyword_hits)
        + len(product_hits)
        + len(category_hits)
        + len(concept_hits)
        + len(alias_hits)
    )

    points = 0

    # Semantic score bands.
    # Keep this conservative. Embeddings are not calibrated.
    if top_score >= 0.82:
        points += 28
    elif top_score >= 0.75:
        points += 22
    elif top_score >= 0.65:
        points += 14
    elif top_score >= 0.55:
        points += 8

    # Rank bonus.
    if top.get("rank") == 1:
        points += 4

    # Evidence boosts.
    if keyword_hits:
        points += min(14, 4 * len(keyword_hits))

    if product_hits:
        points += min(16, 5 * len(product_hits))

    if category_hits:
        points += min(10, 3 * len(category_hits))

    if concept_hits:
        points += min(12, 4 * len(concept_hits))

    if alias_hits:
        points += min(8, 3 * len(alias_hits))

    # If there is only semantic similarity and no concrete evidence,
    # cap the score hard.
    if evidence_hit_count == 0:
        points = min(points, 14)

    return min(points, 45)


def score_soft_risks(signals):
    soft_terms = {
        str(term).lower()
        for term in signals.get("soft_risk_terms", [])
    }

    if not soft_terms:
        return 0

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

    strong_hits = soft_terms.intersection(strong_soft_terms)
    weak_hits = soft_terms - strong_hits

    penalty = -(8 * len(strong_hits) + 4 * len(weak_hits))

    return max(penalty, -24)


def score_contextual_negatives(signals):
    hits = signals.get("contextual_negative_hits", [])

    if not hits:
        return 0

    penalty = -22 * len(hits)

    return max(penalty, -45)


def score_buyer_prior(tender, signals):
    """
    Buyer priors should be split into positive and negative.

    IIT/IISc/nanofab/research institutes help.
    Municipal/CPWD/public works hurt.
    """
    text = " ".join(
        str(x or "")
        for x in [
            tender.get("organization"),
            tender.get("department"),
            tender.get("source_portal"),
            tender.get("source_type"),
        ]
    ).lower()

    buyer_priors = {
        str(x).lower()
        for x in signals.get("buyer_priors", [])
    }

    positive_buyers = [
        "iisc",
        "iit",
        "iit madras",
        "iit goa",
        "iit palakkad",
        "nanofabrication",
        "materials research",
        "research institute",
        "central university",
        "institute of technology",
    ]

    negative_buyers = [
        "municipal",
        "cpwd",
        "public works",
        "pwd",
        "gram panchayat",
        "panchayat",
        "railway",
        "metro",
        "road",
        "highway",
        "port trust",
    ]

    positive = any(x in text for x in positive_buyers)
    negative = any(x in text for x in negative_buyers) or bool(
        buyer_priors.intersection(set(negative_buyers))
    )

    if positive and not negative:
        return 8

    if negative and not positive:
        return -12

    if positive and negative:
        return -4

    return 0


def score_hard_junk(signals):
    clusters = signals.get("hard_junk_clusters", [])

    if not clusters:
        return 0

    strong_count = sum(1 for c in clusters if c.get("strength") == "strong")
    medium_count = sum(1 for c in clusters if c.get("strength") == "medium")

    penalty = -(40 * strong_count + 22 * medium_count)

    return max(penalty, -75)


def score_rescue(signals, concepts, manufacturer_candidates):
    """
    Rescue bonus is only for cases where negative evidence exists
    and real positive evidence also exists.

    Do not rescue using support-only concepts.
    """
    has_real_negative = bool(
        signals.get("hard_junk_clusters")
        or signals.get("contextual_negative_hits")
        or has_strong_soft_risk(signals)
    )

    if not has_real_negative:
        return 0

    has_rescue_term = signals.get("has_rescue", False)
    has_rescue_concept = concepts.get("has_rescue_concept", False)
    has_mfr_evidence = has_strong_manufacturer_evidence(manufacturer_candidates)

    if has_rescue_term or has_rescue_concept or has_mfr_evidence:
        return 22

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


def has_strong_manufacturer_evidence(candidates):
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

    if evidence_count >= 1 and top_score >= 0.55:
        return True

    if top_score >= 0.78:
        return True

    return False


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
        "iit goa",
        "iit palakkad",
        "iit_palakkad",
    ]

    if any(src in source for src in priority_sources):
        return 8

    return 0