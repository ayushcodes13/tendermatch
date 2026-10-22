"""Manufacturer claim-level provenance tracking and validation.

Transitions TenderMatch from profile-level source links to claim-level
traceability. Distinguishes validated capabilities, product-specific limits,
conditional services, region-specific offerings, unverified assertions,
and unsupported claims.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "data" / "manufacturers.json"
DEFAULT_CLAIMS_PATH = PROJECT_ROOT / "data" / "manufacturer_claims.json"

VALID_CLAIM_TYPES = frozenset({
    "product",
    "capability",
    "industry",
    "service",
    "configuration",
})

VALID_VALIDATION_STATES = frozenset({
    "validated_capability",
    "product_specific",
    "historical",
    "region_specific",
    "conditional_service",
    "unverified",
    "unsupported",
})

CLAIM_ID_PATTERN = re.compile(r"^[A-Z0-9_-]+$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _issue(severity: str, code: str, path: str, message: str) -> dict:
    return {"severity": severity, "code": code, "path": path, "message": message}


def load_claims(path: Path | str | None = None) -> list[dict]:
    """Load the claim provenance registry from disk."""
    claims_path = Path(path or DEFAULT_CLAIMS_PATH)
    if not claims_path.is_file():
        return []
    with open(claims_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_claims(claims: list[dict], profiles: list[dict]) -> list[dict]:
    """Validate claim-level records against the active manufacturer catalog."""
    issues = []
    if not isinstance(claims, list):
        return [_issue("error", "claims_type", "$", "Expected a JSON array of claim records.")]

    # Build manufacturer profile lookup
    profiles_by_id = {}
    profile_sources = {}
    if isinstance(profiles, list):
        for idx, p in enumerate(profiles):
            if isinstance(p, dict) and "id" in p:
                pid = p["id"]
                profiles_by_id[pid] = p
                sources = set(p.get("source_links", []))
                website = p.get("website")
                if website:
                    sources.add(website)
                profile_sources[pid] = sources

    seen_ids = set()

    for index, claim in enumerate(claims):
        base = f"$[{index}]"
        if not isinstance(claim, dict):
            issues.append(_issue("error", "claim_type", base, "Expected an object."))
            continue

        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not CLAIM_ID_PATTERN.fullmatch(claim_id):
            issues.append(_issue(
                "error", "invalid_claim_id", f"{base}.claim_id",
                "Expected uppercase alphanumeric claim ID (e.g. KORVUS-PVD-001).",
            ))
        elif claim_id in seen_ids:
            issues.append(_issue("error", "duplicate_claim_id", f"{base}.claim_id", f"Duplicate claim ID: {claim_id}"))
        else:
            seen_ids.add(claim_id)

        m_id = claim.get("manufacturer_id")
        if not isinstance(m_id, str) or not m_id.strip():
            issues.append(_issue("error", "missing_manufacturer_id", f"{base}.manufacturer_id", "Manufacturer ID is required."))
        elif m_id not in profiles_by_id:
            issues.append(_issue("error", "unknown_manufacturer", f"{base}.manufacturer_id", f"Manufacturer '{m_id}' not found in manufacturers.json."))

        claim_type = claim.get("claim_type")
        if claim_type not in VALID_CLAIM_TYPES:
            issues.append(_issue("error", "invalid_claim_type", f"{base}.claim_type", f"Must be one of {sorted(VALID_CLAIM_TYPES)}."))

        claim_text = claim.get("claim_text")
        if not isinstance(claim_text, str) or not claim_text.strip():
            issues.append(_issue("error", "missing_claim_text", f"{base}.claim_text", "Claim text must be a non-empty string."))

        source_url = claim.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            issues.append(_issue("error", "missing_source_url", f"{base}.source_url", "Official source URL is required."))
        else:
            parsed = urlparse(source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                issues.append(_issue("error", "invalid_source_url", f"{base}.source_url", "Expected an absolute HTTP(S) URL."))
            elif m_id in profile_sources and source_url not in profile_sources[m_id]:
                issues.append(_issue(
                    "warning", "unregistered_source_url", f"{base}.source_url",
                    f"URL is not listed in profile source_links for manufacturer '{m_id}'.",
                ))

        source_locator = claim.get("source_locator")
        if not isinstance(source_locator, str) or not source_locator.strip():
            issues.append(_issue("error", "missing_source_locator", f"{base}.source_locator", "Source locator (section/page/heading) is required."))

        supporting_quote = claim.get("supporting_quote")
        if not isinstance(supporting_quote, str) or not supporting_quote.strip():
            issues.append(_issue("error", "missing_supporting_quote", f"{base}.supporting_quote", "Verbatim supporting quote is required."))

        state = claim.get("validation_state")
        if state not in VALID_VALIDATION_STATES:
            issues.append(_issue("error", "invalid_validation_state", f"{base}.validation_state", f"Must be one of {sorted(VALID_VALIDATION_STATES)}."))

        verified_date = claim.get("last_verified_date")
        if not isinstance(verified_date, str) or not DATE_PATTERN.fullmatch(verified_date):
            issues.append(_issue("error", "invalid_date", f"{base}.last_verified_date", "Expected ISO date YYYY-MM-DD."))
        else:
            try:
                date.fromisoformat(verified_date)
            except ValueError:
                issues.append(_issue("error", "invalid_calendar_date", f"{base}.last_verified_date", "Not a valid calendar date."))

        limitations = claim.get("known_limitations")
        if not isinstance(limitations, list):
            issues.append(_issue("error", "limitations_type", f"{base}.known_limitations", "Expected an array of strings."))

    return issues


def assess_candidate_claims(candidate: dict, claims: list[dict]) -> dict:
    """Assess candidate matches against substantiated claim-level provenance.

    Identifies verified vs conditional / unverified claims and emits
    decision warnings when claims require manual sales adjudication.
    """
    m_id = candidate.get("manufacturer_id")
    if not m_id:
        return {
            "claim_status": "unassessed",
            "verified_claims": [],
            "uncertain_claims": [],
            "unsupported_claims": [],
            "claim_warnings": [],
        }

    # Filter claims for this manufacturer
    m_claims = [c for c in claims if c.get("manufacturer_id") == m_id]
    if not m_claims:
        return {
            "claim_status": "unassessed",
            "verified_claims": [],
            "uncertain_claims": [],
            "unsupported_claims": [],
            "claim_warnings": [],
        }

    # Match candidate hits to claim records
    hits = set()
    for field in ("product_hits", "keyword_hits", "category_hits", "service_hits"):
        for term in candidate.get(field, []) or []:
            hits.add(str(term).strip().casefold())

    verified = []
    uncertain = []
    unsupported = []
    warnings = []

    for c in m_claims:
        claim_term = str(c.get("claim_term") or c.get("claim_text", "")).strip().casefold()
        # Check if this claim matches candidate's evidence
        is_hit = (
            claim_term in hits
            or any(term in claim_term for term in hits if len(term) >= 4)
            or any(claim_term in term for term in hits if len(claim_term) >= 4)
        )

        if not is_hit:
            continue

        state = c.get("validation_state")
        summary_record = {
            "claim_id": c.get("claim_id"),
            "claim_text": c.get("claim_text"),
            "validation_state": state,
            "source_locator": c.get("source_locator"),
            "source_url": c.get("source_url"),
            "known_limitations": c.get("known_limitations", []),
        }

        if state in {"validated_capability", "product_specific"}:
            verified.append(summary_record)
            if c.get("known_limitations"):
                for lim in c["known_limitations"]:
                    warnings.append(f"Limitation for {c['claim_id']}: {lim}")
        elif state in {"conditional_service", "region_specific", "historical", "unverified"}:
            uncertain.append(summary_record)
            warnings.append(
                f"Uncertain claim {c['claim_id']} ({state}): {c['claim_text']}. "
                f"Verify service availability and geographic authorization before pursuing."
            )
        elif state == "unsupported":
            unsupported.append(summary_record)
            warnings.append(
                f"Unsupported claim conflict {c['claim_id']}: {c['claim_text']}. "
                "Official documentation does not substantiate this capability."
            )

    if unsupported:
        status = "has_conflicts"
    elif uncertain:
        status = "partially_verified" if verified else "unverified"
    elif verified:
        status = "fully_verified"
    else:
        status = "unassessed"

    return {
        "claim_status": status,
        "verified_claims": verified,
        "uncertain_claims": uncertain,
        "unsupported_claims": unsupported,
        "claim_warnings": warnings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate TenderMatch manufacturer claim provenance")
    parser.add_argument("--claims", default=str(DEFAULT_CLAIMS_PATH), help="Path to manufacturer claims JSON")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILES_PATH), help="Path to manufacturers JSON")
    args = parser.parse_args(argv)

    try:
        claims = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error loading claims file: {exc}", file=sys.stderr)
        return 2

    try:
        profiles = json.loads(Path(args.profiles).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error loading profiles file: {exc}", file=sys.stderr)
        return 2

    issues = validate_claims(claims, profiles)
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    for issue in issues:
        print(f"[{issue['severity'].upper()}] {issue['path']}: {issue['message']}")

    print(f"\nValidated {len(claims)} claim provenance records across {len(profiles)} profiles: {len(errors)} errors, {len(warnings)} warnings.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
