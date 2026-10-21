import json
import sys
from types import SimpleNamespace

import pytest

from data.feedback_adjudication import (
    build_adjudicated_dataset,
    main,
    write_adjudicated_dataset,
)


ADJUDICATOR = "qa@example.com"
TRUSTED = {ADJUDICATOR}


def reviewed_item(**overrides):
    item = {
        "feedback_record_id": 17,
        "tender_identity_key": "tender:42",
        "tender_version": "sha256:version-1",
        "tender_reference": "REF-42",
        "title": "Laboratory mass spectrometer",
        "description": "Supply of a laboratory mass spectrometer with specified resolution.",
        "closing_date": "2026-11-30",
        "source_url": "https://procurement.example.gov/tender/REF-42",
        "source_portal": "official-portal",
        "tender_context_status": "feedback_version_snapshot",
        "manufacturer_id": "maker-1",
        "feedback_label": "worth_pursuing",
        "suggested_evaluation_label": None,
        "reason": "Salesperson's original note",
        "reviewer": "sales@example.com",
        "reviewed_at": "2026-10-22T10:00:00+00:00",
        "review_status": "human_adjudicated",
        "adjudicated_label": "not_relevant",
        "adjudication_reason": "The required mass range is outside the product profile.",
        "adjudicator": ADJUDICATOR,
        "adjudicated_at": "2026-10-22T12:30:00+00:00",
        "technical_evidence": ["specified mass range"],
        "known_exclusions": ["required range unsupported"],
    }
    item.update(overrides)
    return item


def queue(*items, **overrides):
    value = {
        "schema_version": 1,
        "export_kind": "salesperson_feedback_review_queue",
        "eligible_for_metrics": False,
        "items": list(items),
    }
    value.update(overrides)
    return value


def test_only_human_adjudicated_items_enter_a_separate_dataset():
    pending = reviewed_item(feedback_record_id=18, review_status="pending_adjudication")
    dataset = build_adjudicated_dataset(queue(pending, reviewed_item()), trusted_adjudicators=TRUSTED)

    assert dataset["human_reviewed_case_count"] == 1
    assert dataset["synthetic_case_count"] == 0
    assert dataset["ranking_complete_tender_ids"] == []
    case = dataset["cases"][0]
    assert case["case_id"] == "feedback-17"
    assert case["tender_id"] == "tender:42@sha256:version-1"
    assert case["label"] == "not_relevant"
    assert case["label"] != "worth_pursuing"
    assert case["reason"] == "The required mass range is outside the product profile."
    assert case["technical_evidence"] == ["specified mass range"]
    assert case["known_exclusions"] == ["required range unsupported"]
    assert case["provenance"] == {
        "type": "human_reviewed_feedback",
        "source": "salesperson feedback record 17",
        "review_status": "human_adjudicated",
        "feedback_label": "worth_pursuing",
        "feedback_reviewer": "sales@example.com",
        "feedback_reviewed_at": "2026-10-22T10:00:00+00:00",
        "adjudicator": ADJUDICATOR,
        "adjudicated_at": "2026-10-22T12:30:00+00:00",
        "tender_identity_key": "tender:42",
        "tender_reference": "REF-42",
        "tender_version": "sha256:version-1",
        "source_url": "https://procurement.example.gov/tender/REF-42",
        "source_portal": "official-portal",
        "tender_context_status": "feedback_version_snapshot",
    }


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"adjudicator": "untrusted@example.com"}, "not allowlisted"),
        ({"adjudicated_label": "unsupported"}, "unsupported adjudicated evaluation label"),
        ({"source_url": "javascript:alert(1)"}, r"valid HTTP\(S\) source URL"),
        ({"adjudicated_at": "yesterday"}, "timezone-aware timestamp"),
        ({"description": ""}, "missing required context"),
    ],
)
def test_rejects_untrusted_or_incomplete_adjudication(changes, message):
    with pytest.raises(ValueError, match=message):
        build_adjudicated_dataset(queue(reviewed_item(**changes)), trusted_adjudicators=TRUSTED)


def test_rejects_metric_eligible_input_duplicate_pairs_and_no_approved_cases():
    with pytest.raises(ValueError, match="ineligible for metrics"):
        build_adjudicated_dataset(queue(reviewed_item(), eligible_for_metrics=True), trusted_adjudicators=TRUSTED)
    duplicate = reviewed_item(feedback_record_id=18)
    with pytest.raises(ValueError, match="multiple adjudicated feedback records"):
        build_adjudicated_dataset(queue(reviewed_item(), duplicate), trusted_adjudicators=TRUSTED)
    separate_version = reviewed_item(feedback_record_id=19, tender_version="sha256:version-2")
    versioned = build_adjudicated_dataset(queue(reviewed_item(), separate_version), trusted_adjudicators=TRUSTED)
    assert {case["tender_id"] for case in versioned["cases"]} == {
        "tender:42@sha256:version-1",
        "tender:42@sha256:version-2",
    }
    with pytest.raises(ValueError, match="no human-adjudicated"):
        build_adjudicated_dataset(queue(reviewed_item(review_status="pending_adjudication")), trusted_adjudicators=TRUSTED)


def test_dataset_is_deterministic_and_cli_writes_private_non_overwriting_file(tmp_path, monkeypatch, capsys):
    source = tmp_path / "queue.json"
    source.write_text(json.dumps(queue(reviewed_item())), encoding="utf-8")
    output = tmp_path / "human-feedback-cases.json"
    dataset1 = build_adjudicated_dataset(queue(reviewed_item()), trusted_adjudicators=TRUSTED)
    dataset2 = build_adjudicated_dataset(queue(reviewed_item()), trusted_adjudicators=TRUSTED)
    assert dataset1 == dataset2

    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(EVALUATION_ADJUDICATORS=TRUSTED))
    assert main(["--review-queue", str(source), "--output", str(output)]) == 0
    assert "1 cases" in capsys.readouterr().out
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["human_reviewed_case_count"] == 1
    with pytest.raises(FileExistsError):
        write_adjudicated_dataset(source, output, trusted_adjudicators=TRUSTED)


def test_cli_requires_configured_adjudicator_allowlist(tmp_path, monkeypatch):
    source = tmp_path / "queue.json"
    source.write_text(json.dumps(queue(reviewed_item())), encoding="utf-8")
    output = tmp_path / "cases.json"
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(EVALUATION_ADJUDICATORS=frozenset()))
    with pytest.raises(SystemExit) as exc:
        main(["--review-queue", str(source), "--output", str(output)])
    assert exc.value.code == 2
    assert not output.exists()
