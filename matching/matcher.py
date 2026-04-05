import numpy as np
from matching.domain_keywords import company_keywords


class TenderMatcher:
    def __init__(self, embedder, k=3):
        self.embedder = embedder
        self.k = k

        self.manufacturers = embedder.get_manufacturers()
        self.mfr_embeddings = embedder.get_embeddings()

    def match(self, tender):
        text = (tender.get("title") or "") + " " + (tender.get("raw_text") or "")
        text_lower = text.lower()

        query_embedding = self.embedder.embed_text(text)

        scores = np.dot(self.mfr_embeddings, query_embedding)

        # -----------------------
        # KEYWORD BOOST LAYER
        # -----------------------
        for idx, manufacturer in enumerate(self.manufacturers):
            manufacturer_name = manufacturer.get("name", "")
            keywords = company_keywords.get(manufacturer_name, [])

            keyword_hits = sum(
                1 for kw in keywords
                if kw.lower() in text_lower
            )

            if keyword_hits > 0:
                scores[idx] += min(0.03 * keyword_hits, 0.15)

        MIN_SCORE = 0.65

        # ✅ filter first
        valid_indices = np.where(scores >= MIN_SCORE)[0]

        if len(valid_indices) == 0:
            return []

        # ✅ sort only valid ones
        valid_scores = scores[valid_indices]
        sorted_idx = valid_indices[np.argsort(valid_scores)[::-1]]

        # ✅ take top K
        top_k_idx = sorted_idx[:self.k]

        results = []

        for idx in top_k_idx:
            score = float(scores[idx])
            manufacturer = self.manufacturers[idx]

            results.append({
                "manufacturer_id": manufacturer.get("id"),
                "manufacturer_name": manufacturer.get("name"),
                "score": round(score, 4),
                "confidence": self._get_confidence(score)
            })

        return results

    def _get_confidence(self, score):
        if score >= 0.80:
            return "high"
        elif score >= 0.68:
            return "medium"
        else:
            return "low"