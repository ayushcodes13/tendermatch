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
from urllib.parse import urlsplit

def normalize(title):
    """
    Cleans a tender title for standardized display in reports.

    Args:
        title (str): Raw tender title.

    Returns:
        str: Lowercase alphanumeric string with stripped whitespace.
    """
    return re.sub(r'[^a-z0-9 ]', '', title.lower()).strip()


def _items(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    result = []
    for item in value:
        if isinstance(item, dict):
            text = next(
                (item.get(key) for key in ("term", "matched_term", "text", "phrase", "rule_id", "description") if item.get(key)),
                None,
            )
            if text is None:
                for nested in item.values():
                    for nested_text in _items(nested):
                        if nested_text not in result:
                            result.append(nested_text)
                continue
            if not isinstance(text, str):
                text = str(text)
        else:
            text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _explanation(tender):
    classification = tender.get("classification") or {}
    return (
        tender.get("explanation")
        or classification.get("explanation")
        or (classification.get("trace") or {}).get("explanation")
        or {}
    )


def _valid_source_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        return value.strip()
    except ValueError:
        return None


def _render_opportunity(lines, tender, *, kind, heading):
    explanation = _explanation(tender)
    matches = tender.get("matches") or []
    title = tender.get("title") or "Untitled tender"
    organization = tender.get("organization") or "Unknown organization"
    tender_id = tender.get("tender_id")
    reference = str(tender_id) if tender_id is not None and not str(tender_id).startswith(("http://", "https://")) else None
    closing_date = tender.get("closing_date") or "Not listed"
    source_url = _valid_source_url(tender.get("source_url")) or _valid_source_url(tender.get("portal_link"))

    lines.append(f"{heading} {title}")
    lines.append(f"   Organization: {organization}")
    lines.append(f"   Tender reference: {reference or 'Not provided by source'}")
    lines.append(f"   Status: {kind}")
    lines.append(f"   Closing date: {closing_date}")

    if matches:
        lines.append("   Manufacturer matches to review:")
        for match in matches[:3]:
            name = match.get("manufacturer_name") or "Unknown manufacturer"
            lines.append(f"   - {name}")
            families = _items(match.get("product_hits")) + _items(match.get("category_hits")) + _items(match.get("alias_hits"))
            families = list(dict.fromkeys(families))
            lines.append(f"     Product family: {', '.join(families[:4]) or 'Not identified'}")
            profile_warnings = _items(match.get("profile_warnings"))
            if profile_warnings:
                lines.append(f"     Evidence to confirm: {'; '.join(profile_warnings[:2])}")
            reasons = _items(match.get("concept_hits")) + _items(match.get("keyword_hits")) + _items(match.get("service_hits"))
            reasons = list(dict.fromkeys(reasons))
            lines.append(f"     Why it matched: {', '.join(reasons[:4]) or 'No specific profile evidence recorded'}")
            negatives = _items(match.get("negative_hits"))
            if not negatives:
                negative_evidence = explanation.get("negative_evidence") or {}
                negatives = list(dict.fromkeys(
                    item
                    for key in ("hard_junk_clusters", "soft_risk_terms", "contextual_negative_hits", "domain_review_hits")
                    for item in _items(negative_evidence.get(key))
                ))
            if negatives:
                lines.append(f"     Known concerns: {', '.join(negatives[:4])}")
            else:
                lines.append("     Known concerns: No manufacturer-specific negative evidence recorded")
    else:
        lines.append("   Manufacturer/product fit: No manufacturer match details attached; review the source manually.")

    unverified = _items(explanation.get("unverified_requirements"))
    if unverified:
        lines.append("   Unverified requirements:")
        for item in unverified[:3]:
            lines.append(f"   - {item}")
    if source_url:
        lines.append(f"   Official tender: {source_url}")
    else:
        lines.append("   Official tender: No valid HTTP(S) source link recorded")
    if kind == "Updated opportunity":
        action = "Review the amendment, then recheck the official requirements and deadline."
    elif kind == "Potential opportunity; needs review":
        action = "Check the official requirements and confirm product fit and eligibility before pursuing."
    else:
        action = "Check the official requirements and confirm eligibility, technical fit, and delivery before pursuing."
    lines.append(f"   Suggested next action: {action}")
    lines.append("")

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

    for i, tender in enumerate(high_tenders, 1):
        _render_opportunity(
            lines, tender, kind="New to this recipient's digest", heading=f"{i}.",
        )

    lines.append("=" * 50)
    lines.append("EXPLORATION (REQUIRES REVIEW)")
    lines.append("=" * 50)
    lines.append("")

    if not explore_tenders:
        lines.append("No exploration candidates require review.")
        lines.append("")
    for tender in explore_tenders[:5]:
        _render_opportunity(
            lines, tender, kind="Potential opportunity; needs review", heading="-",
        )

    if updated_tenders:
        lines.append("=" * 50)
        lines.append("UPDATED TENDERS")
        lines.append("=" * 50)
        lines.append("")
        for tender in updated_tenders:
            amendment = tender.get("amendment", {})
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
            _render_opportunity(
                lines,
                tender,
                kind="Updated opportunity",
                heading="-",
            )

    body = "\n".join(lines)

    return subject, body
