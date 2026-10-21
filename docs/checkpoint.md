# TenderMatch implementation checkpoint

Update this file through the same focused PR as each implementation where practical. A task is complete only after its implementation is verified and its PR is merged.

## Current repository state

- Current base: `main` at `cc4e236` after merged P0.3 PR #5; the P0.4 branch starts directly from this commit.
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
| P0.4 Database identity, deduplication, transactions | Implemented; pending PR | `fix/tender-database-deduplication`; PR pending | Focused suite: 37 passed; independent review found no confirmed defects; compile and diff checks passed. In an isolated environment, full suite: 39 passed, 1 failed because an existing test stubs SentenceTransformer as `object`; default runtime collection is also blocked by missing `bs4`. | No production SQLite file was available to validate migration on customer data. Cross-portal duplicates without shared official IDs or source URLs remain unresolved; IISc document-link stability needs monitoring. |
| P0.5 Scheduled execution and persistence | Not started | — | — | Deployment/cost/credential choices need review before deployment. |
| P0.6 Recoverable email delivery | Not started | — | — | Design and test crash recovery and SMTP ambiguity. |

## Phase 1 — Evaluation baseline

| Task | Status | Branch / PR | Verification and merge | Remaining blocker |
| --- | --- | --- | --- | --- |
| P1.1 Golden tender matching dataset | Not started | — | — | Human-reviewed labels and provenance. |
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

P0.4: create and merge its focused PR when repository requirements are satisfied, then verify `main`; next implement P0.5 scheduled execution and persistence.
