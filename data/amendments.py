"""Conservative comparison of stored tender content versions."""

import json
import re
import unicodedata
from difflib import SequenceMatcher

from pipeline.freshness import parse_date


_CHANGE_CUES = {
    "cancellation_or_withdrawal": re.compile(
        r"\b(cancel(?:led|ed|lation)?|withdraw(?:n|al)?|annul(?:led|ment)?)\b", re.I
    ),
    "technical_specification_changed": re.compile(
        r"\b(technical specification|specification|capacity|dimension|accuracy|"
        r"voltage|pressure|flow rate|temperature|tolerance|performance)\b", re.I
    ),
    "certification_requirement_changed": re.compile(
        r"\b(certification|certificate|iso\s*\d*|compliance certificate|"
        r"type test|test report|authorization)\b", re.I
    ),
    "eligibility_requirement_changed": re.compile(
        r"\b(eligibility|eligible|qualification|qualifying|mandatory requirement|"
        r"turnover|prior experience|past performance|bidder shall)\b", re.I
    ),
    "quantity_changed": re.compile(
        r"\b(quantity|qty\.?|number of units|units required|nos\.?|lot size)\b", re.I
    ),
}


def _normalized_text(value):
    return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).casefold()


def _normalized_date(value, *, end_of_day=False):
    parsed = parse_date(value, end_of_day=end_of_day)
    return parsed.isoformat() if parsed else _normalized_text(value)


def _changed_lines(old_text, new_text):
    old_lines = [_normalized_text(line) for line in str(old_text or "").splitlines()]
    new_lines = [_normalized_text(line) for line in str(new_text or "").splitlines()]
    matcher = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changed = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            changed.extend(old_lines[i1:i2])
        if tag in {"replace", "insert"}:
            changed.extend(new_lines[j1:j2])
    return changed


def _load_snapshot(value):
    return json.loads(value) if isinstance(value, str) else value


def compare_tender_versions(previous, current):
    """Classify version deltas; unknown substantive text changes require review."""
    previous = _load_snapshot(previous)
    current = _load_snapshot(current)
    old = previous.get("content", {})
    new = current.get("content", {})
    change_types = set()
    evidence = {}

    for field, label in (("closing_date", "deadline_changed"),):
        old_value, new_value = old.get(field), new.get(field)
        old_date, new_date = parse_date(old_value, end_of_day=True), parse_date(new_value, end_of_day=True)
        if old_date != new_date or (
            old_date is None and new_date is None
            and _normalized_text(old_value) != _normalized_text(new_value)
        ):
            if old_date is not None and new_date is not None:
                if new_date > old_date:
                    change_types.add("deadline_extended")
                else:
                    change_types.add("deadline_shortened")
            else:
                change_types.add(label)
            evidence[field] = {"from": old_value, "to": new_value}

    for field, label in (("corrigendum_date", "corrigendum_date_changed"),):
        old_value, new_value = old.get(field), new.get(field)
        if _normalized_date(old_value) != _normalized_date(new_value):
            change_types.add(label)
            evidence[field] = {"from": old_value, "to": new_value}

    for field, label in (("updated_date", "updated_date_changed"),
                         ("published_date", "publication_date_changed"),
                         ("title", "title_changed"),
                         ("organization", "issuer_changed")):
        old_value, new_value = old.get(field), new.get(field)
        old_key = (
            _normalized_date(old_value)
            if field in {"updated_date", "published_date"}
            else _normalized_text(old_value)
        )
        new_key = (
            _normalized_date(new_value)
            if field in {"updated_date", "published_date"}
            else _normalized_text(new_value)
        )
        if old_key != new_key:
            change_types.add(label)
            evidence[field] = {"from": old_value, "to": new_value}

    old_text, new_text = old.get("raw_text"), new.get("raw_text")
    old_normalized, new_normalized = _normalized_text(old_text), _normalized_text(new_text)
    if old_normalized != new_normalized:
        changed_lines = _changed_lines(old_text, new_text)
        matched_cues = set()
        unclassified_line = False
        for line in changed_lines:
            line_cues = {
                name for name, pattern in _CHANGE_CUES.items()
                if pattern.search(line)
            }
            matched_cues.update(line_cues)
            if not line_cues:
                unclassified_line = True
        change_types.update(matched_cues)
        if unclassified_line or not matched_cues:
            change_types.add("unclassified_content_change")
        evidence["raw_text"] = {"from": old_text, "to": new_text}

    if not change_types:
        # The fingerprint differs, but normalized fields do not. Preserve the
        # version pair while identifying it as formatting or extraction noise.
        status = "formatting_only"
    elif change_types <= {"deadline_extended", "deadline_shortened", "deadline_changed",
                          "corrigendum_date_changed", "cancellation_or_withdrawal",
                          "technical_specification_changed", "certification_requirement_changed",
                          "eligibility_requirement_changed", "quantity_changed"}:
        status = "meaningful"
    else:
        status = "needs_review"

    return {
        "status": status,
        "change_types": sorted(change_types),
        "evidence": evidence,
    }
