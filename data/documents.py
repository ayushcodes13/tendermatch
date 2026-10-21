"""Bounded retrieval of explicitly linked official tender PDFs.

Retrieval is opt-in: callers must provide an allowlist of hosts whose access
conditions have been reviewed. This module never discovers links, follows
redirects, or attempts authentication.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_TIMEOUT = (5, 20)


@dataclass(frozen=True)
class DocumentResult:
    source_url: str
    status: str
    content_fingerprint: str | None = None
    storage_path: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
    fetched_at: str | None = None
    error_type: str | None = None


def _validated_host(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must be an HTTPS URL without embedded credentials")
    host = parsed.hostname.lower().rstrip(".")
    approved = {item.lower().rstrip(".") for item in allowed_hosts}
    if host not in approved:
        raise PermissionError("Document host is not allowlisted")
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, 443)}
    except (OSError, ValueError):
        raise OSError("Document host could not be resolved") from None
    if not addresses or any(not address.is_global for address in addresses):
        raise PermissionError("Document host resolves to a non-public address")
    return host


def fetch_official_pdf(
    source_url: str,
    *,
    allowed_hosts: set[str] | frozenset[str] = frozenset(),
    storage_dir: str | Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout: tuple[int, int] = DEFAULT_TIMEOUT,
    http=requests,
) -> DocumentResult:
    """Fetch one explicitly linked PDF, with no redirects or credentials.

    Failure results retain the original URL and a coarse error/status. Response
    bodies are written atomically only after size and PDF signature checks.
    """
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        _validated_host(source_url, set(allowed_hosts))
    except PermissionError:
        return DocumentResult(source_url, "blocked", fetched_at=fetched_at, error_type="HostNotAllowed")
    except (ValueError, OSError):
        return DocumentResult(source_url, "unavailable", fetched_at=fetched_at, error_type="InvalidOrUnresolvableURL")

    try:
        response = http.get(
            source_url,
            stream=True,
            allow_redirects=False,
            timeout=timeout,
            headers={"Accept": "application/pdf", "User-Agent": "TenderMatch/1.0 document fetch"},
        )
    except requests.RequestException as exc:
        return DocumentResult(source_url, "unavailable", fetched_at=fetched_at, error_type=type(exc).__name__)

    try:
        if 300 <= response.status_code < 400:
            return DocumentResult(source_url, "blocked", fetched_at=fetched_at, error_type="RedirectNotFollowed")
        if response.status_code != 200:
            return DocumentResult(source_url, "unavailable", fetched_at=fetched_at, error_type=f"HTTP{response.status_code}")
        declared_size = response.headers.get("Content-Length")
        if declared_size:
            try:
                if int(declared_size) > max_bytes:
                    return DocumentResult(source_url, "rejected", fetched_at=fetched_at, error_type="FileTooLarge")
            except ValueError:
                pass
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/pdf", "application/octet-stream"}:
            return DocumentResult(source_url, "unsupported", content_type=content_type or None, fetched_at=fetched_at, error_type="UnsupportedContentType")

        chunks: list[bytes] = []
        byte_size = 0
        try:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                byte_size += len(chunk)
                if byte_size > max_bytes:
                    return DocumentResult(source_url, "rejected", content_type=content_type, fetched_at=fetched_at, error_type="FileTooLarge")
                chunks.append(chunk)
        except requests.RequestException as exc:
            return DocumentResult(source_url, "unavailable", content_type=content_type, byte_size=byte_size, fetched_at=fetched_at, error_type=type(exc).__name__)
        content = b"".join(chunks)
        if not content.startswith(b"%PDF-"):
            return DocumentResult(source_url, "unsupported", content_type=content_type, byte_size=byte_size, fetched_at=fetched_at, error_type="InvalidPDF")
        fingerprint = hashlib.sha256(content).hexdigest()
        root = Path(storage_dir)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = root / f"{fingerprint}.pdf"
        temporary = root / f".{fingerprint}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        target.chmod(0o600)
        return DocumentResult(source_url, "downloaded", fingerprint, str(target), content_type, byte_size, fetched_at)
    finally:
        response.close()


def record_document_result(conn: sqlite3.Connection, tender_identity_key: str, result: DocumentResult) -> None:
    """Append a retrieval observation; never overwrite previous document versions."""
    conn.execute(
        """INSERT INTO tender_documents
           (tender_identity_key, source_url, content_fingerprint, storage_path,
            status, content_type, byte_size, fetched_at, error_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            tender_identity_key, result.source_url, result.content_fingerprint,
            result.storage_path, result.status, result.content_type,
            result.byte_size, result.fetched_at or datetime.now(timezone.utc).isoformat(), result.error_type,
        ),
    )
    conn.commit()


def retrieve_candidate_documents(
    conn: sqlite3.Connection,
    candidates: list[dict],
    *,
    allowed_hosts: set[str] | frozenset[str] = frozenset(),
    storage_dir: str | Path,
    max_candidates: int = 10,
    max_documents_per_candidate: int = 2,
    max_bytes: int = DEFAULT_MAX_BYTES,
    http=requests,
) -> list[DocumentResult]:
    """Retrieve explicit document links for a bounded shortlist only.

    Candidate dictionaries need `category`, `tender_identity_key`, and
    `document_links`. Uncertain `agent_review` candidates remain eligible for
    evidence gathering, while all other categories are skipped.
    """
    if max_candidates < 0 or max_documents_per_candidate < 0:
        raise ValueError("candidate and per-candidate limits cannot be negative")
    shortlist = [
        candidate for candidate in candidates
        if candidate.get("category") in {"high_signal", "agent_review"}
    ][:max_candidates]
    results = []
    for candidate in shortlist:
        identity = candidate.get("tender_identity_key")
        links = candidate.get("document_links") or []
        if not identity or not isinstance(links, (list, tuple)):
            continue
        for source_url in links[:max_documents_per_candidate]:
            if not isinstance(source_url, str):
                continue
            result = fetch_official_pdf(
                source_url,
                allowed_hosts=allowed_hosts,
                storage_dir=storage_dir,
                max_bytes=max_bytes,
                http=http,
            )
            record_document_result(conn, identity, result)
            results.append(result)
    return results


def document_result_dict(result: DocumentResult) -> dict:
    """Return a JSON-ready result for pipeline reporting."""
    return asdict(result)
