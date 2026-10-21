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
