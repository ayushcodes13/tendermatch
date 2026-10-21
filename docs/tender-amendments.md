# Tender amendment comparison

When `upsert_or_get_tender()` observes a new content fingerprint for an existing stable tender identity, TenderMatch compares the newest prior snapshot with the new snapshot and stores a `tender_amendments` record. The record links the two version fingerprints and contains a status, change-type labels, field-level evidence, and observation timestamp. Historical `tender_versions` snapshots remain intact.

## Classification

- `meaningful`: the comparison found an explicit deadline change, corrigendum date, cancellation/withdrawal cue, or a changed text line containing a technical specification, certification, eligibility, or quantity cue.
- `needs_review`: content changed in a way the rules cannot safely categorize, a mix of categorized and uncategorized text lines changed, or auxiliary fields such as title/update metadata changed.
- `formatting_only`: the content fingerprint changed but normalized tender fields have no substantive difference (for example, whitespace/case changes or equivalent date formats).

Deadline comparisons use the shared date parser and record the old/new values. An unparseable changed deadline is called `deadline_changed`, not an extension. Text labels use only changed lines, which reduces false categorization from terms present in unchanged text. When a change includes both categorized and uncategorized lines, the combined event stays in `needs_review`. The rules can still miss or overstate meaning; they are triage signals and do not establish eligibility, legal effect, or technical compliance.

Amendment notifications use the existing SQLite outbox with a dedicated `amendment_update` type and the destination content fingerprint. Formatting-only changes are not sent. `needs_review` updates are sent with an explicit review instruction so uncertain substantive changes are not silently dropped. SMTP delivery remains at-least-once within the outbox's documented crash window.
