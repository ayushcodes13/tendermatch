from pathlib import Path

import pytest

from matching.evaluation import evaluate_rankings


ROOT = Path(__file__).resolve().parents[1]


def test_metrics_ignore_unjudged_candidates_and_exclude_incomplete_rankings():
    dataset = {
        "dataset_id": "metric-fixture",
        "human_reviewed_case_count": 0,
        "synthetic_case_count": 4,
        "ranking_complete_tender_ids": ["T-1"],
        "cases": [
            {"case_id": "a", "tender_id": "T-1", "manufacturer_id": "m1", "label": "relevant"},
            {"case_id": "b", "tender_id": "T-1", "manufacturer_id": "m2", "label": "not_relevant"},
            {"case_id": "c", "tender_id": "T-1", "manufacturer_id": "m3", "label": "potentially_relevant_needs_review"},
            {"case_id": "d", "tender_id": "T-2", "manufacturer_id": "m1", "label": "relevant"},
        ],
    }
    ranked = {
        "T-1": [
            {"manufacturer_id": "m1", "rank": 1},
            {"manufacturer_id": "m2", "rank": 2},
            {"manufacturer_id": "m3", "rank": 3},
            {"manufacturer_id": "unjudged", "rank": 4},
        ],
        "T-2": [{"manufacturer_id": "m1", "rank": 1}],
    }

    report = evaluate_rankings(
        dataset,
        ranked,
        latencies_ms={"T-1": 10.0, "T-2": 30.0},
        active_manufacturer_ids={"m1", "m2", "m3"},
    )

    assert report["candidate_recall_on_labeled_positives"] == 1.0
    assert report["labeled_candidate_precision"] == pytest.approx(2 / 3)
    assert report["labeled_candidate_precision_denominator"] == 3
    assert report["review_or_insufficient_rate_among_labeled_candidates"] == 0.25
    assert report["unjudged_candidate_count"] == 1
    assert report["false_positive_case_ids"] == ["b"]
    assert report["per_manufacturer"]["m1"]["labeled_positive_recall"] == 1.0
    assert report["per_manufacturer"]["m2"]["labeled_positive_recall"] is None
    assert report["ranking_metrics"]["1"]["eligible_tender_count"] == 0
    assert report["ranking_metrics"]["1"]["excluded_incomplete_tender_count"] == 2
    assert report["ranking_metrics"]["1"]["precision_at_k"] is None
    assert report["latency_ms_per_tender"] == {"count": 2, "mean": 20.0, "median": 20.0}
    assert report["cost_usd_per_tender"] is None
    assert report["cost_measurement_status"] == "unavailable"


def test_ranked_metrics_require_exhaustive_definitive_judgments():
    dataset = {
        "ranking_complete_tender_ids": ["T-1"],
        "cases": [
            {"case_id": "a", "tender_id": "T-1", "manufacturer_id": "m1", "label": "relevant"},
            {"case_id": "b", "tender_id": "T-1", "manufacturer_id": "m2", "label": "not_relevant"},
        ],
    }
    report = evaluate_rankings(
        dataset,
        {"T-1": [{"manufacturer_id": "m1"}, {"manufacturer_id": "m2"}]},
        active_manufacturer_ids={"m1", "m2"},
        top_ks=(1, 2),
    )

    assert report["ranking_metrics"]["1"] == {
        "precision_at_k": 1.0,
        "recall_at_k": 1.0,
        "eligible_tender_count": 1,
        "recall_eligible_tender_count": 1,
        "no_positive_tender_count": 0,
        "excluded_incomplete_tender_count": 0,
    }
    assert report["ranking_metrics"]["2"]["precision_at_k"] == 0.5
    assert report["ranking_metrics"]["2"]["recall_at_k"] == 1.0


def test_unranked_candidates_preserve_input_order_and_no_positive_recall_is_undefined():
    dataset = {
        "ranking_complete_tender_ids": ["T-POSITIVE", "T-NEGATIVE"],
        "cases": [
            {"case_id": "a", "tender_id": "T-POSITIVE", "manufacturer_id": "m-z", "label": "relevant"},
            {"case_id": "b", "tender_id": "T-POSITIVE", "manufacturer_id": "m-a", "label": "not_relevant"},
            {"case_id": "c", "tender_id": "T-NEGATIVE", "manufacturer_id": "m-z", "label": "not_relevant"},
            {"case_id": "d", "tender_id": "T-NEGATIVE", "manufacturer_id": "m-a", "label": "not_relevant"},
        ],
    }
    report = evaluate_rankings(
        dataset,
        {
            "T-POSITIVE": [{"manufacturer_id": "m-z"}, {"manufacturer_id": "m-a"}],
            "T-NEGATIVE": [{"manufacturer_id": "m-a"}, {"manufacturer_id": "m-z"}],
        },
        active_manufacturer_ids={"m-z", "m-a"},
        top_ks=(1,),
    )

    assert report["ranking_metrics"]["1"]["precision_at_k"] == 0.5
    assert report["ranking_metrics"]["1"]["recall_at_k"] == 1.0
    assert report["ranking_metrics"]["1"]["recall_eligible_tender_count"] == 1
    assert report["ranking_metrics"]["1"]["no_positive_tender_count"] == 1


def test_duplicate_tender_manufacturer_judgments_are_rejected():
    dataset = {
        "cases": [
            {"tender_id": "T-1", "manufacturer_id": "m1", "label": "relevant"},
            {"tender_id": "T-1", "manufacturer_id": "m1", "label": "not_relevant"},
        ]
    }
    with pytest.raises(ValueError, match="duplicate tender/manufacturer"):
        evaluate_rankings(dataset, {})


def test_duplicate_candidates_and_nonpositive_k_are_rejected():
    dataset = {
        "cases": [{"tender_id": "T-1", "manufacturer_id": "m1", "label": "relevant"}]
    }
    with pytest.raises(ValueError, match="duplicate manufacturers"):
        evaluate_rankings(
            dataset,
            {"T-1": [{"manufacturer_id": "m1"}, {"manufacturer_id": "m1"}]},
        )
    with pytest.raises(ValueError, match="top_ks values must be positive"):
        evaluate_rankings(dataset, {}, top_ks=(0,))

    with pytest.raises(ValueError, match="incomplete rank values"):
        evaluate_rankings(
            dataset,
            {"T-1": [{"manufacturer_id": "m1", "rank": 1}, {"manufacturer_id": "m2"}]},
        )
    with pytest.raises(ValueError, match="duplicate or nonpositive ranks"):
        evaluate_rankings(
            dataset,
            {"T-1": [{"manufacturer_id": "m1", "rank": 1}, {"manufacturer_id": "m2", "rank": 1}]},
        )
    with pytest.raises(ValueError, match="duplicate or nonpositive ranks"):
        evaluate_rankings(dataset, {"T-1": [{"manufacturer_id": "m1", "rank": 0}]})


def test_current_algorithm_report_is_explicitly_unavailable_without_dependency(capsys):
    from matching.evaluation import main

    result = main(["--dataset", str(ROOT / "data/evaluation/golden_tender_cases.json")])
    captured = capsys.readouterr()

    assert result == 2
    assert "Cannot run current matcher baseline" in captured.err


def test_missing_and_invalid_datasets_return_concise_cli_errors(tmp_path, capsys):
    from matching.evaluation import main

    assert main(["--dataset", str(tmp_path / "missing.json")]) == 2
    missing_error = capsys.readouterr()
    assert "Cannot load evaluation dataset: FileNotFoundError" in missing_error.err
    assert "Traceback" not in missing_error.err

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid", encoding="utf-8")
    assert main(["--dataset", str(invalid)]) == 2
    invalid_error = capsys.readouterr()
    assert "Cannot load evaluation dataset: JSONDecodeError" in invalid_error.err
    assert "Traceback" not in invalid_error.err
