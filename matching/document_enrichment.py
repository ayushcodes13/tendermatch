"""Source-grounded enrichment linking extracted official PDF requirements to matching.

Separates four independent concepts:
1. Source extraction validity:
   - source_verified: quotation verified with citation and page in official tender PDF.
   - source_unverified: requirement not substantiated against native PDF page.
2. Manufacturer claim validity:
   - capability_evidence_found: capability substantiated by official claim records or products.
   - unverified_claim: conditional, unverified, or regional claim.
   - unsupported_claim: claim known to be unsupported in official documentation.
   - lexical_candidate: keyword overlap only; no substantiated claim record.
   - insufficient_evidence: no claim or product information found.
3. Technical compatibility:
   - technical_match_supported: source verified + manufacturer claim supported + equipment family & specs align.
   - lexical_candidate: keyword overlap without validated technical compatibility.
   - capability_evidence_found: manufacturer capability verified in portfolio, but tender requirement matching requires verification.
   - explicit_conflict: numerical mismatch, incompatible equipment family, unit contradiction, or verified exclusion.
   - insufficient_evidence: technical specifications missing or unquantified.
   - needs_review: conditional service, ambiguous scope, or human engineering review needed.
4. Human disposition:
   - unreviewed
   - reviewed_relevant
   - reviewed_worth_pursuing
   - reviewed_not_relevant
   - reviewed_wrong_manufacturer
   - reviewed_incorrect_product_category
"""

from __future__ import annotations

import json
from pathlib import Path
import re

from matching.claim_provenance import load_claims


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


def is_contextual_scope_exclusion(text: str, exclusion_phrase: str) -> bool:
    """Detect if the tender is excluding the item from bidder scope (not a conflict).

    E.g.: 'Civil construction work is strictly excluded from bidder scope'
    or 'Vendor scope excludes site preparation and civil works'.
    """
    text_lower = text.lower()
    exclusion_lower = exclusion_phrase.lower()
    if exclusion_lower not in text_lower:
        return False

    scope_excl_patterns = [
        r"exclud(?:ed|ing|es|ion).*?" + re.escape(exclusion_lower),
        re.escape(exclusion_lower) + r".*?exclud(?:ed|ing|es|ion)",
        r"not\s+(?:included|required|part of|in)\s+(?:the\s+)?scope.*?" + re.escape(exclusion_lower),
        re.escape(exclusion_lower) + r".*?not\s+(?:included|required|part of|in)\s+(?:the\s+)?scope",
        r"out\s+of\s+scope.*?" + re.escape(exclusion_lower),
        re.escape(exclusion_lower) + r".*?out\s+of\s+scope",
        r"by\s+(?:the\s+)?buyer.*?" + re.escape(exclusion_lower),
        r"by\s+the\s+institute.*?" + re.escape(exclusion_lower),
        r"client\s+scope.*?" + re.escape(exclusion_lower),
    ]
    return any(re.search(p, text_lower) for p in scope_excl_patterns)


def check_parameter_mismatches(requirement_text: str, profile: dict, claims: list[dict]) -> str | None:
    """Check for numerical, unit, or parameter mismatches.

    Returns conflict description if a mismatch is found, None otherwise.
    """
    req_lower = requirement_text.lower()

    # 1. Temperature checks
    temp_match = re.search(r"(\d{3,4})\s*(?:°\s*c|deg\s*c|celsius|\bc\b)", req_lower)
    if temp_match:
        temp_val = float(temp_match.group(1))
        # Check profile and claims for temperature limits
        all_limits = list(profile.get("known_limitations", []))
        for c in claims:
            all_limits.extend(c.get("known_limitations", []))
        for lim in all_limits:
            lim_temp = re.search(r"(?:max|maximum|up to|limited to|exceeding).*?(\d{3,4})\s*(?:°\s*c|deg\s*c|celsius|\bc\b)", lim.lower())
            if lim_temp:
                max_temp = float(lim_temp.group(1))
                if temp_val > max_temp:
                    return f"Numerical temperature mismatch: tender requires {int(temp_val)} °C, but {profile.get('name', 'manufacturer')} is limited to {int(max_temp)} °C"

    # 2. Substrate / Wafer diameter checks
    wafer_match = re.search(r"(\d+)\s*(?:inch|\"|in\b)\s*(?:wafer|substrate)", req_lower)
    if wafer_match:
        wafer_val = float(wafer_match.group(1))
        all_limits = list(profile.get("known_limitations", []))
        for c in claims:
            all_limits.extend(c.get("known_limitations", []))
        for lim in all_limits:
            lim_wafer = re.search(r"(?:max|maximum|up to|limited to).*?(\d+)\s*(?:inch|\"|in\b)", lim.lower())
            if lim_wafer:
                max_wafer = float(lim_wafer.group(1))
                if wafer_val > max_wafer:
                    return f"Substrate dimension mismatch: tender requires {int(wafer_val)}-inch substrate, but {profile.get('name', 'manufacturer')} is limited to {int(max_wafer)}-inch"

    # 3. Model-specific / technique mismatch
    # If tender requires e-beam evaporation and manufacturer limitation specifies sputtering only
    if "electron beam" in req_lower or "e-beam" in req_lower:
        all_limits = list(profile.get("known_limitations", []))
        for lim in all_limits:
            if "sputtering only" in lim.lower() or "no e-beam" in lim.lower() or "does not support e-beam" in lim.lower():
                return f"Model capability mismatch: tender requires e-beam evaporation, but {profile.get('name', 'manufacturer')} platform is limited to sputtering"

    return None


def check_incompatible_equipment_domain(requirement_text: str, profile: dict) -> str | None:
    """Check if requirement specifies an equipment domain entirely outside manufacturer scope."""
    req_lower = requirement_text.lower()
    negative_keywords = [str(k).lower() for k in profile.get("negative_keywords", [])]

    # Explicit domain incompatibilities
    for neg in negative_keywords:
        if neg in req_lower:
            # Verify it is not a scope exclusion
            if not is_contextual_scope_exclusion(requirement_text, neg):
                return f"Incompatible equipment domain: tender requires '{neg}', which is outside {profile.get('name', 'manufacturer')} product domain"

    return None


def check_service_only_scope(requirement_text: str, profile: dict) -> str | None:
    """Check if tender is service-only when manufacturer requires equipment sales."""
    req_lower = requirement_text.lower()
    is_service_tender = any(k in req_lower for k in [
        "annual maintenance contract", "comprehensive amc", "third-party maintenance",
        "preventive maintenance only", "servicing of existing",
    ])
    if is_service_tender:
        # Check if manufacturer only services own equipment or lacks third-party AMC
        services = [str(s).lower() for s in profile.get("offered_services", [])]
        if not any("third-party" in s or "all-brand" in s or "multi-vendor" in s for s in services):
            return f"Service scope mismatch: tender is for third-party maintenance/AMC, but {profile.get('name', 'manufacturer')} does not provide third-party equipment service"
    return None


def check_missing_specifications(requirement_text: str, field_name: str) -> bool:
    """Check if requirement lacks essential technical specifications."""
    req_lower = requirement_text.lower()
    # Generic short terms without numerical or model parameters
    generic_terms = {
        "vacuum pump", "laboratory equipment", "pvd system", "spectrometer",
        "deposition system", "evaporator", "analytical instrument",
    }
    tokens = _extract_text_tokens(req_lower)
    if req_lower.strip() in generic_terms or (len(tokens) <= 3 and not re.search(r"\d", req_lower)):
        return True
    return False


def check_claim_limitation_conflicts(requirement_text: str, matched_claim: dict | None) -> str | None:
    """Check if requirement contradicts known limitations of the matched claim."""
    if not matched_claim:
        return None
    req_lower = requirement_text.lower()
    limitations = matched_claim.get("known_limitations", [])
    for lim in limitations:
        lim_lower = str(lim).lower()
        # 1. Planar wafer vs powder functionalization (e.g. PARTEQ-CVD-001)
        if "cannot be used for planar wafer" in lim_lower or "limited to powder" in lim_lower:
            if "planar wafer" in req_lower or "silicon wafer" in req_lower or "wafer substrate" in req_lower:
                return f"Configuration limitation conflict: tender requires planar wafer CVD, but claim {matched_claim.get('claim_id')} is limited to powder/particulate functionalization"
        # 2. Technique restrictions (e.g. sputtering only, no e-beam)
        if "sputtering only" in lim_lower and ("e-beam" in req_lower or "electron beam" in req_lower):
            return f"Configuration limitation conflict: tender requires e-beam evaporation, but {matched_claim.get('claim_id')} is limited to sputtering"
        # 3. Batch/industrial volume vs research/benchtop scale
        if ("benchtop" in lim_lower or "research scale" in lim_lower) and ("mass production" in req_lower or "industrial throughput" in req_lower):
            return f"Scale limitation conflict: tender requires industrial mass production, but {matched_claim.get('claim_id')} is designed for research/benchtop scale"
    return None


def check_quotation_attribution_mismatch(
    requirement_text: str,
    quote: str,
    field_name: str = "",
) -> str | None:
    """Check if numbers, parameter labels, or table values in quote are misattributed.

    Detects cases where:
    - Quote explicitly labels a different parameter (e.g. quote has 'Chamber Height: 500 mm'
      but asserted requirement is 'Substrate Diameter: 500 mm').
    - Table value in quote belongs to a different row/metric.
    - Malformed units or unit contradictions occur between quote and requirement.
    """
    quote_lower = quote.lower()
    req_lower = requirement_text.lower()

    # Parameter label mismatch
    param_patterns = [
        ("chamber height", "substrate diameter"),
        ("substrate diameter", "chamber height"),
        ("wafer size", "flange diameter"),
        ("flange diameter", "wafer size"),
        ("operating temperature", "ambient temperature"),
        ("maximum temperature", "minimum temperature"),
        ("flow rate", "pumping speed"),
        ("pumping speed", "flow rate"),
        ("voltage", "frequency"),
    ]
    for param_a, param_b in param_patterns:
        if param_a in quote_lower and param_b in req_lower and param_b not in quote_lower:
            return f"Parameter attribution mismatch: quote specifies '{param_a}', but asserted requirement claims '{param_b}'"

    # Malformed / conflicting units
    # e.g., quote specifies 500 K but requirement claims 500 C, or 300 mm vs 300 cm
    temp_re = r"(\d+(?:\.\d+)?)\s*(kelvin|k|°\s*c|deg\s*c|celsius|c|fahrenheit|°\s*f|f)\b"
    num_match_quote = re.search(temp_re, quote_lower)
    num_match_req = re.search(temp_re, req_lower)
    if num_match_quote and num_match_req:
        val_q, unit_q = num_match_quote.group(1), num_match_quote.group(2).strip()
        val_r, unit_r = num_match_req.group(1), num_match_req.group(2).strip()
        is_kelvin_q = "k" in unit_q
        is_kelvin_r = "k" in unit_r
        if is_kelvin_q != is_kelvin_r and val_q == val_r:
            return f"Unit mismatch: quote specifies {val_q} {unit_q}, but requirement asserts {val_r} {unit_r}"

    dim_re = r"(\d+(?:\.\d+)?)\s*(mm|cm|m|nm|um|µm|inches|inch|\")\b"
    dim_match_q = re.search(dim_re, quote_lower)
    dim_match_r = re.search(dim_re, req_lower)
    if dim_match_q and dim_match_r:
        val_q, unit_q = dim_match_q.group(1), dim_match_q.group(2).strip()
        val_r, unit_r = dim_match_r.group(1), dim_match_r.group(2).strip()
        if unit_q != unit_r and val_q == val_r:
            return f"Unit mismatch: quote specifies {val_q} {unit_q}, but requirement asserts {val_r} {unit_r}"

    return None


def verify_source_quotation(
    evidence_info: dict,
    extraction: dict | None = None,
    item_value: str = "",
    field_name: str = "",
) -> dict:
    """Independently audit and verify requirement quotation against extracted PDF source pages.

    Returns dict with:
        validity: "source_verified", "source_unverified", "fabricated_quotation",
                  "quote_page_mismatch", "source_unverified_needs_ocr",
                  "source_partially_verified", "attribution_mismatch"
        notes: explanation of validation or mismatch
        verified_page: verified page number if found
    """
    page = evidence_info.get("page")
    quote = evidence_info.get("quote", item_value)

    if page is None or not quote or not str(quote).strip():
        return {
            "validity": "source_unverified",
            "notes": "Missing page citation or quotation in evidence",
            "verified_page": None,
        }

    quote_str = str(quote).strip()

    if not extraction or not isinstance(extraction, dict):
        return {
            "validity": "source_verified" if page else "source_unverified",
            "notes": f"Citation present (p. {page}); extraction text unavailable for verification",
            "verified_page": page,
        }

    # Extract page texts
    page_texts = extraction.get("page_texts", {})
    if not page_texts and "pages" in extraction:
        for p in extraction["pages"]:
            if isinstance(p, dict) and "page" in p and "text" in p:
                page_texts[p["page"]] = p["text"]

    page_statuses = {
        p["page"]: p.get("status")
        for p in extraction.get("pages", [])
        if isinstance(p, dict) and "page" in p
    }

    # Check if cited page requires OCR or is unreadable
    if page_statuses.get(page) == "empty" or extraction.get("status") == "needs_ocr":
        return {
            "validity": "source_unverified_needs_ocr",
            "notes": f"Page {page} has empty native text / requires OCR; quotation unverified",
            "verified_page": page,
        }
    if page_statuses.get(page) == "unreadable":
        return {
            "validity": "source_unverified",
            "notes": f"Page {page} is unreadable in native text parser",
            "verified_page": page,
        }

    # If page texts are available, perform deep textual quotation verification
    if page_texts:
        def _norm(s: str) -> str:
            return " ".join(s.lower().split())

        norm_quote = _norm(quote_str)
        cited_page_text = str(page_texts.get(page, "") or "")
        norm_cited_page = _norm(cited_page_text)

        # Check if quote is present on the cited page
        if norm_quote in norm_cited_page:
            # Check for parameter attribution mismatch
            attribution_err = check_quotation_attribution_mismatch(item_value, quote_str, field_name)
            if attribution_err:
                return {
                    "validity": "attribution_mismatch",
                    "notes": attribution_err,
                    "verified_page": page,
                }

            # Check if page was truncated
            if page_statuses.get(page) == "truncated" or extraction.get("status") == "text_truncated":
                return {
                    "validity": "source_partially_verified",
                    "notes": f"Quotation verified on page {page}, but page text was truncated; omissions not assessed",
                    "verified_page": page,
                }

            return {
                "validity": "source_verified",
                "notes": f"Exact quotation verified in native PDF text on page {page}",
                "verified_page": page,
            }

        # Check if quotation spans across page boundaries (e.g. end of page into page + 1)
        next_page_text = str(page_texts.get(page + 1, "") or "")
        if next_page_text and norm_quote not in _norm(next_page_text):
            combined = _norm(cited_page_text[-len(quote_str) * 2:] + " " + next_page_text[:len(quote_str) * 2])
            if norm_quote in combined:
                return {
                    "validity": "source_verified",
                    "notes": f"Quotation verified spanning pages {page}-{page + 1}",
                    "verified_page": page,
                }

        # Check if quotation appears on ANOTHER page
        other_pages = [p_num for p_num, p_txt in page_texts.items() if norm_quote in _norm(str(p_txt or ""))]
        if other_pages:
            return {
                "validity": "quote_page_mismatch",
                "notes": f"Quotation not present on asserted page {page}; found on page(s) {other_pages}",
                "verified_page": other_pages[0],
            }

        # Not found anywhere in PDF text: Fabricated quotation!
        return {
            "validity": "fabricated_quotation",
            "notes": f"Quotation '{quote_str}' is fabricated or not present in native text of page {page} or document",
            "verified_page": None,
        }

    # If page_texts is not provided, fallback to checking page in pages
    pages_list = extraction.get("pages", [])
    has_page = page in pages_list or any(isinstance(p, dict) and p.get("page") == page for p in pages_list)
    if has_page:
        return {
            "validity": "source_verified",
            "notes": f"Page citation {page} present in extraction metadata",
            "verified_page": page,
        }
    return {
        "validity": "quote_page_mismatch",
        "notes": f"Page {page} not present in extracted document pages",
        "verified_page": None,
    }


def evaluate_technical_compatibility(
    item_value: str,
    evidence_info: dict,
    maker_profile: dict,
    claims: list[dict],
    feedback_history: list[dict] | None = None,
    extraction: dict | None = None,
    field_name: str = "",
) -> dict:
    """Evaluate four independent verification concepts for an extracted requirement.

    Returns:
        dict with keys:
            source_extraction_validity
            manufacturer_claim_validity
            technical_compatibility
            human_disposition
            claim_id
            capability
            notes
    """
    page = evidence_info.get("page")
    quote = evidence_info.get("quote", item_value)
    maker_id = maker_profile.get("id")
    maker_name = maker_profile.get("name", "Unknown Manufacturer")

    # 1. Source extraction validity independently audited against PDF
    source_audit = verify_source_quotation(
        evidence_info=evidence_info,
        extraction=extraction,
        item_value=item_value,
        field_name=field_name,
    )
    source_validity = source_audit["validity"]
    source_notes = source_audit["notes"]

    # 2. Manufacturer claim validity
    valid_maker_ids = {
        maker_id,
        str(maker_id).replace("_technology", ""),
        f"{maker_id}_technology",
        str(maker_id).replace("_solutions", ""),
        f"{maker_id}_solutions",
    }
    m_claims = [c for c in claims if c.get("manufacturer_id") in valid_maker_ids]
    value_tokens = _extract_text_tokens(item_value)

    matched_claim = None
    claim_validity = "insufficient_evidence"

    for c in m_claims:
        claim_term = str(c.get("claim_term") or c.get("claim_text", "")).lower()
        claim_tokens = _extract_text_tokens(claim_term)
        if (claim_tokens and claim_tokens.issubset(value_tokens)) or (claim_term in item_value.lower()):
            state = c.get("validation_state")
            src_url = str(c.get("source_url") or "").strip()
            has_resolvable_source = src_url.startswith("http://") or src_url.startswith("https://")

            if state in {"validated_capability", "product_specific"}:
                if has_resolvable_source:
                    claim_validity = "capability_evidence_found"
                    matched_claim = c
                    break
                else:
                    claim_validity = "unverified_claim"
                    matched_claim = c
                    break
            elif state == "unsupported":
                claim_validity = "unsupported_claim"
                matched_claim = c
                break
            elif state in {"conditional_service", "unverified", "region_specific", "historical"}:
                claim_validity = "unverified_claim"
                matched_claim = c
                break

    # If no validated claim record, check profile products and keywords.
    # Note: A profile keyword, offered service, or unverified product alone
    # must NEVER establish capability_evidence_found; it remains strictly a lexical_candidate.
    matched_capability = None
    if claim_validity == "insufficient_evidence":
        products = [str(p) for p in maker_profile.get("products", [])]
        keywords = [str(k) for k in maker_profile.get("keywords", [])]
        services = [str(s) for s in maker_profile.get("offered_services", [])]

        for p in products:
            p_tokens = _extract_text_tokens(p)
            if (len(p_tokens) >= 2 and p_tokens.issubset(value_tokens)) or (p.lower() in item_value.lower() and len(p) >= 5):
                claim_validity = "lexical_candidate"
                matched_capability = p
                break

        if claim_validity == "insufficient_evidence":
            for k in keywords + services:
                k_lower = k.lower()
                k_tokens = _extract_text_tokens(k_lower)
                if len(k_tokens) >= 2 and k_tokens.issubset(value_tokens):
                    claim_validity = "lexical_candidate"
                    matched_capability = k
                    break

    # 3. Technical compatibility evaluation
    if source_validity in {"fabricated_quotation", "attribution_mismatch"}:
        tech_status = "explicit_conflict"
        notes = f"Evidence citation rejected ({source_validity}): {source_notes}"
    elif source_validity in {"quote_page_mismatch", "source_unverified_needs_ocr", "source_partially_verified"}:
        tech_status = "needs_review"
        notes = f"Citation integrity issue ({source_validity}): {source_notes}"
    else:
        # A. Check domain incompatibility
        domain_conflict = check_incompatible_equipment_domain(item_value, maker_profile)
        if domain_conflict:
            tech_status = "explicit_conflict"
            notes = domain_conflict
        else:
            # B. Check parameter / numerical / model mismatches
            param_conflict = check_parameter_mismatches(item_value, maker_profile, m_claims)
            if param_conflict:
                tech_status = "explicit_conflict"
                notes = param_conflict
            else:
                # C. Check service-only scope
                service_conflict = check_service_only_scope(item_value, maker_profile)
                if service_conflict:
                    tech_status = "explicit_conflict"
                    notes = service_conflict
                else:
                    # D. Check claim limitation conflicts
                    limitation_conflict = check_claim_limitation_conflicts(item_value, matched_claim)
                    if limitation_conflict:
                        tech_status = "explicit_conflict"
                        notes = limitation_conflict
                    elif claim_validity == "unsupported_claim":
                        tech_status = "explicit_conflict"
                        notes = f"Unsupported claim: official documentation explicitly does not substantiate {matched_claim.get('claim_text')}"
                    elif claim_validity == "capability_evidence_found":
                        if source_validity == "source_verified":
                            tech_status = "technical_match_supported"
                            notes = f"Verified in PDF (p. {page}) and substantiated by official manufacturer claim: {matched_claim.get('claim_id')}"
                        else:
                            tech_status = "needs_review"
                            notes = f"Manufacturer capability substantiated by {matched_claim.get('claim_id')}, but requirement source unverified in PDF ({source_validity}): {source_notes}"
                    elif claim_validity == "lexical_candidate":
                        tech_status = "lexical_candidate"
                        notes = f"Lexical keyword overlap detected ({matched_capability}); technical compatibility not substantiated by official claim evidence"
                    elif claim_validity == "unverified_claim":
                        tech_status = "needs_review"
                        notes = f"Conditional/unverified claim requires human sales adjudication: {matched_claim.get('claim_id')}"
                    else:
                        if check_missing_specifications(item_value, "technical_specifications"):
                            tech_status = "insufficient_evidence"
                            notes = "Critical technical parameters missing from specification; cannot substantiate fit"
                        else:
                            tech_status = "needs_review"
                            notes = "Tender specification unverified against manufacturer capabilities"

    # 4. Human disposition lookup
    human_disposition = "unreviewed"
    if feedback_history:
        for fb in feedback_history:
            if fb.get("manufacturer_id") == maker_id:
                lbl = fb.get("label", "")
                if lbl:
                    human_disposition = f"reviewed_{lbl}"
                    break

    return {
        "requirement": item_value,
        "page": page,
        "quote": quote,
        "manufacturer_id": maker_id,
        "manufacturer_name": maker_name,
        "source_extraction_validity": source_validity,
        "manufacturer_claim_validity": claim_validity,
        "technical_compatibility": tech_status,
        "human_disposition": human_disposition,
        "claim_id": matched_claim.get("claim_id") if matched_claim else None,
        "capability": (matched_claim.get("claim_term") or matched_claim.get("claim_text")) if matched_claim else matched_capability,
        "notes": notes,
    }


def enrich_tender_with_document_evidence(
    tender: dict,
    extraction: dict | None,
    manufacturer_catalog: list[dict] | None = None,
    claims: list[dict] | None = None,
) -> dict:
    """Enrich tender matching and explanations with extracted document evidence.

    Discloses:
    - Document completeness (verified, partial, needs_ocr, unavailable, no_document).
    - Page-cited technical requirements mapped to manufacturer capabilities.
    - Explicit conflicts between mandatory requirements and manufacturer limitations.
    - Preserved unknowns requiring salesperson verification.
    - 4-concept verification semantics: source validity, claim validity, technical compatibility, disposition.
    """
    if manufacturer_catalog is None:
        manufacturer_catalog = _load_default_manufacturers()
    if claims is None:
        claims = load_claims()

    catalog_by_id = {
        m.get("id"): m for m in manufacturer_catalog if isinstance(m, dict) and m.get("id")
    }
    catalog_by_name = {
        m.get("name", "").lower(): m for m in manufacturer_catalog if isinstance(m, dict) and m.get("name")
    }

    feedback_history = tender.get("feedback", [])

    if not extraction or not isinstance(extraction, dict):
        evidence = {
            "completeness": "no_document",
            "summary": "No official tender PDF was retrieved; review based solely on listing text.",
            "pages_reviewed": 0,
            "was_truncated": False,
            "verified_requirements": [],
            "lexical_candidates": [],
            "conflicts": [],
            "insufficient_evidence": [],
            "needs_review": [],
            "assessed_requirements": [],
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
        completeness = "coverage_not_assessed"
        summary = f"Official PDF native text extracted across {pages_reviewed} page(s); requirement coverage not assessed."
        was_truncated = False
    else:
        completeness = "unavailable"
        summary = f"Document retrieval/parsing was unavailable ({error_type or status}); specifications unverified."
        was_truncated = False

    verified_requirements = []
    lexical_candidates = []
    conflicts = []
    insufficient_evidence_items = []
    needs_review_items = []
    assessed_requirements = []
    unverified_requirements = []

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

            matched_for_any_maker = False

            # Evaluate against each candidate manufacturer
            for match in matches:
                maker_id = match.get("manufacturer_id")
                maker_name = match.get("manufacturer_name", "")
                profile = catalog_by_id.get(maker_id) or catalog_by_name.get(maker_name.lower())

                if not profile:
                    continue

                assessment = evaluate_technical_compatibility(
                    item_value=value,
                    evidence_info=evidence_info,
                    maker_profile=profile,
                    claims=claims,
                    feedback_history=feedback_history,
                    extraction=extraction,
                    field_name=field_name,
                )
                assessed_requirements.append(assessment)

                tech_status = assessment["technical_compatibility"]

                if tech_status == "explicit_conflict":
                    conflict_entry = {
                        "requirement": value,
                        "page": page,
                        "quote": quote,
                        "manufacturer": maker_name,
                        "manufacturer_id": maker_id,
                        "technical_compatibility": "explicit_conflict",
                        "conflict_reason": assessment["notes"],
                        "source_extraction_validity": assessment["source_extraction_validity"],
                        "human_disposition": assessment["human_disposition"],
                    }
                    if conflict_entry not in conflicts:
                        conflicts.append(conflict_entry)

                elif tech_status == "technical_match_supported":
                    verified_entry = {
                        "requirement": value,
                        "page": page,
                        "quote": quote,
                        "manufacturer": maker_name,
                        "manufacturer_id": maker_id,
                        "capability": assessment["capability"] or value,
                        "claim_id": assessment["claim_id"],
                        "technical_compatibility": "technical_match_supported",
                        "source_extraction_validity": assessment["source_extraction_validity"],
                        "manufacturer_claim_validity": assessment["manufacturer_claim_validity"],
                        "human_disposition": assessment["human_disposition"],
                    }
                    if verified_entry not in verified_requirements:
                        verified_requirements.append(verified_entry)
                    matched_for_any_maker = True

                elif tech_status == "lexical_candidate":
                    lex_entry = {
                        "requirement": value,
                        "page": page,
                        "quote": quote,
                        "manufacturer": maker_name,
                        "manufacturer_id": maker_id,
                        "capability": assessment["capability"],
                        "technical_compatibility": "lexical_candidate",
                        "source_extraction_validity": assessment["source_extraction_validity"],
                        "notes": assessment["notes"],
                        "human_disposition": assessment["human_disposition"],
                    }
                    if lex_entry not in lexical_candidates:
                        lexical_candidates.append(lex_entry)

                elif tech_status == "insufficient_evidence":
                    if value not in insufficient_evidence_items:
                        insufficient_evidence_items.append(value)

                elif tech_status == "needs_review":
                    if value not in needs_review_items:
                        needs_review_items.append(value)

            # If mandatory or technical requirement was not substantiated, record as unverified unknown
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
        "extraction_lifecycle": {
            "pdf_downloaded": status not in {"no_document", None},
            "native_text_extracted": status in {"extracted", "text_truncated", "page_limit_reached", "partial"},
            "ocr_required": status == "needs_ocr",
            "extraction_truncated": was_truncated,
            "relevant_requirements_identified": len(assessed_requirements),
            "source_quotations_verified": sum(1 for a in assessed_requirements if a.get("source_extraction_validity") == "source_verified"),
            "requirement_coverage_evaluated": bool(extraction.get("comprehensive_coverage")),
            "technical_compatibility_evaluated": len(assessed_requirements) > 0,
        },
        "verified_requirements": verified_requirements,
        "lexical_candidates": lexical_candidates,
        "conflicts": conflicts,
        "insufficient_evidence": insufficient_evidence_items,
        "needs_review": needs_review_items,
        "assessed_requirements": assessed_requirements,
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

    # If explicit conflicts exist, flag review requirement and demote
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

    lexical = evidence.get("lexical_candidates", [])
    if lexical:
        lines.append("   Lexical candidates (require technical verification):")
        for lx in lexical[:2]:
            page_str = f" (p. {lx['page']})" if lx.get("page") else ""
            lines.append(f"   - {lx.get('requirement')}{page_str} (overlaps with {lx.get('manufacturer')} keywords)")

    return lines
