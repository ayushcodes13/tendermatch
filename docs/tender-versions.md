# Tender identity and content versions

Tender identity and tender content use separate keys. `data.db.generate_hash()` produces the stable identity key used by the current tender record, manufacturer matches, and notification state. `data.db.generate_content_fingerprint()` produces a SHA-256 digest over canonicalized title, organization, publication/update/corrigendum/closing dates, and raw tender text.

Each observed content fingerprint is stored in `tender_versions` with its JSON snapshot and first/last observation timestamps. Repeated observations of the same content update `last_seen_at`; a changed fingerprint adds a version row and updates `tenders.version_fingerprint`. Version snapshots preserve the content and source provenance available in the normalized tender record.

Existing databases are migrated additively. Initialization seeds one snapshot from each existing tender's current persisted content. Older overwritten content cannot be recovered. The legacy `content_hash` remains unchanged for compatibility and is not the new content fingerprint.

Fingerprints indicate that the normalized content changed. The amendment comparison records deadline extensions/shortenings, corrigendum-date changes, and conservative text cues for technical specifications, required certifications, eligibility, quantity, and cancellation/withdrawal. Formatting-only changes are retained in version history and labeled `formatting_only`; unclassified substantive text changes are labeled `needs_review`. The text rules are heuristics and do not prove legal or technical effect. Notification behavior is unchanged by this comparison.
