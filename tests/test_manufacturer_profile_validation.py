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


def test_cross_profile_alias_collision_and_exclusion_positive_conflicts_fail():
    profiles = load_profiles()[:2]
    profiles[0]["exclusions"] = [profiles[0]["products"][0].upper()]
    profiles[1]["aliases"] = [profiles[0]["aliases"][0]]

    issues = validate_profiles(profiles)
    conflicts = [issue for issue in issues if issue["code"] in {
        "ambiguous_manufacturer_alias", "positive_negative_conflict"
    }]

    assert {issue["code"] for issue in conflicts} == {
        "ambiguous_manufacturer_alias", "positive_negative_conflict"
    }
    assert any(issue["path"] == "$[0].exclusions[0]" for issue in conflicts)
    assert any(issue["path"] == "$[1].aliases[0]" for issue in conflicts)


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


def test_korvus_profile_has_dedicated_tes_thermal_evaporation_source():
    profile = next(p for p in load_profiles() if p["id"] == "korvus_technology")

    assert "TES Thermal Boat Evaporation" in profile["products"]
    assert "https://korvustech.com/pvd-thermal-evaporation/" in profile["source_links"]
    assert profile["profile_version"] == "1.4"


def test_pg_instruments_profile_has_official_product_and_application_sources():
    profile = next(p for p in load_profiles() if p["id"] == "pg_instruments")

    assert "https://www.pginstruments.com/products/" in profile["source_links"]
    assert "https://www.pginstruments.com/industries/" in profile["source_links"]
    assert "https://www.pginstruments.com/product/wp750-series/" in profile["source_links"]
    assert "ICP-OES spectrometers" in profile["product_categories"]
    assert "laboratory water purification systems" in profile["product_categories"]
    assert "gas chromatography systems" not in profile["product_categories"]
    assert "gas chromatography systems" not in profile["products"]
    assert "gas chromatography" not in profile["embedding_text"].lower()
    assert "gas chromatography" not in profile["keywords"]
    assert "gas_chromatography" not in profile["concepts"]
    assert "atomic fluorescence spectrometers" in profile["products"]
    assert "food and beverage quality control and monitoring" in profile["industries_served"]
    assert profile["profile_version"] == "1.3"


def test_spinflex_microwave_amplifier_scope_matches_its_official_product_page():
    profile = next(p for p in load_profiles() if p["id"] == "spinflex")

    assert "solid-state X-band and Q-band pulsed microwave amplifiers" in profile["product_categories"]
    assert "spinAMP solid-state X-band and Q-band pulsed microwave amplifiers" in profile["products"]
    assert not any("amplifier" in item.lower() and "ESR/EPR systems" in item for item in profile["products"])
    assert "https://spin-flex.com/spinamp/" in profile["source_links"]
    assert profile["profile_version"] == "1.4"


def test_nippon_profile_sources_and_capabilities_are_specific_to_mercury_analysis():
    profile = next(p for p in load_profiles() if p["id"] == "nippon_instruments")

    assert "https://www.hg-nic.com/products/" in profile["source_links"]
    assert "https://www.hg-nic.com/industries-application/" in profile["source_links"]
    assert "MA Series direct mercury analyzers" in profile["products"]
    assert "atomic absorption systems" not in profile["product_categories"]
    assert "trace metal analyzers" not in profile["product_categories"]
    assert "fertilizer production mercury analysis" in profile["industries_served"]
    assert "fertilizer production" in profile["embedding_text"].lower()
    assert "https://www.hg-nic.com/fertilizer-production/" in profile["source_links"]
    assert "https://www.hg-nic.com/ra-series/ra-7000a/" in profile["source_links"]
    assert "https://www.hg-nic.com/ra-series/ra-7000f/" in profile["source_links"]
    assert "https://www.hg-nic.com/ma-series/ma-3-solo/" in profile["source_links"]
    assert "https://www.hg-nic.com/ma-series/ma-3000/" in profile["source_links"]
    assert "https://www.hg-nic.com/pe-series/pe-1000/" in profile["source_links"]
    assert "https://www.hg-nic.com/wa-series/wa-5a/" in profile["source_links"]
    assert "https://www.hg-nic.com/wa-series/wa-5f/" in profile["source_links"]
    assert "https://www.hg-nic.com/emp-series/emp-3/" in profile["source_links"]
    assert "https://www.hg-nic.com/emp-series/emp-gold/" in profile["source_links"]
    assert "https://www.hg-nic.com/sgm-series/sgm-9/" in profile["source_links"]
    assert "https://www.hg-nic.com/am-series/am-6f/" in profile["source_links"]
    assert "cement production" in profile["industries_served"]
    assert profile["profile_version"] == "1.15"


def test_nippon_service_signals_match_official_support_scope():
    profile = next(p for p in load_profiles() if p["id"] == "nippon_instruments")

    assert set(profile["service_keywords"]) == {
        "mercury analyzer servicing",
        "technical support for mercury analysis equipment customers",
        "technical advice for prospective mercury analyzer customers",
        "mercury measurement services",
        "product operation training",
        "mercury application demonstrations",
        "mercury application development",
        "sample analysis services",
    }
    assert not {"AMC", "annual maintenance", "maintenance", "repair", "spares", "installation", "commissioning", "calibration", "replacement"} & set(profile["service_keywords"])
    assert "https://www.hg-nic.com/about-nic/" in profile["source_links"]
    assert "https://www.hg-nic.com/support-notice/" in profile["source_links"]
    assert "making repair and maintenance extremely difficult" in profile["embedding_text"]
    assert "Verify model-specific service availability" in profile["embedding_text"]


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
    assert "https://www.teercoatings.co.uk/minting-industry-systems" in teer["source_links"]
    assert "https://www.teercoatings.co.uk/coating-portfolio" in teer["source_links"]
    assert "https://www.teercoatings.co.uk/completed-r-d-projects" in teer["source_links"]
    assert "minting and coin production" in teer["industries_served"]
    assert "semiconductor coating systems" not in teer["industries_served"]
    assert "optical coating R&D" in teer["industries_served"]
    assert "semiconductor and data storage" not in teer["industries_served"]
    assert "optical and photonics" not in teer["industries_served"]
    assert teer["profile_version"] == "1.7"


def test_teer_fuel_cell_and_electrolyser_scope_is_limited_to_documented_r_and_d():
    teer = next(profile for profile in load_profiles() if profile["id"] == "teer_coatings")

    assert "fuel cell and electrolyser coating R&D" in teer["industries_served"]
    assert "fuel cells and electrolysers" not in teer["industries_served"]
    assert "https://www.teercoatings.co.uk/current-r-d-projects" in teer["source_links"]
    assert teer["profile_version"] == "1.7"


def test_teer_service_signals_match_documented_support_and_coating_services():
    profile = next(p for p in load_profiles() if p["id"] == "teer_coatings")

    assert {
        "installation",
        "commissioning",
        "technical support",
        "field servicing",
        "maintenance",
        "preventive maintenance",
        "repair",
        "on-site repairs",
        "calibration",
        "operator training",
        "software updates",
        "process optimisation",
        "system upgrades",
        "magnetron retrofitting",
        "coating services",
    } == set(profile["service_keywords"])
    assert not {
        "AMC",
        "annual maintenance",
        "spares",
        "replacement",
    } & set(profile["service_keywords"])
    assert {
        "https://www.teercoatings.co.uk/technical-support",
        "https://www.teercoatings.co.uk/upgrades",
        "https://www.teercoatings.co.uk/meet-the-team",
        "https://www.teercoatings.co.uk/service-options",
        "https://www.teercoatings.co.uk/testing-capabilities",
        "https://www.teercoatings.co.uk/_files/ugd/4eaae2_e629d6de1a854707bad58b915971abae.pdf",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.7"


def test_staton_profile_does_not_list_tool_reconditioning_as_equipment():
    profile = next(p for p in load_profiles() if p["id"] == "staton")

    assert "tool sharpening and regrinding equipment" not in profile["product_categories"]
    assert "Precision Cutting and Forming Tools" not in profile["products"]
    assert {
        "installation",
        "maintenance",
        "tool production",
        "tool sharpening and regrinding",
        "operator training",
        "remote diagnostics",
        "system upgrades",
        "replacement of coating equipment parts",
        "customer support",
    } == set(profile["service_keywords"])
    assert not {"repair", "replacement", "AMC", "annual maintenance", "spares", "commissioning", "calibration"} & set(profile["service_keywords"])
    assert "https://statoncoating.com/services/" in profile["source_links"]
    assert "https://statoncoating.com/contact/" in profile["source_links"]
    assert "https://statoncoating.com/research/" in profile["source_links"]
    assert "https://statoncoating.com/products/" in profile["source_links"]
    assert "https://www.staton.sk/en/services/sharpening-regrinding-tools/" in profile["source_links"]
    assert "https://www.staton.sk/en/services/tools/tool-production/" in profile["source_links"]
    assert profile["profile_version"] == "1.5"
    assert "tool manufacturing and metalworking" in profile["industries_served"]
    assert "medical and biocompatible coatings" in profile["industries_served"]
    assert "minting and decorative coatings" in profile["industries_served"]
    assert "aerospace and defense" not in profile["industries_served"]
    assert "food processing" not in profile["industries_served"]
    assert "woodworking" not in profile["industries_served"]
    assert "medical and biocompatible devices" not in profile["industries_served"]


def test_genicore_service_terms_match_official_services_page():
    profile = next(p for p in load_profiles() if p["id"] == "genicore")

    assert set(profile["service_keywords"]) == {
        "short-series production using U-FAST technology",
        "guarantee and post-guarantee device servicing",
        "online device service",
        "tele-service contracts",
        "online operational support",
        "technical support through partner network",
        "feasibility studies",
        "proof-of-concept sample production",
        "research and development services",
        "consulting and training on SPS and FAST sintering",
        "graphite machining",
        "graphite mold design",
        "grinding services",
        "microstructure and composition analysis",
        "microscope observation",
        "precision cutting",
        "hot mounting",
        "surface roughness measurement",
        "hardness testing",
    }
    assert "Toll Sintering Services" not in profile["service_keywords"]
    assert not {"AMC", "annual maintenance", "maintenance", "repair", "spares", "installation", "commissioning", "calibration", "replacement"} & set(profile["service_keywords"])
    assert "https://genicore.eu/products/services/" in profile["source_links"]
    assert profile["profile_version"] == "2.0"


def test_genicore_installation_claim_is_not_generalized_from_flash_platform():
    profile = next(p for p in load_profiles() if p["id"] == "genicore")

    assert "installation" not in profile["embedding_text"].lower()
    assert "commissioning" not in profile["embedding_text"].lower()
    assert "installation" not in profile["service_keywords"]
    assert "https://genicore.eu/products/devices/flash/" in profile["source_links"]


def test_genicore_profile_includes_documented_u_fast_flash_platform():
    profile = next(p for p in load_profiles() if p["id"] == "genicore")

    assert "U-FAST FLASH multi-energy sintering platform" in profile["products"]
    assert "multi-energy field-assisted sintering systems" in profile["product_categories"]
    assert "https://genicore.eu/products/devices/flash/" in profile["source_links"]


def test_genicore_material_and_application_claims_link_to_official_sources():
    profile = next(p for p in load_profiles() if p["id"] == "genicore")

    assert "https://genicore.eu/" in profile["source_links"]
    assert "https://genicore.eu/materials/" in profile["source_links"]
    assert "https://genicore.eu/applications/" in profile["source_links"]
    assert "https://genicore.eu/products/graphite-dies-for-spark-plasma-sintering-systems/" in profile["source_links"]
    assert "https://genicore.eu/products/devices/pulse-plasma-compaction-ppc/" in profile["source_links"]
    assert "https://genicore.eu/materials/dec/" in profile["source_links"]
    assert "Diamond Enhanced Cemented Carbide (DEC)" in profile["products"]
    assert "Super Enhanced Ceramic - Whiskers (SEC-W)" in profile["products"]
    assert "CUBNEC (Cubic Boron Nitride Enhanced Cemented Carbide)" in profile["products"]
    assert "CUBNEC" in profile["keywords"]
    assert "Cubic Boron Nitride Enhanced Cemented Carbide" in profile["keywords"]
    assert "aerospace and defense materials" in profile["industries_served"]
    assert profile["profile_version"] == "2.0"


def test_korvus_profile_links_named_deposition_sources():
    profile = next(p for p in load_profiles() if p["id"] == "korvus_technology")

    assert {
        "https://korvustech.com/highly-modular-pvd-system/",
        "https://korvustech.com/magnetron-sputtering-system/",
        "https://korvustech.com/organic-thermal-evaporation/",
        "https://korvustech.com/thermal-deposition/",
        "https://korvustech.com/pvd-thermal-evaporation/",
        "https://korvustech.com/wp-content/uploads/2025/01/Korvus-2pp-TAU.pdf",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.4"


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
    assert profile["profile_version"] == "1.4"


def test_nordiko_profile_omits_unsupported_reactive_ion_etching_claims():
    profile = next(p for p in load_profiles() if p["id"] == "nordiko")

    assert "RIE" not in profile["keywords"]
    assert "rie" not in profile["concepts"]
    assert "plasma etching and deposition" not in profile["product_categories"]
    assert "aerospace and telecommunications" not in profile["industries_served"]
    assert "ion beam milling systems" in profile["product_categories"]
    assert "N1500-600 Large-area PECVD reactor" in profile["products"]
    assert profile["profile_version"] == "1.4"


def test_nordiko_n1500_is_classified_as_pecvd_not_sputtering():
    profile = next(p for p in load_profiles() if p["id"] == "nordiko")

    assert "N1500-600 Large-area PECVD reactor" in profile["products"]
    assert "N1500 Sputtering System" not in profile["products"]
    assert "plasma-enhanced chemical vapour deposition systems" in profile["product_categories"]
    assert profile["profile_version"] == "1.4"


def test_agnitron_profile_links_official_products_software_and_service_sources():
    profile = next(p for p in load_profiles() if p["id"] == "agnitron")

    assert {
        "https://agnitron.com/products/",
        "https://agnitron.com/products/insitu-monitoring/",
        "https://agnitron.com/products/control-software/",
        "https://agnitron.com/services-and-support/",
        "https://agnitron.com/services-and-support/refurbished-mocvd/",
        "https://agnitron.com/products/mocvd/agilis-100/",
        "https://agnitron.com/products/mocvd/agilis-500/",
        "https://agnitron.com/products/mocvd/agilis-700/",
        "https://agnitron.com/products/mocvd/agilis-series-300/",
        "https://agnitron.com/products/mocvd/custom-systems/",
        "https://agnitron.com/products/mocvd/a-series/",
    } <= set(profile["source_links"])
    assert "Agilis GOX300 Gallium Oxide MOCVD system" in profile["products"]
    assert "GOX Series Gallium Oxide systems" not in profile["products"]
    assert "Agilis GOX300 large-production reactor" in profile["embedding_text"]
    assert "AgniTemp multiwavelength pyrometer" in profile["products"]
    assert profile["profile_version"] == "1.8"


def test_agnitron_legacy_mocvd_upgrades_are_classified_as_services():
    profile = next(p for p in load_profiles() if p["id"] == "agnitron")

    assert "Legacy MOCVD system upgrades" not in profile["products"]
    assert "legacy MOCVD system upgrades" in profile["service_keywords"]


def test_agnitron_service_terms_match_parts_and_refurbishment_sources():
    profile = next(p for p in load_profiles() if p["id"] == "agnitron")

    assert set(profile["service_keywords"]) == {
        "legacy MOCVD spare parts",
        "legacy MOCVD replacement parts",
        "legacy MOCVD system customization",
        "legacy MOCVD software upgrades",
        "legacy MOCVD hardware upgrades",
        "legacy MOCVD service plans",
        "preventive maintenance for refurbished MOCVD systems",
        "startup for refurbished MOCVD equipment",
        "refurbishment of legacy MOCVD systems",
        "legacy MOCVD process development services",
        "legacy MOCVD system upgrades",
    }
    assert not {
        "AMC",
        "annual maintenance",
        "maintenance",
        "repair",
        "installation",
        "commissioning",
        "calibration",
        "replacement",
    } & set(profile["service_keywords"])
    assert "https://agnitron.com/services-and-support/parts-and-services/" in profile["source_links"]
    assert "Parts, service plans, customization, and hardware/software upgrades are documented for Emcore/Veeco, Discovery, and Enterprise legacy MOCVD systems." in profile["embedding_text"]
    assert profile["profile_version"] == "1.8"


def test_parteq_service_terms_are_specific_to_published_research_services():
    profile = next(p for p in load_profiles() if p["id"] == "parteq")

    assert set(profile["service_keywords"]) == {
        "aerosol measurement services",
        "particle characterization services",
        "contract synthesis",
        "process development and optimization",
        "scale-up studies",
        "economic and technical process analysis",
        "equipment prototype design",
        "turn-key production system realization",
        "nanopowder development and production",
        "functionalized particle synthesis to customer specifications",
    }
    assert not {
        "AMC",
        "annual maintenance",
        "maintenance",
        "repair",
        "spares",
        "installation",
        "commissioning",
        "calibration",
        "replacement",
    } & set(profile["service_keywords"])
    assert "https://parteq.net/en/services-in-aerosol-technology/forschungsdienstleistungen.html" in profile["source_links"]
    assert "low competition" not in profile["embedding_text"].lower()
    assert "nanomaterial synthesis, aerosol science, and pilot-scale material development infrastructure" in profile["embedding_text"]
    assert profile["profile_version"] == "1.5"


def test_korvus_service_signals_match_documented_support_and_training():
    profile = next(p for p in load_profiles() if p["id"] == "korvus_technology")

    assert "installation" not in profile["embedding_text"].lower()
    assert "maintenance" not in profile["embedding_text"].lower()
    assert "designs and manufactures modular PVD systems" in profile["embedding_text"]
    assert profile["service_keywords"] == [
        "customer support",
        "thin-film training",
        "PVD training",
    ]
    assert not {
        "installation",
        "maintenance",
        "servicing",
        "system upgrades",
    } & set(profile["service_keywords"])
    assert not {
        "AMC",
        "annual maintenance",
        "repair",
        "spares",
        "commissioning",
        "calibration",
        "replacement",
    } & set(profile["service_keywords"])
    assert {
        "https://korvustech.com/pvd-teaching-and-training/",
        "https://korvustech.com/latest-developments-of-the-hex-series/",
        "https://korvustech.com/hex-online-user-meeting/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.4"


def test_parteq_profile_links_official_synthesis_instrumentation_and_service_sources():
    profile = next(p for p in load_profiles() if p["id"] == "parteq")

    assert {
        "https://parteq.net/en/products/nanopowder-synthesis/",
        "https://parteq.net/en/products/aerosolmesstechnik/",
        "https://parteq.net/en/products/aerosolmesstechnik/nanoparticle-measurement-systems/",
        "https://parteq.net/en/products/aerosolmesstechnik/fine-dust-monitoring/",
        "https://parteq.net/en/products/aerosolmesstechnik/fine-dust-monitoring/aq-guard.html",
        "https://parteq.net/en/services-in-aerosol-technology/forschungsdienstleistungen.html",
        "https://parteq.net/produkte/partikelstrukturierung-und-funktionalisierung/",
        "https://parteq.net/en/",
    } <= set(profile["source_links"])
    assert "air quality and fine-dust monitoring" in profile["industries_served"]
    assert "environmental monitoring" not in profile["industries_served"]
    assert "aerosol measurement instruments" in profile["embedding_text"]
    assert "AQ Guard air-quality aerosol measurement" not in profile["embedding_text"]
    assert profile["profile_version"] == "1.5"


def test_pg_instruments_service_terms_are_limited_to_documented_support():
    profile = next(p for p in load_profiles() if p["id"] == "pg_instruments")

    assert set(profile["service_keywords"]) == {
        "authorized distributor instrument servicing",
        "instrument installation",
        "IQ/OQ testing",
        "emergency service support",
        "technical support",
        "warranty replacement of defective parts",
        "spare parts availability",
    }
    assert not {"AMC", "annual maintenance", "maintenance", "repair", "commissioning", "calibration"} & set(profile["service_keywords"])
    assert "https://storage.mtender.gov.md/get/b70ad211-467f-476d-a519-99540a51cd56-1637088115424" in profile["source_links"]
    assert profile["profile_version"] == "1.3"


def test_nordiko_service_terms_match_official_service_and_support_page():
    profile = next(p for p in load_profiles() if p["id"] == "nordiko")

    assert set(profile["service_keywords"]) == {
        "worldwide ongoing customer support",
        "preventative maintenance packages tailored to system use",
        "hourly online service and support",
        "repair of electrical and electronic components",
        "replacement unit quoted when repair is not possible",
        "spare parts and consumables service",
        "system maintenance and refurbishment",
        "end-user and maintenance training courses",
        "hotline technical support",
        "legacy system upgrades",
        "production ion beam system upgrades",
    }
    assert "installation" not in profile["service_keywords"]
    assert "https://nordiko-tech.co.uk/service-and-support" in profile["source_links"]
    assert "Supply and procurement of industrial-scale PVD coating systems" in profile["embedding_text"]
    assert "procurement, and installation" not in profile["embedding_text"]
    assert profile["profile_version"] == "1.4"


def test_spinflex_service_keywords_remain_unset_without_verified_support_scope():
    profile = next(p for p in load_profiles() if p["id"] == "spinflex")

    assert profile["service_keywords"] == []
    assert profile["profile_version"] == "1.4"


def test_thesix_profile_links_fuel_cell_and_electrolyzer_test_sources():
    profile = next(p for p in load_profiles() if p["id"] == "thesix_solutions")

    assert {
        "https://thesixtech.com/collections/fuel-cell-testing-hardware",
        "https://thesixtech.com/products/ionic-conductivity-cell",
        "https://thesixtech.com/collections/fuel-cell-production-units",
        "https://thesixtech.com/products/electrolyzer-test-cell",
        "https://thesixtech.com/products/flow-battery-test-cell",
        "https://thesixtech.com/products/gas-humidifier-cabinet",
        "https://thesixtech.com/products/anode-cathode-gas-humidifier",
        "https://thesixtech.com/products/heated-ss316-flexible-gas-transfer-hose",
        "https://thesixtech.com/products/heated-vacuum-plate-s",
        "https://thesixtech.com/products/ultrasonic-spray-coating-system-copy",
        "https://thesixtech.com/products/temperature-controlled-fuel-cell-membrane-electrode-mea-press",
        "https://thesixtech.com/products/heated-vacuum-plate",
    } <= set(profile["source_links"])
    assert "flow battery test cells" in profile["products"]
    assert "Gas Humidifier for Fuel Cells" in profile["products"]
    assert "Anode & Cathode Gas Humidifier for Fuel Cells" in profile["products"]
    assert "Heated SS316 Gas Transfer Hose for Fuel Cells" in profile["products"]
    assert "HVT-200 Heated Vacuum Table" in profile["products"]
    assert "Ultrasonic Spray Coating System CoatSys" in profile["products"]
    assert "Temperature Controlled Fuel Cell MEA Press" in profile["products"]
    assert "Large Heated Vacuum Table HVT-300" in profile["products"]
    assert "Supply and installation of fuel cell testing systems" not in profile["embedding_text"]
    assert "Supply of fuel cell testing systems" in profile["embedding_text"]
    assert profile["service_keywords"] == []
    assert profile["profile_version"] == "1.7"


def test_adnanotek_services_are_limited_to_officially_described_support():
    profile = next(p for p in load_profiles() if p["id"] == "adnanotek")

    assert set(profile["service_keywords"]) == {
        "in-depth theoretical and hands-on training",
        "professional technology consultation",
        "technical support",
        "customer and technical services",
        "customer support",
    }
    assert not {"AMC", "annual maintenance", "maintenance", "repair", "spares", "installation", "commissioning", "calibration", "replacement"} & set(profile["service_keywords"])
    assert "https://adnano-tek.com/about-adnanotek/" in profile["source_links"]
    assert "Official service descriptions include customer and technical services" in profile["embedding_text"]
    assert "Confirm any requested maintenance, repair, spare parts, installation, commissioning, or calibration scope" in profile["embedding_text"]
    assert "high-end research tenders" not in profile["embedding_text"]
    assert "relevant for tenders involving thin-film growth, semiconductor fabrication, and UHV material processing" in profile["embedding_text"]
    assert profile["profile_version"] == "1.7"


def test_sald_profile_links_patented_deposition_head_claim_to_official_sources():
    profile = next(p for p in load_profiles() if p["id"] == "sald")

    assert "Patented Spatial ALD Deposition Head" not in profile["products"]
    assert "Atmospheric Pressure ALD Reactor" not in profile["products"]
    assert "atmospheric pressure thin film equipment" in profile["product_categories"]
    assert "atmospheric pressure" in profile["keywords"]
    assert "patented spatial ALD deposition head technology" in profile["keywords"]
    assert {
        "https://spatialald.com/solutions/rd-system/",
        "https://spatialald.com/solutions/high-volume-production-systems/",
        "https://spatialald.com/technology/atomic-layer-deposition/",
        "https://spatialald.com/markets/battery-technology/",
        "https://spatialald.com/markets/solar-energy/",
        "https://spatialald.com/markets/green-hydrogen/",
        "https://spatialald.com/markets/barriers-and-packaging/",
        "https://www2.avs.org/symposium2019/Papers/Paper_TF-TuA3.html",
        "https://spatialald.com/terms-conditions/",
        "https://spatialald.com/careers/service-engineer/",
    } <= set(profile["source_links"])
    assert profile["profile_version"] == "1.7"


def test_sald_service_terms_are_grounded_in_terms_and_service_role():
    profile = next(p for p in load_profiles() if p["id"] == "sald")

    assert set(profile["service_keywords"]) == {
        "installation and acceptance testing",
        "preventive maintenance monitoring",
        "equipment maintenance services",
        "equipment repair services",
        "warranty service",
        "field upgrades",
        "technical support",
        "upgrade-related customer training",
        "technical troubleshooting support",
    }
    assert not {"AMC", "annual maintenance", "calibration", "commissioning"} & set(profile["service_keywords"])
    assert not {"spare parts", "replacement parts", "hardware upgrades", "software upgrades"} & set(profile["service_keywords"])
    assert "https://spatialald.com/terms-conditions/" in profile["source_links"]
    assert "https://spatialald.com/careers/service-engineer/" in profile["source_links"]
    assert profile["profile_version"] == "1.7"


def test_spinflex_industries_limit_health_claim_to_biomedical_research():
    profile = next(p for p in load_profiles() if p["id"] == "spinflex")

    assert "biomedical research" in profile["industries_served"]
    assert "structural biology research" in profile["industries_served"]
    assert "medicine research" not in profile["industries_served"]
    assert "https://spin-flex.com/pulse-epr-structural-biology/" in profile["source_links"]
    assert profile["profile_version"] == "1.4"


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
    assert "C3+ Large-Substrate Spin Coater" in profile["products"]
    assert not any("World's Largest" in product for product in profile["products"])
    assert "patented C3+ process" not in profile["embedding_text"]
    assert profile["profile_version"] == "1.5"


def test_on_nano_service_signals_are_conditional_on_order_terms():
    profile = next(p for p in load_profiles() if p["id"] == "on_nano")

    assert set(profile["service_keywords"]) == {
        "contracted equipment installation",
        "contracted assembly and commissioning",
        "customer instruction for delivered equipment",
        "defect remediation",
        "replacement delivery",
        "delivery of service parts",
        "service technician deployment",
    }
    assert not {"AMC", "annual maintenance", "maintenance", "repair", "spares", "calibration", "upgrade"} & set(profile["service_keywords"])
    assert "https://on-nano.com/terms-and-conditions/" in profile["source_links"]
    assert "when included in the customer order" in profile["embedding_text"]
    assert "verify the specific scope in the order confirmation" in profile["embedding_text"]
    assert profile["profile_version"] == "1.5"


def test_adnanotek_profile_links_official_deposition_quantum_and_etching_sources():
    profile = next(p for p in load_profiles() if p["id"] == "adnanotek")

    assert {
        "https://adnano-tek.com/quantum-computing-deposition-system/",
        "https://adnano-tek.com/quantum-computing-deposition-system/jeb-2/",
        "https://adnano-tek.com/quantum-computing-deposition-system/jeb-3/",
        "https://adnano-tek.com/ion-beam-etching/",
        "https://adnano-tek.com/ion-beam-sputter-deposition/",
        "https://adnano-tek.com/plasma-system/",
        "https://adnano-tek.com/reactive-ion-etching-rie/",
        "https://adnano-tek.com/inductively-coupled-plasma-icp/",
        "https://adnano-tek.com/electron-cyclotron-resonance-ecr/",
        "https://adnano-tek.com/uhv-design-components/",
        "https://adnano-tek.com/manipulators/",
        "https://adnano-tek.com/uhv-design-components/transfer-arms/",
        "https://adnano-tek.com/thermo-evaporator-system/",
        "https://adnano-tek.com/molecular-beam-epitaxy-mbe/",
        "https://adnano-tek.com/pulsed-laser-deposition-pld/",
        "https://adnano-tek.com/magnetron-sputtering-systems/",
    } <= set(profile["source_links"])
    assert "thin film characterization" not in profile["product_categories"]
    assert profile["profile_version"] == "1.7"


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


def test_on_nano_substrate_formats_are_not_industry_labels():
    profile = next(p for p in load_profiles() if p["id"] == "on_nano")

    assert "GPS (Glass Panel Substrates)" not in profile["industries_served"]
    assert "organic panels" not in profile["industries_served"]
    assert "glass panel substrates" in profile["keywords"]
    assert "glass-panel substrates" in profile["embedding_text"]
    assert profile["profile_version"] == "1.5"


def test_thesix_profile_excludes_clinical_infusion_equipment():
    profile = next(p for p in load_profiles() if p["id"] == "thesix_solutions")

    assert profile["negative_keywords"] == [
        "medical infusion pump",
        "patient dose control",
        "intravenous pump",
    ]
    assert profile["profile_version"] == "1.7"
