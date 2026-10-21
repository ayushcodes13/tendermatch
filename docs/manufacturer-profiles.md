# Manufacturer profiles

Profiles are stored in `data/manufacturers.json`. The structural contract is in `data/manufacturer-profile.schema.json`; run its standard-library semantic validator with:

```bash
python -m matching.profile_validation
```

The validator checks required identity and matching fields, types, non-empty values, duplicate IDs and names, repeated values within a list, exact positive/negative keyword conflicts, absolute HTTP(S) URLs, and optional metadata formats. Errors return a non-zero exit status. Warnings are visible but do not prevent use of existing profiles.

Optional fields include `aliases`, `exclusions`, `supported_services`, `source_links`, `profile_version`, and `profile_last_updated`. A profile's `website` identifies the organization; it does not establish that every product or capability claim has been verified. `source_links` are profile-level evidence pointers, not a claim-by-claim mapping. A linked page supports only the product or category details visible on that page; other profile claims remain unverified until mapped and reviewed.

Current audit (2026-10-22): 14 profiles have no structural validation errors. Thirteen profiles include selected official product/application pages, a repository-maintained profile version, and a review date. P.G. Instruments Ltd. still lacks source links, version, and review date; the validator reports three warnings. Official Spinflex pages showed the old NMR profile did not match the manufacturer's EPR/ESR products; the profile was corrected and its repository version advanced to `1.1`. This source review supports the listed EPR/ESR product families and application areas, but does not verify every claim or configuration. The validator does not access the network or judge the truth/completeness of profile claims. Shared terminology across different manufacturers is allowed because product offerings can overlap.

`profile_version` is a TenderMatch-maintained revision, not a manufacturer-controlled catalog version; it advances when a profile receives a substantive correction. `profile_last_updated` records the repository's review date, not the manufacturer's catalog date. Source links remain profile-level pointers, so any capability claim not directly supported by a linked page remains unverified.
