"""Validate manufacturer profile structure without inferring capabilities.

Optional provenance and version fields are checked when present. Their absence
is reported as a warning so existing profiles remain usable while claims await
source-backed review.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "data" / "manufacturers.json"

REQUIRED_STRINGS = ("id", "name", "country", "website", "embedding_text")
REQUIRED_LISTS = (
    "products",
    "product_categories",
    "industries_served",
    "keywords",
    "concepts",
    "negative_keywords",
    "service_keywords",
)
OPTIONAL_LISTS = ("aliases", "source_links", "exclusions", "supported_services")
POSITIVE_LISTS = (
    "products",
    "product_categories",
    "industries_served",
    "keywords",
    "concepts",
    "aliases",
    "service_keywords",
    "supported_services",
)
VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _issue(severity, code, path, message):
    return {"severity": severity, "code": code, "path": path, "message": message}


def _valid_http_url(value):
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_profiles(profiles):
    """Return structured errors and warnings for a manufacturer profile list."""
    issues = []
    if not isinstance(profiles, list):
        return [_issue("error", "profiles_type", "$", "Expected a JSON array of manufacturer profiles.")]
    if not profiles:
        return [_issue("error", "profiles_empty", "$", "At least one manufacturer profile is required.")]

    seen_ids = {}
    seen_names = {}
    for index, profile in enumerate(profiles):
        base = f"$[{index}]"
        if not isinstance(profile, dict):
            issues.append(_issue("error", "profile_type", base, "Expected an object."))
            continue

        for field in REQUIRED_STRINGS:
            value = profile.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(_issue("error", "required_string", f"{base}.{field}", "Expected a non-empty string."))

        if not isinstance(profile.get("active"), bool):
            issues.append(_issue("error", "active_type", f"{base}.active", "Expected a boolean."))

        profile_id = profile.get("id")
        if isinstance(profile_id, str) and profile_id.strip():
            normalized_id = profile_id.strip().casefold()
            if normalized_id in seen_ids:
                issues.append(_issue("error", "duplicate_id", f"{base}.id", f"Duplicates profile at index {seen_ids[normalized_id]}."))
            else:
                seen_ids[normalized_id] = index

        name = profile.get("name")
        if isinstance(name, str) and name.strip():
            normalized_name = name.strip().casefold()
            if normalized_name in seen_names:
                issues.append(_issue("error", "duplicate_name", f"{base}.name", f"Duplicates profile at index {seen_names[normalized_name]}."))
            else:
                seen_names[normalized_name] = index

        website = profile.get("website")
        if isinstance(website, str) and website.strip() and not _valid_http_url(website.strip()):
            issues.append(_issue("error", "invalid_website", f"{base}.website", "Expected an absolute HTTP(S) URL."))

        for field in REQUIRED_LISTS + OPTIONAL_LISTS:
            if field not in profile and field in OPTIONAL_LISTS:
                continue
            values = profile.get(field)
            if not isinstance(values, list):
                issues.append(_issue("error", "list_type", f"{base}.{field}", "Expected an array of non-empty strings."))
                continue
            normalized = []
            for term_index, value in enumerate(values):
                term_path = f"{base}.{field}[{term_index}]"
                if not isinstance(value, str) or not value.strip():
                    issues.append(_issue("error", "list_item_type", term_path, "Expected a non-empty string."))
                    continue
                normalized.append(value.strip().casefold())
            if len(set(normalized)) != len(normalized):
                issues.append(_issue("error", "duplicate_term", f"{base}.{field}", "Contains repeated values after case and whitespace normalization."))

        negatives = profile.get("negative_keywords", [])
        if isinstance(negatives, list):
            positive_terms = set()
            for field in POSITIVE_LISTS:
                values = profile.get(field, [])
                if isinstance(values, list):
                    positive_terms.update(
                        value.strip().casefold()
                        for value in values
                        if isinstance(value, str) and value.strip()
                    )
            for neg_index, value in enumerate(negatives):
                if isinstance(value, str) and value.strip() and value.strip().casefold() in positive_terms:
                    issues.append(_issue(
                        "error", "positive_negative_conflict", f"{base}.negative_keywords[{neg_index}]",
                        "The same normalized term appears in a positive capability or service field.",
                    ))

        source_links = profile.get("source_links")
        if source_links is None or source_links == []:
            issues.append(_issue("warning", "missing_source_links", f"{base}.source_links", "No claim-level source links are recorded; profile claims remain unverified."))
        elif isinstance(source_links, list):
            for source_index, source in enumerate(source_links):
                if not isinstance(source, str) or not source.strip() or not _valid_http_url(source.strip()):
                    issues.append(_issue("error", "invalid_source_link", f"{base}.source_links[{source_index}]", "Expected an absolute HTTP(S) URL."))

        version = profile.get("profile_version")
        if version is None:
            issues.append(_issue("warning", "missing_profile_version", f"{base}.profile_version", "No profile version is recorded."))
        elif not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            issues.append(_issue("error", "invalid_profile_version", f"{base}.profile_version", "Expected a version such as 1 or 1.2.0."))

        updated = profile.get("profile_last_updated")
        if updated is None:
            issues.append(_issue("warning", "missing_profile_last_updated", f"{base}.profile_last_updated", "No profile update date is recorded."))
        elif not isinstance(updated, str) or not DATE_PATTERN.fullmatch(updated):
            issues.append(_issue("error", "invalid_profile_last_updated", f"{base}.profile_last_updated", "Expected an ISO date in YYYY-MM-DD form."))
        elif not _is_valid_iso_date(updated):
            issues.append(_issue("error", "invalid_profile_last_updated", f"{base}.profile_last_updated", "Date is not a valid calendar date."))

    return issues


def _is_valid_iso_date(value):
    from datetime import date

    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate TenderMatch manufacturer profiles")
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILE_PATH), help="Path to manufacturer JSON array")
    args = parser.parse_args(argv)
    try:
        profiles = json.loads(Path(args.profiles).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot load manufacturer profiles: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    issues = validate_profiles(profiles)
    counts = {severity: sum(issue["severity"] == severity for issue in issues) for severity in ("error", "warning")}
    for issue in issues:
        print(f"{issue['severity'].upper()} {issue['code']} {issue['path']}: {issue['message']}")
    print(f"Validated {len(profiles) if isinstance(profiles, list) else 0} profiles: {counts['error']} errors, {counts['warning']} warnings")
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
