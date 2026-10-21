# TenderMatch implementation checkpoint

Update this file through the same focused PR as each implementation where practical. A task is complete only after its implementation is verified and its PR is merged.

## Current repository state

- Current base: `main` at `9992849` after merged P3.1 tender-version PR #19; `fix/institution-source-identity` addresses an unstable generic scraper ID before P3.2.
- Open unrelated draft: [PR #1](https://github.com/ayushcodes13/tendermatch/pull/1), “Document TenderMatch hosting and runtime needs”.
- `main` is not branch-protected. PR CI now runs the deterministic regression workflow; no checks are marked as required by branch protection.
- No live scraper or SMTP delivery has been run. The current matcher was downloaded and evaluated in an isolated temporary environment for the synthetic baseline; no model dependency was added to the project or run in CI.
- Required runtime setup still missing: GitHub Actions secret `RECEIVER_EMAIL`.

## Phase 0 — Reliability

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P0.1 Digest stats and formatting | Complete | `fix/digest-stats-contract`; [PR #2](https://github.com/ayushcodes13/tendermatch/pull/2) | 3 targeted tests passed; merged as `609ff68`. | Live scraper and SMTP delivery are intentionally not part of the controlled test. |
| P0.2 Configuration and email credentials | Partially verified | `fix/email-config-contract`; [PR #3](https://github.com/ayushcodes13/tendermatch/pull/3) | 5 targeted tests passed; merged as `c90d30c`. SMTP uses mocked transport. | Add `RECEIVER_EMAIL` secret before scheduled delivery can work. |
| P0.3 Date parsing and freshness | Complete | `fix/tender-date-freshness`; [PR #5](https://github.com/ayushcodes13/tendermatch/pull/5) | 25 targeted tests passed; compile check passed; independently reviewed; merged as `cc4e236`. | No live portal drift check; date-unknown candidates remain reviewable. |
| P0.4 Database identity, deduplication, transactions | Complete | `fix/tender-database-deduplication`; [PR #6](https://github.com/ayushcodes13/tendermatch/pull/6) | Focused suite: 37 passed; independent review found no confirmed defects; merged as `18728e3`. | No production SQLite file was available to validate migration on customer data. Cross-portal duplicates without shared official IDs or source URLs remain unresolved; IISc document-link stability needs monitoring. |
| P0.5 Scheduled execution and persistence | Partially verified; Actions retained temporarily | [PR #7](https://github.com/ayushcodes13/tendermatch/pull/7), [PR #8](https://github.com/ayushcodes13/tendermatch/pull/8), merged as `ae5d928` and `12e34cb` | Workflow runs serialize across refs; `TENDERMATCH_DB_PATH` supports an existing mounted volume and fails when its directory is absent. | User selected Actions temporarily. Its cache is not durable storage; provider, costs, credentials, backup/recovery, and deployment remain unresolved. New queued runs can replace a pending run. |
| P0.6 Recoverable email delivery | Complete | `feat/recoverable-email-outbox`; [PR #9](https://github.com/ayushcodes13/tendermatch/pull/9) | Focused suite: 49 passed; compileall and `git diff --check` passed. The former model-loading debug test has since been made deterministic in PR #12; full suite now passes. Independent adversarial review found no remaining correctness issue; outbox/sender/pipeline subset: 12 passed. Merged as `c029b5d`. | Legacy global emailed flags cannot identify a recipient, so current recipient may get one duplicate while outbox history is established. Changed versions currently queue as new-opportunity digests; meaningful amendment comparison/type-specific messaging remains P3. Actions cache loss can still lose delivery state; SMTP's accepted-then-crashed window can cause a duplicate retry. |

## Phase 1 — Evaluation baseline

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P1.1 Golden tender matching dataset | Complete | `test/golden-tender-dataset`; [PR #10](https://github.com/ayushcodes13/tendermatch/pull/10) | Dataset integrity test: 1 passed; independent review findings fixed and rechecked; merged as `f7aa1e8`. 16 synthetic pairs cover required adversarial categories; zero human-reviewed cases. | Human-reviewed labels and source provenance are still needed before ground-truth evaluation. |
| P1.2 Measurable matching evaluation | Implemented; synthetic baseline recorded | `feat/matching-evaluation-metrics`; [PR #11](https://github.com/ayushcodes13/tendermatch/pull/11) | Focused metric/dataset plus outbox/pipeline subset: 18 passed; compileall and `git diff --check` passed. Merged as `08c7391`. Baseline details are documented in `docs/evaluation-dataset.md`. | Zero human-reviewed labels and no exhaustive per-tender judgments; do not treat synthetic metrics as ground truth or production accuracy. |
| P1.3 Adversarial/regression suite and PR CI | Complete | `test/matching-adversarial-ci`; [PR #12](https://github.com/ayushcodes13/tendermatch/pull/12) | Deterministic suite: 12 passed; full suite: 61 passed with one LibreSSL warning. GitHub Actions `deterministic-tests` succeeded. Merged as `5cfa61d`. | Human-reviewed relevance labels remain outstanding under P1.1/P1.2. |

## Phase 2 — Manufacturer matching

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P2.1 Manufacturer capability schema and validation | Complete | `feat/manufacturer-profile-validation`; [PR #13](https://github.com/ayushcodes13/tendermatch/pull/13) | 18 focused tests passed; full suite: 67 passed with one LibreSSL warning. GitHub Actions deterministic tests succeeded. Validator reports 0 errors and 42 provenance/version/date warnings across 14 profiles. Merged as `e53fe6b`. | Source-backed claims, profile versions, and update dates remain unrecorded; warnings are intentional until evidence is supplied. |
| P2.2 Separate high-recall candidate generation from ranking | Complete | `feat/separate-candidate-generation`; [PR #14](https://github.com/ayushcodes13/tendermatch/pull/14) | 12 focused tests; full suite 68 passed with one LibreSSL warning. Pre/post-refactor rankings and synthetic diagnostic metrics identical for all 15 evaluation tenders. GitHub Actions passed; merged as `90e891d`. | Small-catalog full-pool retrieval is intentional. |
| P2.3 Domain compatibility and negative matching | Complete | `feat/contextual-domain-compatibility`; [PR #15](https://github.com/ayushcodes13/tendermatch/pull/15) | Focused suite: 21 passed; full suite: 77 passed with one LibreSSL warning. GitHub Actions passed. Merged as `25c6989`. | Rules are contextual string patterns and require human review; no manufacturer eligibility or technical compliance is established. |
| P2.4 Explainable scoring and threshold calibration | Complete | [PR #16](https://github.com/ayushcodes13/tendermatch/pull/16), [PR #17](https://github.com/ayushcodes13/tendermatch/pull/17), [PR #18](https://github.com/ayushcodes13/tendermatch/pull/18) | PR #16 merged as `a632361`; PR #17 as `713d227`; PR #18 as `0f92d4e`. PR #18 passed 43 focused tests, 92 full-suite tests (one LibreSSL warning), `compileall`, JSON parsing, and diff checks; CI `deterministic-tests` succeeded. Synthetic results retain 7/7 explicitly judged positives in both scenarios; unjudged displayed candidates are counted separately (36 and 37). | Dataset has zero human-reviewed labels and incomplete judgments. Results do not establish production precision, recall, or calibration. |

## Phase 3 — Tender lifecycle

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P3.1 Stable identity and version fingerprints | In progress | [PR #19](https://github.com/ayushcodes13/tendermatch/pull/19) merged as `9992849`; follow-up `fix/institution-source-identity` | Version history passed 22 focused and 95 full-suite tests. Follow-up removes the generic institution scraper's process-randomized Python hash identity; focused suite: 15 passed, full suite: 96 passed with one LibreSSL warning. | Migration seeds current persisted content; older overwritten versions are unavailable. Identity stability still depends on IDs/URLs supplied by individual sources. |
| P3.2 Meaningful amendment detection and history | Deferred pending P3.1 identity follow-up | — | Initial implementation and its 33 focused/106 full-suite test results are preserved in the local stash `wip meaningful tender amendment comparison`; it is not yet based on the corrected identity state. | Resume on a fresh branch from updated `main` after the identity follow-up merges. |
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

P3.1: merge the generic institution source-identity correction. Then restore P3.2 on a new branch from updated `main` and rerun its validation.
