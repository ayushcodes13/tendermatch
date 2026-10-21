"""Persistence helpers for compact, secret-safe pipeline run summaries."""
import json
import time
import uuid
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


def start_run(conn):
    run_id = str(uuid.uuid4())
    started_at = _now()
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, status, started_at) VALUES (?, 'running', ?)",
        (run_id, started_at),
    )
    conn.commit()
    return run_id, time.monotonic()


def complete_run(conn, run_id, started_clock, source_results, summary):
    conn.execute(
        """UPDATE pipeline_runs
           SET status = 'completed', completed_at = ?, duration_seconds = ?,
               source_results_json = ?, summary_json = ?, error_type = NULL
           WHERE run_id = ? AND status = 'running'""",
        (_now(), max(0.0, time.monotonic() - started_clock),
         json.dumps(source_results, sort_keys=True), json.dumps(summary, sort_keys=True), run_id),
    )
    conn.commit()


def fail_run(conn, run_id, started_clock, source_results, error):
    conn.execute(
        """UPDATE pipeline_runs
           SET status = 'failed', completed_at = ?, duration_seconds = ?,
               source_results_json = ?, error_type = ?
           WHERE run_id = ? AND status = 'running'""",
        (_now(), max(0.0, time.monotonic() - started_clock),
         json.dumps(source_results, sort_keys=True), type(error).__name__, run_id),
    )
    conn.commit()
