from matching.filter import classify_tender


def test_recommendation_explanation_separates_evidence_and_states_unknowns():
    candidate = {
        "manufacturer_id": "korvus_technology",
        "manufacturer_name": "Korvus Technology",
        "rank": 1,
        "base_semantic_score": 0.71,
        "score": 0.84,
        "keyword_hits": ["PVD"],
        "product_hits": ["HEX Series PVD systems"],
        "category_hits": ["thin film deposition systems"],
        "alias_hits": ["HEX-L"],
        "concept_hits": ["pvd", "sputtering"],
        "service_hits": ["installation"],
        "negative_hits": ["annual maintenance"],
        "reason_codes": ["MANUFACTURER_PRODUCT_EVIDENCE"],
        "manufacturer_source_links": ["https://example.test/profile"],
    }
    tender = {
        "title": "Research PVD sputtering system; annual maintenance for existing chamber",
        "organization": "IISc",
        "source_url": "https://example.test/tender/1",
    }

    result = classify_tender(tender, manufacturer_candidates=[candidate])
    explanation = result["explanation"]
    manufacturer = explanation["manufacturer_evidence"][0]

    assert explanation is result["trace"]["explanation"]
    assert explanation["decision"] == result["decision"]
    assert explanation["overall_score"] == {
        "value": result["score"],
        "scale": "heuristic points on a 0-100 scale",
        "calibrated_probability": False,
    }
    assert explanation["technical_concept_evidence"]
    assert manufacturer["semantic_similarity"] == {
        "value": 0.71,
        "meaning": "embedding similarity signal; not a probability",
    }
    assert manufacturer["combined_heuristic_rank_score"] == {
        "value": 0.84,
        "meaning": "semantic and profile evidence score after penalties; not a probability",
    }
    assert manufacturer["product_family_agreement"] == {
        "product_hits": ["HEX Series PVD systems"],
        "category_hits": ["thin film deposition systems"],
        "alias_hits": ["HEX-L"],
    }
    assert manufacturer["negative_evidence"] == ["annual maintenance"]
    assert explanation["negative_evidence"]["soft_risk_terms"]
    assert explanation["source_quality"] == {
        "assessment": "not_assessed",
        "tender_source_url_recorded": True,
        "manufacturer_profile_source_links_recorded": True,
    }
    assert any("certifications are not verified" in item for item in explanation["unverified_requirements"])


def test_explanation_marks_source_quality_not_assessed_when_links_are_absent():
    result = classify_tender({"title": "Unspecified laboratory equipment"})

    assert result["explanation"]["source_quality"] == {
        "assessment": "not_assessed",
        "tender_source_url_recorded": False,
        "manufacturer_profile_source_links_recorded": False,
    }
    assert result["explanation"]["unverified_requirements"]
