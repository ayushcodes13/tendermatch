
"""
Decision trace builder.

Standardizes classification output for DB/email/debugging.
"""

from datetime import datetime


PIPELINE_VERSION = "matching_v2_1"


def build_trace(tender, signals, concepts, scoring, decision, manufacturer_candidates=None):
    manufacturer_candidates = manufacturer_candidates or []
    explanation = build_explanation(
        tender=tender,
        signals=signals,
        concepts=concepts,
        scoring=scoring,
        decision=decision,
        manufacturer_candidates=manufacturer_candidates,
    )

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
        "explanation": explanation,
    }


def build_explanation(tender, signals, concepts, scoring, decision, manufacturer_candidates):
    """Build a structured, explicitly uncalibrated account of the decision."""
    manufacturer_evidence = []
    for candidate in manufacturer_candidates[:5]:
        manufacturer_evidence.append({
            "manufacturer_id": candidate.get("manufacturer_id"),
            "manufacturer_name": candidate.get("manufacturer_name"),
            "rank": candidate.get("rank"),
            "semantic_similarity": {
                "value": candidate.get("base_semantic_score"),
                "meaning": "embedding similarity signal; not a probability",
            },
            "combined_heuristic_rank_score": {
                "value": candidate.get("score"),
                "meaning": "semantic and profile evidence score after penalties; not a probability",
            },
            "product_family_agreement": {
                "product_hits": candidate.get("product_hits", []) or [],
                "category_hits": candidate.get("category_hits", []) or [],
                "alias_hits": candidate.get("alias_hits", []) or [],
            },
            "manufacturer_keyword_evidence": candidate.get("keyword_hits", []) or [],
            "manufacturer_concept_evidence": candidate.get("concept_hits", []) or [],
            "service_evidence": candidate.get("service_hits", []) or [],
            "negative_evidence": candidate.get("negative_hits", []) or [],
            "reason_codes": candidate.get("reason_codes", []) or [],
            "manufacturer_source_links": candidate.get("manufacturer_source_links", []) or [],
        })

    concepts_found = concepts.get("matched_concepts", []) or []
    source_links_recorded = any(item["manufacturer_source_links"] for item in manufacturer_evidence)
    return {
        "decision": decision["decision"],
        "reason_codes": decision.get("reason_codes", []),
        "overall_score": {
            "value": scoring.get("score"),
            "scale": "heuristic points on a 0-100 scale",
            "calibrated_probability": False,
        },
        "technical_concept_evidence": concepts_found,
        "manufacturer_evidence": manufacturer_evidence,
        "negative_evidence": {
            "hard_junk_clusters": signals.get("hard_junk_clusters", []) or [],
            "soft_risk_terms": signals.get("soft_risk_terms", []) or [],
            "contextual_negative_hits": signals.get("contextual_negative_hits", []) or [],
            "domain_review_hits": signals.get("domain_review_hits", []) or [],
        },
        "source_quality": {
            "assessment": "not_assessed",
            "tender_source_url_recorded": bool(tender.get("source_url")),
            "manufacturer_profile_source_links_recorded": source_links_recorded,
        },
        "unverified_requirements": [
            "Manufacturer eligibility and required certifications are not verified.",
            "Mandatory technical specifications are not validated against source-backed product documentation.",
            "Product availability and delivery capability are not established.",
        ],
    }
