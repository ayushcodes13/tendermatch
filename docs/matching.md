# Manufacturer matching stages

The matcher now exposes candidate generation and ranking as separate operations in `matching/matcher.py`:

1. `generate_candidates(tender)` embeds the tender and computes manufacturer-specific lexical evidence, including keywords, products, categories, aliases, concepts, service terms, and negative terms.
2. The current catalog has 14 profiles, so candidate generation retains the full catalog for ranking. It does not apply a semantic threshold or discard a candidate because of one negative phrase. The candidate pool contains the raw semantic score and structured evidence for each profile.
3. `rank_candidates(candidate_pool, top_k=...)` applies the existing evidence boosts and negative penalties, then sorts the pool. `match_topk` remains the compatibility entry point and composes both stages.

Keeping the full small catalog preserves recall at candidate generation and makes its output inspectable. It does not establish that the final top-k ranking has good precision or technical compatibility. Scores remain heuristic, and tenders may require human review. Eligibility, conflicting specifications, context-aware domain exclusions, and calibrated thresholds remain later roadmap work.

`classify_tender` returns a structured `explanation` and includes the same object in its decision trace. It separates embedding similarity, product/category/alias agreement, technical concepts, service and negative evidence, decision reasons, and the overall heuristic score. It explicitly marks source quality as `not_assessed` and lists eligibility, specification compliance, availability, and delivery as unverified. Manufacturer source links are passed through only when the profile records them; the current catalog has none. No score is represented as a probability.

The synthetic baseline in `data/evaluation/baseline_synthetic_2026-10-22.json` records the earlier combined matcher behavior and remains a historical pre-refactor diagnostic. A controlled rerun produced identical rankings for all 15 synthetic tenders, with unchanged synthetic diagnostic metrics. This confirms behavior preservation, not a matching quality improvement. The deterministic matcher tests verify that lexical candidates remain in the generated pool even when their semantic score is low, inactive profiles are skipped, and the ranking stage limits only the returned top-k list.
