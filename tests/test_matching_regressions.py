"""Adversarial matcher cases that run without models, portals, or SMTP."""

import json
from pathlib import Path

import numpy as np
import pytest

from matching.matcher import TenderMatcher

ROOT = Path(__file__).resolve().parents[1]


class FakeEmbedder:
    def __init__(self, manufacturers, embeddings, query_embedding):
        self._manufacturers = manufacturers
        self._embeddings = np.asarray(embeddings, dtype=float)
        self._query_embedding = np.asarray(query_embedding, dtype=float)

    def get_manufacturers(self):
        return self._manufacturers

    def get_embeddings(self):
        return self._embeddings

    def embed_text(self, _text):
        return self._query_embedding


def make_matcher(manufacturers, embeddings, query_embedding):
    return TenderMatcher(FakeEmbedder(manufacturers, embeddings, query_embedding))


def test_negative_keyword_penalizes_but_does_not_silently_drop_candidate():
    matcher = make_matcher(
        [
            {
                "id": "pump-maker",
                "name": "Pump Maker",
                "products": ["industrial pump"],
                "negative_keywords": ["medical infusion"],
            },
            {"id": "other", "name": "Other Maker"},
        ],
        [[0.9, 0.1], [0.8, 0.2]],
        [1.0, 0.0],
    )

    candidates = matcher.match_topk(
        {"title": "Industrial pump maintenance for medical infusion wards"}, top_k=2
    )

    pump = next(candidate for candidate in candidates if candidate["manufacturer_id"] == "pump-maker")
    assert pump["negative_hits"] == ["medical infusion"]
    assert pump["score"] < pump["base_semantic_score"]
    assert {candidate["manufacturer_id"] for candidate in candidates} == {"pump-maker", "other"}


def test_short_acronym_requires_token_boundary():
    matcher = make_matcher(
        [{"id": "thin-film", "name": "Thin Film Co", "aliases": ["PVD"]}],
        [[1.0, 0.0]],
        [1.0, 0.0],
    )

    embedded = matcher.match_topk({"title": "SPVD coating system"})[0]
    standalone = matcher.match_topk({"title": "PVD coating system"})[0]

    assert embedded["alias_hits"] == []
    assert standalone["alias_hits"] == ["PVD"]


def test_semantic_only_candidate_is_still_returned_without_technical_evidence():
    matcher = make_matcher(
        [{"id": "unrelated", "name": "Unrelated Manufacturer"}],
        [[0.58, 0.0]],
        [1.0, 0.0],
    )

    candidates = matcher.match_topk({"title": "unseen technical requirement"})

    assert len(candidates) == 1
    assert candidates[0]["keyword_hits"] == []
    assert candidates[0]["product_hits"] == []
    assert candidates[0]["reason_codes"][-1] == "MANUFACTURER_SCORE_LOW_RELATIVE"


def test_candidate_generation_keeps_semantic_and_lexical_candidates_before_top_k():
    matcher = make_matcher(
        [
            {"id": "semantic", "name": "Semantic Neighbor"},
            {"id": "alias", "name": "Alias Manufacturer", "aliases": ["PVD"]},
            {"id": "other", "name": "Other Manufacturer"},
            {"id": "inactive", "name": "Inactive Manufacturer", "active": False},
        ],
        [[0.95, 0.0], [0.1, 0.9], [0.0, 1.0], [1.0, 0.0]],
        [1.0, 0.0],
    )

    pool = matcher.generate_candidates({"title": "PVD process equipment"})
    ranked = matcher.rank_candidates(pool, top_k=1)

    assert [candidate["manufacturer"]["id"] for candidate in pool] == [
        "semantic",
        "alias",
        "other",
    ]
    alias_candidate = next(candidate for candidate in pool if candidate["manufacturer"]["id"] == "alias")
    assert alias_candidate["evidence"]["alias_hits"] == ["PVD"]
    assert len(ranked) == 1
    assert ranked[0]["manufacturer_id"] == "semantic"
    assert matcher.match_topk({"title": "PVD process equipment"}, top_k=1) == ranked
    assert matcher.rank_candidates(pool, top_k=0) == []
    with pytest.raises(ValueError, match="non-negative integer"):
        matcher.rank_candidates(pool, top_k=-1)


def test_parteq_spark_synthesis_profile_emits_lexical_match_evidence():
    profiles = json.loads((ROOT / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    parteq = next(profile for profile in profiles if profile["id"] == "parteq")
    matcher = make_matcher([parteq], [[0.0]], [1.0])

    pool = matcher.generate_candidates({
        "title": "Spark-discharge synthesis system for graphitic nanoparticles and metallic nanoparticles",
        "description": "Precursor-free laboratory production of functional particles.",
    })

    assert len(pool) == 1
    candidate = pool[0]
    assert candidate["manufacturer"]["id"] == "parteq"
    assert "spark-discharge synthesis" in candidate["evidence"]["keyword_hits"]
    assert "graphitic nanoparticles" in candidate["evidence"]["keyword_hits"]


def test_match_exposes_profile_warnings_without_treating_them_as_ranking_evidence():
    manufacturers = [
        {
            "id": "dated-authorization",
            "name": "Instrument Supplier",
            "profile_warnings": ["Verify the dated local authorization."],
        },
        {"id": "plain", "name": "Plain Supplier"},
    ]
    matcher = make_matcher(manufacturers, [[1.0, 0.0], [1.0, 0.0]], [1.0, 0.0])

    result = next(item for item in matcher.match_topk({"title": "laboratory instrument"}, top_k=2) if item["manufacturer_id"] == "dated-authorization")

    assert result["profile_warnings"] == ["Verify the dated local authorization."]
    assert result["score"] == result["base_semantic_score"]


def test_spinflex_profile_has_epr_evidence_but_no_nmr_lexical_evidence():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    spinflex = next(profile for profile in manufacturers if profile["id"] == "spinflex")
    matcher = make_matcher([spinflex], [[1.0]], [1.0])

    epr_match = matcher.match_topk({"title": "Supply of spinUP pulse EPR/ESR systems"})[0]
    nmr_match = matcher.match_topk({"title": "Time-domain NMR analyzer for relaxation and diffusion"})[0]

    assert epr_match["product_hits"]
    assert epr_match["category_hits"]
    assert nmr_match["product_hits"] == []
    assert nmr_match["category_hits"] == []
    assert nmr_match["keyword_hits"] == []
    assert nmr_match["concept_hits"] == []


def test_pg_instruments_profile_matches_documented_icp_oes_equipment():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    pg_instruments = next(profile for profile in manufacturers if profile["id"] == "pg_instruments")
    matcher = make_matcher([pg_instruments], [[1.0]], [1.0])

    match = matcher.match_topk({"title": "Supply of ICP-OES spectrometers"})[0]

    assert "ICP-OES spectrometers" in match["product_hits"]
    assert "ICP-OES spectrometers" in match["category_hits"]
    assert "ICP-OES" in match["keyword_hits"]


def test_nippon_profile_matches_mercury_analysis_but_not_generic_aas():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    nippon = next(profile for profile in manufacturers if profile["id"] == "nippon_instruments")
    matcher = make_matcher([nippon], [[1.0]], [1.0])

    mercury_match = matcher.match_topk({"title": "MA Series direct mercury analyzers for solid samples"})[0]
    other_aas_match = matcher.match_topk({"title": "Atomic absorption spectrometer for lead and cadmium analysis"})[0]

    assert mercury_match["product_hits"]
    assert mercury_match["category_hits"]
    assert other_aas_match["product_hits"] == []
    assert other_aas_match["category_hits"] == []
    assert other_aas_match["keyword_hits"] == []
    assert other_aas_match["concept_hits"] == []


def test_nippon_fertilizer_commodity_candidate_gets_contextual_penalty_not_hard_exclusion():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    nippon = next(profile for profile in manufacturers if profile["id"] == "nippon_instruments")
    other = {"id": "other", "name": "Other Manufacturer"}
    matcher = make_matcher([nippon, other], [[0.72, 0.0], [0.70, 0.0]], [1.0, 0.0])

    commodity = matcher.match_topk({
        "title": "Supply of bulk urea and phosphate fertilizer for seasonal agricultural distribution; "
        "no mercury analysis or measurement equipment is requested."
    }, top_k=2)
    fertilizer_analyzer = matcher.match_topk({
        "title": "Supply of a mercury analyzer for fertilizer-plant natural gas and finished fertilizer samples."
    }, top_k=2)

    nippon_commodity = next(x for x in commodity if x["manufacturer_id"] == "nippon_instruments")
    assert commodity[0]["manufacturer_id"] == "other"
    assert "MANUFACTURER_CONTEXTUAL_DOMAIN_CONFLICT" in nippon_commodity["reason_codes"]
    assert nippon_commodity["contextual_negative_hits"][0]["rule_id"] == (
        "FERTILIZER_COMMODITY_WITHOUT_MERCURY_INSTRUMENT"
    )
    assert any(x["manufacturer_id"] == "nippon_instruments" for x in commodity)
    assert fertilizer_analyzer[0]["manufacturer_id"] == "nippon_instruments"
    assert fertilizer_analyzer[0]["contextual_negative_hits"] == []


def test_teer_profile_does_not_match_nordiko_only_product_names():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    teer = next(profile for profile in manufacturers if profile["id"] == "teer_coatings")
    matcher = make_matcher([teer], [[1.0]], [1.0])

    for title in (
        "Supply of the Mnem-iX Broad Ion Beam System",
        "Supply of the Nordiko N300 Laboratory Scale Sputtering System",
    ):
        match = matcher.match_topk({"title": title})[0]
        assert match["product_hits"] == []


def test_teer_profile_does_not_claim_plasma_enhanced_cvd_systems():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    teer = next(profile for profile in manufacturers if profile["id"] == "teer_coatings")
    matcher = make_matcher([teer], [[1.0]], [1.0])

    match = matcher.match_topk({"title": "Procurement of plasma enhanced CVD systems"})[0]

    assert match["category_hits"] == []


def test_staton_profile_does_not_match_tool_reconditioning_as_equipment():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    staton = next(profile for profile in manufacturers if profile["id"] == "staton")
    matcher = make_matcher([staton], [[1.0]], [1.0])

    match = matcher.match_topk({"title": "Procurement of tool sharpening and regrinding equipment"})[0]

    assert match["category_hits"] == []


def test_staton_tool_sharpening_and_regrinding_is_service_evidence():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    staton = next(profile for profile in manufacturers if profile["id"] == "staton")
    matcher = make_matcher([staton], [[1.0]], [1.0])

    match = matcher.match_topk({"title": "Tool sharpening and regrinding service"})[0]

    assert match["product_hits"] == []
    assert match["service_hits"] == ["tool sharpening and regrinding"]


def test_genicore_short_series_sintering_matches_service_not_product():
    root = Path(__file__).resolve().parents[1]
    manufacturers = json.loads((root / "data" / "manufacturers.json").read_text(encoding="utf-8"))
    genicore = next(profile for profile in manufacturers if profile["id"] == "genicore")
    matcher = make_matcher([genicore], [[1.0]], [1.0])

    match = matcher.match_topk({"title": "Short-series production using U-FAST technology for ceramic powders"})[0]

    assert match["product_hits"] == []
    assert "short-series production using U-FAST technology" in match["service_hits"]


def test_thesix_medical_infusion_mismatch_is_softly_penalized_and_retained():
    profiles = json.loads((ROOT / "data/manufacturers.json").read_text(encoding="utf-8"))
    thesix = next(profile for profile in profiles if profile["id"] == "thesix_solutions")
    matcher = make_matcher([thesix, {"id": "other", "name": "Other"}], [[0.8, 0.6], [0.1, 0.9]], [1.0, 0.0])

    medical = matcher.match_topk(
        {"title": "Medical infusion pumps with patient dose controls for hospital wards"},
        top_k=2,
    )
    candidate = next(item for item in medical if item["manufacturer_id"] == "thesix_solutions")

    assert set(candidate["negative_hits"]) == {"medical infusion pump", "patient dose control"}
    assert candidate["score"] < candidate["base_semantic_score"]
    assert "thesix_solutions" in {item["manufacturer_id"] for item in medical}

    industrial = matcher.match_topk(
        {"title": "Industrial water transfer pump for a manufacturing cooling loop"},
        top_k=2,
    )
    industrial_candidate = next(item for item in industrial if item["manufacturer_id"] == "thesix_solutions")
    assert industrial_candidate["negative_hits"] == []
    assert industrial_candidate["score"] == industrial_candidate["base_semantic_score"]
