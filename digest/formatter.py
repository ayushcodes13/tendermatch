from collections import defaultdict
import re


def normalize(title):
    return re.sub(r'[^a-z0-9 ]', '', title.lower()).strip()

def format_email(high_tenders, explore_tenders, low_tenders, stats):
    subject = f"Tender Intelligence Report | {len(high_tenders)} High-Value Opportunities"

    lines = []

    lines.append("Tender Intelligence Summary")
    lines.append("")
    lines.append("=" * 50)
    lines.append("")
    lines.append("OVERVIEW")
    lines.append("-" * 50)
    lines.append(f"Total scanned: {stats['total']}")
    lines.append(f"High relevance: {stats['high']}")
    lines.append(f"Exploration candidates: {stats['explore']}")
    lines.append(f"Low relevance: {stats['low']}")
    lines.append("")

    lines.append("=" * 50)
    lines.append("HIGH CONFIDENCE OPPORTUNITIES")
    lines.append("=" * 50)
    lines.append("")

    if not high_tenders:
        lines.append("No high-confidence opportunities identified.")
        lines.append("")

    for i, t in enumerate(high_tenders, 1):
        lines.append(f"{i}. {t['title']}")
        lines.append(f"   Organization: {t['organization']}")

        if t.get("matches"):
            lines.append("   Recommended Manufacturers:")
            for m in t["matches"][:3]:
                lines.append(f"   - {m['manufacturer_name']} ({m['score']})")

        lines.append(f"   Portal: {t.get('portal_link', 'N/A')}")
        lines.append("")

    lines.append("=" * 50)
    lines.append("EXPLORATION (REQUIRES REVIEW)")
    lines.append("=" * 50)
    lines.append("")

    for t in explore_tenders[:5]:
        lines.append(f"- {t['title']} ({t['organization']})")
        lines.append(f"  Portal: {t.get('portal_link', 'N/A')}")
        lines.append("")

    body = "\n".join(lines)

    return subject, body
