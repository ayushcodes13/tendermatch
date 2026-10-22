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

The historical pre-profile-correction report is `data/evaluation/baseline_synthetic_2026-10-22.json`. `data/evaluation/baseline_synthetic_profiles_2026-10-22.json` records the catalog after the initial profile updates; `data/evaluation/baseline_synthetic_staton_audit_2026-10-22.json` includes the earlier STATON category correction, and `data/evaluation/baseline_synthetic_parteq_cvd_provenance_2026-10-22.json` preserves the prior ParteQ profile report. The latest report is `data/evaluation/baseline_synthetic_nippon_fertilizer_context_2026-10-22.json`; it includes the current SALD, GeniCore, Teer, Spinflex, ParteQ, STATON, ON NANO, Thesix, Nordiko, Nippon, and Agnitron profiles. It adds two explicitly synthetic fertilizer cases: mercury-analysis equipment at a fertilizer plant ranks Nippon first, while a bulk-fertilizer-only procurement is a labeled false positive. The report keeps the supported mercury analyzer first and moves Nippon to third for the bulk-fertilizer-only case using a contextual penalty; the high-recall candidate remains visible. Evaluation totals are unchanged: 8/8 labeled relevant pairs retrieved, 8/11 definitively labeled retrieved pairs relevant, and 68 candidates unjudged. This ordering change is diagnostic, not evidence of improved matching quality. The Agnitron GOX300 wording changes one top-five ordering on `SYN-CORRIGENDUM-013`: Agnitron moves ahead of Nippon, and both pairs are unjudged. The report preserves the full manufacturer-profile file hash from the matcher run (`72aa40cc…`) and separately records a ranking-input projection hash. After GeniCore, P.G. Instruments, and Korvus Technology, Agnitron service, and Nippon Instruments RA-7000A/RA-7000F/MA-3 Solo/MA-3000/PE-1000/WA-5A/WA-5F/EMP-3/EMP-Gold+/SGM-9/AM-6F provenance-only updates, the metadata records the current full catalog hash while the ranking-input hash remains unchanged. The local environment lacked `sentence-transformers`, so no fresh matcher run was possible; the report’s rankings and generation timestamp are unchanged. Each report records dataset, manufacturer profile, and evaluator/matcher source hashes, model revision, runtime versions, candidate lists, and per-tender latency. A regression test checks the dataset hash, preserved run-time profile-file hash, current catalog hash, and the ranking-input projection hash.

The latest run returned all 8 labeled relevant pairs in its top-five candidates. Of the 11 retrieved tender/manufacturer pairs with definitive labels, 8 were labeled relevant and 3 were labeled not relevant (`syn-fertilizer-commodity-018`, `syn-pump-002`, `syn-pump-003`). It returned 68 additional candidates without judgments. The earlier reports had 61 additional unjudged candidates and the original pre-profile-correction run had 1 false positive among 8 definitively labeled retrieved pairs. This is a synthetic diagnostic over a small, incomplete set, not precision or recall against ground truth and not a production accuracy claim. Differences reflect manufacturer-profile input changes; they are not an algorithm improvement comparison.

No tender is exhaustively labeled across the active manufacturer catalog, so precision@K and recall@K remain null. There are zero human-reviewed cases. The latest report records median candidate-generation latency of 16.0 ms and mean latency of 16.9 ms over 17 unique synthetic tenders on Python 3.12.13 with Sentence Transformers 6.2.0, Torch 2.14.1, and model revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, after model loading. These environment-specific timings are not a service-level measurement. No cost source is configured, so per-tender cost is unavailable. Model load time, live portal time, SMTP time, and full pipeline latency are not measured by these numbers.

Run the dataset integrity checks with:

```bash
python -m pytest -q tests/test_matching_dataset.py
```
