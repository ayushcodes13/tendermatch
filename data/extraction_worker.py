"""Isolated command-line worker for bounded tender PDF extraction."""
from __future__ import annotations

import json
import sys

from data.extraction import (
    _apply_worker_resource_limits,
    _extract_pdf_requirements_in_worker,
    _worker_failure,
)


def main() -> int:
    try:
        arguments = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError):
        return 2
    if not isinstance(arguments, dict):
        return 2

    try:
        _apply_worker_resource_limits()
        result = _extract_pdf_requirements_in_worker(**arguments)
    except MemoryError:
        result = _worker_failure(arguments, "limited", "MemoryLimitExceeded")
    except Exception as exc:
        error_type = str(exc) if str(exc) in {
            "ResourceLimitsUnavailable", "MemoryLimitTooSmall", "CPULimitTooSmall"
        } else type(exc).__name__
        result = _worker_failure(arguments, "unavailable", error_type)

    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
