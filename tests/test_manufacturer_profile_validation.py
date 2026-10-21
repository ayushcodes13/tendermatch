import copy
import json
from pathlib import Path

from matching.profile_validation import (
    OPTIONAL_LISTS,
    REQUIRED_LISTS,
    REQUIRED_STRINGS,
    main,
    validate_profiles,
)


ROOT = Path(__file__).resolve().parents[1]


def load_profiles():
    return json.loads((ROOT / "data" / "manufacturers.json").read_text(encoding="utf-8"))


def test_current_profiles_match_contract_and_only_unverified_profiles_warn():
    profiles = load_profiles()

    issues = validate_profiles(profiles)

    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    assert len(profiles) == 14
    assert errors == []
    assert len(warnings) == 6
    assert {issue["code"] for issue in warnings} == {
        "missing_source_links",
        "missing_profile_version",
        "missing_profile_last_updated",
    }
    assert {issue["path"].split(".")[0] for issue in warnings} == {"$[2]", "$[7]"}


def test_json_schema_documents_the_same_required_and_optional_fields():
    schema = json.loads(
        (ROOT / "data" / "manufacturer-profile.schema.json").read_text(encoding="utf-8")
    )

    expected_required = set(REQUIRED_STRINGS) | {"active"} | set(REQUIRED_LISTS)
    assert set(schema["required"]) == expected_required
    assert set(REQUIRED_LISTS) | set(OPTIONAL_LISTS) <= set(schema["properties"])


def test_duplicate_identity_duplicate_terms_and_positive_negative_conflicts_fail():
    profiles = load_profiles()[:1]
    duplicate = copy.deepcopy(profiles[0])
    duplicate["id"] = profiles[0]["id"]
    duplicate["name"] = "Korvus Technology"
    duplicate["products"].append(duplicate["products"][0].upper())
    duplicate["negative_keywords"].append(duplicate["products"][0])

    codes = {issue["code"] for issue in validate_profiles(profiles + [duplicate])}

    assert {"duplicate_id", "duplicate_name", "duplicate_term", "positive_negative_conflict"} <= codes


def test_metadata_and_urls_are_validated_without_being_fabricated():
    profile = load_profiles()[0]
    profile["source_links"] = ["not a URL"]
    profile["profile_version"] = "v1"
    profile["profile_last_updated"] = "2026-02-30"

    codes = {issue["code"] for issue in validate_profiles([profile])}

    assert {"invalid_source_link", "invalid_profile_version", "invalid_profile_last_updated"} <= codes
    assert "missing_source_links" not in codes
    assert "missing_profile_version" not in codes
    assert "missing_profile_last_updated" not in codes


def test_empty_source_list_does_not_hide_missing_evidence_warning():
    profile = load_profiles()[0]
    profile["source_links"] = []

    warnings = validate_profiles([profile])

    warning = next(issue for issue in warnings if issue["code"] == "missing_source_links")
    assert warning["severity"] == "warning"
    assert warning["message"] == (
        "No profile-level source links are recorded; capability claims remain unverified."
    )


def test_profile_cli_reports_warnings_but_only_fails_on_errors(capsys):
    result = main(["--profiles", str(ROOT / "data" / "manufacturers.json")])

    output = capsys.readouterr().out
    assert result == 0
    assert "Validated 14 profiles: 0 errors, 6 warnings" in output
