"""Contextual compatibility signals for ranking manufacturer candidates.

These signals add a soft ranking penalty. They never remove a candidate from
the high-recall pool, and explicit product evidence can override a contextual
negative when a tender discusses both the application and its products.
"""

import re


_FERTILIZER_COMMODITY_TERMS = (
    "bulk urea",
    "bulk phosphate",
    "bulk fertilizer",
    "fertilizer commodities",
    "agricultural distribution",
    "farm supply",
)

_MERCURY_INSTRUMENT_TERMS = (
    "mercury analyzer",
    "mercury monitor",
    "mercury measurement",
    "analyzer for mercury",
    "monitor for mercury",
)


def detect_candidate_contextual_negatives(text, manufacturer):
    """Return scoped negative signals where the tender context conflicts.

    NIC's fertilizer-sector page supports mercury analyzers for fertilizer
    production. A fertilizer commodity purchase is outside that product scope
    when it does not request mercury measurement equipment. Keep the candidate
    visible, but lower it in ranking.
    """
    if manufacturer.get("id") != "nippon_instruments":
        return []

    normalized = normalize_text(text)
    if not any(term in normalized for term in ("fertilizer", "urea", "phosphate")):
        return []

    commodity_hits = [term for term in _FERTILIZER_COMMODITY_TERMS if term in normalized]
    if not commodity_hits:
        return []

    instrument_hits = [
        term for term in _MERCURY_INSTRUMENT_TERMS
        if _has_unnegated_phrase(normalized, term)
    ]
    if instrument_hits:
        return []

    return [{
        "rule_id": "FERTILIZER_COMMODITY_WITHOUT_MERCURY_INSTRUMENT",
        "commodity_hits": commodity_hits,
    }]


def _has_unnegated_phrase(text, phrase):
    for match in re.finditer(re.escape(phrase), text):
        prefix = text[max(0, match.start() - 70):match.start()]
        if not re.search(
            r"\b(?:no|not|without|does not|doesn't|is not|isn't|not requested|not required|not needed)"
            r"(?:\W+\w+){0,5}\W*$",
            prefix,
        ):
            return True
    return False


def normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()
