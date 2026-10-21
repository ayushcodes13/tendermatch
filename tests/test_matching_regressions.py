"""Adversarial matcher cases that run without models, portals, or SMTP."""

import json
from pathlib import Path

import numpy as np
import pytest

from matching.matcher import TenderMatcher


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
