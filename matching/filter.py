"""1. If BLOCKLIST → blocked

2. Else if STRONG_KEYWORD or DOMAIN_MAP → high_signal

3. Else compute SEMANTIC_SCORE:

    if score > 0.70:
        high_signal

    elif 0.45 < score < 0.70:
        explore

    elif weak keywords exist:
        low_signal

    else:
        blocked
"""

import re
import numpy as np
from matching.embedder import ManufacturerEmbedder

# -----------------------
# BLOCKLIST (unchanged)
# -----------------------
BLOCKLIST = [
    "road", "construction", "civil", "repair", "maintenance",
    "drain", "pipeline", "renovation", "fencing", "water",    "cable",
    "pump",
    "motor",
    "starter",
    "underground mine",
    "mine",
    "coal",
    "transportation",
    "charging"
]

NEGATIVE_CONTEXT = [
    "labour", "manpower", "vehicle",
    "insurance", "furniture", "cleaning"
]

# -----------------------
# STRONG DOMAIN MAP
# -----------------------
STRONG_KEYWORDS = [
    # Thin film / deposition (core business)
    "pvd", "cvd", "ald", "pld",
    "sputtering", "magnetron sputtering",
    "ion beam deposition", "ion beam milling",
    "electron beam evaporation", "thermal evaporation",
    "thin film deposition", "vacuum deposition",

    # Advanced coating variants
    "pecvd", "hipims", "hitus", "ion plating",

    # Material characterization (high intent)
    "xrd", "x-ray diffraction",
    "xrf", "x-ray fluorescence",
    "optical emission spectrometer", "oes",
    "ftir", "spectrometer", "spectrophotometer",

    # Sintering (very niche → high value)
    "spark plasma sintering", "sps", "spad",
    "field assisted sintering", "fast", "pecvd", "peld", "icp-rie", 
    "mocvd", "sald", "lithography", "femtosecond-laser",
    "pulsed epr", "cw-pulsed esr", "snspd", "spr", 
    "quantum deposition system", "quantum deposition",
    "cryogenic system", "sps", "spark plasma sintering", "probstation", "rcm",

    # Electrochem / energy systems
    "fuel cell test", "electrolyzer testing",
    "battery testing system",

    # Niche high-signal instruments
    "nmr", "time-domain nmr",
    "mercury analyzer"
]

# -----------------------
# WEAK SIGNALS
# -----------------------
WEAK_KEYWORDS = [
    "equipment", "instrument", "system",
    "laboratory", "testing", "diagnostic",
    "analytical", "analyzer", "measurement"
]

# -----------------------
# SEMANTIC DOMAIN QUERIES
# -----------------------
DOMAIN_QUERIES = [
    # Thin film & coatings
    "thin film deposition systems for research and industry",
    "physical vapor deposition and sputtering equipment",
    "vacuum coating and surface engineering systems",
    "atomic layer deposition and conformal coating systems",

    # Advanced materials processing
    "advanced material synthesis and sintering systems",
    "spark plasma sintering and powder metallurgy equipment",
    "nanoparticle synthesis and aerosol processing systems",

    # Material characterization
    "material characterization instruments using x-ray and spectroscopy",
    "analytical instruments for chemical and elemental analysis",
    "laboratory spectrometry and diffraction systems",

    # Energy & electrochemistry
    "fuel cell and battery testing systems for energy research",
    "electrochemical testing and hydrogen research equipment",

    # Environmental & gas analysis
    "gas analyzers and emission monitoring systems",
    "environmental monitoring and water analysis instruments",

    # Industrial + research lab systems
    "scientific laboratory equipment for research and testing",
    "advanced instrumentation for physics and material science labs"
]

# -----------------------
# CLEAN TEXT
# -----------------------
def clean_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text


# -----------------------
# INIT EMBEDDINGS (ONCE)
# -----------------------
embedder = ManufacturerEmbedder()
domain_embeddings = None


def init_semantic():
    global domain_embeddings

    if domain_embeddings is None:
            domain_embeddings = np.array([
                embedder.embed_text(q) for q in DOMAIN_QUERIES
            ])


# -----------------------
# SEMANTIC SCORE
# -----------------------
def get_semantic_score(text):
    query_vec = embedder.embed_text(text)
    scores = np.dot(domain_embeddings, query_vec)
    return float(np.max(scores))


# -----------------------
# MAIN CLASSIFIER
# -----------------------
def classify_tender(tender):

    init_semantic()

    title = tender.get("title") or ""
    raw_text = tender.get("raw_text") or ""

    text = clean_text(title + " " + raw_text)
    words = set(text.split())

    # -----------------------
    # 1. HARD BLOCK
    # -----------------------
    for word in BLOCKLIST:
        if word in text:
            return {
                "is_blocked": True,
                "has_signal": False,
                "category": "blocked",
                "reason": f"blocklist: {word}"
            }

    score = 0
    reasons = []

    # -----------------------
    # 2. STRONG KEYWORDS
    # -----------------------
    for word in STRONG_KEYWORDS:
        if word in text:
            score += 2
            reasons.append(word)

    if score >= 2:
        return {
            "is_blocked": False,
            "has_signal": True,
            "category": "high_signal",
            "reason": f"strong_keywords: {reasons}"
        }

    # -----------------------
    # 3. SEMANTIC LAYER
    # -----------------------
    semantic_score = get_semantic_score(text)

    if semantic_score >= 0.78:
        return {
            "is_blocked": False,
            "has_signal": True,
            "category": "high_signal",
            "reason": f"semantic_high: {round(semantic_score, 3)}"
        }

    elif 0.60 <= semantic_score < 0.78:
        return {
            "is_blocked": False,
            "has_signal": False,
            "category": "explore",
            "reason": f"semantic_explore: {round(semantic_score, 3)}"
        }

    # -----------------------
    # 4. WEAK KEYWORDS
    # -----------------------
    weak_hits = [w for w in WEAK_KEYWORDS if w in text]

    if weak_hits:
        return {
            "is_blocked": False,
            "has_signal": False,
            "category": "low_signal",
            "reason": f"weak_keywords: {weak_hits}"
        }

    # -----------------------
    # 5. NEGATIVE CONTEXT
    # -----------------------
    for bad in NEGATIVE_CONTEXT:
        if bad in text:
            return {
                "is_blocked": True,
                "has_signal": False,
                "category": "blocked",
                "reason": f"negative_context: {bad}"
            }

    # -----------------------
    # 6. DEFAULT
    # -----------------------
    return {
        "is_blocked": True,
        "has_signal": False,
        "category": "blocked",
        "reason": "no signal"
    }