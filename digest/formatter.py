"""
Content generator for the tender intelligence email digest.

Pipeline role:
Transforms raw tender and match data into a human-readable text report. 
Ensures that high-value opportunities are prioritized at the top of 
the email body.

Key responsibilities:
- Aggregating classification stats for the email header.
- Formatting 'high_signal' tenders with their recommended manufacturers.
- Formatting 'explore' candidates for manual review.
- Cleaning and normalizing titles for consistent presentation.

Inputs:
- Lists of high, explore, and low-relevance tenders.
- Pipeline execution statistics.

Outputs:
- A formatted email subject line and plaintext body.
"""
from collections import defaultdict
import re

def normalize(title):
    """
    Cleans a tender title for standardized display in reports.

    Args:
        title (str): Raw tender title.

    Returns:
        str: Lowercase alphanumeric string with stripped whitespace.
    """
    return re.sub(r'[^a-z0-9 ]', '', title.lower()).strip()

def format_email(high_tenders, explore_tenders, low_tenders, stats):
    """
    Constructs the full email body from processed tender data.

    Args:
        high_tenders (list): Tenders with confirmed manufacturer matches.
        explore_tenders (list): Tenders with moderate semantic signal.
        low_tenders (list): Tenders with weak signals.
        stats (dict): Counts for total scanned and category breakdowns.

    Returns:
        tuple: (subject_string, body_string)
    """
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
