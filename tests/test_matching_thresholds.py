import json
from pathlib import Path

import pytest

from matching.decision import decide_tender
from matching.filter import classify_tender
from matching.decision import has_strong_manufacturer_evidence as decision_has_mfr_evidence
from matching.scoring import has_strong_manufacturer_evidence as scoring_has_mfr_evidence
from matching.thresholds import load_thresholds, resolve_thresholds


ROOT = Path(__file__).resolve().parents[1]


def test_threshold_file_is_loaded_and_matches_expected_contract():
    expected = json.loads((ROOT / "data" / "matching_thresholds.json").read_text())

    assert load_thresholds() == expected
    assert resolve_thresholds() == expected


def test_threshold_override_changes_bucket_at_boundary():
    signals = {}
    concepts = {}
    scoring = {"score": 56}

    default = decide_tender(signals, concepts, scoring)
    raised_explore = decide_tender(signals, concepts, scoring, thresholds={"explore": 60})

    assert default["decision"] == "explore"
    assert raised_explore["decision"] == "agent_review"


def test_manufacturer_evidence_threshold_is_configurable_in_decision_and_scoring():
    candidate = {"score": 0.58, "product_hits": ["PVD system"]}
    stricter = {"manufacturer_semantic_with_evidence_min_percent": 60}

    assert decision_has_mfr_evidence([candidate]) is True
    assert scoring_has_mfr_evidence([candidate]) is True
    assert decision_has_mfr_evidence([candidate], stricter) is False
    assert scoring_has_mfr_evidence([candidate], stricter) is False


def test_custom_thresholds_are_recorded_in_explanation_and_trace():
    result = classify_tender({"title": "Unspecified procurement"}, thresholds={"explore": 60})

    assert result["trace"]["pipeline_version"] == "matching_v2_2"
    assert result["trace"]["decision_thresholds"]["explore"] == 60
    assert result["explanation"]["decision_thresholds"]["explore"] == 60


@pytest.mark.parametrize(
    "overrides",
    [
        {"unknown_threshold": 50},
        {"explore": 101},
        {"explore": True},
        {"soft_risk_high_signal": 20},
        {"rescue_concept_review_min": 80},
        {"manufacturer_semantic_only_min_percent": 50},
    ],
)
def test_invalid_threshold_overrides_are_rejected(overrides):
    with pytest.raises(ValueError):
        resolve_thresholds(overrides)


def test_malformed_threshold_file_fails_with_actionable_error(tmp_path):
    path = tmp_path / "thresholds.json"
    path.write_text("{bad", encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot load matching thresholds: JSONDecodeError"):
        load_thresholds(path)
