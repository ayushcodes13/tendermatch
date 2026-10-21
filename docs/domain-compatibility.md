# Contextual domain compatibility

`matching.signals.detect_domain_review_hits` looks for explicit co-occurrence of potentially incompatible domain or specification terms. Current review-only patterns cover:

- Medical infusion pump requirements alongside industrial water-pump requirements.
- Laboratory vacuum or deposition requirements alongside household cleaning vacuum requirements.
- Semiconductor/thin-film process requirements alongside high-voltage infrastructure work.
- A process-system request alongside a clause that prohibits its core process or vacuum requirement.

These patterns add a structured reason code and route the tender to `agent_review`, even when no current manufacturer has a strong match. They do not automatically reject it because one notice can contain multiple lots or contradictory text that needs clarification.

Ordinary context is not itself a conflict. A medical pump by itself, an industrial water pump by itself, a household vacuum cleaner by itself, or a PVD chamber by itself does not trigger these cross-domain review patterns. A new PVD purchase remains eligible for a strong signal even when a separate existing chamber has an AMC clause.

The rules are deterministic term co-occurrence checks. They do not parse document structure, identify which clause applies to which lot, prove technical incompatibility, or confirm manufacturer eligibility. Reviewers must inspect the official notice. Matching scores remain heuristic.
