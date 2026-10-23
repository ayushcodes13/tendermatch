"""Authenticated local review server for salesperson tender feedback."""

from __future__ import annotations

import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import hmac
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import threading
from urllib.parse import urlparse

from config import FEEDBACK_REVIEWERS
from data.db import get_connection, init_db
from data.feedback import FEEDBACK_LABELS, capture_feedback


WEB_DIR = Path(__file__).resolve().parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
AUTH_TOKEN_ENV = "TENDERMATCH_REVIEW_AUTH_TOKEN"
AUTH_REVIEWER_ENV = "TENDERMATCH_REVIEW_REVIEWER"
AUTH_TOKENS_MAP_ENV = "TENDERMATCH_REVIEW_TOKENS"
MIN_TOKEN_LENGTH = 16
MAX_REQUEST_BODY_BYTES = 64 * 1024  # 64 KB limit
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DB_WRITE_LOCK = threading.Lock()

logger = logging.getLogger("tendermatch.review")


def get_configured_token() -> str:
    """Retrieve and validate the configured review authentication token.

    Raises:
        ValueError: If token is not set, empty, or shorter than MIN_TOKEN_LENGTH.
    """
    token = os.environ.get(AUTH_TOKEN_ENV, "").strip()
    if not token:
        raise ValueError(
            f"Review interface requires {AUTH_TOKEN_ENV} to be configured. "
            "No default or fallback token is permitted."
        )
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(
            f"{AUTH_TOKEN_ENV} must be at least {MIN_TOKEN_LENGTH} characters long (got {len(token)})."
        )
    return token


def resolve_reviewer_for_token(auth_token: str | None) -> str | None:
    """Resolve authenticated reviewer identity bound to the given Bearer token.

    Precedence:
    1. TENDERMATCH_REVIEW_TOKENS: JSON mapping of {token: reviewer_email}.
    2. TENDERMATCH_REVIEW_REVIEWER: Single designated operator bound to TENDERMATCH_REVIEW_AUTH_TOKEN.
    3. If trusted reviewers set contains exactly one reviewer, bind to it.
    """
    if not auth_token:
        return None

    # 1. Multi-token JSON mapping
    tokens_json = os.getenv(AUTH_TOKENS_MAP_ENV, "").strip()
    if tokens_json:
        try:
            mapping = json.loads(tokens_json)
            if isinstance(mapping, dict):
                for tok, rev in mapping.items():
                    if hmac.compare_digest(tok.strip(), auth_token):
                        return rev.strip()
        except Exception:
            pass

    # 2. Single-user designated reviewer
    designated = os.getenv(AUTH_REVIEWER_ENV, "").strip()
    if designated:
        return designated

    # 3. Exactly one reviewer in trusted reviewers
    trusted = get_trusted_reviewers()
    if len(trusted) == 1:
        return next(iter(trusted))

    return None


def get_trusted_reviewers() -> frozenset[str]:
    """Retrieve trusted reviewers from environment or config."""
    env_reviewers = os.getenv("TENDERMATCH_FEEDBACK_REVIEWERS", "")
    if env_reviewers.strip():
        return frozenset(r.strip() for r in env_reviewers.split(",") if r.strip())
    return FEEDBACK_REVIEWERS


class TenderMatchReviewHandler(BaseHTTPRequestHandler):
    server_version = "TenderMatchReview/1.2"

    def log_message(self, format: str, *args):
        """Redact sensitive query parameters and headers from standard logs."""
        msg = format % args
        clean_msg = msg.split("?")[0] if "?" in msg else msg
        sys.stderr.write(f"[{self.log_date_time_string()}] {clean_msg}\n")

    def _get_auth_token(self) -> str | None:
        """Extract and safely verify Bearer token from Authorization header.

        Query parameter token authentication is strictly rejected to prevent
        credential leakage in browser history, logs, and Referer headers.
        """
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        candidate = auth_header[7:].strip()
        if not candidate:
            return None

        # Check multi-token map if present
        tokens_json = os.getenv(AUTH_TOKENS_MAP_ENV, "").strip()
        if tokens_json:
            try:
                mapping = json.loads(tokens_json)
                if isinstance(mapping, dict):
                    for tok in mapping.keys():
                        if hmac.compare_digest(tok.strip(), candidate):
                            return candidate
            except Exception:
                pass

        # Check primary token
        try:
            expected = get_configured_token()
            if hmac.compare_digest(candidate, expected):
                return candidate
        except ValueError:
            pass

        return None

    def _check_host_header(self) -> bool:
        """Validate Host header against loopback to prevent DNS rebinding."""
        host_header = self.headers.get("Host", "")
        if host_header:
            req_host = host_header.split(":")[0].strip().lower()
            if req_host not in LOOPBACK_HOSTS:
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({
                        "error": "Forbidden",
                        "message": f"Non-loopback Host '{req_host}' rejected. Single-user loopback model enforced.",
                    }).encode("utf-8")
                )
                return False
        return True

    def _send_security_headers(self):
        """Send comprehensive defensive headers on all responses."""
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")

    def _check_authenticated(self) -> bool:
        if self._get_auth_token() is not None:
            return True
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("WWW-Authenticate", 'Bearer realm="TenderMatch Review"')
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(
            json.dumps({
                "error": "Unauthorized",
                "message": f"Set {AUTH_TOKEN_ENV} and provide Authorization: Bearer <token>.",
            }).encode("utf-8")
        )
        return False

    def do_GET(self):
        if not self._check_host_header():
            return

        parsed = urlparse(self.path)
        path = parsed.path

        # Static assets
        if path == "/" or path == "/index.html":
            self._serve_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        elif path == "/styles.css":
            self._serve_file(WEB_DIR / "styles.css", "text/css; charset=utf-8")
            return
        elif path == "/app.js":
            self._serve_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
            return

        # Authenticated API endpoints
        if not self._check_authenticated():
            return

        if path == "/api/auth/check":
            token = self._get_auth_token()
            bound_rev = resolve_reviewer_for_token(token)
            self._send_json({"authenticated": True, "bound_reviewer": bound_rev})
        elif path == "/api/reviewers":
            token = self._get_auth_token()
            bound_rev = resolve_reviewer_for_token(token)
            reviewers = [bound_rev] if bound_rev else sorted(list(get_trusted_reviewers()))
            self._send_json({"reviewers": reviewers, "bound_reviewer": bound_rev})
        elif path == "/api/labels":
            self._send_json({"labels": sorted(list(FEEDBACK_LABELS))})
        elif path == "/api/tenders":
            self._handle_get_tenders()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if not self._check_host_header():
            return
        if not self._check_authenticated():
            return

        parsed = urlparse(self.path)
        if parsed.path == "/api/feedback":
            self._handle_post_feedback()
        else:
            self.send_error(404, "Not Found")

    def _serve_file(self, file_path: Path, content_type: str):
        if not file_path.is_file():
            self.send_error(404, "File not found")
            return
        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(500, "Error reading file")

    def _send_json(self, data: dict | list, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_tenders(self):
        conn = get_connection()
        try:
            init_db(conn)
            cursor = conn.execute("""
                SELECT t.id, t.tender_id, t.identity_key, t.version_fingerprint,
                       t.title, t.organization, t.published_date, t.closing_date,
                       t.source_url, t.source_portal, t.raw_text, t.emailed
                FROM tenders t
                ORDER BY t.id DESC LIMIT 100
            """)
            rows = cursor.fetchall()

            tenders = []
            for row in rows:
                tid, official_id, identity_key, version_fp, title, org, pub_date, close_date, url, portal, text, emailed = row

                # Retrieve matches
                match_cursor = conn.execute("""
                    SELECT manufacturer_id, manufacturer_name, score, confidence
                    FROM tender_matches
                    WHERE tender_identity_key = ?
                    ORDER BY score DESC
                """, (identity_key,))
                matches = [
                    {
                        "manufacturer_id": m[0],
                        "manufacturer_name": m[1],
                        "score": m[2],
                        "confidence": m[3],
                    }
                    for m in match_cursor.fetchall()
                ]

                # Retrieve existing feedback history
                fb_cursor = conn.execute("""
                    SELECT label, reviewer, reviewed_at, reason, manufacturer_id
                    FROM salesperson_feedback
                    WHERE tender_identity_key = ?
                    ORDER BY id DESC
                """, (identity_key,))
                feedback = [
                    {
                        "label": f[0],
                        "reviewer": f[1],
                        "reviewed_at": f[2],
                        "reason": f[3],
                        "manufacturer_id": f[4],
                    }
                    for f in fb_cursor.fetchall()
                ]

                # Check amendments
                amend_cursor = conn.execute("""
                    SELECT change_status, change_types_json, evidence_json
                    FROM tender_amendments
                    WHERE tender_identity_key = ?
                    ORDER BY id DESC LIMIT 1
                """, (identity_key,))
                amend_row = amend_cursor.fetchone()
                amendment = None
                if amend_row:
                    try:
                        amendment = {
                            "status": amend_row[0],
                            "change_types": json.loads(amend_row[1]),
                            "evidence": json.loads(amend_row[2]),
                        }
                    except Exception:
                        pass

                tenders.append({
                    "id": tid,
                    "tender_id": official_id,
                    "identity_key": identity_key,
                    "version_fingerprint": version_fp,
                    "title": title,
                    "organization": org,
                    "published_date": pub_date,
                    "closing_date": close_date,
                    "source_url": url,
                    "source_portal": portal,
                    "matches": matches,
                    "feedback": feedback,
                    "amendment": amendment,
                })

            self._send_json({"tenders": tenders})
        finally:
            conn.close()

    def _handle_post_feedback(self):
        # 1. CSRF / Cross-Origin check
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if origin:
            parsed_origin = urlparse(origin)
            hostname = (parsed_origin.hostname or "").lower()
            if hostname not in LOOPBACK_HOSTS:
                self._send_json({"error": "Forbidden: Cross-origin feedback submission rejected"}, 403)
                return
        sec_fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if sec_fetch_site == "cross-site":
            self._send_json({"error": "Forbidden: Cross-site request rejected"}, 403)
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("application/json"):
            self._send_json({"error": "Unsupported Media Type: application/json required"}, 415)
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            self._send_json({"error": "Invalid Content-Length header"}, 400)
            return

        if content_length <= 0:
            self._send_json({"error": "Empty request body"}, 400)
            return

        if content_length > MAX_REQUEST_BODY_BYTES:
            self._send_json({"error": f"Request body exceeds maximum permitted size of {MAX_REQUEST_BODY_BYTES} bytes"}, 413)
            return

        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                self._send_json({"error": "JSON payload must be an object"}, 400)
                return
        except Exception:
            self._send_json({"error": "Malformed JSON payload"}, 400)
            return

        tender_identity_key = payload.get("tender_identity_key")
        manufacturer_id = payload.get("manufacturer_id")
        label = payload.get("label")
        reviewer = payload.get("reviewer")
        reason = payload.get("reason")
        tender_version = payload.get("tender_version")

        # 2. Reviewer Identity Spoofing Protection
        token = self._get_auth_token()
        bound_reviewer = resolve_reviewer_for_token(token)
        if bound_reviewer and reviewer != bound_reviewer:
            self._send_json({
                "error": f"Reviewer identity spoofing rejected: token is bound to '{bound_reviewer}', cannot submit as '{reviewer}'"
            }, 403)
            return

        # 3. Reason sanitization: reject null bytes and strip non-printable control chars
        if reason:
            if "\x00" in reason:
                self._send_json({"error": "Invalid character in reviewer notes: null bytes are prohibited"}, 400)
                return
            reason = "".join(ch for ch in reason if ch.isprintable() or ch in "\n\r\t")

        conn = get_connection()
        try:
            init_db(conn)
            # Verify tender_identity_key exists
            row = conn.execute("SELECT id FROM tenders WHERE identity_key = ?", (tender_identity_key,)).fetchone()
            if not row:
                self._send_json({"error": f"Tender identity key '{tender_identity_key}' not found in database"}, 404)
                return

            with _DB_WRITE_LOCK:
                feedback_id = capture_feedback(
                    conn,
                    tender_identity_key=tender_identity_key,
                    manufacturer_id=manufacturer_id,
                    label=label,
                    reviewer=reviewer,
                    trusted_reviewers=get_trusted_reviewers(),
                    reason=reason,
                    tender_version=tender_version,
                )
            self._send_json({
                "status": "success",
                "feedback_id": feedback_id,
                "label": label,
                "reviewer": reviewer,
            }, 201)
        except (ValueError, PermissionError) as exc:
            self._send_json({"error": str(exc)}, 400)
        finally:
            conn.close()


def run_review_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, allow_public: bool = False):
    """Start authenticated TenderMatch review HTTP server.

    Args:
        host: Host IP or hostname to bind to. Default: 127.0.0.1.
        port: TCP port. Default: 8080.
        allow_public: If True, rejected with guidance on secure TLS reverse-proxy deployment.
    """
    token = get_configured_token()

    if host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"Insecure public binding to host '{host}' rejected. "
            "TenderMatch review server operates under a trusted single-user loopback model "
            "and must bind to loopback (127.0.0.1, localhost, ::1). "
            "Public access over unencrypted HTTP without a TLS reverse proxy is strictly prohibited."
        )

    if allow_public:
        raise ValueError(
            "--allow-public is not supported in the single-user prototype model. "
            "To access the review interface across hosts, terminate TLS using a dedicated reverse proxy "
            "(e.g. Nginx, Caddy) forwarding to 127.0.0.1 with strong mutual or perimeter authentication."
        )

    server = HTTPServer((host, port), TenderMatchReviewHandler)
    bound_rev = resolve_reviewer_for_token(token)
    rev_msg = f" (bound operator: {bound_rev})" if bound_rev else " (single-user loopback mode)"
    print(f"🚀 TenderMatch Salesperson Review Interface running at http://{host}:{port}/")
    print(f"   Security: Bearer authentication enforced ({AUTH_TOKEN_ENV} configured with {len(token)} chars; value redacted){rev_msg}")
    print(f"   Deployment: Trusted single-user loopback model enforced on {host}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server.")
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run authenticated TenderMatch review web server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 8080)")
    parser.add_argument("--allow-public", action="store_true", help="Allow binding to non-loopback host")
    args = parser.parse_args()
    try:
        run_review_server(args.host, args.port, allow_public=args.allow_public)
    except (ValueError, RuntimeError) as exc:
        print(f"❌ Server startup failed: {exc}", file=sys.stderr)
        sys.exit(1)
