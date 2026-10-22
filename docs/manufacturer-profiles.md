# Manufacturer profiles

Profiles are stored in `data/manufacturers.json`. The structural contract is in `data/manufacturer-profile.schema.json`; run its standard-library semantic validator with:

```bash
python -m matching.profile_validation
```

The validator checks required identity and matching fields, types, non-empty values, duplicate IDs and names, repeated values within a list, aliases that collide across manufacturers, exact positive/negative keyword or exclusion conflicts, absolute HTTP(S) URLs, and optional metadata formats. Errors return a non-zero exit status. Warnings are visible but do not prevent use of existing profiles.

Optional fields include `aliases`, `exclusions`, `supported_services`, `source_links`, `profile_version`, and `profile_last_updated`. A profile's `website` identifies the organization; it does not establish that every product or capability claim has been verified. `source_links` are profile-level evidence pointers, not a claim-by-claim mapping. A linked page supports only the product or category details visible on that page; other profile claims remain unverified until mapped and reviewed.

Current audit (2026-10-22): 14 profiles have no structural validation errors. All 14 include selected official product/application pages, a repository-maintained profile version, and a review date; the validator reports no missing-provenance warnings. P.G. Instruments' product range and application sectors were aligned to its official product and industries pages. Official Spinflex pages showed its prior NMR profile did not match its EPR/ESR product range; that profile was corrected and its repository version advanced to `1.1`. Nippon Instruments' current catalog is specifically mercury analyzers and monitors, so its prior generic trace-metal and atomic-absorption profile wording was narrowed to the documented mercury domain and its version advanced to `1.1`. These sources support the listed product families and stated application areas, but do not verify every claim, configuration, service, or eligibility detail. The validator does not access the network or judge the truth/completeness of profile claims. Shared terminology across different manufacturers is allowed because product offerings can overlap.

`profile_version` is a TenderMatch-maintained revision, not a manufacturer-controlled catalog version; it advances when a profile receives a substantive correction. `profile_last_updated` records the repository's review date, not the manufacturer's catalog date. Source links remain profile-level pointers, so any capability claim not directly supported by a linked page remains unverified.

## Nordiko N1500 substrate capacity

The official [Nordiko N1500 page](https://nordiko-tech.co.uk/nordiko-n1500) identifies the N1500-600 as a cold-wall, RF-excited PECVD reactor and says it accepts substrates up to 500 mm in diameter. The profile names that model and records the documented substrate limit explicitly so the model suffix is not mistaken for a 600 mm substrate rating. This clarification affects a ranking input; a paired matcher run was not available in the current local environment because `sentence_transformers` is not installed and the package installation attempt timed out. The deterministic profile regression test checks the source URL and capacity wording, but does not measure ranking effects.

## TheSix TIC-95 conductivity product scope

The official [TIC-95 product page](https://thesixtech.com/products/ionic-conductivity-cell) describes one Ionic Conductivity Cell for membrane testing, including membrane conductivity and resistance measurements. The profile now names that specific cell rather than a generic plural family of conductivity measurement systems. The revised product text affects ranking inputs; a paired matcher run was not available because `sentence_transformers` is missing locally. Historical evaluation reports retain their original run hashes and rankings and are marked as historical for the new profile fingerprint.
