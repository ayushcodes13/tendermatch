import pytest

from matching.threshold_evaluation import evaluate_threshold_scenarios
from matching.evaluation import validate_dataset_provenance


def _synthetic(dataset):
    for case in dataset.get("cases", []):
        case.setdefault("provenance", {
            "type": "synthetic", "review_status": "not_human_reviewed",
            "source": "unit-test fixture",
        })
    dataset.setdefault("synthetic_case_count", len(dataset.get("cases", [])))
    dataset.setdefault("human_reviewed_case_count", 0)
    return dataset


class FakeMatcher:
    def __init__(self, candidates):
        self.candidates = candidates

    def match_topk(self, _tender, top_k=5):
        return self.candidates[:top_k]


def test_threshold_evaluation_keeps_unknown_pairs_separate_and_compares_scenarios():
    dataset = {
        "dataset_id": "threshold-fixture",
        "synthetic_case_count": 3,
        "human_reviewed_case_count": 0,
        "cases": [
            {"case_id": "positive", "tender_id": "T1", "manufacturer_id": "m1", "description": "PVD", "label": "relevant"},
            {"case_id": "negative", "tender_id": "T1", "manufacturer_id": "m2", "description": "PVD", "label": "not_relevant"},
            {"case_id": "review", "tender_id": "T1", "manufacturer_id": "m3", "description": "PVD", "label": "potentially_relevant_needs_review"},
        ],
    }
    _synthetic(dataset)
    matcher = FakeMatcher([
        {"manufacturer_id": "m1", "score": 0.8, "product_hits": ["PVD"]},
        {"manufacturer_id": "m2", "score": 0.7, "keyword_hits": ["PVD"]},
        {"manufacturer_id": "m3", "score": 0.65, "concept_hits": ["pvd"]},
        {"manufacturer_id": "unknown", "score": 0.9},
    ])

    def fake_classifier(_tender, *, manufacturer_candidates, thresholds):
        assert manufacturer_candidates == matcher.candidates
        if thresholds["explore"] >= 60:
            return {"decision": "reject_soft", "category": "blocked"}
        return {"decision": "explore", "category": "explore"}

    report = evaluate_threshold_scenarios(
        dataset,
        matcher,
        {"configured": {}, "higher_cutoff": {"explore": 60}},
        classifier=fake_classifier,
    )

    configured = report["scenarios"]["configured"]
    assert configured["labeled_positive_pair_digest_recall"] == 1.0
    assert configured["definitive_labeled_pair_precision"] == 0.5
    assert configured["definitive_labeled_pairs_delivered"] == 2
    assert configured["review_or_insufficient_pairs_delivered"] == 1
    assert configured["unjudged_displayed_candidate_count"] == 1
    assert configured["false_positive_case_ids"] == ["negative"]
    assert configured["missed_relevant_case_ids"] == []

    restrictive = report["scenarios"]["higher_cutoff"]
    assert restrictive["labeled_positive_pair_digest_recall"] == 0.0
    assert restrictive["definitive_labeled_pair_precision"] is None
    assert restrictive["missed_relevant_case_ids"] == ["positive"]
    assert restrictive["unjudged_displayed_candidate_count"] == 0


def test_duplicate_judgments_and_unknown_labels_are_rejected():
    dataset = {"cases": [
        {"case_id": "a", "tender_id": "T1", "manufacturer_id": "m1", "description": "x", "label": "relevant"},
        {"case_id": "b", "tender_id": "T1", "manufacturer_id": "m1", "description": "x", "label": "not_relevant"},
    ]}
    _synthetic(dataset)
    with pytest.raises(ValueError, match="duplicate tender/manufacturer"):
        evaluate_threshold_scenarios(dataset, FakeMatcher([]), {"default": {}})

    dataset["cases"][1]["manufacturer_id"] = "m2"
    dataset["cases"][1]["label"] = "unknown"
    with pytest.raises(ValueError, match="unknown relevance label"):
        evaluate_threshold_scenarios(dataset, FakeMatcher([]), {"default": {}})


def test_dataset_provenance_counts_are_derived_and_must_match_cases():
    dataset = _synthetic({"cases": [{
        "case_id": "a", "tender_id": "T1", "manufacturer_id": "m1", "label": "relevant",
    }]})
    assert validate_dataset_provenance(dataset) == {
        "synthetic_case_count": 1, "human_reviewed_case_count": 0,
    }

    dataset["synthetic_case_count"] = 0
    with pytest.raises(ValueError, match="declares 0 but provenance contains 1"):
        validate_dataset_provenance(dataset)


@pytest.mark.parametrize("provenance", [
    {"type": "synthetic", "review_status": "human_reviewed", "source": "fixture"},
    {"type": "human_reviewed", "review_status": "human_reviewed", "source": "fixture"},
])
def test_dataset_provenance_rejects_unsubstantiated_human_or_synthetic_status(provenance):
    with pytest.raises(ValueError):
        validate_dataset_provenance({
            "synthetic_case_count": 0, "human_reviewed_case_count": 1,
            "cases": [{"provenance": provenance}],
        })


def test_dataset_provenance_accepts_adjudicated_feedback_with_source_evidence():
    dataset = {
        "synthetic_case_count": 0,
        "human_reviewed_case_count": 1,
        "cases": [{"provenance": {
            "type": "human_reviewed_feedback",
            "review_status": "human_adjudicated",
            "source": "reviewed feedback export",
            "adjudicator": "reviewer-1",
            "adjudicated_at": "2026-10-22T09:30:00+05:30",
            "source_url": "https://procurement.example/tender/123",
        }}],
    }
    assert validate_dataset_provenance(dataset) == {
        "synthetic_case_count": 0, "human_reviewed_case_count": 1,
    }
