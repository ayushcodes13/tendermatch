"""
Manufacturer matching engine.

v2 behavior:
- Always returns top-k manufacturer candidates.
- Does not use semantic score as a hard gate.
- Uses manufacturer profile fields from data/manufacturers.json.
- Combines:
    1. embedding similarity
    2. keyword/product/category/alias evidence
    3. concept overlap evidence
    4. service compatibility evidence
    5. negative keyword penalties
- Keeps old match() method for backward compatibility.

Important:
match_topk() should be used by the repaired pipeline.
match() is only for legacy compatibility.
"""

import re
# pyrefly: ignore [missing-import]
import numpy as np

from matching.domain_keywords import company_keywords


class TenderMatcher:
    """
    Calculates manufacturer fit for a tender using:
    1. embedding similarity
    2. manufacturer-specific keyword evidence
    3. product/category/alias evidence
    4. concept evidence
    5. service compatibility
    6. negative keyword penalties

    match_topk() should be used by the new pipeline.
    match() is kept for legacy compatibility.
    """

    def __init__(self, embedder, k=5):
        self.embedder = embedder
        self.k = k

        self.manufacturers = embedder.get_manufacturers()
        self.mfr_embeddings = embedder.get_embeddings()

    def match_topk(self, tender, top_k=None):
        """
        Return top-k manufacturer candidates regardless of absolute score.

        Correct tenders can have mediocre absolute embedding scores but still
        have strong relative manufacturer evidence through product/category/
        concept hits.

        Args:
            tender (dict): normalized tender
            top_k (int): number of candidates to return

        Returns:
            list[dict]: ranked manufacturer candidates
        """
        if top_k is None:
            top_k = self.k

        text = self._build_tender_text(tender)
        text_lower = self._normalize_text(text)

        if not text_lower:
            return []

        query_embedding = self.embedder.embed_text(text)

        base_scores = np.dot(self.mfr_embeddings, query_embedding)
        final_scores = base_scores.copy()

        evidence_by_idx = {}

        for idx, manufacturer in enumerate(self.manufacturers):
            evidence = self._score_manufacturer_evidence(
                text_lower=text_lower,
                manufacturer=manufacturer,
            )

            final_scores[idx] += evidence["total_boost"]
            final_scores[idx] -= evidence["negative_penalty"]

            # Keep scores bounded. Embedding dot products are usually 0-1,
            # but boosts can push over 1.0.
            final_scores[idx] = max(0.0, min(float(final_scores[idx]), 1.0))

            evidence_by_idx[idx] = evidence

        sorted_indices = np.argsort(final_scores)[::-1]
        top_indices = sorted_indices[:top_k]

        results = []

        for rank, idx in enumerate(top_indices, start=1):
            manufacturer = self.manufacturers[idx]
            base_score = float(base_scores[idx])
            final_score = float(final_scores[idx])
            evidence = evidence_by_idx.get(idx, {})

            results.append({
                "manufacturer_id": manufacturer.get("id"),
                "manufacturer_name": manufacturer.get("name"),
                "rank": rank,

                "base_semantic_score": round(base_score, 4),
                "score": round(final_score, 4),
                "confidence": self._get_confidence(final_score),

                "keyword_hits": evidence.get("keyword_hits", []),
                "product_hits": evidence.get("product_hits", []),
                "category_hits": evidence.get("category_hits", []),
                "alias_hits": evidence.get("alias_hits", []),
                "concept_hits": evidence.get("concept_hits", []),
                "service_hits": evidence.get("service_hits", []),
                "negative_hits": evidence.get("negative_hits", []),

                "keyword_boost": evidence.get("keyword_boost", 0.0),
                "product_boost": evidence.get("product_boost", 0.0),
                "category_boost": evidence.get("category_boost", 0.0),
                "alias_boost": evidence.get("alias_boost", 0.0),
                "concept_boost": evidence.get("concept_boost", 0.0),
                "service_boost": evidence.get("service_boost", 0.0),
                "negative_penalty": evidence.get("negative_penalty", 0.0),
                "total_boost": evidence.get("total_boost", 0.0),

                "reason_codes": self._build_reason_codes(
                    rank=rank,
                    score=final_score,
                    evidence=evidence,
                ),
            })

        return results

    def match(self, tender):
        """
        Legacy method.

        Old behavior filtered before returning.
        New behavior still returns only decent matches for old pipeline
        compatibility, but internally uses match_topk().

        Later, pipeline/run.py should call match_topk() directly.
        """
        candidates = self.match_topk(tender, top_k=self.k)

        return [
            c for c in candidates
            if (
                c["score"] >= 0.60
                or c["keyword_hits"]
                or c["product_hits"]
                or c["category_hits"]
                or c["concept_hits"]
            )
        ]

    def _score_manufacturer_evidence(self, text_lower, manufacturer):
        """
        Scores structured evidence from one manufacturer profile.
        """
        manufacturer_name = manufacturer.get("name", "")

        keyword_pool = self._build_keyword_pool(manufacturer_name, manufacturer)
        product_pool = manufacturer.get("products", []) or []
        category_pool = manufacturer.get("product_categories", []) or []
        alias_pool = manufacturer.get("aliases", []) or []
        concept_pool = manufacturer.get("concepts", []) or []
        service_pool = manufacturer.get("service_keywords", []) or []
        negative_pool = manufacturer.get("negative_keywords", []) or []

        keyword_hits = self._find_phrase_hits(text_lower, keyword_pool)
        product_hits = self._find_phrase_hits(text_lower, product_pool)
        category_hits = self._find_phrase_hits(text_lower, category_pool)
        alias_hits = self._find_phrase_hits(text_lower, alias_pool)
        concept_hits = self._find_concept_hits(text_lower, concept_pool)
        service_hits = self._find_phrase_hits(text_lower, service_pool)
        negative_hits = self._find_phrase_hits(text_lower, negative_pool)

        keyword_boost = min(0.025 * len(keyword_hits), 0.15)
        product_boost = min(0.04 * len(product_hits), 0.16)
        category_boost = min(0.035 * len(category_hits), 0.14)
        alias_boost = min(0.025 * len(alias_hits), 0.08)
        concept_boost = min(0.035 * len(concept_hits), 0.18)

        # Service words alone should not create a strong manufacturer match.
        # They only help when there is already technical evidence.
        has_technical_evidence = bool(
            keyword_hits
            or product_hits
            or category_hits
            or concept_hits
        )

        if has_technical_evidence:
            service_boost = min(0.015 * len(service_hits), 0.05)
        else:
            service_boost = 0.0

        negative_penalty = min(0.08 * len(negative_hits), 0.24)

        total_boost = (
            keyword_boost
            + product_boost
            + category_boost
            + alias_boost
            + concept_boost
            + service_boost
        )

        return {
            "keyword_hits": keyword_hits,
            "product_hits": product_hits,
            "category_hits": category_hits,
            "alias_hits": alias_hits,
            "concept_hits": concept_hits,
            "service_hits": service_hits,
            "negative_hits": negative_hits,

            "keyword_boost": round(float(keyword_boost), 4),
            "product_boost": round(float(product_boost), 4),
            "category_boost": round(float(category_boost), 4),
            "alias_boost": round(float(alias_boost), 4),
            "concept_boost": round(float(concept_boost), 4),
            "service_boost": round(float(service_boost), 4),
            "negative_penalty": round(float(negative_penalty), 4),
            "total_boost": round(float(total_boost), 4),
        }

    def _build_keyword_pool(self, manufacturer_name, manufacturer):
        """
        Combines legacy domain_keywords.py with structured manufacturer fields.

        This is the important upgrade:
        manufacturers.json now becomes active matching data, not metadata.
        """
        pool = []

        pool.extend(company_keywords.get(manufacturer_name, []) or [])
        pool.extend(manufacturer.get("keywords", []) or [])
        pool.extend(manufacturer.get("products", []) or [])
        pool.extend(manufacturer.get("product_categories", []) or [])
        pool.extend(manufacturer.get("aliases", []) or [])

        return self._dedupe_terms(pool)

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

    def _normalize_text(self, text):
        text = str(text or "").lower()
        text = text.replace("/", " ")
        text = text.replace("_", " ")
        text = re.sub(r"[^a-z0-9\-\+\.\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _normalize_term(self, term):
        term = str(term or "").lower().strip()
        term = term.replace("/", " ")
        term = term.replace("_", " ")
        term = re.sub(r"[^a-z0-9\-\+\.\s]", " ", term)
        term = re.sub(r"\s+", " ", term)
        return term.strip()

    def _find_phrase_hits(self, text_lower, terms):
        """
        Finds phrase hits using safer matching.

        Short technical acronyms use boundaries:
        xrd, xrf, oes, pld, ald, pvd, rie, mbe, sps, aas

        Longer phrases use normalized substring matching.
        """
        hits = []

        for term in terms:
            if not term:
                continue

            term_norm = self._normalize_term(term)
            if not term_norm:
                continue

            if self._term_matches(text_lower, term_norm):
                hits.append(term)

        return self._dedupe_terms(hits)[:30]

    def _find_concept_hits(self, text_lower, concepts):
        """
        Matches concept IDs against tender text.

        Example:
        concept_id = "thin_film_deposition"
        variants:
        - "thin film deposition"
        - "thin-film deposition"
        - "thinfilmdeposition" is intentionally not used
        """
        hits = []

        for concept in concepts:
            concept_norm = self._normalize_term(concept)
            if not concept_norm:
                continue

            variants = {
                concept_norm,
                concept_norm.replace("_", " "),
                concept_norm.replace("-", " "),
            }

            # Since _normalize_term already replaces "_" with spaces,
            # add a direct version from raw concept too.
            raw = str(concept).lower().strip()
            variants.add(raw.replace("_", " "))
            variants.add(raw.replace("-", " "))

            for variant in variants:
                variant = self._normalize_term(variant)
                if variant and self._term_matches(text_lower, variant):
                    hits.append(concept)
                    break

        return self._dedupe_terms(hits)[:30]

    def _term_matches(self, text_lower, term_norm):
        if not term_norm:
            return False

        compact = term_norm.replace(" ", "")

        # Acronyms and short terms need boundaries.
        if len(compact) <= 4 and compact.replace("-", "").isalnum():
            pattern = r"(?<![a-z0-9])" + re.escape(term_norm) + r"(?![a-z0-9])"
            return bool(re.search(pattern, text_lower))

        return term_norm in text_lower

    def _dedupe_terms(self, terms):
        seen = set()
        unique = []

        for term in terms:
            key = str(term).lower().strip()
            if not key:
                continue

            if key not in seen:
                seen.add(key)
                unique.append(term)

        return unique

    def _build_reason_codes(self, rank, score, evidence):
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

        if evidence.get("keyword_hits"):
            reason_codes.append("MANUFACTURER_KEYWORD_EVIDENCE")

        if evidence.get("product_hits"):
            reason_codes.append("MANUFACTURER_PRODUCT_EVIDENCE")

        if evidence.get("category_hits"):
            reason_codes.append("MANUFACTURER_CATEGORY_EVIDENCE")

        if evidence.get("concept_hits"):
            reason_codes.append("MANUFACTURER_CONCEPT_EVIDENCE")

        if evidence.get("service_hits"):
            reason_codes.append("MANUFACTURER_SERVICE_COMPATIBLE")

        if evidence.get("negative_hits"):
            reason_codes.append("MANUFACTURER_NEGATIVE_KEYWORD_CONFLICT")

        return reason_codes

    def _get_confidence(self, score):
        if score >= 0.80:
            return "high"
        elif score >= 0.65:
            return "medium"
        else:
            return "low"