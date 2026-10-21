# TenderMatch matching evaluation data

`data/evaluation/golden_tender_cases.json` is a versioned regression dataset for tender/manufacturer pairs. Its 16 current examples are synthetic and intentionally adversarial. They cover domain confusion, generic descriptions, service-only work, acronyms and aliases, conflicting requirements, negative terms, overlapping manufacturers, amendments, and missing capability evidence.

## Label meaning

- `relevant`: profile and tender evidence directly support a product-family fit.
- `potentially_relevant_needs_review`: a plausible fit exists, but a material issue needs a person to check.
- `not_relevant`: the request belongs to a different equipment or service domain.
- `insufficient_information`: current information cannot support a relevance decision.

Labels describe the authored synthetic scenario, not eligibility, product certification, or a probability that a manufacturer can win. A single tender can be relevant to more than one manufacturer; labels are per tender/manufacturer pair.

## Provenance and use

Every case records whether it is synthetic or human reviewed, a case-specific rationale, technical evidence, known exclusions, and provenance. The current dataset has zero human-reviewed cases. Synthetic examples can support deterministic regression tests and expose failure patterns, but they must not be reported as ground truth or used to claim production accuracy.

Before reporting evaluation metrics, add a separately identified set of human-reviewed cases with reviewer and source provenance, preserve disputed labels for adjudication, and report synthetic and human-reviewed results separately. Do not convert a synthetic case to human-reviewed without recording the review provenance and date.

## Evaluation runner

The evaluator in matching/evaluation.py reports candidate recall over labeled positive pairs, precision over retrieved definitive judgments, review/insufficient-information rate, unjudged candidate count, false-positive case IDs, per-manufacturer results, latency, and cost availability. It never treats an unlabeled candidate as a negative. Matcher scores are retained as heuristic ranking signals and are not calibrated probabilities.

Run the current candidate generator with the installed SentenceTransformer dependency and model available using:

    python -m matching.evaluation --dataset data/evaluation/golden_tender_cases.json

## Current synthetic diagnostic

The baseline artifact is data/evaluation/baseline_synthetic_2026-10-22.json. It records the dataset, manufacturer profile, and evaluator/matcher source hashes, model revision, runtime versions, candidate lists, and per-tender latency.

In this run, the current matcher returned all 7 of 7 labeled relevant pairs in its top-five candidates. Among retrieved pairs with definitive labels, 7 of 8 were labeled relevant; syn-pump-002 was a labeled false positive. It returned 61 additional candidates without judgments. This is a synthetic diagnostic over a small, incomplete set, not precision or recall against ground truth and not a production accuracy claim.

No tender is exhaustively labeled across the active manufacturer catalog, so precision@K and recall@K remain null. There are zero human-reviewed cases. Median candidate-generation latency was 15.0 ms per tender and mean latency was 15.8 ms over 15 unique synthetic tenders on the recorded local runtime, after model loading. No cost source is configured, so per-tender cost is unavailable. Model load time, live portal time, SMTP time, and full pipeline latency are not measured by these numbers.

Run the dataset integrity checks with:

```bash
python -m pytest -q tests/test_matching_dataset.py
```
