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


def test_current_profiles_match_contract_without_missing_provenance_warnings():
    profiles = load_profiles()

    issues = validate_profiles(profiles)

    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    assert len(profiles) == 14
    assert errors == []
    assert warnings == []


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


def test_pg_instruments_profile_has_official_product_and_application_sources():
    profile = next(p for p in load_profiles() if p["id"] == "pg_instruments")

    assert "https://www.pginstruments.com/products/" in profile["source_links"]
    assert "https://www.pginstruments.com/industries/" in profile["source_links"]
    assert "ICP-OES spectrometers" in profile["product_categories"]
    assert "atomic fluorescence spectrometers" in profile["products"]
    assert "food and beverage quality control and monitoring" in profile["industries_served"]


def test_nippon_profile_sources_and_capabilities_are_specific_to_mercury_analysis():
    profile = next(p for p in load_profiles() if p["id"] == "nippon_instruments")

    assert "https://www.hg-nic.com/products/" in profile["source_links"]
    assert "https://www.hg-nic.com/industries-application/" in profile["source_links"]
    assert "MA Series direct mercury analyzers" in profile["products"]
    assert "atomic absorption systems" not in profile["product_categories"]
    assert "trace metal analyzers" not in profile["product_categories"]
    assert profile["profile_version"] == "1.1"


def test_teer_profile_does_not_claim_nordiko_products():
    profiles = load_profiles()
    teer = next(profile for profile in profiles if profile["id"] == "teer_coatings")
    nordiko = next(profile for profile in profiles if profile["id"] == "nordiko")

    assert "https://www.teercoatings.co.uk/clusterbeam" in teer["source_links"]
    assert "Mnem-iX Broad Ion Beam System" in nordiko["products"]
    assert "N300 Laboratory Scale Sputtering System" in nordiko["products"]
    assert not any("Mnem-iX" in product or "N300" in product for product in teer["products"])
    assert "plasma assisted CVD systems" not in teer["product_categories"]
    assert "https://www.teercoatings.co.uk/pvd" in teer["source_links"]
    assert teer["profile_version"] == "1.2"


def test_staton_profile_does_not_list_tool_reconditioning_as_equipment():
    profile = next(p for p in load_profiles() if p["id"] == "staton")

    assert "tool sharpening and regrinding equipment" not in profile["product_categories"]
    assert "https://statoncoating.com/research/" in profile["source_links"]
    assert profile["profile_version"] == "1.1"


def test_genicore_toll_sintering_is_a_service_not_a_product():
    profile = next(p for p in load_profiles() if p["id"] == "genicore")

    assert "Toll Sintering Services" not in profile["products"]
    assert "Toll Sintering Services" in profile["service_keywords"]
    assert "https://genicore.eu/products/services/" in profile["source_links"]
    assert profile["profile_version"] == "1.1"


def test_korvus_profile_links_named_deposition_sources():
    profile = next(p for p in load_profiles() if p["id"] == "korvus_technology")

    assert {
        "https://korvustech.com/highly-modular-pvd-system/",
        "https://korvustech.com/magnetron-sputtering-system/",
        "https://korvustech.com/organic-thermal-evaporation/",
        "https://korvustech.com/thermal-deposition/",
        "https://korvustech.com/wp-content/uploads/2025/01/Korvus-2pp-TAU.pdf",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.1"


def test_nordiko_profile_links_official_model_and_process_sources():
    profile = next(p for p in load_profiles() if p["id"] == "nordiko")

    assert {
        "https://nordiko-tech.co.uk/nordiko-mnem-ix-broad-ion-beam-system",
        "https://nordiko-tech.co.uk/nordiko-3000",
        "https://nordiko-tech.co.uk/nordiko-i-octave",
        "https://nordiko-tech.co.uk/nordiko-3400-broad-ion-beam-deposition-system",
        "https://nordiko-tech.co.uk/nordiko-5000-configurable-module",
        "https://nordiko-tech.co.uk/nordiko-9000-9550-series",
        "https://nordiko-tech.co.uk/nordiko-n1500",
        "https://nordiko-tech.co.uk/ion-beam-technology",
        "https://nordiko-tech.co.uk/sputtering-technology",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.2"


def test_nordiko_n1500_is_classified_as_pecvd_not_sputtering():
    profile = next(p for p in load_profiles() if p["id"] == "nordiko")

    assert "N1500-600 Large-area PECVD reactor" in profile["products"]
    assert "N1500 Sputtering System" not in profile["products"]
    assert "plasma-enhanced chemical vapour deposition systems" in profile["product_categories"]
    assert profile["profile_version"] == "1.2"


def test_agnitron_profile_links_official_products_software_and_service_sources():
    profile = next(p for p in load_profiles() if p["id"] == "agnitron")

    assert {
        "https://agnitron.com/products/",
        "https://agnitron.com/products/control-software/",
        "https://agnitron.com/services-and-support/",
        "https://agnitron.com/products/mocvd/agilis-100/",
        "https://agnitron.com/products/mocvd/agilis-500/",
        "https://agnitron.com/products/mocvd/agilis-700/",
        "https://agnitron.com/products/mocvd/agilis-series-300/",
        "https://agnitron.com/products/mocvd/a-series/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.2"


def test_agnitron_legacy_mocvd_upgrades_are_classified_as_services():
    profile = next(p for p in load_profiles() if p["id"] == "agnitron")

    assert "Legacy MOCVD system upgrades" not in profile["products"]
    assert "legacy MOCVD system upgrades" in profile["service_keywords"]


def test_parteq_profile_links_official_synthesis_instrumentation_and_service_sources():
    profile = next(p for p in load_profiles() if p["id"] == "parteq")

    assert {
        "https://parteq.net/en/products/nanopowder-synthesis/",
        "https://parteq.net/en/products/aerosolmesstechnik/",
        "https://parteq.net/en/products/aerosolmesstechnik/nanoparticle-measurement-systems/",
        "https://parteq.net/en/services-in-aerosol-technology/forschungsdienstleistungen.html",
        "https://parteq.net/en/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.1"


def test_thesix_profile_links_fuel_cell_and_electrolyzer_test_sources():
    profile = next(p for p in load_profiles() if p["id"] == "thesix_solutions")

    assert {
        "https://thesixtech.com/collections/fuel-cell-testing-hardware",
        "https://thesixtech.com/products/ionic-conductivity-cell",
        "https://thesixtech.com/collections/fuel-cell-production-units",
        "https://thesixtech.com/products/electrolyzer-test-cell",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.1"


def test_sald_profile_links_official_technology_and_market_sources():
    profile = next(p for p in load_profiles() if p["id"] == "sald")

    assert {
        "https://spatialald.com/technology/atomic-layer-deposition/",
        "https://spatialald.com/markets/battery-technology/",
        "https://spatialald.com/markets/solar-energy/",
        "https://spatialald.com/markets/green-hydrogen/",
        "https://spatialald.com/markets/barriers-and-packaging/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.2"


def test_sald_industries_do_not_overclaim_textiles_or_medical_packaging():
    profile = next(p for p in load_profiles() if p["id"] == "sald")

    assert "textiles and medical packaging" not in profile["industries_served"]
    assert "sustainable packaging and barrier films" in profile["industries_served"]
    assert "membranes and porous materials" in profile["industries_served"]


def test_on_nano_profile_links_official_products_and_subsystems():
    profile = next(p for p in load_profiles() if p["id"] == "on_nano")

    assert {
        "https://on-nano.com/products/",
        "https://on-nano.com/sub-systems/",
        "https://on-nano.com/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.1"


def test_adnanotek_profile_links_official_deposition_quantum_and_etching_sources():
    profile = next(p for p in load_profiles() if p["id"] == "adnanotek")

    assert {
        "https://adnano-tek.com/quantum-computing-deposition-system/",
        "https://adnano-tek.com/quantum-computing-deposition-system/jeb-2/",
        "https://adnano-tek.com/quantum-computing-deposition-system/jeb-3/",
        "https://adnano-tek.com/ion-beam-etching/",
        "https://adnano-tek.com/ion-beam-sputter-deposition/",
        "https://adnano-tek.com/plasma-system/",
        "https://adnano-tek.com/thermo-evaporator-system/",
        "https://adnano-tek.com/molecular-beam-epitaxy-mbe/",
        "https://adnano-tek.com/pulsed-laser-deposition-pld/",
        "https://adnano-tek.com/magnetron-sputtering-systems/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.2"


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
    assert "Validated 14 profiles: 0 errors, 0 warnings" in output
