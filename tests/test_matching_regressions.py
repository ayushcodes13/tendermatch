"""Adversarial matcher cases that run without models, portals, or SMTP."""

import numpy as np

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
