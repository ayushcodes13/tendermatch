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
from matching.domain_keywords import company_keywords

# -----------------------
# BLOCKLIST
# -----------------------
BLOCKLIST = [
    "11 kv", "leakages", "Photostat", "IndianOil", "Bharat Heavy Electricals Limited", "shauchalaya", "BOGIE",
    "33 kv", "Oil and Natural Gas Corporation Limited", "Biopsy", "fans", "Onion", "Truck", " Audio-Video system",
    "aluminum door", "chauraha", "Bank of Baroda", "NTPC", "WHEAT", "straw", "Ventilator", "PANTRIES", "Jal",
    "auction", "GRAM PANCHAYAT", "Adobe Creative Cloud Software", "GHAR", "GRAM", "CATERING", "PANTRY", "Washer",
    "balaclava", "Shock bars", "Trolley", "vehicles", "powergrid", "powergrid corporation of india limited",
    "bridge", "Coil Spring Machine", "spring washer",
    "axle box",
    "coach",
    "wagon",
    "railway",
    "locomotive",
    "bogie",
    "brake unit",
    "pressure regulating valve",
    "coil spring"
    "building repair",
    "building upgradation",
    "bus stand",
    "cable",
    "charging",
    "civil",
    "civil work",
    "civil works",
    "cleaning",
    "coal",
    "colour wash",
    "compound wall",
    "connected electrical works",
    "construction",
    "cpwd",
    "culvert",
    "dam",
    "desilting",
    "display board",
    "disposal",
    "door",
    "double circuit line",
    "drain",
    "drainage",
    "earth filling",
    "electrical connection",
    "electrical line shifting",
    "false ceiling",
    "felling",
    "fencing",
    "fertilizer",
    "flooring",
    "gaiter",
    "garland drain",
    "gloves",
    "gymnasium",
    "helmet",
    "housekeeping",
    "ht line",
    "information board",
    "kv line",
    "landscaping",
    "load enhancement",
    "lt extension",
    "maintenance",
    "marg",
    "methanol",
    "military engineer services",
    "mine",
    "motor",
    "municipal",
    "nallah",
    "neck gaiter",
    "open gym",
    "paint",
    "paint work",
    "painting",
    "park",
    "park development",
    "pest",
    "pesticide",
    "pipeline",
    "pipeline laying",
    "plantation",
    "plastering",
    "plumbing",
    "power line shifting",
    "public works department",
    "pump",
    "rasta",
    "rectification",
    "renovation",
    "repair",
    "road",
    "road marking",
    "roof covering",
    "roof leak",
    "sadak",
    "sale of scrap",
    "sapling",
    "sapling plantation",
    "scrap",
    "sewer",
    "sewerage",
    "shoe",
    "sign board",
    "sock",
    "socks",
    "solid waste",
    "sports hub",
    "stadium",
    "starter",
    "sub station",
    "surveillance unit",
    "sweeping",
    "thermoplastic paint",
    "timber",
    "toilet",
    "transformer repair",
    "transportation",
    "underground mine",
    "uniform",
    "upgradation",
    "ups installation",
    "warning board",
    "waste disposal",
    "water",
    "water supply",
    "well cleaning",
    "wells",
    "white wash",
    "window",
    "murum",
    "crush sand",
    "crush metal",
    "sand",
    "metal spreading",
    "spreading",
    "allotment of space",
    "hanger",
    "hangar",
    "dome",
    "festival",
    "fair",
    "spring festival",
    "temporary structure",
    "mementoe",
    "mementoes",
    "beautification",
    "pond",
    "pathway",
    "flood protection",
    "flood work",
    "ward-",
    "ward ",
    "lane",
    "village",
    "protection work"
]

ORG_BLOCKLIST = {
    # transport / infra / public works
    "chennai metro rail limited",
    "delhi metro rail corporation limited",
    "ministry of railways - world bank tenders",
    "ministry of road transport and highways",
    "national highways and infrastructure development corporation",
    "andaman lakshadweep harbour works",
    "chennai port trust",
    "jawaharlal nehru port trust",
    "kolkata port trust",
    "mumbai port trust",
    "new mangalore port trust",
    "mormugao port authority",
    "land ports authority of india",
    "inland waterways authority of india",
    "ministry of shipping",

    # utilities / infra / power / heavy civil
    "delhi development authority",
    "chenab valley power projects",
    "bundelkhand saur urja limited",
    "nhdc ltd.",
    "nhpc limited",
    "thdc india limited",
    "bridge and roof company (india) limited",

    # oil / industrial infra / chemicals
    "engineers india limited,mopng",
    "hindustan organic chemicals limited",
    "hindustan urvarak and rasayan limited",
    "madras fertilizers limited",
    "numaligarh refinery limited",
    "rashtriya chemicals and fertilizers ltd.",
    "the fertilisers and chemicals travancore ltd.",
    "projects and development india limited, fert",

    # telecom / utilities noise
    "bharat sanchar nigam limited",
    "mahanagar telephone nigam limited",

    # govt administrative / public sector noise
    "food corporation of india",
    "department of posts",
    "sports authority of india",
    "navodaya vidyalaya samiti",
    "staff selection commission",
    "supreme court of india",
    "office of the cag of india",
    "india trade promotion organisation",
    "national archives of india",

    # police / border / forces / infra ops
    "assam rifles - mha",
    "dg,bsf,mha",
    "dg,crpf,mha",
    "dg, indo-tibetan border police force",
    "dg,national security guard,mha",
    "dg sashastra seema bal,mha",
    "directorate general ndrf",

    # roads / survey / public administration
    "archaeological survey of india",
    "central ground water board",
    "geological survey of india",
    "directorate general of shipping",
    "directorate general of lighthouses and lightships",
    "directorate of construction services and estate management"
}

NEGATIVE_CONTEXT = [
    "labour", "manpower", "vehicle",
    "insurance", "furniture", "cleaning",
    "catering", "food service","pantry",
    "cleaning", "painting",
    "civil", "road",
    "drain", "railway hospitality",
    "amc of building","whitewash"
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
    "field assisted sintering", "fast", "pecvd", "peld",
    "icp-rie", "mocvd", "sald", "lithography",
    "femtosecond-laser", "pulsed epr",
    "cw-pulsed esr", "snspd", "spr",
    "quantum deposition system", "quantum deposition",
    "cryogenic system", "sps",
    "spark plasma sintering", "probstation", "rcm",

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
    "thin film deposition systems for research and industry",
    "physical vapor deposition and sputtering equipment",
    "vacuum coating and surface engineering systems",
    "atomic layer deposition and conformal coating systems",

    "advanced material synthesis and sintering systems",
    "spark plasma sintering and powder metallurgy equipment",
    "nanoparticle synthesis and aerosol processing systems",

    "material characterization instruments using x-ray and spectroscopy",
    "analytical instruments for chemical and elemental analysis",
    "laboratory spectrometry and diffraction systems",

    "fuel cell and battery testing systems for energy research",
    "electrochemical testing and hydrogen research equipment",

    "gas analyzers and emission monitoring systems",
    "environmental monitoring and water analysis instruments",

    "scientific laboratory equipment for research and testing",
    "advanced instrumentation for physics and material science labs"
]

# -----------------------
# COMPANY KEYWORD POOL
# -----------------------
ALL_COMPANY_KEYWORDS = set()

for keywords in company_keywords.values():
    for kw in keywords:
        ALL_COMPANY_KEYWORDS.add(kw.lower())

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
    organization = (tender.get("organization") or "").lower().strip()

    text = clean_text(title + " " + raw_text)
    words = set(text.split())

    # -----------------------
    # 0. ORGANIZATION BLOCK
    # -----------------------
    for blocked_org in ORG_BLOCKLIST:
        if blocked_org in organization:
            return {
                "is_blocked": True,
                "has_signal": False,
                "category": "blocked",
                "reason": f"organization_blocked: {blocked_org}"
            }
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
    # 3. COMPANY KEYWORD RECALL
    # -----------------------
    company_hits = []

    for kw in ALL_COMPANY_KEYWORDS:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, text):
            company_hits.append(kw)

    if company_hits:
        return {
            "is_blocked": False,
            "has_signal": True,
            "category": "high_signal",
            "reason": f"company_keyword_match: {company_hits[:3]}"
        }

    # -----------------------
    # 4. SEMANTIC LAYER
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
    # 5. WEAK KEYWORDS
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
    # 6. NEGATIVE CONTEXT
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
    # 7. DEFAULT
    # -----------------------
    return {
        "is_blocked": True,
        "has_signal": False,
        "category": "blocked",
        "reason": "no signal"
    }