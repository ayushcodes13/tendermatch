import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "evaluation" / "golden_tender_cases.json"
VALID_LABELS = {
    "relevant",
    "potentially_relevant_needs_review",
    "not_relevant",
    "insufficient_information",
}


def test_golden_dataset_cases_are_complete_and_provenance_labeled():
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    manufacturers = json.loads((ROOT / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    manufacturer_ids = {manufacturer["id"] for manufacturer in manufacturers}
    cases = dataset["cases"]

    assert dataset["human_reviewed_case_count"] == 0
    assert dataset["synthetic_case_count"] == len(cases) == 18
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {
        "syn-pump-002", "syn-pump-003", "syn-lab-generic-004", "syn-amc-005",
        "syn-acronym-006", "syn-alias-007", "syn-conflict-008",
        "syn-negative-009", "syn-overlap-korvus-011", "syn-overlap-staton-012",
        "syn-corrigendum-013", "syn-updated-014", "syn-vacuum-cleaner-010",
        "syn-missing-capability-016",
        "syn-fertilizer-mercury-017", "syn-fertilizer-commodity-018",
    } <= {case["case_id"] for case in cases}
    assert len({(case["tender_id"], case["manufacturer_id"]) for case in cases}) == len(cases)
    overlap_cases = [case for case in cases if case["tender_id"] == "SYN-OVERLAP-011"]
    assert {case["manufacturer_id"] for case in overlap_cases} == {"korvus_technology", "staton"}

    for case in cases:
        assert case["manufacturer_id"] in manufacturer_ids
        assert case["label"] in VALID_LABELS
        assert case["description"].strip()
        assert case["reason"].strip()
        assert isinstance(case["technical_evidence"], list)
        assert isinstance(case["known_exclusions"], list)
        assert case["provenance"]["type"] == "synthetic"
        assert case["provenance"]["review_status"] == "not_human_reviewed"
        assert case["provenance"]["source"]
