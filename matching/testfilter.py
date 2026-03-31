from matching.filter import classify_tender

# =========================
# TEST DATA
# =========================

HIGH_SIGNAL = [
    "Supply of UV-Vis Spectrophotometer for laboratory use",
    "Procurement of Atomic Absorption Spectrometer with accessories",
    "Supply and installation of XRD system for material analysis",
    "Procurement of FTIR spectrometer for research lab",
    "Supply of gas chromatography system with detectors",
    "Installation of thin film deposition system using magnetron sputtering",
    "Supply of PVD coating system for research purposes",
    "Procurement of analytical instruments for chemical testing laboratory",
    "Supply of vacuum coating unit for thin film applications",
    "Installation of plasma sputtering deposition system"
]

LOW_SIGNAL = [
    "Supply of UPS system for office backup",
    "Procurement of LED lighting system",
    "Supply of general electrical equipment for building",
    "Installation of CCTV surveillance system",
    "Supply of water pumps for irrigation"
]

BLOCKED = [
    "Construction of internal roads in residential colony",
    "Repair and maintenance of drainage system",
    "Civil works for building renovation",
    "Supply of manpower for cleaning services",
    "Hiring of vehicles for transportation"
]


# =========================
# TEST RUNNER
# =========================

def run_tests():

    print("\n================ HIGH SIGNAL TESTS ================\n")
    for t in HIGH_SIGNAL:
        result = classify_tender({"title": t, "raw_text": ""})
        print(f"TITLE: {t}")
        print(f"RESULT: {result}")
        print("--------------------------------------------------")

    print("\n================ LOW SIGNAL TESTS ================\n")
    for t in LOW_SIGNAL:
        result = classify_tender({"title": t, "raw_text": ""})
        print(f"TITLE: {t}")
        print(f"RESULT: {result}")
        print("--------------------------------------------------")

    print("\n================ BLOCKED TESTS ================\n")
    for t in BLOCKED:
        result = classify_tender({"title": t, "raw_text": ""})
        print(f"TITLE: {t}")
        print(f"RESULT: {result}")
        print("--------------------------------------------------")


if __name__ == "__main__":
    run_tests()