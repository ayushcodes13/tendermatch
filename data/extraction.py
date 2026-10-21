"""Native-text extraction of tender requirement lines with page citations."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_PAGES = 100
MAX_PAGE_TEXT_CHARS = 100_000
MAX_PDF_BYTES = 20 * 1024 * 1024

# Deliberately extract only explicitly labelled fields. This is not a
# free-form interpretation of tender prose, and it cannot establish eligibility.
FIELD_LABELS = {
    "equipment_type": ("equipment type", "item name", "name of equipment", "item description"),
    "technical_specifications": ("technical specifications", "technical specification", "specifications", "technical requirements"),
    "mandatory_requirements": ("mandatory requirements", "mandatory requirement", "essential requirements"),
    "optional_requirements": ("optional requirements", "optional requirement"),
    "quantity": ("quantity", "required quantity", "qty"),
    "delivery_requirements": ("delivery requirements", "delivery period", "delivery schedule"),
    "eligibility_requirements": ("eligibility requirements", "eligibility criteria", "qualifying criteria"),
    "closing_date": ("closing date", "submission deadline", "bid submission end date", "last date for submission"),
}

_ALIAS_TO_FIELD = {
    alias.casefold(): field
    for field, aliases in FIELD_LABELS.items()
    for alias in aliases
}
_LABEL_RE = re.compile(
    r"^\s*(?P<label>[A-Za-z][A-Za-z /()_-]{1,80})\s*[:\-–]\s*(?P<value>\S.*?)\s*$"
)


def extract_pdf_requirements(
    pdf_path: str | Path,
    *,
    source_url: str,
    content_fingerprint: str,
    max_pages: int = MAX_PDF_PAGES,
    max_page_text_chars: int = MAX_PAGE_TEXT_CHARS,
) -> dict:
    """Extract native text and labelled fields; every field has page/quote evidence.

    No OCR is attempted. Empty native text is reported as `needs_ocr`; parser
    errors are coarse statuses and never silently become empty requirements.
    """
    if max_pages < 1 or max_page_text_chars < 1:
        raise ValueError("extraction limits must be positive")
    result = {
        "source_url": source_url,
        "content_fingerprint": content_fingerprint,
        "status": "unavailable",
        "pages": [],
        "fields": {},
        "error_type": None,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        path = Path(pdf_path)
        if path.stat().st_size > MAX_PDF_BYTES:
            result.update(status="limited", error_type="FileTooLarge")
            return result
        reader = PdfReader(str(path), strict=False, root_object_recovery_limit=2_000)
        if reader.is_encrypted:
            result.update(status="needs_review", error_type="EncryptedPDF")
            return result
        total_pages = len(reader.pages)
        pages_to_read = min(total_pages, max_pages)
        saw_text = False
        truncated = False
        for index in range(pages_to_read):
            try:
                page_text = reader.pages[index].extract_text() or ""
            except Exception as exc:
                result["pages"].append({"page": index + 1, "status": "unreadable"})
                result["error_type"] = type(exc).__name__
                continue
            was_truncated = len(page_text) > max_page_text_chars
            if was_truncated:
                page_text = page_text[:max_page_text_chars]
                truncated = True
            nonempty_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
            if nonempty_lines:
                saw_text = True
                result["pages"].append({"page": index + 1, "status": "truncated" if was_truncated else "text"})
            else:
                result["pages"].append({"page": index + 1, "status": "empty"})
            for line in nonempty_lines:
                match = _LABEL_RE.match(line)
                if not match:
                    continue
                field = _ALIAS_TO_FIELD.get(match.group("label").strip().casefold())
                value = match.group("value").strip()
                if not field or not value:
                    continue
                result["fields"].setdefault(field, []).append({
                    "value": value,
                    "evidence": {
                        "source_url": source_url,
                        "page": index + 1,
                        "quote": line.strip(),
                    },
                })
        if total_pages > max_pages:
            result["status"] = "page_limit_reached"
        elif truncated:
            result["status"] = "text_truncated"
        elif result["error_type"]:
            result["status"] = "partial" if saw_text else "unavailable"
        elif saw_text:
            result["status"] = "extracted"
        else:
            result["status"] = "needs_ocr"
    except PdfReadError as exc:
        result.update(status="invalid", error_type=type(exc).__name__)
    except (OSError, ValueError) as exc:
        result.update(status="unavailable", error_type=type(exc).__name__)
    return result


def record_extraction_result(conn: sqlite3.Connection, extraction: dict) -> None:
    """Append a source-grounded extraction observation to SQLite."""
    conn.execute(
        """INSERT INTO document_extractions
           (source_url, content_fingerprint, extraction_status, result_json,
            error_type, extracted_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            extraction["source_url"], extraction["content_fingerprint"],
            extraction["status"], json.dumps(extraction, sort_keys=True),
            extraction.get("error_type"), extraction["extracted_at"],
        ),
    )
    conn.commit()
