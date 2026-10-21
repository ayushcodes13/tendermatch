# TenderMatch implementation checkpoint

Update this file through the same focused PR as each implementation where practical. A task is complete only after its implementation is verified and its PR is merged.

## Current repository state

- Current base: `main` at `c029b5d` after merged P0.6 outbox PR #9; this P1.1 branch starts directly from that commit.
- Open unrelated draft: [PR #1](https://github.com/ayushcodes13/tendermatch/pull/1), “Document TenderMatch hosting and runtime needs”.
- `main` is not branch-protected. The repository has no PR status checks configured; the existing workflow is schedule/manual only.
- No live scraper, model download, or SMTP delivery has been run as verification.
- Required runtime setup still missing: GitHub Actions secret `RECEIVER_EMAIL`.

## Phase 0 — Reliability

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P0.1 Digest stats and formatting | Complete | `fix/digest-stats-contract`; [PR #2](https://github.com/ayushcodes13/tendermatch/pull/2) | 3 targeted tests passed; merged as `609ff68`. | Live scraper and SMTP delivery are intentionally not part of the controlled test. |
| P0.2 Configuration and email credentials | Partially verified | `fix/email-config-contract`; [PR #3](https://github.com/ayushcodes13/tendermatch/pull/3) | 5 targeted tests passed; merged as `c90d30c`. SMTP uses mocked transport. | Add `RECEIVER_EMAIL` secret before scheduled delivery can work. |
| P0.3 Date parsing and freshness | Complete | `fix/tender-date-freshness`; [PR #5](https://github.com/ayushcodes13/tendermatch/pull/5) | 25 targeted tests passed; compile check passed; independently reviewed; merged as `cc4e236`. | No live portal drift check; date-unknown candidates remain reviewable. |
| P0.4 Database identity, deduplication, transactions | Complete | `fix/tender-database-deduplication`; [PR #6](https://github.com/ayushcodes13/tendermatch/pull/6) | Focused suite: 37 passed; independent review found no confirmed defects; merged as `18728e3`. | No production SQLite file was available to validate migration on customer data. Cross-portal duplicates without shared official IDs or source URLs remain unresolved; IISc document-link stability needs monitoring. |
| P0.5 Scheduled execution and persistence | Partially verified; Actions retained temporarily | [PR #7](https://github.com/ayushcodes13/tendermatch/pull/7), [PR #8](https://github.com/ayushcodes13/tendermatch/pull/8), merged as `ae5d928` and `12e34cb` | Workflow runs serialize across refs; `TENDERMATCH_DB_PATH` supports an existing mounted volume and fails when its directory is absent. | User selected Actions temporarily. Its cache is not durable storage; provider, costs, credentials, backup/recovery, and deployment remain unresolved. New queued runs can replace a pending run. |
| P0.6 Recoverable email delivery | Complete | `feat/recoverable-email-outbox`; [PR #9](https://github.com/ayushcodes13/tendermatch/pull/9) | Focused suite: 49 passed; compileall and `git diff --check` passed. Full suite: 49 passed, 1 existing failure (`tests/test_specific_tender.py` expects a model but test stub supplies `SentenceTransformer=object`). Independent adversarial review found no remaining correctness issue; outbox/sender/pipeline subset: 12 passed. Merged as `c029b5d`. | Legacy global emailed flags cannot identify a recipient, so current recipient may get one duplicate while outbox history is established. Changed versions currently queue as new-opportunity digests; meaningful amendment comparison/type-specific messaging remains P3. Actions cache loss can still lose delivery state; SMTP's accepted-then-crashed window can cause a duplicate retry. |

## Phase 1 — Evaluation baseline

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P1.1 Golden tender matching dataset | Implemented; independently reviewed; PR pending | `test/golden-tender-dataset`; PR pending | Dataset integrity test: 1 passed; P0.6 outbox/pipeline regression subset: 10 passed; compileall and `git diff --check` passed. Independent review findings were fixed and rechecked. 16 synthetic tender/manufacturer pairs cover required adversarial categories; zero human-reviewed cases are labeled as such. | Human-reviewed labels and source provenance are still needed before ground-truth evaluation. |
| P1.2 Measurable matching evaluation | Not started | — | — | P1.1 labelled cases. |
| P1.3 Adversarial/regression suite and PR CI | Not started | — | — | Stable deterministic cases and current model dependency boundaries. |

## Phase 2 — Manufacturer matching

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P2.1 Manufacturer capability schema and validation | Not started | — | — | Verified source provenance for manufacturer claims. |
| P2.2 Separate high-recall candidate generation from ranking | Not started | — | — | P1 baseline to measure recall. |
| P2.3 Domain compatibility and negative matching | Not started | — | — | Adversarial labelled coverage. |
| P2.4 Explainable scoring and threshold calibration | Not started | — | — | Evaluation dataset and baseline. |

## Phase 3 — Tender lifecycle

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P3.1 Stable identity and version fingerprints | Not started | — | — | Coordinate with P0.4 database identity work. |
| P3.2 Meaningful amendment detection and history | Not started | — | — | Source-specific change fixtures. |
| P3.3 Amendment-specific notifications | Not started | — | — | P0.6 recoverable delivery and P3.2 version history. |

## Phase 4 — Document intelligence

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P4.1 Selective official-document retrieval | Not started | — | — | Access/terms review, bounded downloads and storage. |
| P4.2 Technical extraction with provenance | Not started | — | — | Representative native/scanned document fixtures. |
| P4.3 Selective LLM verification | Not started | — | — | Evidence-backed value, cost, latency, and safety evaluation. |

## Phase 5 — Usability and feedback

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P5 Actionable digest | Not started | — | — | Stable tender versions and evidence fields. |
| P6 Feedback collection and evaluation improvements | Not started | — | — | Smallest practical interaction and integrity requirements. |

## Phase 6 — Production readiness

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| Security, reliability, observability, and recovery | Not started | — | — | Build on P0.5/P0.6 persistence and delivery contracts. |
| Deployment smoke verification | Not started | — | — | Authorized deployment target and credentials. |
| README and operational documentation reconciliation | Not started | — | — | Update against final verified behavior and evaluation. |

## Next

P1.1: review and merge the synthetic dataset PR, then build reproducible metrics on clearly separated synthetic and human-reviewed cases.
