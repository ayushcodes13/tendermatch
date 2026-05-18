from matching.signals import detect_signals
from matching.concepts import detect_concepts
from matching.scoring import score_tender
from matching.decision import decide_tender
from matching.trace import build_trace


TEST_TENDERS = [
    {
        "tender_id": "t1",
        "title": "AMC of ICP-RIE system",
        "organization": "IIT Madras",
        "raw_text": "Annual maintenance contract for ICP-RIE plasma etching system",
        "source_portal": "iitm",
    },
    {
        "tender_id": "t2",
        "title": "Pump for water supply pipeline",
        "organization": "Municipal Corporation",
        "raw_text": "Repair of pump and motor for water supply pipeline",
        "source_portal": "cppp",
    },
    {
        "tender_id": "t3",
        "title": "Supply of vacuum pump for thin film deposition system",
        "organization": "IISc Bangalore",
        "raw_text": "Dry scroll pump for vacuum chamber used in sputtering system",
        "source_portal": "iisc",
    },
    {
        "tender_id": "t4",
        "title": "Civil work for laboratory building",
        "organization": "CPWD",
        "raw_text": "Civil works, painting, flooring and plumbing for lab building",
        "source_portal": "cppp",
    },
    {
        "tender_id": "t5",
        "title": "Supply of XRD system",
        "organization": "IIT Goa",
        "raw_text": "Supply installation commissioning of X-ray diffractometer",
        "source_portal": "iit_goa",
    },
]


def run():
    for tender in TEST_TENDERS:
        signals = detect_signals(tender)
        concepts = detect_concepts(tender)
        scoring = score_tender(tender, signals, concepts, manufacturer_candidates=[])
        decision = decide_tender(signals, concepts, scoring, manufacturer_candidates=[])
        trace = build_trace(tender, signals, concepts, scoring, decision, [])

        print("\n" + "=" * 80)
        print(tender["title"])
        print("Decision:", trace["decision"])
        print("Score:", trace["score"])
        print("Reasons:", trace["reason_codes"])
        print("Signals:", trace["signals"])
        print("Concepts:", trace["concepts"])


if __name__ == "__main__":
    run()