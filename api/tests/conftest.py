"""Pytest conftest for API tests.

Inserts api/src at sys.path[0] and evicts a stale namespace import if
pytest's collection already resolved 'api' as a namespace package pointing
at the outer directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATHS = [REPO_ROOT / "api" / "src"]

for p in reversed(SRC_PATHS):
    s = str(p)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

_pkg = sys.modules.get("api")
if _pkg is not None and not getattr(_pkg, "__file__", None):
    del sys.modules["api"]
