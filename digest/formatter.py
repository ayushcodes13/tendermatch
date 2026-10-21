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

def format_email(high_tenders, explore_tenders, stats):
    """
    Constructs the full email body from processed tender data.

    Args:
        high_tenders (list): Tenders with confirmed manufacturer matches.
        explore_tenders (list): Tenders with moderate semantic signal.
        stats (dict): Counts for total scanned and category breakdowns.

    Returns:
        tuple: (subject_string, body_string)
    """
    high_signal_label = "Opportunity" if len(high_tenders) == 1 else "Opportunities"
    subject = (
        f"Tender Intelligence Report | {len(high_tenders)} "
        f"High-Signal {high_signal_label}"
    )

    lines = []

    lines.append("Tender Intelligence Summary")
    lines.append("")
    lines.append("=" * 50)
    lines.append("")
    lines.append("OVERVIEW")
    lines.append("-" * 50)
    lines.append(f"Total scraped: {stats.get('total_scraped', stats.get('total', 0))}")
    lines.append(f"Fresh tenders processed: {stats.get('fresh_processed', 0)}")
    lines.append(f"High-signal opportunities: {stats.get('high', len(high_tenders))}")
    lines.append(f"Exploration candidates: {stats.get('explore', len(explore_tenders))}")
    lines.append(f"Low-signal tenders: {stats.get('low', 0)}")
    lines.append(f"Blocked tenders: {stats.get('blocked', 0)}")
    lines.append(f"Stale tenders skipped: {stats.get('stale_skipped', 0)}")
    lines.append(f"Duplicates skipped: {stats.get('duplicates_skipped', 0)}")
    lines.append(f"Previously emailed skipped: {stats.get('already_emailed_skipped', 0)}")
    lines.append("")

    lines.append("=" * 50)
    lines.append("HIGH-SIGNAL OPPORTUNITIES")
    lines.append("=" * 50)
    lines.append("")

    if not high_tenders:
        lines.append("No high-signal opportunities identified.")
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
