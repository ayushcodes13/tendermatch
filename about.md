# TenderMatch system overview

TenderMatch is a scheduled Python pipeline for finding and reviewing government tenders that may fit a small catalog of equipment manufacturers. It is a procurement-intelligence aid; it does not decide compliance, eligibility, or bid suitability.

## Architecture

```text
scrapers/ → pipeline/run.py → data/db.py (SQLite)
                  ↓                 ↓
       matching/ + profiles     versions, amendments,
                  ↓             feedback, outbox, run ledger
           digest/ → email
```

The current scraper set collects selected CPPP listings and specific tender pages from IIT Madras, IIT Palakkad, IIT Goa, and IISc. `pipeline/run.py` checks freshness, updates tender versions, classifies tenders, ranks manufacturer candidates, and queues eligible notifications. SQLite stores tender state, amendments, document observations, salesperson feedback, email delivery state, and run summaries.

## Matching

Manufacturer profiles live in `data/manufacturers.json`; there are currently 14. Candidate generation combines BAAI/bge-small-en-v1.5 embeddings with lexical terms, aliases, concepts, categories, products, services, and negative evidence. Candidates are ranked with heuristic evidence and placed in high-signal, exploratory, low-signal, blocked, or review-required outcomes.

Scores and thresholds are not calibrated probabilities. They do not prove a manufacturer can meet a tender's technical or eligibility requirements. `docs/matching.md` documents the scoring evidence and limitations. The current synthetic evaluation cases are regression examples, not ground truth, and no matching-accuracy percentage is established.

## Documents and notifications

Document retrieval is bounded and disabled by default. It requires an explicit HTTPS host allowlist and configured storage path. Native PDF text extraction returns only supported labelled fields with page/source evidence; it does not perform OCR or infer unlabelled requirements.

Email digests distinguish high-signal, potential, and updated opportunities and include source links and match explanations. SQLite outbox retries are designed for recovery, but SMTP cannot provide exactly-once delivery. The configured GitHub Actions runner currently persists its database through a cache, which is not guaranteed durable.

## Runtime boundaries

`.github/workflows/tender_pipeline.yml` runs on a 30-minute schedule and supports manual dispatch. `scheduler.py` is a separate local serial loop. There is no web dashboard, hosted API, persistent production host, configured backup, or verified live portal-to-email deployment in this repository. A persistent SQLite volume is required for reliable history; see `README.md` and `docs/checkpoint.md` for setup and current limitations.
