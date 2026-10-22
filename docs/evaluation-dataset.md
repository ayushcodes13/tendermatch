# TenderMatch matching evaluation data

`data/evaluation/golden_tender_cases.json` is a versioned regression dataset for tender/manufacturer pairs. Its 18 current examples are synthetic and intentionally adversarial. They cover domain confusion, generic descriptions, service-only work, acronyms and aliases, conflicting requirements, negative terms, overlapping manufacturers, amendments, and missing capability evidence.

## Label meaning

- `relevant`: profile and tender evidence directly support a product-family fit.
- `potentially_relevant_needs_review`: a plausible fit exists, but a material issue needs a person to check.
- `not_relevant`: the request belongs to a different equipment or service domain.
- `insufficient_information`: current information cannot support a relevance decision.

Labels describe the authored synthetic scenario, not eligibility, product certification, or a probability that a manufacturer can win. A single tender can be relevant to more than one manufacturer; labels are per tender/manufacturer pair.

## Provenance and use

Every case records whether it is synthetic or human reviewed, a case-specific rationale, technical evidence, known exclusions, and provenance. The current dataset has zero human-reviewed cases. Synthetic examples can support deterministic regression tests and expose failure patterns, but they must not be reported as ground truth or used to claim production accuracy.

Before reporting evaluation metrics, add a separately identified set of human-reviewed cases with reviewer and source provenance, preserve disputed labels for adjudication, and report synthetic and human-reviewed results separately. Do not convert a synthetic case to human-reviewed without recording the review provenance and date.

## Evaluation runner

The evaluator in matching/evaluation.py reports candidate recall over labeled positive pairs, precision over retrieved definitive judgments, review/insufficient-information rate, unjudged candidate count, false-positive case IDs, per-manufacturer results, latency, and cost availability. It never treats an unlabeled candidate as a negative. Matcher scores are retained as heuristic ranking signals and are not calibrated probabilities.

Run the current candidate generator with the installed SentenceTransformer dependency and model available using:

    python -m matching.evaluation --dataset data/evaluation/golden_tender_cases.json

## Current synthetic diagnostic

The current Teer Coatings scope review is preserved in `data/evaluation/baseline_synthetic_teer_semiconductor_industry_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_teer_semiconductor_industry_2026-10-22.json`. Teer’s PVD overview describes deposition onto semiconductor wafers as a general PVD example, but the reviewed official material did not establish semiconductor systems or semiconductor deployments as a Teer industry capability. The profile therefore removes `semiconductor coating systems` from `industries_served`. Its matched 18-case synthetic run leaves labeled metrics and all top-five rankings unchanged. This supports a narrower claim; it does not demonstrate matching-quality improvement.

The Korvus Technology service-scope pair is preserved in `data/evaluation/baseline_synthetic_korvus_service_scope_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_korvus_service_scope_2026-10-22.json`. The official teaching-and-training page describes thin-film training and customer support; the profile no longer uses generic installation, maintenance, servicing, or system-upgrade terms. Its upgrade webinar describes upgrade compatibility but does not establish an offered service. In the matched 18-case synthetic run, all 8 labeled positives remain retrieved; 11 top-five orderings change, and one labeled false positive drops out. Labeled precision changes from 8/11 to 8/10, with one fewer false-positive case and one additional unjudged candidate. These are synthetic labels and do not establish production quality or ground truth.

The latest Nippon Instruments service-scope review is preserved in `data/evaluation/baseline_synthetic_nippon_service_evidence_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_nippon_service_evidence_2026-10-22.json`. The official About page describes analyzer servicing, technical support and advice, measurement services, training, demonstrations, and application development. NIC’s support notice cautions that repair and maintenance may become extremely difficult for discontinued models when parts and consumables are unavailable. The paired run leaves labeled metrics unchanged (8/8 positives retrieved; 8/11 definitively labeled retrieved pairs relevant) and changes five unjudged top-five rankings. None of these examples is a human-reviewed Nippon service judgment.

The repository retains historical profile snapshots in `data/evaluation/`. The latest ON NANO service-scope review has matched before-and-after runs in `data/evaluation/baseline_synthetic_onnano_service_evidence_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_onnano_service_evidence_2026-10-22.json`. Both use the same 18-case synthetic dataset, matcher code, model revision, and top-five setting; only the profile snapshot differs. ON NANO's 2025 official terms support installation, assembly, commissioning and instruction by ON Nano personnel when those services are included in the customer order. They also describe defect remediation, replacement delivery, service parts, and deployment of a service technician. The paired diagnostic changes two unjudged top-five rankings (`SYN-CORRIGENDUM-013` and `SYN-OVERLAP-CONCEPT-015`), while labeled aggregate metrics remain unchanged: 8/8 positives retrieved, 8/11 definitively labeled retrieved pairs relevant, and 68 candidates unjudged. There are zero human-reviewed labels, so the ranking changes do not establish a quality improvement.

The previous AdNaNoTek service review is retained in `data/evaluation/baseline_synthetic_adnanotek_service_evidence_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_adnanotek_service_evidence_2026-10-22.json`. AdNaNoTek remains at rank 5 on the synthetic annual-maintenance case with its exact maintenance support still unverified. Historical metadata records the current ON NANO fingerprint refresh without changing its original report hashes or rankings.

The previous SALD service review is retained in `data/evaluation/baseline_synthetic_sald_service_evidence_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_sald_service_evidence_2026-10-22.json`. It preserved all top-five rankings and labeled metrics. Historical metadata records the later AdNaNoTek fingerprint refresh without changing SALD's original ranking snapshot or run hashes.

The prior SALD deposition-head pair is preserved in `data/evaluation/baseline_synthetic_sald_head_scope_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_sald_head_scope_2026-10-22.json`. It reclassifies patented deposition-head technology as a feature of the R&D system and retains an exact lexical cue; its paired run also left top-five rankings and metrics unchanged.

The GeniCore CUBNEC pair is preserved in `data/evaluation/baseline_synthetic_genicore_cubnec_name_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_genicore_cubnec_name_2026-10-22.json`. It corrects the expansion to “Cubic Boron Nitride Enhanced Cemented Carbide” and adds exact lexical terms; it left all rankings and synthetic metrics unchanged.

The ON NANO paired run is preserved in `data/evaluation/baseline_synthetic_on_nano_glass_panel_scope_before_2026-10-22.json` and `data/evaluation/baseline_synthetic_on_nano_glass_panel_scope_2026-10-22.json`. It changed one unjudged top-five candidate on `SYN-VACUUM-CLEANER-010`; the case is judged only against Korvus, so no false-positive reduction is established.

These remain synthetic diagnostics, not ground truth or production-accuracy estimates. There are zero human-reviewed examples and no tender is exhaustively labeled across the active catalog, so precision@K and recall@K remain null. Do not interpret unchanged labeled-pair metrics as a quality improvement.

The latest Thesix profile run records a median candidate-generation latency of 14.0 ms and a mean of 14.6 ms over 17 unique synthetic tenders after model loading, using Python 3.12.13, Sentence Transformers 6.2.0, Torch 2.14.1, and model revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`. This local timing is not a service-level measurement. Cost, model-load time, portal time, SMTP time, and full pipeline latency are not measured.

Run the dataset integrity checks with:

```bash
python -m pytest -q tests/test_matching_dataset.py
```
