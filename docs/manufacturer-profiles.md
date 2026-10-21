# Manufacturer profiles

Profiles are stored in `data/manufacturers.json`. The structural contract is in `data/manufacturer-profile.schema.json`; run its standard-library semantic validator with:

```bash
python -m matching.profile_validation
```

The validator checks required identity and matching fields, types, non-empty values, duplicate IDs and names, repeated values within a list, exact positive/negative keyword conflicts, absolute HTTP(S) URLs, and optional metadata formats. Errors return a non-zero exit status. Warnings are visible but do not prevent use of existing profiles.

Optional fields include `aliases`, `exclusions`, `supported_services`, `source_links`, `profile_version`, and `profile_last_updated`. A profile's `website` identifies the organization; it does not establish that every product or capability claim has been verified. `source_links` are profile-level evidence pointers, not a claim-by-claim mapping. A linked page supports only the product or category details visible on that page; other profile claims remain unverified until mapped and reviewed.

Current audit (2026-10-22): 14 profiles have no structural validation errors. Twelve profiles now include selected official product pages, a repository-maintained version (`1.0`), and a review date. Two profiles (P.G. Instruments Ltd. and Spinflex Instruments Ltd.) still lack source links, version, and review date; the validator reports six warnings. Research for P.G. Instruments' and Spinflex's official product pages was inconclusive, so no substitute capability claims or source links were added. The validator does not access the network or judge the truth/completeness of profile claims. Shared terminology across different manufacturers is allowed because product offerings can overlap.

The recorded `1.0` version is TenderMatch's first provenance review marker, not a manufacturer-controlled catalog version. Existing `products`, `industries_served`, and `embedding_text` were not rewritten by that review; unless a listed claim is directly supported by a linked page, continue to treat it as unverified.
