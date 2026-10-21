# TenderMatch implementation plan

## Objective

Make the existing TenderMatch Python workflow dependable and measurable for procurement and sales teams. Preserve high recall during discovery, then improve precision through explainable evidence and human review. Do not represent heuristic scores as probabilities or verified eligibility.

## Current architecture

`pipeline/run.py` orchestrates the flow. It collects CPPP tenders and specific scrapers for IIT Madras, IIT Palakkad, IIT Goa, and IISc; writes tender and match records to SQLite through `data/db.py`; obtains up to five manufacturer candidates through `matching/embedder.py` and `matching/matcher.py`; classifies records through deterministic evidence, scoring, and decision modules; and formats/sends a digest through `digest/`.

`scrapers/institutions.py` contains a generic institutional scraper but is not called by `collect_all_tenders()`. Scheduled execution is configured through `.github/workflows/tender_pipeline.yml` every 30 minutes; `scheduler.py` is a separate local loop. GitHub Actions restores and saves the SQLite file as a cache, which is not a durable database guarantee.

## Confirmed audit findings

| Severity | Finding | Evidence / current state |
| --- | --- | --- |
| P0, fixed | Digest formatting indexed `stats['total']` although the pipeline supplies `total_scraped`; digest labels also called the heuristic bucket high confidence. | Fixed in PR #2. Formatter and controlled pipeline regression tests pass. |
| P0, implementation merged; runtime setup pending | Configuration used inconsistent SMTP names, CI omitted the recipient, the README referenced a missing `.env.example`, and `digest/testmail.py` embedded a recipient and sent on import. | Code fixed in PR #3. GitHub has `EMAIL_USER` and `EMAIL_PASS` secrets, but no `RECEIVER_EMAIL` secret. No live delivery has been tested. |
| P0, fixed | Freshness handling rejected missing/unrecognized dates and conflated publication, update, corrigendum, and deadline dates. | Fixed in P0.3 PR #5; source-specific parsing and explicit unknown/open states now preserve candidates for review. No live portal drift check was run. |
| P0, fixed | Identity used a title-plus-organization digest, conflating same-title notices and failing to persist refreshed fields. Runtime title dedupe could suppress distinct tenders. | Fixed in P0.4 PR #6 with source/official identity keys, persisted upserts, stable per-source scraper identities, and migration/deduplication tests. |
| P0, partially addressed | Scheduled persistence is an Actions cache, not durable storage. A workflow concurrency guard prevents overlapping runs. | `.github/workflows/tender_pipeline.yml`; GitHub retains at most one pending run per concurrency group, so a newer queued event can replace an older pending run. Durable storage, host selection, costs, backups, and recovery still require a concrete reviewed deployment plan. |
| P0 | Email state is a boolean on the tender row and is set after SMTP returns. It cannot record per-recipient attempts, failures, or crash ambiguity between SMTP delivery and database commit. | `data/db.py:359-395`, `pipeline/run.py:283-292`. |
| P1 | There is no LLM verification stage. The current path is SentenceTransformer retrieval plus deterministic rules and scoring. | `matching/embedder.py`, `matching/scoring.py`, `matching/decision.py`; no LLM client or verifier exists. |
| P1 | There is no labelled evaluation dataset or measured baseline. The test directory contains live/debug scripts; the scheduled workflow does not run tests on pull requests. | `tests/`, `.github/workflows/tender_pipeline.yml`. |
| P1 | Profiles parse as JSON and contain 14 records, but there is no schema/contradiction validator or provenance/version contract. | `data/manufacturers.json`; `matching/embedder.py:102-107` reads the file directly. |
| P2 | Documentation has unsupported or stale claims: 97.2% accuracy, 20+ manufacturers, an APScheduler schedule, top-three output, and dashboard/API availability are not supported by current code/evidence. | `README.md`, `about.md`; actual profile count is 14 and the pipeline asks for top five. |

## Implementation sequence and acceptance criteria

Follow the objective's dependency order and use one focused PR per logical change. Each task is measured against its stated acceptance conditions in the objective.

1. **Phase 0 reliability:** P0.1 digest (merged), P0.2 configuration (merged; receiver secret pending), P0.3 date parsing/freshness, P0.4 identity/deduplication/transactions, P0.5 durable scheduled execution and recovery, P0.6 recoverable notification state.
2. **Phase 1 evaluation:** P1.1 labelled golden data with human-reviewed labels distinguished from synthetic cases, P1.2 reproducible metrics and baseline, P1.3 deterministic adversarial/regression suite and PR CI.
3. **Phase 2 relevance:** P2.1 manufacturer profile schema and validation, P2.2 high-recall candidate generation separated from ranking, P2.3 domain compatibility/negative evidence, P2.4 explainable and evaluated scores.
4. **Phase 3 lifecycle:** P3.1 stable source identity and SHA-256 content versions, P3.2 meaningful amendment detection with history, P3.3 version-deduplicated amendment notifications.
5. **Phase 4 evidence:** P4.1 selective official document retrieval, P4.2 source-located extraction, P4.3 bounded and evidence-checked LLM verification only where measured value justifies it.
6. **Phase 5 usability:** P5 actionable digest, P6 feedback collection and evaluation use.
7. **Phase 6 operations:** security, observability, recovery, deployment smoke evidence, and accurate documentation.

## Technical approach

- Preserve the existing Python modules and SQLite approach where they meet the workload; add migrations rather than discard records.
- Normalize scraper dates into explicit typed meanings and retain source values. Unknown dates remain explicit and reviewable rather than being fabricated or silently conflated with expiration.
- Keep tender identity separate from version fingerprints. Track source provenance and relevant field changes.
- Favor at-least-once retries with idempotency and an outbox over claims of exactly-once SMTP delivery.
- Freeze labelled cases and algorithm settings for comparisons. Separate human-reviewed ground truth from synthetic adversarial tests.
- Keep deterministic and model-dependent tests isolated from live portals, external model downloads, and real recipients.
- Add dependencies only for a demonstrated requirement; keep infrastructure appropriate to the current workload.

## Dependencies and risks

- P0.2 requires a user-provided `RECEIVER_EMAIL` GitHub Actions secret before scheduled emails can be delivered. No live SMTP test is authorized by the objective.
- P0.5 deployment selection requires review of costs, credentials, and authorization before external infrastructure is deployed.
- Existing SQLite files need backward-compatible schema migration and must not lose history.
- Scraper IDs and date fields vary by source. Fixtures are needed before asserting source-specific parsing behavior.
- Matching quality claims require verified labels and sufficient sample sizes; synthetic data alone cannot support production accuracy claims.

## Deferred until evidence justifies them

Persistent hosted infrastructure, OCR/layout-aware extraction, LLM verification, a review UI, and feedback-driven rule changes remain deferred until their prerequisites and measurable value are established. No autonomous emails, unverified eligibility claims, or automatic rule changes from unreviewed feedback are in scope.
