"""Evaluate decision-threshold scenarios against judged tender/manufacturer pairs.

Unjudged pairs remain unknown. Because current labels are synthetic and
incomplete, reported rates are scoped diagnostics, not calibrated quality.
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from matching.filter import classify_tender
from matching.evaluation import validate_dataset_provenance
from matching.thresholds import resolve_thresholds


PIPELINE_MATCH_SCORE_MIN = 0.60
DELIVERED_CATEGORIES = {"high_signal", "explore"}
LABELS = {
    "relevant",
    "not_relevant",
    "potentially_relevant_needs_review",
    "insufficient_information",
}
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def _matches_shown_in_digest(candidates):
    return [
        candidate
        for candidate in candidates
        if (
            candidate.get("score", 0) >= PIPELINE_MATCH_SCORE_MIN
            or candidate.get("keyword_hits")
            or candidate.get("product_hits")
            or candidate.get("category_hits")
            or candidate.get("concept_hits")
        )
    ]


def evaluate_threshold_scenarios(dataset, matcher, scenarios, *, classifier=classify_tender):
    """Run each threshold profile over the same deterministic matcher outputs."""
    provenance_counts = validate_dataset_provenance(dataset)
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError("At least one named threshold scenario is required")
    cases = dataset["cases"]
    if any(case.get("label") not in LABELS for case in cases):
        raise ValueError("Dataset contains an unknown relevance label")
    case_by_pair = {}
    tender_by_id = {}
    for case in cases:
        pair = (case["tender_id"], case["manufacturer_id"])
        if pair in case_by_pair:
            raise ValueError("Dataset contains duplicate tender/manufacturer judgments")
        case_by_pair[pair] = case
        tender_by_id.setdefault(case["tender_id"], {
            "title": case["description"],
            "raw_text": case["description"],
        })

    rankings = {
        tender_id: matcher.match_topk(tender, top_k=5)
        for tender_id, tender in tender_by_id.items()
    }
    scenario_results = {}
    for name, overrides in scenarios.items():
        effective_thresholds = resolve_thresholds(overrides)
        decision_counts = {}
        displayed_pair_ids = set()
        unjudged_displayed = 0
        delivered_tender_count = 0

        for tender_id, tender in tender_by_id.items():
            candidates = rankings[tender_id]
            result = classifier(
                tender,
                manufacturer_candidates=candidates,
                thresholds=effective_thresholds,
            )
            decision = result.get("decision", "unknown")
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            if result.get("category") not in DELIVERED_CATEGORIES:
                continue
            delivered_tender_count += 1
            displayed_ids = {
                candidate.get("manufacturer_id")
                for candidate in _matches_shown_in_digest(candidates)
            }
            for manufacturer_id in displayed_ids:
                case = case_by_pair.get((tender_id, manufacturer_id))
                if case is None:
                    unjudged_displayed += 1
                else:
                    displayed_pair_ids.add(case["case_id"])

        delivered_relevant = [
            case for case in cases
            if case["label"] == "relevant" and case["case_id"] in displayed_pair_ids
        ]
        delivered_not_relevant = [
            case for case in cases
            if case["label"] == "not_relevant" and case["case_id"] in displayed_pair_ids
        ]
        review_labels = [
            case for case in cases
            if case["label"] in {"potentially_relevant_needs_review", "insufficient_information"}
        ]
        delivered_review = [
            case for case in review_labels if case["case_id"] in displayed_pair_ids
        ]
        positive_count = sum(case["label"] == "relevant" for case in cases)
        definitive_delivered_count = len(delivered_relevant) + len(delivered_not_relevant)
        scenario_results[name] = {
            "thresholds": effective_thresholds,
            "decision_counts_by_tender": dict(sorted(decision_counts.items())),
            "delivered_tender_count": delivered_tender_count,
            "case_count": len(cases),
            "labeled_positive_case_count": positive_count,
            "labeled_positive_pair_digest_recall": (
                len(delivered_relevant) / positive_count if positive_count else None
            ),
            "definitive_labeled_pair_precision": (
                len(delivered_relevant) / definitive_delivered_count
                if definitive_delivered_count else None
            ),
            "definitive_labeled_pairs_delivered": definitive_delivered_count,
            "review_or_insufficient_pairs_delivered": len(delivered_review),
            "unjudged_displayed_candidate_count": unjudged_displayed,
            "false_positive_case_ids": sorted(case["case_id"] for case in delivered_not_relevant),
            "missed_relevant_case_ids": sorted(
                case["case_id"] for case in cases
                if case["label"] == "relevant" and case["case_id"] not in displayed_pair_ids
            ),
        }

    return {
        "dataset_id": dataset.get("dataset_id"),
        "dataset_case_count": len(cases),
        "synthetic_case_count": provenance_counts["synthetic_case_count"],
        "human_reviewed_case_count": provenance_counts["human_reviewed_case_count"],
        "label_counts": {
            label: sum(case["label"] == label for case in cases)
            for label in sorted({case["label"] for case in cases})
        },
        "metric_scope": {
            "candidate_top_k": 5,
            "digest_categories": sorted(DELIVERED_CATEGORIES),
            "displayed_match_rule": (
                "Candidate score >= 0.60 or at least one keyword, product, category, or concept hit; "
                "matches the current pipeline filter."
            ),
            "unjudged_policy": "Unjudged displayed candidates are counted separately, never treated as negative.",
        },
        "scope": (
            "Pairs are joined only when an explicitly judged manufacturer appears in the digest match list. "
            "Unjudged candidates are counted separately and never treated as negative. All current labels are synthetic."
        ),
        "scenarios": scenario_results,
    }


def _read_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load {label}: {type(exc).__name__}: {exc}") from exc


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Evaluate TenderMatch decision thresholds on labeled cases")
    parser.add_argument("--dataset", default=str(root / "data/evaluation/golden_tender_cases.json"))
    parser.add_argument("--scenarios", help="Optional JSON object mapping scenario names to threshold overrides")
    parser.add_argument("--output", help="Optional report path; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        dataset = _read_json(args.dataset, "evaluation dataset")
        scenarios = _read_json(args.scenarios, "threshold scenarios") if args.scenarios else {"configured_default": {}}
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        from matching.embedder import build_matcher

        matcher = build_matcher()
        report = evaluate_threshold_scenarios(dataset, matcher, scenarios)
    except Exception as exc:
        print(f"Cannot evaluate threshold scenarios: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["matcher"] = "TenderMatcher.match_topk"
    report["top_k"] = 5
    report["runtime"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            package: _package_version(package)
            for package in ("sentence-transformers", "torch", "numpy")
        },
    }
    report["embedding_model"] = MODEL_NAME
    report["model_revision"] = _local_model_revision()
    report["input_sha256"] = {
        "dataset": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
        "manufacturer_profiles": hashlib.sha256((root / "data/manufacturers.json").read_bytes()).hexdigest(),
        "threshold_scenarios": (
            hashlib.sha256(Path(args.scenarios).read_bytes()).hexdigest()
            if args.scenarios else None
        ),
        "code": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                Path(__file__),
                root / "matching" / "matcher.py",
                root / "matching" / "filter.py",
                root / "matching" / "decision.py",
                root / "matching" / "scoring.py",
                root / "matching" / "signals.py",
                root / "matching" / "concepts.py",
                root / "matching" / "thresholds.py",
            )
        },
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def _package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _local_model_revision():
    try:
        from huggingface_hub import snapshot_download

        return Path(snapshot_download(MODEL_NAME, local_files_only=True)).name
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
