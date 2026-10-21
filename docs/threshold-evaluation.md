# Decision-threshold sensitivity evaluation

Run the deterministic label-scope report with the locally configured SentenceTransformer model:

```bash
python -m matching.threshold_evaluation \
  --dataset data/evaluation/golden_tender_cases.json \
  --scenarios data/evaluation/threshold_scenarios_synthetic.json \
  --output data/evaluation/threshold_sensitivity_synthetic_2026-10-22.json
```

The runner reuses the same top-five manufacturer candidates for every scenario, applies the current pipeline digest match filter, and then runs classification with each threshold profile. A pair is included in the judged metrics only when its manufacturer is displayed in the digest and the dataset has an explicit label for that tender/manufacturer pair. `relevant` and `not_relevant` labels contribute to definitive pair precision; review/insufficient labels and unjudged candidates are reported separately. Unknown pairs are never treated as negative.

## Recorded synthetic diagnostic

The report uses 16 synthetic labeled pairs across 15 tender IDs; there are no human-reviewed labels. It records hashes for the dataset, manufacturer profiles, threshold scenarios, and code, plus runtime and model revision.

| Scenario | Tender buckets | Digest tenders | Labeled relevant pairs retained | Definitive delivered pairs | Unjudged displayed candidates |
| --- | --- | ---: | ---: | ---: | ---: |
| Configured defaults | 8 high-signal, 2 agent-review, 1 low-signal, 1 hard reject, 3 soft reject | 10 | 7/7 | 7/7 labeled relevant | 36 |
| Diagnostic review minimum 20 | 8 high-signal, 3 agent-review, 1 hard reject, 3 soft reject | 11 | 7/7 | 7/7 labeled relevant | 37 |

Lowering the review minimum changed one tender from low-signal to agent-review, adding it to the digest. The seven delivered pairs with definitive labels remained relevant, while one additional displayed candidate was unjudged. The synthetic labels are incomplete, so these figures cannot establish production precision, recall, or calibrated thresholds. The diagnostic threshold is illustrative and is not a recommended setting.
