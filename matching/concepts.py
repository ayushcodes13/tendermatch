
"""
Technical concept extraction.

This module detects positive technical evidence.
It should not decide final classification.
"""

import re


TECHNICAL_CONCEPTS = {
    "icp_rie": {
        "weight": 45,
        "aliases": [
            "icp-rie",
            "icp rie",
            "inductively coupled plasma reactive ion etching",
            "reactive ion etching",
            "plasma etcher",
            "plasma etching",
            "dry etching",
        ],
    },
    "thin_film_deposition": {
        "weight": 35,
        "aliases": [
            "thin film",
            "thin-film",
            "thin film deposition",
            "pvd",
            "physical vapor deposition",
            "vacuum deposition",
            "deposition system",
            "coating system",
        ],
    },
    "sputtering": {
        "weight": 40,
        "aliases": [
            "sputtering",
            "magnetron sputtering",
            "rf sputtering",
            "dc sputtering",
            "sputter coater",
            "sputter deposition",
        ],
    },
    "pld": {
        "weight": 38,
        "aliases": [
            "pld",
            "pulsed laser deposition",
        ],
    },
    "mbe": {
        "weight": 38,
        "aliases": [
            "mbe",
            "molecular beam epitaxy",
        ],
    },
    "xrd": {
        "weight": 35,
        "aliases": [
            "xrd",
            "x-ray diffractometer",
            "x ray diffractometer",
            "x-ray diffraction",
            "x ray diffraction",
        ],
    },
    "microscopy": {
        "weight": 30,
        "aliases": [
            "sem",
            "scanning electron microscope",
            "tem",
            "transmission electron microscope",
            "afm",
            "atomic force microscope",
        ],
    },
    "vacuum_system": {
        "weight": 28,
        "aliases": [
            "vacuum chamber",
            "uhv",
            "ultra high vacuum",
            "high vacuum",
            "vacuum system",
            "turbo molecular pump",
            "turbomolecular pump",
            "dry scroll pump",
            "cryopump",
            "cryo pump",
        ],
    },
    "rf_power": {
        "weight": 25,
        "aliases": [
            "rf power supply",
            "rf generator",
            "matching network",
            "plasma power supply",
        ],
    },
    "gas_flow_control": {
        "weight": 22,
        "aliases": [
            "mass flow controller",
            "mfc",
            "gas flow controller",
            "gas manifold",
        ],
    },
    "cleanroom_nanofab": {
        "weight": 30,
        "aliases": [
            "cleanroom",
            "nanofabrication",
            "lithography",
            "photo lithography",
            "photolithography",
            "mask aligner",
        ],
    },
    "spectroscopy": {
        "weight": 25,
        "aliases": [
            "spectrometer",
            "spectroscopy",
            "raman",
            "ftir",
            "ellipsometer",
            "uv-vis",
            "uv vis",
        ],
    },
    "thermal_processing": {
        "weight": 22,
        "aliases": [
            "furnace",
            "tube furnace",
            "muffle furnace",
            "rapid thermal annealing",
            "rta",
        ],
    },
    "glovebox": {
        "weight": 25,
        "aliases": [
            "glove box",
            "glovebox",
            "argon glovebox",
            "inert atmosphere glovebox",
        ],
    },
}


def detect_concepts(tender):
    text = build_search_text(tender)
    text_lower = normalize_text(text)

    matches = []

    for concept_id, config in TECHNICAL_CONCEPTS.items():
        aliases = config["aliases"]
        weight = config["weight"]

        alias_hits = find_alias_hits(text_lower, aliases)

        if alias_hits:
            matches.append({
                "concept_id": concept_id,
                "matched_aliases": alias_hits,
                "weight": weight,
                "reason_code": f"TECH_CONCEPT_{concept_id.upper()}",
            })

    return {
        "matched_concepts": matches,
        "concept_score": sum(m["weight"] for m in matches),
        "has_technical_concept": bool(matches),
    }


def build_search_text(tender):
    parts = [
        tender.get("title"),
        tender.get("raw_text"),
        tender.get("organization"),
        tender.get("department"),
        tender.get("product_category"),
        tender.get("category"),
    ]
    return " ".join(str(p) for p in parts if p)


def normalize_text(text):
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_alias_hits(text_lower, aliases):
    hits = []

    for alias in aliases:
        alias_norm = str(alias).lower().strip()
        if not alias_norm:
            continue

        if should_use_boundary_match(alias_norm):
            pattern = r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])"
            if re.search(pattern, text_lower):
                hits.append(alias)
        else:
            if alias_norm in text_lower:
                hits.append(alias)

    return dedupe_preserve_order(hits)


def should_use_boundary_match(term):
    compact = term.replace("-", "").replace(" ", "")
    return len(compact) <= 5 and compact.isalnum()


def dedupe_preserve_order(items):
    seen = set()
    out = []

    for item in items:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            out.append(item)

    return out