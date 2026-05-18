"""
Technical concept extraction.

This module detects positive technical evidence from tenders.

Important:
- This module should NOT make final classification decisions.
- It only extracts concept evidence.
- Final decisions should happen in scoring.py / decision.py.

Design:
1. Load active concept IDs from data/manufacturers.json.
2. Detect only concepts supported by active manufacturers.
3. Suppress overlapping concepts to avoid score inflation.
4. Mark generic/support-only concepts so they cannot rescue tenders alone.
"""

import json
import re
from pathlib import Path


# ---------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANUFACTURERS_PATH = PROJECT_ROOT / "data" / "manufacturers.json"


# ---------------------------------------------------------------------
# TECHNICAL CONCEPTS
# ---------------------------------------------------------------------
# Keep this broader than the current client list.
# Active filtering happens dynamically from manufacturers.json.
#
# Rule:
# - If a concept is not present in active manufacturers.json, it will not fire.
# - So stale concepts like XRD will automatically disappear if no manufacturer uses them.
# ---------------------------------------------------------------------

TECHNICAL_CONCEPTS = {
    # ---------------------------------------------------------
    # Etching / plasma / nanofab
    # ---------------------------------------------------------
    "icp_rie": {
        "weight": 45,
        "support_only": False,
        "aliases": [
            "icp-rie",
            "icp rie",
            "inductively coupled plasma reactive ion etching",
            "inductively coupled plasma rie",
            "plasma reactive ion etching",
            "reactive ion etching",
            "plasma etcher",
            "plasma etching",
            "dry etching",
        ],
    },
    "rie": {
        "weight": 35,
        "support_only": False,
        "aliases": [
            "rie",
            "reactive ion etching",
            "plasma etching",
            "dry etching",
            "plasma etcher",
        ],
    },
    "ion_beam_etching": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "ion beam etching",
            "ion beam milling",
            "ibe",
            "ion milling",
            "broad ion beam",
        ],
    },

    # ---------------------------------------------------------
    # Thin film / deposition
    # ---------------------------------------------------------
    "thin_film_deposition": {
        "weight": 35,
        "support_only": False,
        "aliases": [
            "thin film",
            "thin-film",
            "thin film deposition",
            "thin-film deposition",
            "deposition system",
            "coating system",
            "vacuum deposition",
            "physical vapor deposition",
            "pvd",
        ],
    },
    "pvd": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "pvd",
            "physical vapor deposition",
            "physical vapour deposition",
            "vacuum deposition",
            "pvd coating",
            "pvd system",
        ],
    },
    "sputtering": {
        "weight": 40,
        "support_only": False,
        "aliases": [
            "sputtering",
            "sputter deposition",
            "sputter coater",
            "sputtering system",
        ],
    },
    "magnetron_sputtering": {
        "weight": 42,
        "support_only": False,
        "aliases": [
            "magnetron sputtering",
            "rf magnetron sputtering",
            "dc magnetron sputtering",
            "magnetron sputter",
            "magnetron sputter coating",
        ],
    },
    "electron_beam_evaporation": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "electron beam evaporation",
            "e-beam evaporation",
            "ebeam evaporation",
            "e beam evaporator",
            "electron beam evaporator",
        ],
    },
    "thermal_evaporation": {
        "weight": 34,
        "support_only": False,
        "aliases": [
            "thermal evaporation",
            "thermal evaporator",
            "resistive evaporation",
            "vacuum evaporation",
        ],
    },
    "pld": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "pld",
            "pulsed laser deposition",
            "pulsed laser deposition system",
        ],
    },
    "mbe": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "mbe",
            "molecular beam epitaxy",
            "molecular beam epitaxy system",
        ],
    },
    "mocvd": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "mocvd",
            "metal organic chemical vapor deposition",
            "metal organic chemical vapour deposition",
            "metalorganic chemical vapor deposition",
            "metalorganic chemical vapour deposition",
        ],
    },
    "ald": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "ald",
            "atomic layer deposition",
            "atomic layer deposition system",
            "ald coating",
        ],
    },
    "spatial_ald": {
        "weight": 42,
        "support_only": False,
        "aliases": [
            "spatial ald",
            "spatial atomic layer deposition",
            "spatial ald coating",
            "sald",
        ],
    },
    "semiconductor_deposition": {
        "weight": 25,
        "support_only": True,
        "aliases": [
            "semiconductor deposition",
            "semiconductor coating",
            "semiconductor thin film",
            "compound semiconductor",
        ],
    },
    "epitaxial_growth": {
        "weight": 32,
        "support_only": False,
        "aliases": [
            "epitaxial growth",
            "epitaxy",
            "epitaxial deposition",
            "epitaxial layer",
        ],
    },

    # ---------------------------------------------------------
    # Spin / spray / coating processing
    # ---------------------------------------------------------
    "spin_coating": {
        "weight": 32,
        "support_only": False,
        "aliases": [
            "spin coating",
            "spin coater",
            "photoresist spin coater",
            "spin coating system",
        ],
    },
    "spray_coating": {
        "weight": 32,
        "support_only": False,
        "aliases": [
            "spray coating",
            "spray coater",
            "spray coating system",
            "thin film spray coating",
        ],
    },
    "coater_developer": {
        "weight": 30,
        "support_only": False,
        "aliases": [
            "coater developer",
            "coater and developer",
            "photoresist coater",
            "resist coater developer",
        ],
    },
    "hmds": {
        "weight": 25,
        "support_only": False,
        "aliases": [
            "hmds",
            "hmds oven",
            "hexamethyldisilazane",
            "adhesion promoter",
        ],
    },
    "hotplate": {
        "weight": 20,
        "support_only": True,
        "aliases": [
            "hotplate",
            "hot plate",
            "precision hotplate",
            "bake plate",
        ],
    },
    "wafer_processing": {
        "weight": 24,
        "support_only": True,
        "aliases": [
            "wafer processing",
            "wafer coating",
            "wafer baking",
            "wafer cleaning",
            "substrate processing",
        ],
    },

    # ---------------------------------------------------------
    # Sintering / powder metallurgy
    # ---------------------------------------------------------
    "spark_plasma_sintering": {
        "weight": 45,
        "support_only": False,
        "aliases": [
            "spark plasma sintering",
            "spark plasma sintering system",
            "sps system",
        ],
    },
    "sps": {
        "weight": 35,
        "support_only": False,
        "aliases": [
            "sps",
            "spark plasma sintering",
        ],
    },
    "field_assisted_sintering": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "field assisted sintering",
            "field assisted sintering technology",
            "field-assisted sintering",
        ],
    },
    "fast": {
        "weight": 30,
        "support_only": False,
        "aliases": [
            "fast",
            "field assisted sintering technology",
            "field-assisted sintering technology",
        ],
    },
    "powder_metallurgy": {
        "weight": 28,
        "support_only": True,
        "aliases": [
            "powder metallurgy",
            "metal powder",
            "sintered powder",
            "powder processing",
        ],
    },

    # ---------------------------------------------------------
    # Fuel cell / hydrogen / electrochemical
    # ---------------------------------------------------------
    "fuel_cell_testing": {
        "weight": 42,
        "support_only": False,
        "aliases": [
            "fuel cell testing",
            "fuel cell test station",
            "fuel cell test system",
            "fuel cell test bench",
            "pem fuel cell",
            "fuel cell characterization",
        ],
    },
    "electrolyzer_testing": {
        "weight": 40,
        "support_only": False,
        "aliases": [
            "electrolyzer testing",
            "electrolyser testing",
            "electrolyzer test station",
            "electrolyser test station",
            "electrolyzer test system",
            "electrolyser test system",
        ],
    },
    "hydrogen_research": {
        "weight": 25,
        "support_only": True,
        "aliases": [
            "hydrogen research",
            "green hydrogen",
            "hydrogen generation",
            "hydrogen testing",
            "pem electrolyzer",
            "pem electrolyser",
        ],
    },
    "battery_testing": {
        "weight": 35,
        "support_only": False,
        "aliases": [
            "battery testing",
            "battery test system",
            "battery cycler",
            "cell testing system",
            "battery analyzer",
            "battery analyser",
        ],
    },
    "electrochemical_testing": {
        "weight": 32,
        "support_only": False,
        "aliases": [
            "electrochemical testing",
            "electrochemical workstation",
            "potentiostat",
            "galvanostat",
            "impedance analyzer",
            "impedance analyser",
        ],
    },

    # ---------------------------------------------------------
    # Nanoparticle / aerosol / powder
    # ---------------------------------------------------------
    "flame_spray_pyrolysis": {
        "weight": 42,
        "support_only": False,
        "aliases": [
            "flame spray pyrolysis",
            "fsp",
            "flame aerosol synthesis",
            "flame spray synthesis",
        ],
    },
    "nanoparticle_synthesis": {
        "weight": 35,
        "support_only": False,
        "aliases": [
            "nanoparticle synthesis",
            "nano particle synthesis",
            "nanomaterial synthesis",
            "nanopowder synthesis",
        ],
    },
    "nanopowder": {
        "weight": 28,
        "support_only": True,
        "aliases": [
            "nanopowder",
            "nano powder",
            "nanopowders",
            "nano powders",
        ],
    },
    "aerosol_measurement": {
        "weight": 32,
        "support_only": False,
        "aliases": [
            "aerosol measurement",
            "aerosol particle",
            "particle size analyzer",
            "particle size analyser",
            "aerosol spectrometer",
        ],
    },
    "particle_engineering": {
        "weight": 25,
        "support_only": True,
        "aliases": [
            "particle engineering",
            "particle processing",
            "powder engineering",
        ],
    },
    "cvd_functionalization": {
        "weight": 35,
        "support_only": False,
        "aliases": [
            "cvd functionalization",
            "chemical vapor deposition functionalization",
            "chemical vapour deposition functionalization",
            "surface functionalization",
            "surface functionalisation",
        ],
    },

    # ---------------------------------------------------------
    # Analytical / elemental / mercury / spectroscopy
    # ---------------------------------------------------------
    "mercury_analyzer": {
        "weight": 40,
        "support_only": False,
        "aliases": [
            "mercury analyzer",
            "mercury analyser",
            "mercury analysis system",
            "total mercury analyzer",
            "total mercury analyser",
        ],
    },
    "cold_vapor_aas": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "cold vapor aas",
            "cold vapour aas",
            "cold vapor atomic absorption",
            "cold vapour atomic absorption",
            "cv-aas",
            "cvaas",
        ],
    },
    "aas": {
        "weight": 30,
        "support_only": False,
        "aliases": [
            "aas",
            "atomic absorption spectrometer",
            "atomic absorption spectroscopy",
        ],
    },
    "flame_photometer": {
        "weight": 30,
        "support_only": False,
        "aliases": [
            "flame photometer",
            "flame photometry",
        ],
    },
    "elemental_analysis": {
        "weight": 25,
        "support_only": True,
        "aliases": [
            "elemental analysis",
            "elemental analyzer",
            "elemental analyser",
            "trace element analysis",
        ],
    },
    "uv_vis": {
        "weight": 28,
        "support_only": False,
        "aliases": [
            "uv-vis",
            "uv vis",
            "uv visible",
            "uv-visible spectrophotometer",
            "uv vis spectrophotometer",
            "spectrophotometer",
        ],
    },
    "nmr": {
        "weight": 38,
        "support_only": False,
        "aliases": [
            "nmr",
            "nuclear magnetic resonance",
            "nmr spectrometer",
        ],
    },
    "time_domain_nmr": {
        "weight": 42,
        "support_only": False,
        "aliases": [
            "time-domain nmr",
            "time domain nmr",
            "td-nmr",
            "td nmr",
        ],
    },

    # ---------------------------------------------------------
    # Generic scientific/materials concepts
    # These are support-only. They should not rescue alone.
    # ---------------------------------------------------------
    "material_characterization": {
        "weight": 22,
        "support_only": True,
        "aliases": [
            "material characterization",
            "materials characterization",
            "material characterisation",
            "materials characterisation",
            "characterization laboratory",
            "characterisation laboratory",
        ],
    },
    "materials_research": {
        "weight": 20,
        "support_only": True,
        "aliases": [
            "materials research",
            "material science",
            "materials science",
            "advanced materials",
        ],
    },

    # ---------------------------------------------------------
    # Vacuum / utility concepts
    # Useful support signal, dangerous as standalone rescue.
    # ---------------------------------------------------------
    "vacuum_system": {
        "weight": 28,
        "support_only": True,
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
}


# ---------------------------------------------------------------------
# CONCEPT SUPPRESSION GROUPS
# ---------------------------------------------------------------------
# Prevent duplicate scoring for the same equipment family.
#
# Example:
# - ICP-RIE tender often also contains RIE.
# - SPS tender often also contains FAST.
# - Spatial ALD tender often also contains ALD.
#
# Without suppression, your score becomes fake confidence.
# ---------------------------------------------------------------------

CONCEPT_SUPPRESSION_GROUPS = [
    [
        "icp_rie",
        "rie",
    ],
    [
        "spark_plasma_sintering",
        "sps",
        "field_assisted_sintering",
        "fast",
    ],
    [
        "spatial_ald",
        "ald",
    ],
    [
        "magnetron_sputtering",
        "sputtering",
    ],
    [
        "pvd",
        "thin_film_deposition",
    ],
    [
        "mocvd",
        "epitaxial_growth",
    ],
    [
        "time_domain_nmr",
        "nmr",
    ],
    [
        "cold_vapor_aas",
        "aas",
    ],
    [
        "fuel_cell_testing",
        "hydrogen_research",
    ],
    [
        "electrolyzer_testing",
        "hydrogen_research",
    ],
]


# ---------------------------------------------------------------------
# SUPPORT-ONLY CONCEPTS
# ---------------------------------------------------------------------
# These can strengthen a match but should not rescue a tender alone.
# scoring.py / decision.py should use this field.
# ---------------------------------------------------------------------

SUPPORT_ONLY_CONCEPTS = {
    concept_id
    for concept_id, config in TECHNICAL_CONCEPTS.items()
    if config.get("support_only") is True
}


# ---------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------

def detect_concepts(tender, active_concept_ids=None):
    """
    Detect technical concepts in a tender.

    Args:
        tender (dict):
            Normalized tender dictionary.

        active_concept_ids (set/list/None):
            Optional set of concept IDs to consider.
            If None, concepts are loaded from active manufacturers.json.

    Returns:
        dict:
            {
                "matched_concepts": [...],
                "concept_score": int,
                "has_technical_concept": bool,
                "has_rescue_concept": bool,
                "has_support_only_concepts": bool,
                "active_concept_count": int
            }
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

        aliases = config.get("aliases", [])
        weight = int(config.get("weight", 0))
        support_only = bool(config.get("support_only", False))

        alias_hits = find_alias_hits(text_lower, aliases)

        if alias_hits:
            matches.append({
                "concept_id": concept_id,
                "matched_aliases": alias_hits,
                "weight": weight,
                "support_only": support_only,
                "reason_code": f"TECH_CONCEPT_{concept_id.upper()}",
            })

    matches = suppress_overlapping_concepts(matches)

    rescue_matches = [
        m for m in matches
        if not m.get("support_only", False)
    ]

    support_only_matches = [
        m for m in matches
        if m.get("support_only", False)
    ]

    return {
        "matched_concepts": matches,
        "concept_score": sum(m["weight"] for m in matches),
        "rescue_concept_score": sum(m["weight"] for m in rescue_matches),
        "support_only_concept_score": sum(m["weight"] for m in support_only_matches),
        "has_technical_concept": bool(matches),
        "has_rescue_concept": bool(rescue_matches),
        "has_support_only_concepts": bool(support_only_matches),
        "active_concept_count": len(active_concept_ids),
    }


def get_active_concept_ids_from_manufacturers(path=MANUFACTURERS_PATH):
    """
    Load active concept IDs from manufacturers.json.

    Expected manufacturer fields can include:
    - concepts
    - concept_ids
    - supported_concepts

    This function is intentionally tolerant because your manufacturers.json
    may evolve.
    """
    if not Path(path).exists():
        return set()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    manufacturers = extract_manufacturer_list(data)

    active_concepts = set()

    for manufacturer in manufacturers:
        if not isinstance(manufacturer, dict):
            continue

        if manufacturer.get("active") is False:
            continue

        for field in ["concepts", "concept_ids", "supported_concepts"]:
            values = manufacturer.get(field, [])

            if isinstance(values, str):
                values = [values]

            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        concept_id = normalize_concept_id(value)
                        if concept_id:
                            active_concepts.add(concept_id)

    return active_concepts


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def extract_manufacturer_list(data):
    """
    Supports multiple manufacturers.json shapes.

    Accepted shapes:
    1. [ {...}, {...} ]

    2. {
         "manufacturers": [ {...}, {...} ]
       }

    3. {
         "active_manufacturers": [ {...}, {...} ]
       }
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["manufacturers", "active_manufacturers", "companies"]:
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def normalize_concept_id(value):
    """
    Normalize concept names into snake_case IDs.
    """
    value = str(value or "").strip().lower()

    if not value:
        return ""

    value = value.replace("-", "_")
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")

    return value


def suppress_overlapping_concepts(matches):
    """
    Prevent duplicate scoring for concepts that describe the same equipment family.

    Keeps the strongest concept in each suppression group.

    Example:
    - icp_rie suppresses rie
    - spark_plasma_sintering suppresses sps / fast
    - spatial_ald suppresses ald
    """
    if not matches:
        return matches

    by_id = {m["concept_id"]: m for m in matches}
    suppressed_ids = set()

    for group in CONCEPT_SUPPRESSION_GROUPS:
        present = [
            concept_id
            for concept_id in group
            if concept_id in by_id
        ]

        if len(present) <= 1:
            continue

        strongest = max(
            present,
            key=lambda concept_id: by_id[concept_id]["weight"],
        )

        for concept_id in present:
            if concept_id != strongest:
                suppressed_ids.add(concept_id)

    return [
        m for m in matches
        if m["concept_id"] not in suppressed_ids
    ]


def build_search_text(tender):
    """
    Build searchable tender text from normalized fields.
    """
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
    """
    Normalize tender text for matching.
    """
    text = (text or "").lower()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_alias_hits(text_lower, aliases):
    """
    Find aliases in normalized text.
    """
    hits = []

    for alias in aliases:
        alias_norm = str(alias).lower().strip()

        if not alias_norm:
            continue

        alias_norm = alias_norm.replace("–", "-").replace("—", "-")

        if should_use_boundary_match(alias_norm):
            pattern = r"(?<![a-z0-9])" + re.escape(alias_norm) + r"(?![a-z0-9])"
            if re.search(pattern, text_lower):
                hits.append(alias)
        else:
            if alias_norm in text_lower:
                hits.append(alias)

    return dedupe_preserve_order(hits)


def should_use_boundary_match(term):
    """
    Use strict boundary matching for short terms like:
    - sps
    - fast
    - rie
    - ald
    - pvd
    - mbe
    - nmr
    - aas

    This prevents accidental substring matches.
    """
    compact = term.replace("-", "").replace("_", "").replace(" ", "")
    return len(compact) <= 5 and compact.isalnum()


def dedupe_preserve_order(items):
    """
    Remove duplicates while preserving order.
    """
    seen = set()
    out = []

    for item in items:
        key = str(item).lower().strip()

        if key not in seen:
            seen.add(key)
            out.append(item)

    return out


def list_active_concepts():
    """
    Debug helper.
    """
    return sorted(get_active_concept_ids_from_manufacturers())


def list_known_concepts():
    """
    Debug helper.
    """
    return sorted(TECHNICAL_CONCEPTS.keys())