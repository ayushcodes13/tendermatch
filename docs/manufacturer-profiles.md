# Manufacturer profiles

Profiles are stored in `data/manufacturers.json`. The structural contract is in `data/manufacturer-profile.schema.json`; run its standard-library semantic validator with:

```bash
python -m matching.profile_validation
```

The validator checks required identity and matching fields, types, non-empty values, duplicate IDs and names, repeated values within a list, exact positive/negative keyword conflicts, absolute HTTP(S) URLs, and optional metadata formats. Errors return a non-zero exit status. Warnings are visible but do not prevent use of existing profiles.

Optional fields include `aliases`, `exclusions`, `supported_services`, `source_links`, `profile_version`, and `profile_last_updated`. A profile's `website` identifies the organization; it does not establish that every product or capability claim has been verified. `source_links` should point to evidence supporting the profile claims. Do not populate them or mark claims verified without checking the source.

Current audit: 14 profiles have no structural validation errors. They produce 42 warnings: each currently lacks claim-level source links, a profile version, and an update date. The validator does not access the network, judge product claims, or invent missing manufacturer capabilities. Shared terminology across different manufacturers is allowed because product offerings can overlap.
