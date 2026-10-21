"""Load and validate transparent tender-decision score thresholds."""

import json
from pathlib import Path


DEFAULT_THRESHOLDS_PATH = Path(__file__).resolve().parents[1] / "data" / "matching_thresholds.json"
REQUIRED_THRESHOLD_KEYS = {
    "soft_risk_high_signal",
    "soft_risk_rescued",
    "soft_risk_review_below",
    "high_signal",
    "manufacturer_explore",
    "manufacturer_semantic_with_evidence_min_percent",
    "manufacturer_semantic_only_min_percent",
    "rescue_concept_review_min",
    "rescue_concept_review_max_exclusive",
    "support_review",
    "explore",
    "review",
}


def load_thresholds(path=DEFAULT_THRESHOLDS_PATH):
    try:
        thresholds = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load matching thresholds: {type(exc).__name__}: {exc}") from exc
    return _validate_thresholds(thresholds)


def resolve_thresholds(overrides=None):
    """Return defaults merged with validated per-call overrides."""
    thresholds = load_thresholds()
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise ValueError("Threshold overrides must be a dictionary")
        unknown = set(overrides) - REQUIRED_THRESHOLD_KEYS
        if unknown:
            raise ValueError(f"Unknown matching threshold keys: {', '.join(sorted(unknown))}")
        thresholds.update(overrides)
    return _validate_thresholds(thresholds)


def _validate_thresholds(thresholds):
    if not isinstance(thresholds, dict):
        raise ValueError("Matching thresholds must be a JSON object")
    missing = REQUIRED_THRESHOLD_KEYS - set(thresholds)
    unknown = set(thresholds) - REQUIRED_THRESHOLD_KEYS
    if missing:
        raise ValueError(f"Missing matching threshold keys: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"Unknown matching threshold keys: {', '.join(sorted(unknown))}")
    for key, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(f"Threshold {key} must be an integer between 0 and 100")

    if thresholds["soft_risk_high_signal"] < thresholds["soft_risk_rescued"]:
        raise ValueError("soft_risk_high_signal must be at least soft_risk_rescued")
    if thresholds["soft_risk_review_below"] < thresholds["soft_risk_rescued"]:
        raise ValueError("soft_risk_review_below must be at least soft_risk_rescued")
    if thresholds["high_signal"] < thresholds["manufacturer_explore"]:
        raise ValueError("high_signal must be at least manufacturer_explore")
    if thresholds["manufacturer_semantic_only_min_percent"] < thresholds["manufacturer_semantic_with_evidence_min_percent"]:
        raise ValueError("manufacturer_semantic_only_min_percent must be at least the with-evidence minimum")
    if thresholds["rescue_concept_review_min"] > thresholds["rescue_concept_review_max_exclusive"]:
        raise ValueError("rescue concept review minimum must not exceed its exclusive maximum")
    if thresholds["explore"] < thresholds["review"]:
        raise ValueError("explore must be at least review")
    if thresholds["support_review"] < thresholds["review"]:
        raise ValueError("support_review must be at least review")
    return dict(thresholds)
