# TenderMatch

TenderMatch is a Python workflow that helps equipment manufacturers and sales teams find potentially relevant government tenders. It collects listings from selected procurement portals and research institutions, stores tender history in SQLite, classifies and ranks manufacturer matches, and can send an evidence-oriented email digest.

Matches are screening suggestions. Similarity and decision scores are heuristic, are not calibrated probabilities, and do not establish technical compliance, eligibility, or likelihood of winning. The workflow favors surfacing candidates for review over silently excluding uncertain opportunities.

## Current capabilities

- Scrapes selected CPPP listings and tender pages from IIT Madras, IIT Palakkad, IIT Goa, and IISc.
- Stores tender identity, content versions, amendments, manufacturer matches, notification state, feedback, and pipeline run summaries in SQLite.
- Uses the `BAAI/bge-small-en-v1.5` SentenceTransformer with lexical and manufacturer-profile evidence. The current catalog contains 14 profiles in `data/manufacturers.json`.
- Profile validation checks structure. Each profile includes a shared source-link list, profile version, and last-updated date, but capability claims are not individually mapped to sources; verify each product, industry, and service claim before relying on it.
- Classifies results into blocked, low-signal, high-signal, exploratory, and review-required outcomes. Thresholds are configurable in `data/matching_thresholds.json`; they are not calibrated confidence levels.
- Produces a plaintext digest with source links, product-family evidence, concerns, unverified requirements, and suggested next actions.
- Supports bounded official PDF retrieval and labelled-field text extraction only when an operator explicitly configures an approved host list and protected storage directory. Both are disabled by default.
- Captures salesperson feedback in SQLite and provides a separate, adjudicator-controlled path for adding reviewed cases to evaluation data.

There is no web dashboard or hosted API in this repository. Feedback capture is a command-line/database workflow rather than a review interface.

## Data flow

```text
Selected tender portals
        ↓
Scrapers and date/freshness checks
        ↓
SQLite identity, content versions, and run ledger
        ↓
High-recall candidate generation and explainable ranking
        ↓
Human-review categories and optional document evidence
        ↓
Notification outbox → plaintext email digest
```

The matching implementation and its limitations are described in [`docs/matching.md`](docs/matching.md). Tender amendment behavior is heuristic and requires human review. See [`docs/document-retrieval.md`](docs/document-retrieval.md) and [`docs/document-extraction.md`](docs/document-extraction.md) before enabling document processing.

## Repository setup and tests

Use Python 3.12 to match the pull-request CI environment. Install dependencies and run deterministic tests:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pytest numpy
python -m pytest -q
python -m matching.profile_validation
```

The regression and evaluation fixtures are synthetic; they do not establish real-world matching accuracy. The PR workflow runs the deterministic subset in `.github/workflows/tests.yml` without contacting tender portals or sending email.

Running `python -m pipeline.run` performs real portal requests and may send email when all sender and recipient settings are configured. Do not use it as a dry run. The environment variables are `SENDER_EMAIL`, `SENDER_PASSWORD`, and `RECEIVER_EMAIL`. Supply them through a protected secret store; never commit them. Email delivery is not part of normal tests.

## Scheduled execution and storage

`.github/workflows/tender_pipeline.yml` schedules the pipeline every 30 minutes and also supports manual dispatch. The workflow serializes executions. It caches an authenticated encrypted SQLite snapshot because GitHub documents that fork pull-request workflows can read caches from the base branch; the database contains email recipients and salesperson feedback. Configure the `TENDERMATCH_DB_CACHE_KEY` repository secret before running the one-time manual workflow `.github/workflows/migrate_tender_db_cache.yml`; it encrypts the existing database cache and removes the legacy plaintext cache entries. The scheduled workflow fails closed when no encrypted cache is available. The cache is still **not durable storage** and can be evicted or expire, losing tender history, feedback, run records, notification state, and document metadata. This repository has no configured persistent deployment host, backup, or recovery target.

For a persistent host, set `TENDERMATCH_DB_PATH` to a SQLite file on a mounted durable volume. Its parent directory must already exist. Keep document storage on protected persistent storage too before enabling `TENDERMATCH_DOCUMENT_HOSTS` and `TENDERMATCH_DOCUMENT_DIR`. Review source access terms before allowlisting a host.

For operator-managed snapshots on a protected host, `python -m data.backup backup "$TENDERMATCH_DB_PATH" /protected/backups/tenders-YYYYMMDD.sqlite3` creates an integrity-checked, owner-readable SQLite backup using SQLite's online backup API. Restore with `python -m data.backup restore /protected/backups/tenders-YYYYMMDD.sqlite3 "$TENDERMATCH_DB_PATH" --replace`. Stop the scheduler and pipeline before restoring. The command does not schedule backups or upload them; the operator must protect and retain the destination separately. The Actions cache remains temporary and is not a backup target.

The local `scheduler.py` process runs serially every 30 minutes but is not supervised by a service manager. The Actions workflow is the configured scheduled runner; neither configuration makes its cache durable. See [`docs/checkpoint.md`](docs/checkpoint.md) for verified status and remaining operational blockers.

For persistent recurring operation, use a supervised Python VM or container with a durable mounted SQLite volume, protected secret configuration, and backup/recovery procedures. No such host or Vercel web application is configured in this repository.

## Evaluation and evidence limits

`data/evaluation/golden_tender_cases.json` contains 18 synthetic adversarial examples. Human-reviewed examples are maintained separately when explicitly adjudicated. The recorded baseline and threshold sensitivity report are synthetic diagnostics, not accuracy claims. No live end-to-end portal-to-email run has been performed as part of the deterministic test suite.

Manufacturer profiles include profile-level source links, version numbers, and last-updated dates, but do not yet map every product or capability claim to its own source. Profile validation checks structure, not the truth of each claim. A profile website alone is not proof of every listed capability.

## Feedback and documents

- Profile format and validation: [`docs/manufacturer-profiles.md`](docs/manufacturer-profiles.md)
- Matching and score interpretation: [`docs/matching.md`](docs/matching.md)
- Email behavior and feedback workflow: [`docs/salesperson-feedback.md`](docs/salesperson-feedback.md)
- Official document access and limits: [`docs/document-retrieval.md`](docs/document-retrieval.md)
- Text extraction and evidence provenance: [`docs/document-extraction.md`](docs/document-extraction.md)
- Current implementation checkpoint: [`docs/checkpoint.md`](docs/checkpoint.md)

## License

MIT License. See [`LICENSE`](LICENSE).
