"""
Manufacturer matching engine.

v2 behavior:
- Always returns top-k manufacturer candidates.
- Does not use semantic score as a hard gate.
- Adds keyword evidence and rank information.
- Keeps old match() method for backward compatibility.
"""

import re
import numpy as np
from matching.domain_keywords import company_keywords


class TenderMatcher:
    """
    Calculates manufacturer fit for a tender using:
    1. embedding similarity
    2. manufacturer-specific keyword evidence
    3. rank-based output

    Important:
    match_topk() should be used by the new pipeline.
    match() is kept for legacy compatibility.
    """

    def __init__(self, embedder, k=3):
        self.embedder = embedder
        self.k = k

        self.manufacturers = embedder.get_manufacturers()
        self.mfr_embeddings = embedder.get_embeddings()

    def match_topk(self, tender, top_k=None):
        """
        Return top-k manufacturer candidates regardless of absolute score.

        This fixes the old failure mode:
        correct tenders can score below 0.65 but still be the best relative match.

        Args:
            tender (dict): normalized tender
            top_k (int): number of candidates to return

        Returns:
            list[dict]: ranked manufacturer candidates
        """
        if top_k is None:
            top_k = self.k

        text = self._build_tender_text(tender)
        text_lower = text.lower().strip()

        if not text_lower:
            return []

        query_embedding = self.embedder.embed_text(text)

        base_scores = np.dot(self.mfr_embeddings, query_embedding)
        final_scores = base_scores.copy()

        keyword_evidence_by_idx = {}

        for idx, manufacturer in enumerate(self.manufacturers):
            manufacturer_name = manufacturer.get("name", "")
            keywords = company_keywords.get(manufacturer_name, [])

            keyword_hits = self._find_keyword_hits(text_lower, keywords)
            keyword_boost = min(0.03 * len(keyword_hits), 0.15)

            final_scores[idx] += keyword_boost

            keyword_evidence_by_idx[idx] = {
                "keyword_hits": keyword_hits,
                "keyword_boost": round(float(keyword_boost), 4)
            }

        sorted_indices = np.argsort(final_scores)[::-1]
        top_indices = sorted_indices[:top_k]

        results = []

        for rank, idx in enumerate(top_indices, start=1):
            manufacturer = self.manufacturers[idx]
            base_score = float(base_scores[idx])
            final_score = float(final_scores[idx])
            keyword_evidence = keyword_evidence_by_idx.get(idx, {})

            results.append({
                "manufacturer_id": manufacturer.get("id"),
                "manufacturer_name": manufacturer.get("name"),
                "rank": rank,
                "base_semantic_score": round(base_score, 4),
                "score": round(final_score, 4),
                "confidence": self._get_confidence(final_score),
                "keyword_hits": keyword_evidence.get("keyword_hits", []),
                "keyword_boost": keyword_evidence.get("keyword_boost", 0.0),
                "reason_codes": self._build_reason_codes(
                    rank=rank,
                    score=final_score,
                    keyword_hits=keyword_evidence.get("keyword_hits", [])
                )
            })

        return results

    def match(self, tender):
        """
        Legacy method.

        Old behavior filtered before returning.
        New behavior still returns only decent matches for old pipeline compatibility,
        but internally uses match_topk().

        Later, pipeline/run.py should call match_topk() directly.
        """
        candidates = self.match_topk(tender, top_k=self.k)

        # Keep a loose threshold for old email behavior.
        # Do not use this method in the repaired decision core.
        return [
            c for c in candidates
            if c["score"] >= 0.60 or c["keyword_hits"]
        ]

    def _build_tender_text(self, tender):
        parts = [
            tender.get("title"),
            tender.get("raw_text"),
            tender.get("organization"),
            tender.get("department"),
            tender.get("product_category"),
            tender.get("category"),
        ]

        return " ".join(str(p) for p in parts if p)

    def _find_keyword_hits(self, text_lower, keywords):
        """
        Finds keyword hits using safer phrase matching.

        Avoids some substring accidents by using token-ish boundaries
        for short keywords, while still allowing phrase matches.
        """
        hits = []

        for kw in keywords:
            if not kw:
                continue

            kw_norm = str(kw).lower().strip()
            if not kw_norm:
                continue

            # For short terms like xrd, sem, pld, use boundaries.
            if len(kw_norm) <= 4 and kw_norm.replace("-", "").isalnum():
                pattern = r"(?<![a-z0-9])" + re.escape(kw_norm) + r"(?![a-z0-9])"
                if re.search(pattern, text_lower):
                    hits.append(kw)
            else:
                if kw_norm in text_lower:
                    hits.append(kw)

        # Deduplicate while preserving order
        seen = set()
        unique_hits = []

        for hit in hits:
            key = str(hit).lower()
            if key not in seen:
                seen.add(key)
                unique_hits.append(hit)

        return unique_hits[:20]

    def _build_reason_codes(self, rank, score, keyword_hits):
        reason_codes = []

        if rank == 1:
            reason_codes.append("MANUFACTURER_TOP1_MATCH")
        elif rank <= 3:
            reason_codes.append("MANUFACTURER_TOP3_MATCH")
        else:
            reason_codes.append("MANUFACTURER_TOPK_MATCH")

        if score >= 0.80:
            reason_codes.append("MANUFACTURER_SCORE_HIGH")
        elif score >= 0.65:
            reason_codes.append("MANUFACTURER_SCORE_MEDIUM")
        else:
            reason_codes.append("MANUFACTURER_SCORE_LOW_RELATIVE")

        if keyword_hits:
            reason_codes.append("MANUFACTURER_KEYWORD_EVIDENCE")

        return reason_codes

    def _get_confidence(self, score):
        if score >= 0.80:
            return "high"
        elif score >= 0.65:
            return "medium"
        else:
            return "low"