# Salesperson feedback capture

TenderMatch can append a human feedback record for a tender/manufacturer pair to the configured SQLite database. This is a small operator-mediated CLI, not a hosted review interface:

```sh
TENDERMATCH_DB_PATH=/var/lib/tendermatch/tenders.db \
TENDERMATCH_FEEDBACK_REVIEWERS='reviewer@example.com' \
python -m data.feedback \
  --tender-identity-key 'sha256:...' \
  --tender-version 'sha256:...' \
  --manufacturer-id 'maker-1' \
  --label relevant \
  --reviewer reviewer@example.com \
  --reason 'The stated operating range appears suitable'
```

`TENDERMATCH_FEEDBACK_REVIEWERS` is a comma-separated operator-managed allowlist. The CLI rejects a reviewer not in that list. This is an identity assertion by the local operator; it is not authentication for a multi-user web service. Do not expose the CLI or database to untrusted users.

Supported labels are `relevant`, `not_relevant`, `already_known`, `worth_pursuing`, `wrong_manufacturer`, `incorrect_product_category`, `missing_technical_evidence`, and `eligibility_not_met`. The optional reason is limited to 1,000 characters. Each row includes tender identity, optional content version, manufacturer identity, label, reason, reviewer, and an ISO-8601 UTC timestamp.

Feedback is append-only at the application layer. SQLite triggers reject updates and deletes; a new opinion creates a new historical row. These controls reduce accidental changes but are not tamper-proof against an operator with direct database-file access. Protect and back up the SQLite file appropriately. Reviewers should avoid putting personal or confidential information in free-text reasons.

Feedback is not automatically used to alter matching rules, retrain a model, or rewrite the golden dataset. A later evaluation-import step must preserve reviewer, provenance, label, and the tender/manufacturer/version join, then be reviewed before feedback is treated as evaluation ground truth. GitHub Actions currently does not provide durable database storage, so do not configure this capture path there until the database persistence decision is resolved.

## Export for evaluation review

Export the current records to a new private JSON file for adjudication:

```sh
TENDERMATCH_DB_PATH=/var/lib/tendermatch/tenders.db \
python -m data.feedback_export --output /var/lib/tendermatch/feedback-review-2026-10-22.json
```

The exporter joins the exact `tender_version` snapshot that was reviewed when one is available; it marks a fallback to current tender content when historical context is missing. Every item remains `pending_adjudication`, and the top-level `eligible_for_metrics` value is `false`. The suggested evaluation label is populated only for direct labels (`relevant`, `not_relevant`, and `missing_technical_evidence` → `insufficient_information`); workflow dispositions such as `already_known`, `worth_pursuing`, and `eligibility_not_met` are left unmapped. A human must verify the tender text and label before creating a separate evaluation case. The export refuses to overwrite an existing file.

To promote reviewed records, edit the exported JSON items only after checking the cited source and tender version. For each approved row set `review_status` to `human_adjudicated`, then provide `adjudicated_label` (`relevant`, `not_relevant`, `potentially_relevant_needs_review`, or `insufficient_information`), `adjudication_reason`, `adjudicator`, a timezone-aware ISO-8601 `adjudicated_at`, and any relevant `technical_evidence` or `known_exclusions`. The source URL and description must remain available. Configure trusted adjudicators separately with `TENDERMATCH_EVALUATION_ADJUDICATORS` before running:

```sh
TENDERMATCH_EVALUATION_ADJUDICATORS='qa@example.com' \
python -m data.feedback_adjudication \
  --review-queue /var/lib/tendermatch/feedback-review-2026-10-22.json \
  --output /var/lib/tendermatch/human-feedback-cases.json
```

The importer creates a separate evaluation dataset; it never modifies `golden_tender_cases.json`. It ignores pending rows, rejects untrusted adjudicators, invalid labels, missing provenance, duplicate tender/version/manufacturer pairs, or an input queue marked eligible for metrics. When a feedback row has a tender version, the evaluation tender ID includes that fingerprint so two amended versions are not collapsed into one case. Run the evaluator explicitly against the output file, for example `python -m matching.evaluation --dataset /var/lib/tendermatch/human-feedback-cases.json`. Keep real feedback exports private and review them before using their metrics.
