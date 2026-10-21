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

Run the dataset integrity checks with:

```bash
python -m pytest -q tests/test_matching_dataset.py
```
