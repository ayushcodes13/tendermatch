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

def format_email(high_tenders, explore_tenders, stats, updated_tenders=None):
    """
    Constructs the full email body from processed tender data.

    Args:
        high_tenders (list): Tenders with confirmed manufacturer matches.
        explore_tenders (list): Tenders with moderate semantic signal.
        stats (dict): Counts for total scanned and category breakdowns.

    Returns:
        tuple: (subject_string, body_string)
    """
    updated_tenders = updated_tenders or []
    high_signal_label = "Opportunity" if len(high_tenders) == 1 else "Opportunities"
    if updated_tenders and not high_tenders and not explore_tenders:
        subject = f"Tender Intelligence Update | {len(updated_tenders)} Updated"
    else:
        subject = (
            f"Tender Intelligence Report | {len(high_tenders)} "
            f"High-Signal {high_signal_label}"
        )
        if updated_tenders:
            subject += f" | {len(updated_tenders)} Updated"

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

    if updated_tenders:
        lines.append("=" * 50)
        lines.append("UPDATED TENDERS")
        lines.append("=" * 50)
        lines.append("")
        for tender in updated_tenders:
            amendment = tender.get("amendment", {})
            lines.append(f"- {tender.get('title', 'Untitled tender')} ({tender.get('organization', 'Unknown organization')})")
            if amendment.get("status") == "needs_review":
                lines.append("  Update detected; review the official tender source.")
            labels = [item.replace("_", " ").capitalize() for item in amendment.get("change_types", [])]
            if labels:
                lines.append(f"  Change indicators: {', '.join(labels)}")
            closing = amendment.get("evidence", {}).get("closing_date", {})
            if closing:
                change_types = amendment.get("change_types", [])
                if "deadline_extended" in change_types:
                    message = "Closing date extended"
                elif "deadline_shortened" in change_types:
                    message = "Closing date shortened"
                else:
                    message = "Closing date changed"
                lines.append(f"  {message} from {closing.get('from') or 'unknown'} to {closing.get('to') or 'unknown'}.")
            lines.append(f"  Official tender: {tender.get('source_url') or tender.get('portal_link', 'N/A')}")
            lines.append("")

    body = "\n".join(lines)

    return subject, body
