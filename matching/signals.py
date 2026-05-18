
"""
Negative and rescue signal detection.

This module should not decide final classification.
It only extracts evidence:
- hard junk clusters
- soft risk terms
- contextual negative patterns
- buyer priors
- rescue terms
"""

import re


HARD_JUNK_CLUSTERS = {
    "civil_infra": [
        "civil work", "civil works", "construction", "building repair",
        "building upgradation", "road", "road marking", "sadak", "rasta",
        "bridge", "culvert", "drain", "drainage", "earth filling",
        "flooring", "plastering", "plumbing", "false ceiling",
        "compound wall", "roof covering", "roof leak", "white wash",
        "colour wash", "painting", "paint work", "renovation",
        "protection work", "flood protection", "pathway", "lane",
        "ward-", "ward ", "village"
    ],
    "municipal_sanitation": [
        "housekeeping", "cleaning", "sweeping", "solid waste",
        "waste disposal", "sewer", "sewerage", "toilet",
        "shauchalaya", "well cleaning", "desilting", "nallah"
    ],
    "food_catering": [
        "catering", "canteen", "pantry", "pantries",
        "restaurant", "fast food", "cafe"
    ],
    "sports_events": [
        "football ground", "sports activity", "sports hub",
        "stadium", "gymnasium", "open gym", "festival",
        "fair", "spring festival", "temporary structure"
    ],
    "scrap_auction": [
        "auction", "sale of scrap", "scrap"
    ],
    "railway_rolling_stock": [
        "railway", "wagon", "locomotive", "bogie", "coach",
        "axle box", "brake unit", "coil spring machine"
    ],
    "apparel_misc": [
        "uniform", "shoe", "sock", "socks", "helmet",
        "gloves", "balaclava", "neck gaiter", "gaiter"
    ],
    "agriculture_raw_material": [
        "onion", "wheat", "straw", "fertilizer", "pesticide",
        "sapling", "sapling plantation", "plantation"
    ],
}


SOFT_RISK_TERMS = [
    "amc",
    "annual maintenance",
    "maintenance",
    "repair",
    "rectification",
    "upgradation",
    "calibration",
    "spares",
    "consumables",
    "service contract",
    "warranty extension",
    "replacement",
    "installation",
    "commissioning",
    "testing",
    "cable",
    "motor",
    "pump",
    "starter",
    "valve",
    "charging",
    "ups installation",
    "surveillance unit",
    "fire alarm",
    "fire alarm system",
    "fire detection",
    "fire fighting",
]


CONTEXTUAL_NEGATIVE_RULES = [
    {
        "id": "WATER_PUMP_INFRA",
        "terms": ["pump", "motor", "starter"],
        "contexts": ["water supply", "pipeline", "sewer", "drainage", "municipal"],
    },
    {
        "id": "ELECTRICAL_LINE_WORK",
        "terms": ["cable", "charging", "sub station", "transformer repair"],
        "contexts": ["11 kv", "33 kv", "ht line", "lt extension", "kv line", "line shifting"],
    },
    {
        "id": "CIVIL_MATERIAL_SUPPLY",
        "terms": ["cement", "sand", "crush sand", "crush metal", "murum", "steel"],
        "contexts": ["road", "construction", "building", "civil work", "drain"],
    },
    {
        "id": "RAILWAY_MECHANICAL_PARTS",
        "terms": ["spring", "washer", "fasteners", "coil spring", "spring washer"],
        "contexts": ["railway", "wagon", "coach", "locomotive", "bogie"],
    },
]


BUYER_PRIOR_NEGATIVE = [
    "gram panchayat",
    "public works department",
    "cpwd",
    "municipal",
    "military engineer services",
]


RESCUE_TERMS = [
    "icp-rie",
    "icp rie",
    "reactive ion etching",
    "plasma etching",
    "plasma etcher",
    "dry etching",
    "sputtering",
    "magnetron sputtering",
    "rf sputtering",
    "pvd",
    "physical vapor deposition",
    "thin film",
    "thin-film",
    "thin film deposition",
    "pld",
    "pulsed laser deposition",
    "mbe",
    "molecular beam epitaxy",
    "xrd",
    "x-ray diffractometer",
    "sem",
    "tem",
    "afm",
    "vacuum chamber",
    "uhv",
    "cleanroom",
    "nanofabrication",
    "lithography",
    "thermal evaporator",
    "e-beam evaporator",
    "electron beam evaporator",
    "rf power supply",
    "mass flow controller",
    "mfc",
    "cryopump",
    "cryo pump",
    "turbo molecular pump",
    "turbomolecular pump",
    "glove box",
    "glovebox",
    "cvd",
    "chemical vapor deposition",
    "ald",
    "atomic layer deposition",
    "furnace",
    "spectrometer",
    "raman",
    "ftir",
    "ellipsometer",
    "profilometer",
    "probe station",
]


def detect_signals(tender):
    text = build_search_text(tender)
    text_lower = normalize_text(text)

    hard_clusters = detect_hard_junk_clusters(text_lower)
    soft_risks = find_terms(text_lower, SOFT_RISK_TERMS)
    contextual_negatives = detect_contextual_negatives(text_lower)
    buyer_priors = detect_buyer_priors(text_lower)
    rescue_terms = find_terms(text_lower, RESCUE_TERMS)

    return {
        "hard_junk_clusters": hard_clusters,
        "soft_risk_terms": soft_risks,
        "contextual_negative_hits": contextual_negatives,
        "buyer_priors": buyer_priors,
        "rescue_terms": rescue_terms,
        "has_rescue": bool(rescue_terms),
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


def detect_hard_junk_clusters(text_lower):
    clusters = []

    for cluster_id, terms in HARD_JUNK_CLUSTERS.items():
        hits = find_terms(text_lower, terms)

        # Cluster logic:
        # - one very specific phrase in title/text can be enough
        # - otherwise multiple hits make it stronger
        if len(hits) >= 2:
            clusters.append({
                "cluster_id": cluster_id,
                "hits": hits,
                "strength": "strong"
            })
        elif len(hits) == 1 and is_strong_single_junk_term(hits[0]):
            clusters.append({
                "cluster_id": cluster_id,
                "hits": hits,
                "strength": "medium"
            })

    return clusters


def is_strong_single_junk_term(term):
    strong_terms = {
        "housekeeping",
        "catering",
        "canteen",
        "sale of scrap",
        "auction",
        "civil work",
        "civil works",
        "road marking",
        "toilet",
        "shauchalaya",
        "football ground",
        "stadium",
    }
    return term.lower() in strong_terms


def detect_contextual_negatives(text_lower):
    hits = []

    for rule in CONTEXTUAL_NEGATIVE_RULES:
        term_hits = find_terms(text_lower, rule["terms"])
        context_hits = find_terms(text_lower, rule["contexts"])

        if term_hits and context_hits:
            hits.append({
                "rule_id": rule["id"],
                "term_hits": term_hits,
                "context_hits": context_hits,
            })

    return hits


def detect_buyer_priors(text_lower):
    return find_terms(text_lower, BUYER_PRIOR_NEGATIVE)


def find_terms(text_lower, terms):
    hits = []

    for term in terms:
        term_norm = str(term).lower().strip()
        if not term_norm:
            continue

        if should_use_boundary_match(term_norm):
            pattern = r"(?<![a-z0-9])" + re.escape(term_norm) + r"(?![a-z0-9])"
            if re.search(pattern, text_lower):
                hits.append(term)
        else:
            if term_norm in text_lower:
                hits.append(term)

    return dedupe_preserve_order(hits)


def should_use_boundary_match(term):
    # Use boundary matching for short tokens to avoid bad substring hits.
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