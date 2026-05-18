from matching.embedder import build_matcher

matcher = build_matcher()

tests = [
    {
        "title": "Supply of thin film deposition PVD system",
        "raw_text": "Procurement of magnetron sputtering and thermal evaporation system for materials research laboratory",
        "organization": "IIT Madras",
    },
    {
        "title": "AMC of ICP-RIE system",
        "raw_text": "Annual maintenance contract for ICP-RIE plasma etching system",
        "organization": "IIT Madras",
    },
    {
        "title": "Supply of U-FAST spark plasma sintering system",
        "raw_text": "Procurement of SPS equipment for powder metallurgy research",
        "organization": "IISc Bangalore",
    },
    {
        "title": "Fuel cell test station",
        "raw_text": "Supply installation and commissioning of fuel cell testing system for hydrogen research",
        "organization": "IIT Goa",
    },
    {
        "title": "Spatial ALD coating system",
        "raw_text": "Procurement of spatial atomic layer deposition system for battery coating research",
        "organization": "IIT Bombay",
    },
    {
        "title": "Spin coater and developer system",
        "raw_text": "Supply of spin coating, developer, hotplate and wafer processing equipment",
        "organization": "SCL Mohali",
    },
    {
        "title": "Mercury analyzer",
        "raw_text": "Procurement of mercury analysis system for water and environmental sample testing",
        "organization": "Research Laboratory",
    },
    {
        "title": "Time-domain NMR analyzer",
        "raw_text": "Supply of benchtop time-domain NMR system for material characterization",
        "organization": "IISc Bangalore",
    },
]

for tender in tests:
    print("\n" + "=" * 80)
    print(tender["title"])

    candidates = matcher.match_topk(tender, top_k=3)

    for c in candidates:
        print(
            c["rank"],
            c["manufacturer_name"],
            c["score"],
            c["confidence"],
            c["reason_codes"],
        )
        print("  base:", c["base_semantic_score"])
        print("  total_boost:", c["total_boost"])
        print("  keyword_hits:", c["keyword_hits"][:5])
        print("  product_hits:", c["product_hits"][:5])
        print("  category_hits:", c["category_hits"][:5])
        print("  alias_hits:", c["alias_hits"][:5])
        print("  concept_hits:", c["concept_hits"][:5])
        print("  service_hits:", c["service_hits"][:5])
        print("  negative_hits:", c["negative_hits"][:5])