# Manufacturer profiles

Profiles are stored in `data/manufacturers.json`. The structural contract is in `data/manufacturer-profile.schema.json`; run its standard-library semantic validator with:

```bash
python -m matching.profile_validation
```

The validator checks required identity, matching, and profile-provenance fields, types, non-empty values, duplicate IDs and names, repeated values within a list, aliases that collide across manufacturers, exact positive/negative keyword or exclusion conflicts, absolute HTTP(S) URLs, and metadata formats. Errors return a non-zero exit status. Warnings are visible but do not prevent use of existing profiles.

Optional fields include `aliases`, `exclusions`, `supported_services`, and `profile_warnings`. Every profile must include at least one HTTP(S) `source_links` entry, a TenderMatch-maintained `profile_version`, and a repository review date in `profile_last_updated`. A profile's `website` identifies the organization; it does not establish that every product or capability claim has been verified. `source_links` are profile-level evidence pointers, not a claim-by-claim mapping. A linked page supports only the product or category details visible on that page; other profile claims remain unverified until mapped and reviewed.

Current audit (2026-10-22): 14 profiles have no structural validation errors. All 14 include selected official product/application pages, a repository-maintained profile version, and a review date. The validator requires these fields but does not access the network or judge the truth/completeness of profile claims. P.G. Instruments' product range and application sectors were aligned to its official product and industries pages. Official Spinflex pages showed its prior NMR profile did not match its EPR/ESR product range; that profile was corrected and its repository version advanced to `1.1`. Nippon Instruments' current catalog is specifically mercury analyzers and monitors, so its prior generic trace-metal and atomic-absorption profile wording was narrowed to the documented mercury domain and its version advanced to `1.1`. These sources support the listed product families and stated application areas, but do not verify every claim, configuration, service, or eligibility detail. Shared terminology across different manufacturers is allowed because product offerings can overlap.

`profile_version` is a TenderMatch-maintained revision, not a manufacturer-controlled catalog version; it advances when a profile receives a substantive correction. `profile_last_updated` records the repository's review date, not the manufacturer's catalog date. Source links remain profile-level pointers, so any capability claim not directly supported by a linked page remains unverified.

## Nordiko N1500 substrate capacity

The official [Nordiko N1500 page](https://nordiko-tech.co.uk/nordiko-n1500) identifies the N1500-600 as a cold-wall, RF-excited PECVD reactor and says it accepts substrates up to 500 mm in diameter. The profile names that model and records the documented substrate limit explicitly so the model suffix is not mistaken for a 600 mm substrate rating. This clarification affects a ranking input; a paired matcher run was not available in the current local environment because `sentence_transformers` is not installed and the package installation attempt timed out. The deterministic profile regression test checks the source URL and capacity wording, but does not measure ranking effects.

## TheSix TIC-95 conductivity product scope

The official [TIC-95 product page](https://thesixtech.com/products/ionic-conductivity-cell) describes one Ionic Conductivity Cell for membrane testing, including membrane conductivity and resistance measurements. The profile now names that specific cell rather than a generic plural family of conductivity measurement systems. The revised product text affects ranking inputs; a paired matcher run was not available because `sentence_transformers` is missing locally. Historical evaluation reports retain their original run hashes and rankings and are marked as historical for the new profile fingerprint.

## Claim-level provenance and validation

In addition to profile-level metadata, claim-level provenance is tracked in `data/manufacturer_claims.json` under the schema `data/claim-provenance.schema.json`. Run the claim validator with:

```bash
python -m matching.claim_provenance
```

Each claim record tracks:
- **`claim_id`**: Deterministic uppercase identifier (e.g. `KORVUS-PVD-001`).
- **`manufacturer_id`**: Foreign key to `data/manufacturers.json`.
- **`claim_type`**: `product`, `capability`, `industry`, `service`, or `configuration`.
- **`claim_text`**: Exact description of the claimed capability.
- **`source_url`**: Direct official URL from the profile's verified `source_links`.
- **`source_locator`**: Specific heading, section, or page.
- **`supporting_quote`**: Verbatim quote from official documentation.
- **`validation_state`**: One of:
  - `validated_capability`: Direct official documentation substantiating the capability.
  - `product_specific`: Capability supported only for a specific model or configuration (e.g. Agilis GOX300 wafer carrier).
  - `conditional_service`: Service offered conditionally (e.g. customer training with active warranty).
  - `region_specific`: Service or distributorship restricted to specific territories.
  - `historical`: Capability documented historically but not verified current.
  - `unverified`: Asserted claim lacking direct official source citation.
  - `unsupported`: Capability contradicted or unsubstantiated by official sources.
- **`known_limitations`**: Explicit operational boundaries (e.g. maximum substrate size, required consumables).

In the matching engine, candidates whose evidence relies on `conditional_service` or `unverified` claims produce human-readable warnings under `claim_warnings`. Candidates with `unsupported` claim conflicts are automatically routed to `agent_review` (`UNSUPPORTED_MANUFACTURER_CLAIM_CONFLICT`) in `matching/decision.py`, preventing unverified claims from inflating automated recommendations into `high_signal` opportunities.

