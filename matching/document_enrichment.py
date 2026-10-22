"""Source-grounded enrichment linking extracted official PDF requirements to matching.

Addresses Phase 4 (P4.3, P4.4):
1. Connects extracted native PDF requirements directly to manufacturer capability validation.
2. Identifies substantiated requirements vs explicit conflicts vs unverified unknowns.
3. Discloses complete document provenance: full verification vs partial vs needs_ocr.
"""

from __future__ import annotations

import json
from pathlib import Path
import re


def _load_default_manufacturers() -> list[dict]:
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "manufacturers.json"
    if catalog_path.is_file():
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return data.get("manufacturers", [])
        except Exception:
            return []
    return []


def _extract_text_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_-]+", text.lower()))


def enrich_tender_with_document_evidence(
    tender: dict,
    extraction: dict | None,
    manufacturer_catalog: list[dict] | None = None,
) -> dict:
    """Enrich tender matching and explanations with extracted document evidence.

    Discloses:
    - Document completeness (verified, partial, needs_ocr, unavailable, no_document).
    - Page-cited technical requirements mapped to manufacturer capabilities.
    - Explicit conflicts between mandatory requirements and manufacturer limitations.
    - Preserved unknowns requiring salesperson verification.
    """
    if manufacturer_catalog is None:
        manufacturer_catalog = _load_default_manufacturers()

    catalog_by_id = {
        m.get("id"): m for m in manufacturer_catalog if isinstance(m, dict) and m.get("id")
    }
    catalog_by_name = {
        m.get("name", "").lower(): m for m in manufacturer_catalog if isinstance(m, dict) and m.get("name")
    }

    if not extraction or not isinstance(extraction, dict):
        evidence = {
            "completeness": "no_document",
            "summary": "No official tender PDF was retrieved; review based solely on listing text.",
            "pages_reviewed": 0,
            "was_truncated": False,
            "verified_requirements": [],
            "conflicts": [],
            "unverified_requirements": [],
        }
        tender["document_evidence"] = evidence
        explanation = tender.setdefault("explanation", {})
        explanation["document_evidence"] = evidence
        return tender

    status = extraction.get("status")
    error_type = extraction.get("error_type")
    pages = extraction.get("pages", [])
    pages_reviewed = len(pages)
    fields = extraction.get("fields", {})

    if status == "needs_ocr":
        completeness = "needs_ocr"
        summary = "Tender PDF is scanned or image-based; native text extraction yielded no text. OCR or manual review required."
        was_truncated = False
    elif status == "text_truncated" or status == "page_limit_reached" or status == "partial":
        completeness = "partial"
        summary = f"Tender PDF partially reviewed ({pages_reviewed} pages); subsequent requirements unverified."
        was_truncated = True
    elif status == "extracted":
        completeness = "verified"
        summary = f"Official PDF verified natively across {pages_reviewed} page(s)."
        was_truncated = False
    else:
        completeness = "unavailable"
        summary = f"Document retrieval/parsing was unavailable ({error_type or status}); specifications unverified."
        was_truncated = False

    verified_requirements = []
    conflicts = []
    unverified_requirements = []

    # Analyze extracted fields against matched manufacturers
    matches = tender.get("matches", [])

    for field_name, items in fields.items():
        if not isinstance(items, list):
            continue
        for item in items:
            value = item.get("value", "")
            evidence_info = item.get("evidence", {})
            page = evidence_info.get("page")
            quote = evidence_info.get("quote", value)
            value_tokens = _extract_text_tokens(value)
            if not value_tokens:
                continue

            # Compare against each candidate manufacturer
            matched_for_any_maker = False
            for match in matches:
                maker_id = match.get("manufacturer_id")
                maker_name = match.get("manufacturer_name", "")
                profile = catalog_by_id.get(maker_id) or catalog_by_name.get(maker_name.lower())

                if not profile:
                    continue

                # Check negative keywords / limitations for explicit conflict
                exclusions = [str(k).lower() for k in profile.get("negative_keywords", [])]
                limitations = [str(k).lower() for k in profile.get("known_limitations", [])]

                for exclusion in exclusions + limitations:
                    excl_tokens = _extract_text_tokens(exclusion)
                    if excl_tokens and excl_tokens.issubset(value_tokens):
                        conflict_entry = {
                            "requirement": value,
                            "page": page,
                            "quote": quote,
                            "manufacturer": maker_name,
                            "conflict_reason": f"Conflicts with {maker_name} limitation: '{exclusion}'",
                        }
                        if conflict_entry not in conflicts:
                            conflicts.append(conflict_entry)

                # Check supported products and capabilities
                products = [str(p).lower() for p in profile.get("products", [])]
                services = [str(s).lower() for s in profile.get("offered_services", [])]
                keywords = [str(k).lower() for k in profile.get("keywords", [])]

                for capability in products + services + keywords:
                    cap_tokens = _extract_text_tokens(capability)
                    if len(cap_tokens) >= 2 and cap_tokens.issubset(value_tokens):
                        verified_entry = {
                            "requirement": value,
                            "page": page,
                            "quote": quote,
                            "manufacturer": maker_name,
                            "capability": capability,
                        }
                        if verified_entry not in verified_requirements:
                            verified_requirements.append(verified_entry)
                        matched_for_any_maker = True
                        break

            # If mandatory or technical requirement was not matched, record as unverified unknown
            if field_name in {"mandatory_requirements", "technical_specifications", "equipment_type"}:
                if not matched_for_any_maker:
                    unverified_str = f"{field_name.replace('_', ' ').capitalize()}: '{value}'"
                    if page:
                        unverified_str += f" (p. {page})"
                    if unverified_str not in unverified_requirements:
                        unverified_requirements.append(unverified_str)

    evidence = {
        "completeness": completeness,
        "summary": summary,
        "pages_reviewed": pages_reviewed,
        "was_truncated": was_truncated,
        "verified_requirements": verified_requirements,
        "conflicts": conflicts,
        "unverified_requirements": unverified_requirements,
    }

    tender["document_evidence"] = evidence
    explanation = tender.setdefault("explanation", {})
    explanation["document_evidence"] = evidence

    # Incorporate unverified requirements into explanation
    existing_unverified = explanation.setdefault("unverified_requirements", [])
    for u in unverified_requirements:
        if u not in existing_unverified:
            existing_unverified.append(u)

    # If explicit conflicts exist, flag review requirement
    if conflicts:
        tender["has_document_conflicts"] = True
        tender["agent_review_required"] = True
        if tender.get("category") == "high_signal":
            tender["category"] = "explore"
            tender["decision"] = "explore"
            tender["reason"] = (
                f"Demoted to explore: document conflicts detected ({conflicts[0]['conflict_reason']})"
            )

    return tender


def format_document_evidence_lines(evidence: dict) -> list[str]:
    """Format human-readable document evidence disclosure lines for reports/digests."""
    if not evidence:
        return ["   Document review: No official document analyzed."]

    lines = [f"   Document review: {evidence.get('summary', 'Unknown status')}"]

    conflicts = evidence.get("conflicts", [])
    if conflicts:
        lines.append("   ⚠️ Document conflicts detected:")
        for c in conflicts[:3]:
            page_str = f" (p. {c['page']})" if c.get("page") else ""
            lines.append(f"   - {c.get('requirement')}{page_str}: {c.get('conflict_reason')}")

    verified = evidence.get("verified_requirements", [])
    if verified:
        lines.append("   Verified document requirements:")
        for v in verified[:3]:
            page_str = f" (p. {v['page']})" if v.get("page") else ""
            lines.append(f"   - {v.get('requirement')}{page_str} (matches {v.get('manufacturer')} {v.get('capability')})")

    return lines
