"""
Technical concept extraction.

This module detects positive technical evidence.
It should not decide final classification.

Important design:
- TECHNICAL_CONCEPTS is only a registry.
- Active relevance is controlled by manufacturers.json.
- A concept is only active if at least one active manufacturer references it.
"""

import json
import re
from functools import lru_cache
from pathlib import Path


TECHNICAL_CONCEPTS = {
    # -----------------------
    # Thin film / deposition
    # -----------------------
    "thin_film_deposition": {
        "weight": 35,
        "aliases": [
            "thin film",
            "thin-film",
            "thin film deposition",
            "thin-film deposition",
            "pvd",
            "physical vapor deposition",
            "vacuum deposition",
            "deposition system",
            "coating system",
            "coating unit",
            "thin film coating",
        ],
    },
    "pvd": {
        "weight": 38,
        "aliases": [
            "pvd",
            "physical vapor deposition",
            "physical vapour deposition",
            "pvd coating",
            "pvd system",
            "pvd deposition",
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
            "sputtering system",
        ],
    },
    "magnetron_sputtering": {
        "weight": 42,
        "aliases": [
            "magnetron sputtering",
            "magnetron sputter",
            "rf magnetron sputtering",
            "dc magnetron sputtering",
            "magnetron sputtering system",
        ],
    },
    "electron_beam_evaporation": {
        "weight": 35,
        "aliases": [
            "electron beam evaporation",
            "e-beam evaporation",
            "ebeam evaporation",
            "electron beam evaporator",
            "e-beam evaporator",
        ],
    },
    "thermal_evaporation": {
        "weight": 32,
        "aliases": [
            "thermal evaporation",
            "thermal evaporator",
            "boat evaporation",
            "thermal boat evaporation",
            "resistive evaporation",
        ],
    },
    "pld": {
        "weight": 38,
        "aliases": [
            "pld",
            "pulsed laser deposition",
            "pulsed laser deposition system",
        ],
    },
    "mbe": {
        "weight": 38,
        "aliases": [
            "mbe",
            "molecular beam epitaxy",
            "molecular beam epitaxy system",
        ],
    },
    "ald": {
        "weight": 38,
        "aliases": [
            "ald",
            "atomic layer deposition",
            "atomic layer deposition system",
        ],
    },
    "spatial_ald": {
        "weight": 42,
        "aliases": [
            "spatial ald",
            "spatial atomic layer deposition",
            "sald",
            "spatial ald coating",
            "spatial ald system",
        ],
    },
    "mocvd": {
        "weight": 40,
        "aliases": [
            "mocvd",
            "metal organic chemical vapor deposition",
            "metalorganic chemical vapor deposition",
            "metal organic cvd",
            "epitaxy reactor",
        ],
    },
    "epitaxial_growth": {
        "weight": 35,
        "aliases": [
            "epitaxial growth",
            "epitaxy",
            "epitaxial deposition",
            "epitaxial reactor",
        ],
    },

    # -----------------------
    # Etching / nanofab
    # -----------------------
    "icp_rie": {
        "weight": 45,
        "aliases": [
            "icp-rie",
            "icp rie",
            "icp reactive ion etching",
            "inductively coupled plasma reactive ion etching",
            "plasma etcher",
            "plasma etching",
            "dry etching",
        ],
    },
    "rie": {
        "weight": 35,
        "aliases": [
            "rie",
            "reactive ion etching",
            "reactive ion etcher",
            "plasma etching",
            "dry etching",
        ],
    },
    "ion_beam_etching": {
        "weight": 38,
        "aliases": [
            "ion beam etching",
            "ion beam milling",
            "ibe",
            "ion milling",
            "broad beam ion source",
        ],
    },
    "spin_coating": {
        "weight": 34,
        "aliases": [
            "spin coating",
            "spin coater",
            "spin coating system",
            "photoresist coating",
        ],
    },
    "spray_coating": {
        "weight": 30,
        "aliases": [
            "spray coating",
            "spray coater",
            "spray coating system",
            "photoresist spray coating",
        ],
    },
    "coater_developer": {
        "weight": 36,
        "aliases": [
            "coater developer",
            "coater and developer",
            "spin coater developer",
            "photoresist developer",
            "developer system",
            "wafer developer",
        ],
    },
    "wafer_processing": {
        "weight": 30,
        "aliases": [
            "wafer processing",
            "wafer coating",
            "wafer developer",
            "semiconductor wafer",
            "semiconductor processing",
        ],
    },
    "hmds": {
        "weight": 26,
        "aliases": [
            "hmds",
            "hmds oven",
            "hmds priming",
            "hexamethyldisilazane",
        ],
    },
    "hotplate": {
        "weight": 18,
        "aliases": [
            "hotplate",
            "hot plate",
            "bake plate",
            "soft bake",
            "post exposure bake",
        ],
    },

    # -----------------------
    # Vacuum / components
    # -----------------------
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

    # -----------------------
    # SPS / sintering
    # -----------------------
    "spark_plasma_sintering": {
        "weight": 45,
        "aliases": [
            "spark plasma sintering",
            "sps",
            "sps system",
            "spark plasma sintering system",
        ],
    },
    "field_assisted_sintering": {
        "weight": 40,
        "aliases": [
            "field assisted sintering",
            "field assisted sintering technique",
            "fast sintering",
            "fast system",
        ],
    },
    "sps": {
        "weight": 35,
        "aliases": [
            "sps",
            "spark plasma sintering",
        ],
    },
    "fast": {
        "weight": 30,
        "aliases": [
            "fast",
            "field assisted sintering technique",
        ],
    },
    "powder_metallurgy": {
        "weight": 28,
        "aliases": [
            "powder metallurgy",
            "powder consolidation",
            "sintering of powders",
            "metal powder sintering",
        ],
    },

    # -----------------------
    # Energy systems
    # -----------------------
    "fuel_cell_testing": {
        "weight": 42,
        "aliases": [
            "fuel cell test",
            "fuel cell testing",
            "fuel cell test station",
            "fuel cell test bench",
            "fuel cell system",
        ],
    },
    "electrolyzer_testing": {
        "weight": 40,
        "aliases": [
            "electrolyzer testing",
            "electrolyser testing",
            "electrolyzer test station",
            "electrolyser test station",
            "hydrogen electrolyzer",
        ],
    },
    "battery_testing": {
        "weight": 32,
        "aliases": [
            "battery testing",
            "battery test system",
            "battery cycler",
            "cell testing system",
            "energy storage testing",
        ],
    },
    "electrochemical_testing": {
        "weight": 30,
        "aliases": [
            "electrochemical testing",
            "electrochemical workstation",
            "potentiostat",
            "galvanostat",
        ],
    },
    "hydrogen_research": {
        "weight": 30,
        "aliases": [
            "hydrogen research",
            "green hydrogen",
            "hydrogen test station",
            "hydrogen generation",
        ],
    },

    # -----------------------
    # Nanoparticles / aerosol
    # -----------------------
    "nanoparticle_synthesis": {
        "weight": 38,
        "aliases": [
            "nanoparticle synthesis",
            "nanoparticle generation",
            "nanoparticle production",
            "nanomaterial synthesis",
        ],
    },
    "flame_spray_pyrolysis": {
        "weight": 42,
        "aliases": [
            "flame spray pyrolysis",
            "fsp",
            "flame aerosol synthesis",
        ],
    },
    "aerosol_measurement": {
        "weight": 32,
        "aliases": [
            "aerosol measurement",
            "aerosol instrument",
            "particle size measurement",
            "particle counter",
        ],
    },
    "particle_engineering": {
        "weight": 30,
        "aliases": [
            "particle engineering",
            "powder functionalization",
            "particle synthesis",
        ],
    },
    "nanopowder": {
        "weight": 28,
        "aliases": [
            "nanopowder",
            "nano powder",
            "nanopowder synthesis",
        ],
    },
    "cvd_functionalization": {
        "weight": 32,
        "aliases": [
            "cvd functionalization",
            "chemical vapor deposition functionalization",
            "powder functionalization",
        ],
    },

    # -----------------------
    # Analytical instruments still covered
    # -----------------------
    "nmr": {
        "weight": 35,
        "aliases": [
            "nmr",
            "nuclear magnetic resonance",
            "nmr analyzer",
            "nmr spectrometer",
        ],
    },
    "time_domain_nmr": {
        "weight": 40,
        "aliases": [
            "time-domain nmr",
            "time domain nmr",
            "td-nmr",
            "td nmr",
            "benchtop nmr",
        ],
    },
    "mercury_analyzer": {
        "weight": 38,
        "aliases": [
            "mercury analyzer",
            "mercury analyser",
            "mercury analysis system",
            "mercury determination",
        ],
    },
    "cold_vapor_aas": {
        "weight": 35,
        "aliases": [
            "cold vapor aas",
            "cold vapour aas",
            "cold vapor atomic absorption",
            "cold vapour atomic absorption",
        ],
    },
    "aas": {
        "weight": 32,
        "aliases": [
            "aas",
            "atomic absorption spectrometer",
            "atomic absorption spectroscopy",
            "atomic absorption",
        ],
    },
    "uv_vis": {
        "weight": 26,
        "aliases": [
            "uv-vis",
            "uv vis",
            "uv visible",
            "uv-visible spectrophotometer",
            "spectrophotometer",
        ],
    },
    "flame_photometer": {
        "weight": 25,
        "aliases": [
            "flame photometer",
            "flame photometry",
        ],
    },
    "elemental_analysis": {
        "weight": 25,
        "aliases": [
            "elemental analysis",
            "trace metal analysis",
            "metal ion analysis",
        ],
    },

    # -----------------------
    # Generic support concepts
    # Keep lower weight. These should not rescue alone.
    # -----------------------
    "materials_research": {
        "weight": 12,
        "aliases": [
            "materials research",
            "material science",
            "materials science",
            "advanced materials",
        ],
    },
    "material_characterization": {
        "weight": 16,
        "aliases": [
            "material characterization",
            "materials characterization",
            "characterization laboratory",
        ],
    },
    "semiconductor_deposition": {
        "weight": 30,
        "aliases": [
            "semiconductor deposition",
            "semiconductor thin film",
            "compound semiconductor",
            "semiconductor coating",
        ],
    },
}


def detect_concepts(tender, active_concept_ids=None):
    """
    Detect technical concepts in a tender.

    Args:
        tender (dict): normalized tender
        active_concept_ids (set/list/None):
            If provided, only these concept IDs are considered.
            This should come from active manufacturers in manufacturers.json.

    Returns:
        dict
    """
    text = build_search_text(tender)
    text_lower = normalize_text(text)

    if active_concept_ids is None:
        active_concept_ids = get_active_concept_ids_from_manufacturers()

    active_concept_ids = set(active_concept_ids or [])

    matches = []

    for concept_id, config in TECHNICAL_CONCEPTS.items():
        if active_concept_ids and concept_id not in active_concept_ids:
            continue

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
        "active_concept_count": len(active_concept_ids),
    }


@lru_cache(maxsize=1)
def get_active_concept_ids_from_manufacturers(path="data/manufacturers.json"):
    """
    Reads active manufacturer concepts from manufacturers.json.

    This prevents stale concepts from rescuing tenders after the client
    removes a manufacturer.
    """
    manufacturer_path = Path(path)

    if not manufacturer_path.exists():
        return set()

    with manufacturer_path.open("r", encoding="utf-8") as f:
        manufacturers = json.load(f)

    active_concepts = set()

    for manufacturer in manufacturers:
        if manufacturer.get("active") is False:
            continue

        for concept_id in manufacturer.get("concepts", []) or []:
            if concept_id in TECHNICAL_CONCEPTS:
                active_concepts.add(concept_id)

    return active_concepts


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
    text = text.replace("/", " ")
    text = text.replace("_", " ")
    text = re.sub(r"[^a-z0-9\-\+\.\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_alias_hits(text_lower, aliases):
    hits = []

    for alias in aliases:
        alias_norm = normalize_text(alias)
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
    compact = term.replace("-", "").replace(" ", "").replace(".", "")
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