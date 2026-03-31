import random
from datetime import datetime

def generate_tenders(n=100):
    tenders = []

    HIGH_SIGNAL = [
        "Dual-Ion Beam Sputtering Coating system with optical monitoring",
        "XRD diffractometer system for material characterization",
        "FTIR spectrometer for chemical analysis",
        "Thin film deposition system using PVD technology",
        "Gas Chromatography system with mass spectrometer"
    ]

    LOW_SIGNAL = [
        "Supply and installation of laboratory equipment",
        "Procurement of analytical instruments",
        "Testing equipment for diagnostics lab",
        "Measurement system for industrial application",
        "Scientific instrument supply"
    ]

    BLOCKED = [
        "Construction of road and drainage system",
        "Repair of sewage pipeline and maintenance",
        "Civil work for building renovation",
        "Hiring of manpower for cleaning services",
        "Electrical repair and maintenance works"
    ]

    for i in range(n):
        category = random.choices(
            ["high", "low", "blocked"],
            weights=[0.1, 0.2, 0.7]   # realistic distribution
        )[0]

        if category == "high":
            title = random.choice(HIGH_SIGNAL)

        elif category == "low":
            title = random.choice(LOW_SIGNAL)

        else:
            title = random.choice(BLOCKED)

        tenders.append({
            "tender_id": f"test_{i}",
            "title": title,
            "organization": random.choice([
                "AIIMS Delhi",
                "IIT Bombay",
                "PWD Department",
                "Municipal Corporation",
                "DRDO Lab"
            ]),
            "published_date": "2026-03-27",
            "closing_date": "2026-04-10",
            "source_url": "test",
            "source_portal": "synthetic",
            "raw_text": title + " with additional technical specifications",
            "scraped_at": str(datetime.now())
        })

    return tenders