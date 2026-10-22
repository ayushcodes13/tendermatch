import hashlib
import json
from pathlib import Path

import pytest

from matching.evaluation import evaluate_rankings, hash_ranking_profile_inputs


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


def test_ranking_profile_fingerprint_ignores_provenance_but_tracks_match_inputs():
    profile = {
        "active": True,
        "id": "maker",
        "name": "Maker Inc.",
        "embedding_text": "sintering systems",
        "keywords": ["SPS"],
        "products": ["SPS system"],
        "product_categories": ["sintering"],
        "aliases": ["Maker"],
        "concepts": ["spark_plasma_sintering"],
        "service_keywords": ["maintenance"],
        "negative_keywords": ["medical pump"],
        "source_links": ["https://example.test/old"],
        "profile_version": "1.0",
    }

    initial = hash_ranking_profile_inputs([profile])
    metadata_only = {**profile, "source_links": ["https://example.test/new"], "profile_version": "1.1"}
    changed_ranking_input = {**metadata_only, "products": ["different product"]}

    assert hash_ranking_profile_inputs([metadata_only]) == initial
    assert hash_ranking_profile_inputs([changed_ranking_input]) != initial


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


def test_synthetic_baseline_preserves_run_catalog_hash_and_tracks_ranking_inputs():
    report = json.loads(
        (ROOT / "data/evaluation/baseline_synthetic_nippon_fertilizer_context_2026-10-22.json")
        .read_text(encoding="utf-8")
    )
    dataset = json.loads(
        (ROOT / "data/evaluation/golden_tender_cases.json").read_text(encoding="utf-8")
    )
    dataset_bytes = json.dumps(
        dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    current_profiles = json.loads(
        (ROOT / "data/manufacturers.json").read_text(encoding="utf-8")
    )
    current_profiles_sha256 = hashlib.sha256(
        (ROOT / "data/manufacturers.json").read_bytes()
    ).hexdigest()
    original_run_profiles_sha256 = "72aa40cc0f28f25afaac1d0a6e525f5548ec342933117dabbc4d6bc27c55c374"
    assert report["input_sha256"]["manufacturer_profiles"] == original_run_profiles_sha256
    assert report["profile_metadata_refresh"]["run_manufacturer_profiles_sha256"] == (
        original_run_profiles_sha256
    )
    assert report["profile_metadata_refresh"]["current_manufacturer_profiles_sha256"] == (
        current_profiles_sha256
    )
    assert report["input_sha256"]["ranking_profile_inputs"] != hash_ranking_profile_inputs(
        current_profiles
    )
    assert report["profile_metadata_refresh"]["current_ranking_profile_inputs_sha256"] == (
        hash_ranking_profile_inputs(current_profiles)
    )
    assert report["profile_metadata_refresh"]["rankings_reused"] is False
    assert report["profile_metadata_refresh"]["rankings_current_for_profile_inputs"] is False
    assert report["profile_metadata_refresh"]["run_generated_at_utc"] == report[
        "generated_at_utc"
    ]
    assert "historical" in report["profile_metadata_refresh"]["reason"]
    assert "sentence-transformers" in report["profile_metadata_refresh"]["reason"]
    assert any(
        "Agnitron" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "GeniCore" in update and "Pulse Plasma Compaction" in update and "direct provenance" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "GeniCore" in update and "Diamond Enhanced Cemented Carbide" in update
        and "direct provenance" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Agnitron" in update and "GOX300" in update and "Custom Systems" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "AdNaNoTek" in update and "RIE" in update and "direct provenance" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "AdNaNoTek" in update and "transfer-arm" in update and "direct provenance" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "P.G. Instruments" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Korvus Technology" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "legacy MOCVD refurbishment" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "RA-7000A" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "RA-7000F" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "MA-3 Solo" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "MA-3000" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "PE-1000" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "WA-5A" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "WA-5F" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "EMP-3" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "EMP-Gold+" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "SGM-9" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Nippon Instruments" in update and "AM-6F" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "P.G. Instruments" in update and "unsupported gas chromatography" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert any(
        "Spinflex" in update and "spinAMP" in update and "ESR/EPR-only" in update
        for update in report["profile_metadata_refresh"]["metadata_updates"]
    )
    assert report["input_sha256"]["dataset"] == hashlib.sha256(dataset_bytes).hexdigest()
    assert report["candidate_recall_on_labeled_positives"] == 1.0
    assert report["human_reviewed_case_count"] == 0
    assert report["rankings"]["SYN-FERTILIZER-MERCURY-017"][0]["manufacturer_id"] == "nippon_instruments"
    commodity_ranking = report["rankings"]["SYN-FERTILIZER-COMMODITY-018"]
    nippon_commodity = next(
        item for item in commodity_ranking if item["manufacturer_id"] == "nippon_instruments"
    )
    assert nippon_commodity["rank"] > 1
    assert nippon_commodity["contextual_negative_hits"][0]["rule_id"] == (
        "FERTILIZER_COMMODITY_WITHOUT_MERCURY_INSTRUMENT"
    )
    assert "syn-fertilizer-commodity-018" in report["false_positive_case_ids"]


def test_current_on_nano_profile_evaluation_snapshot_matches_rank_inputs():
    report = json.loads(
        (ROOT / "data/evaluation/baseline_synthetic_on_nano_glass_panel_scope_2026-10-22.json")
        .read_text(encoding="utf-8")
    )
    before = json.loads(
        (ROOT / "data/evaluation/baseline_synthetic_on_nano_glass_panel_scope_before_2026-10-22.json")
        .read_text(encoding="utf-8")
    )
    dataset = json.loads(
        (ROOT / "data/evaluation/golden_tender_cases.json").read_text(encoding="utf-8")
    )
    profiles_path = ROOT / "data/manufacturers.json"
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    dataset_bytes = json.dumps(
        dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    assert report["input_sha256"]["dataset"] == hashlib.sha256(dataset_bytes).hexdigest()
    assert report["input_sha256"]["manufacturer_profiles"] == hashlib.sha256(
        profiles_path.read_bytes()
    ).hexdigest()
    assert report["input_sha256"]["ranking_profile_inputs"] == hash_ranking_profile_inputs(
        profiles
    )
    assert report["dataset_case_count"] == 18
    assert report["synthetic_case_count"] == 18
    assert report["human_reviewed_case_count"] == 0
    assert report["candidate_recall_on_labeled_positives"] == 1.0
    assert report["labeled_candidate_precision"] == 8 / 11
    assert report["rankings"]["SYN-VACUUM-CLEANER-010"][4]["manufacturer_id"] == "sald"
    assert before["input_sha256"]["dataset"] == report["input_sha256"]["dataset"]
    assert before["input_sha256"]["evaluation_and_matching_code"] == (
        report["input_sha256"]["evaluation_and_matching_code"]
    )
    assert before["model_revision"] == report["model_revision"]
    assert before["candidate_recall_on_labeled_positives"] == (
        report["candidate_recall_on_labeled_positives"]
    )
    assert before["labeled_candidate_precision"] == report["labeled_candidate_precision"]
    changed_tenders = {
        tender_id
        for tender_id in before["rankings"]
        if [item["manufacturer_id"] for item in before["rankings"][tender_id]]
        != [item["manufacturer_id"] for item in report["rankings"][tender_id]]
    }
    assert changed_tenders == {"SYN-VACUUM-CLEANER-010"}
    assert before["rankings"]["SYN-VACUUM-CLEANER-010"][4]["manufacturer_id"] == "on_nano"
