from matching.concepts import (
    detect_concepts,
    get_active_concept_ids_from_manufacturers,
)

print("Active concepts:")
for c in sorted(get_active_concept_ids_from_manufacturers()):
    print("-", c)

tests = [
    {
        "title": "Supply of XRD system",
        "raw_text": "Procurement of X-ray diffractometer",
    },
    {
        "title": "AMC of ICP-RIE system",
        "raw_text": "Annual maintenance of plasma etching system",
    },
    {
        "title": "Supply of U-FAST spark plasma sintering system",
        "raw_text": "SPS equipment for powder metallurgy",
    },
    {
        "title": "Spatial ALD coating system",
        "raw_text": "Spatial atomic layer deposition for battery coating",
    },
]

for tender in tests:
    print("\n" + "=" * 80)
    print(tender["title"])
    result = detect_concepts(tender)
    print(result)