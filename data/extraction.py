"""Native-text extraction of tender requirement lines with page citations."""
from __future__ import annotations

import json
import math
import os
import re
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_WORKER_TIMEOUT_SECONDS = 20
DEFAULT_WORKER_TIMEOUT_SECONDS = MAX_WORKER_TIMEOUT_SECONDS
WORKER_MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
WORKER_CPU_LIMIT_SECONDS = 15

MAX_PDF_PAGES = 100
MAX_PAGE_TEXT_CHARS = 100_000
MAX_EXTRACTED_VALUES = 500
MAX_EVIDENCE_LINE_CHARS = 10_000
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


def _extract_pdf_requirements_in_worker(
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
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

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
        field_limit_reached = False
        extracted_values = 0
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
                if len(line) > MAX_EVIDENCE_LINE_CHARS:
                    truncated = True
                    continue
                if extracted_values >= MAX_EXTRACTED_VALUES:
                    field_limit_reached = True
                    break
                result["fields"].setdefault(field, []).append({
                    "value": value,
                    "evidence": {
                        "source_url": source_url,
                        "page": index + 1,
                        "quote": line.strip(),
                    },
                })
                extracted_values += 1
            if field_limit_reached:
                break
        if total_pages > max_pages:
            result["status"] = "page_limit_reached"
        elif field_limit_reached:
            result["status"] = "field_limit_reached"
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


def _apply_worker_resource_limits() -> None:
    """Apply CPU limits everywhere supported and an address-space cap on Linux."""
    import sys

    try:
        import resource
        cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
        cpu_hard_limit = (
            WORKER_CPU_LIMIT_SECONDS + 1
            if cpu_hard == resource.RLIM_INFINITY
            else min(WORKER_CPU_LIMIT_SECONDS + 1, cpu_hard)
        )
        cpu_soft_limit = min(WORKER_CPU_LIMIT_SECONDS, cpu_hard_limit)
        if cpu_soft_limit < 1:
            raise RuntimeError("CPULimitTooSmall")
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft_limit, cpu_hard_limit))
        if sys.platform.startswith("linux"):
            memory_hard = resource.getrlimit(resource.RLIMIT_AS)[1]
            memory_limit = (
                WORKER_MEMORY_LIMIT_BYTES
                if memory_hard == resource.RLIM_INFINITY
                else min(WORKER_MEMORY_LIMIT_BYTES, memory_hard)
            )
            if memory_limit < 128 * 1024 * 1024:
                raise RuntimeError("MemoryLimitTooSmall")
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    except (ImportError, OSError, ValueError) as exc:
        raise RuntimeError("ResourceLimitsUnavailable") from exc


def _worker_failure(arguments: dict, status: str, error_type: str) -> dict:
    return {
        "source_url": arguments["source_url"],
        "content_fingerprint": arguments["content_fingerprint"],
        "status": status,
        "pages": [],
        "fields": {},
        "error_type": error_type,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }


def _worker_environment() -> dict[str, str]:
    """Pass only runtime paths and locale to the untrusted-document worker."""
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "WINDIR")
        if key in os.environ
    }
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return environment


def extract_pdf_requirements(
    pdf_path: str | Path,
    *,
    source_url: str,
    content_fingerprint: str,
    max_pages: int = MAX_PDF_PAGES,
    max_page_text_chars: int = MAX_PAGE_TEXT_CHARS,
    worker_timeout_seconds: float = DEFAULT_WORKER_TIMEOUT_SECONDS,
) -> dict:
    """Extract a PDF in a short-lived child with CPU, memory, and wall-clock caps."""
    if not 1 <= max_pages <= MAX_PDF_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_PDF_PAGES}")
    if not 1 <= max_page_text_chars <= MAX_PAGE_TEXT_CHARS:
        raise ValueError(
            f"max_page_text_chars must be between 1 and {MAX_PAGE_TEXT_CHARS}"
        )
    if (
        isinstance(worker_timeout_seconds, bool)
        or not isinstance(worker_timeout_seconds, (int, float))
        or not math.isfinite(worker_timeout_seconds)
        or not 0 < worker_timeout_seconds <= MAX_WORKER_TIMEOUT_SECONDS
    ):
        raise ValueError(
            f"worker_timeout_seconds must be between 0 and {MAX_WORKER_TIMEOUT_SECONDS}"
        )

    arguments = {
        "pdf_path": str(Path(pdf_path).resolve()),
        "source_url": source_url,
        "content_fingerprint": content_fingerprint,
        "max_pages": max_pages,
        "max_page_text_chars": max_page_text_chars,
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "data.extraction_worker"],
            input=json.dumps(arguments),
            capture_output=True,
            text=True,
            timeout=worker_timeout_seconds,
            cwd=Path(__file__).resolve().parents[1],
            env=_worker_environment(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _worker_failure(arguments, "limited", "WorkerTimeout")
    except OSError as exc:
        return _worker_failure(arguments, "unavailable", type(exc).__name__)

    if completed.returncode:
        if completed.returncode == -getattr(signal, "SIGXCPU", -999):
            return _worker_failure(arguments, "limited", "WorkerCPUTimeLimit")
        return _worker_failure(arguments, "unavailable", "WorkerExited")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _worker_failure(arguments, "unavailable", "InvalidWorkerResponse")
    if not isinstance(result, dict):
        return _worker_failure(arguments, "unavailable", "InvalidWorkerResponse")
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
            extraction.get("error_type"),
            extraction.get("extracted_at") or datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
