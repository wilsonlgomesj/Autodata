"""Thin wrapper around tools/validate.py for use inside the ingestion service.

Kept separate so the ingestion service can be packaged and shipped without
copying the entire validator module. Prefers the installed module if present;
falls back to path-based import for local dev.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _import_validator():
    # First try a direct import (works when tools/ is on PYTHONPATH).
    try:
        from validate import Report, validate_payload  # type: ignore
        return Report, validate_payload
    except ImportError:
        pass

    # Fallback: find repo root heuristically.
    here = Path(__file__).resolve()
    for ancestor in [*here.parents]:
        candidate = ancestor / "tools" / "validate.py"
        if candidate.exists():
            sys.path.insert(0, str(candidate.parent))
            from validate import Report, validate_payload  # type: ignore
            return Report, validate_payload
    raise ImportError("Could not locate tools/validate.py")


Report, _validate_payload = _import_validator()


def validate(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a payload dict. Returns (ok, errors)."""
    report = Report()
    _validate_payload(payload, report)
    return report.ok(), list(report.errors)
