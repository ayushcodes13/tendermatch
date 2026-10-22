"""Metrics and runner for explicitly labeled tender/manufacturer cases.

Unlabeled manufacturer pairs are never counted as negative. Ranked metrics are
reported only for tenders marked complete and exhaustively labeled against the
active manufacturer catalog.
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


RELEVANT = "relevant"
NOT_RELEVANT = "not_relevant"
REVIEW_LABELS = {"potentially_relevant_needs_review", "insufficient_information"}
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def evaluate_rankings(dataset, ranked_candidates, *, latencies_ms=None, costs_by_tender=None,
                      active_manufacturer_ids=None, top_ks=(1, 3, 5)):
    """Summarize ranking outputs without assuming unknown pairs are negative.

    ranked_candidates maps tender_id to candidate dictionaries containing
    manufacturer_id and optionally rank. Latencies and costs are optional
    tender_id-to-number mappings.
    """
    if any(k <= 0 for k in top_ks):
        raise ValueError("top_ks values must be positive integers")

    cases = dataset["cases"]
    case_by_pair = {
        (case["tender_id"], case["manufacturer_id"]): case
        for case in cases
    }
    if len(case_by_pair) != len(cases):
        raise ValueError("Dataset contains duplicate tender/manufacturer judgments")

    relevant_cases = [case for case in cases if case["label"] == RELEVANT]
    found_relevant = 0
    judged_found = 0
    true_positive = 0
    review_found = 0
    unjudged_found = 0
    false_positive_ids = []
    manufacturer_stats = {}
    normalized_rankings = {}

    for case in cases:
        stats = manufacturer_stats.setdefault(
            case["manufacturer_id"], {"labeled_relevant": 0, "found_relevant": 0}
        )
        if case["label"] == RELEVANT:
            stats["labeled_relevant"] += 1

    for tender_id, candidates in ranked_candidates.items():
        manufacturer_ids = [candidate["manufacturer_id"] for candidate in candidates]
        if len(set(manufacturer_ids)) != len(manufacturer_ids):
            raise ValueError(f"Ranking contains duplicate manufacturers for tender {tender_id}")
        has_rank = [candidate.get("rank") is not None for candidate in candidates]
        if any(has_rank) and not all(has_rank):
            raise ValueError(f"Ranking has incomplete rank values for tender {tender_id}")
        if all(has_rank):
            ranks = [candidate["rank"] for candidate in candidates]
            if len(set(ranks)) != len(ranks) or any(rank <= 0 for rank in ranks):
                raise ValueError(f"Ranking has duplicate or nonpositive ranks for tender {tender_id}")
            normalized = sorted(candidates, key=lambda candidate: candidate["rank"])
        else:
            normalized = list(candidates)
        normalized_rankings[tender_id] = normalized
        for candidate in normalized:
            manufacturer_id = candidate["manufacturer_id"]
            case = case_by_pair.get((tender_id, manufacturer_id))
            if case is None:
                unjudged_found += 1
                continue

            stats = manufacturer_stats.setdefault(
                manufacturer_id, {"labeled_relevant": 0, "found_relevant": 0}
            )
            if case["label"] == RELEVANT:
                true_positive += 1
                stats["found_relevant"] += 1
            if case["label"] in {RELEVANT, NOT_RELEVANT}:
                judged_found += 1
            elif case["label"] in REVIEW_LABELS:
                review_found += 1
            if case["label"] == NOT_RELEVANT:
                false_positive_ids.append(case["case_id"])

    for case in relevant_cases:
        if any(
            candidate["manufacturer_id"] == case["manufacturer_id"]
            for candidate in normalized_rankings.get(case["tender_id"], [])
        ):
            found_relevant += 1

    declared_complete_ids = set(dataset.get("ranking_complete_tender_ids", []))
    complete_ids = set()
    if active_manufacturer_ids is not None:
        for tender_id in declared_complete_ids:
            judged_ids = {
                case["manufacturer_id"] for case in cases if case["tender_id"] == tender_id
            }
            labels = {
                case["label"] for case in cases if case["tender_id"] == tender_id
            }
            if judged_ids == set(active_manufacturer_ids) and labels <= {RELEVANT, NOT_RELEVANT}:
                complete_ids.add(tender_id)

    top_k_metrics = {}
    for k in top_ks:
        precision_by_tender = []
        recall_by_tender = []
        no_positive_count = 0
        for tender_id in complete_ids:
            if tender_id not in normalized_rankings:
                continue
            labels = {
                case["manufacturer_id"]: case["label"]
                for case in cases if case["tender_id"] == tender_id
            }
            positives = {manufacturer_id for manufacturer_id, label in labels.items() if label == RELEVANT}
            top_ids = [candidate["manufacturer_id"] for candidate in normalized_rankings[tender_id][:k]]
            precision_by_tender.append(
                sum(labels[manufacturer_id] == RELEVANT for manufacturer_id in top_ids) / k
            )
            if positives:
                recall_by_tender.append(
                    sum(manufacturer_id in positives for manufacturer_id in top_ids) / len(positives)
                )
            else:
                no_positive_count += 1
        top_k_metrics[str(k)] = {
            "precision_at_k": statistics.mean(precision_by_tender) if precision_by_tender else None,
            "recall_at_k": statistics.mean(recall_by_tender) if recall_by_tender else None,
            "eligible_tender_count": len(precision_by_tender),
            "recall_eligible_tender_count": len(recall_by_tender),
            "no_positive_tender_count": no_positive_count,
            "excluded_incomplete_tender_count": len({case["tender_id"] for case in cases}) - len(precision_by_tender),
        }

    latencies = list((latencies_ms or {}).values())
    costs = list((costs_by_tender or {}).values())
    for manufacturer_id, stats in manufacturer_stats.items():
        denominator = stats["labeled_relevant"]
        stats["labeled_positive_recall"] = (
            stats["found_relevant"] / denominator if denominator else None
        )

    return {
        "dataset_id": dataset.get("dataset_id"),
        "dataset_case_count": len(cases),
        "label_counts": {
            label: sum(case["label"] == label for case in cases)
            for label in sorted({case["label"] for case in cases})
        },
        "human_reviewed_case_count": dataset.get("human_reviewed_case_count", 0),
        "synthetic_case_count": dataset.get("synthetic_case_count", 0),
        "candidate_recall_on_labeled_positives": (
            found_relevant / len(relevant_cases) if relevant_cases else None
        ),
        "labeled_candidate_precision": true_positive / judged_found if judged_found else None,
        "labeled_candidate_precision_denominator": judged_found,
        "review_or_insufficient_rate_among_labeled_candidates": (
            review_found / (judged_found + review_found) if judged_found + review_found else None
        ),
        "unjudged_candidate_count": unjudged_found,
        "false_positive_case_ids": sorted(set(false_positive_ids)),
        "per_manufacturer": manufacturer_stats,
        "ranking_metrics": top_k_metrics,
        "ranking_metrics_scope": (
            "Only tenders explicitly marked complete, exhaustively labeled against the active catalog, "
            "and labeled with definitive relevant/not_relevant judgments are eligible."
        ),
        "latency_ms_per_tender": {
            "count": len(latencies),
            "mean": statistics.mean(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
        },
        "cost_usd_per_tender": statistics.mean(costs) if costs else None,
        "cost_measurement_status": "provided" if costs else "unavailable",
    }


def run_current_matcher(dataset, *, top_k=5):
    """Run current local candidate generation; requires the configured model dependency."""
    from matching.embedder import build_matcher

    matcher = build_matcher()
    tender_by_id = {}
    for case in dataset["cases"]:
        tender_by_id.setdefault(case["tender_id"], {
            "title": case["description"],
            "raw_text": case["description"],
        })

    rankings = {}
    latency_ms = {}
    for tender_id, tender in tender_by_id.items():
        started = time.perf_counter()
        raw_candidates = matcher.match_topk(tender, top_k=top_k)
        latency_ms[tender_id] = (time.perf_counter() - started) * 1000
        evidence_fields = (
            "manufacturer_id", "manufacturer_name", "rank", "base_semantic_score",
            "score", "keyword_hits", "product_hits", "category_hits", "alias_hits",
            "concept_hits", "service_hits", "negative_hits", "contextual_negative_hits", "reason_codes",
        )
        rankings[tender_id] = [
            {key: candidate[key] for key in evidence_fields if key in candidate}
            for candidate in raw_candidates
        ]

    catalog_ids = [manufacturer["id"] for manufacturer in matcher.manufacturers]
    try:
        from huggingface_hub import snapshot_download

        model_revision = Path(
            snapshot_download(MODEL_NAME, local_files_only=True)
        ).name
    except Exception:
        model_revision = None
    runtime_versions = {"python": platform.python_version()}
    for package in ("sentence-transformers", "torch", "numpy", "transformers"):
        try:
            runtime_versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            runtime_versions[package] = None
    report = evaluate_rankings(
        dataset,
        rankings,
        latencies_ms=latency_ms,
        active_manufacturer_ids=catalog_ids,
    )
    report["runtime_versions"] = runtime_versions
    report["model_revision"] = model_revision
    report["per_tender_latency_ms"] = latency_ms
    return report, rankings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate TenderMatch manufacturer candidate ranking")
    parser.add_argument("--dataset", default="data/evaluation/golden_tender_cases.json")
    parser.add_argument("--output", help="Optional path to write the JSON report; defaults to stdout")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)

    try:
        dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot load evaluation dataset: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        report, rankings = run_current_matcher(dataset, top_k=args.top_k)
    except Exception as exc:
        print(f"Cannot run current matcher baseline: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    report["algorithm"] = "TenderMatcher.match_topk"
    report["embedding_model"] = MODEL_NAME
    report["score_interpretation"] = "Heuristic ranking score, not a calibrated probability"
    report["top_k"] = args.top_k
    report["rankings"] = rankings
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    root = Path(__file__).resolve().parents[1]
    dataset_bytes = json.dumps(dataset, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    profile_path = root / "data" / "manufacturers.json"
    code_paths = (
        Path(__file__),
        root / "matching" / "embedder.py",
        root / "matching" / "matcher.py",
        root / "matching" / "candidate_compatibility.py",
        root / "matching" / "domain_keywords.py",
    )
    report["input_sha256"] = {
        "dataset": hashlib.sha256(dataset_bytes).hexdigest(),
        "manufacturer_profiles": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "evaluation_and_matching_code": {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in code_paths
        },
    }
    report["runtime_platform"] = platform.platform()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
