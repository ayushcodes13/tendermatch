# TenderMatch matching evaluation data

`data/evaluation/golden_tender_cases.json` is a versioned regression dataset for tender/manufacturer pairs. Its 18 current examples are synthetic and intentionally adversarial. They cover domain confusion, generic descriptions, service-only work, acronyms and aliases, conflicting requirements, negative terms, overlapping manufacturers, amendments, and missing capability evidence.

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

The repository retains historical profile snapshots in `data/evaluation/`. For the ON NANO wording correction, the matched before-and-after runs are `data/evaluation/baseline_synthetic_on_nano_glass_panel_scope_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_on_nano_glass_panel_scope_2026-10-22.json`. Both use the same 18-case synthetic dataset, matcher code, model revision, and top-five setting; only the manufacturer profile snapshot differs.

Both runs retrieved all 8 labeled relevant pairs, returned 8 of 11 definitively labeled candidates as relevant, and left 68 candidates unjudged. One unjudged top-five result changed for `SYN-VACUUM-CLEANER-010`: ON NANO left the list and SALD entered it. That tender is judged only against Korvus, so this does not demonstrate reduced false positives or improved matching quality. The updated ON NANO profile removes unsupported glass-core-substrate and high-density-packaging wording while retaining the official products page's glass-panel substrate and advanced-packaging descriptions.

These remain synthetic diagnostics, not ground truth or production-accuracy estimates. There are zero human-reviewed examples and no tender is exhaustively labeled across the active catalog, so precision@K and recall@K remain null. Do not interpret unchanged labeled-pair metrics as a quality improvement.

The current-profile run records a median candidate-generation latency of 14.0 ms and a mean of 14.7 ms over 17 unique synthetic tenders after model loading, using Python 3.12.13, Sentence Transformers 6.2.0, Torch 2.14.1, and model revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. This local timing is not a service-level measurement. Cost, model-load time, portal time, SMTP time, and full pipeline latency are not measured.

Run the dataset integrity checks with:

```bash
python -m pytest -q tests/test_matching_dataset.py
```
