"""Pytest conftest for ingestion tests.

Inserts ingestion/src at sys.path[0] so that 'ingestion' resolves to the
real package regardless of cwd or of pytest's namespace-package discovery.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATHS = [REPO_ROOT / "ingestion" / "src", REPO_ROOT / "tools"]

for p in reversed(SRC_PATHS):  # reversed so the first one ends up at [0]
    s = str(p)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

# If pytest's collection already imported 'ingestion' as a namespace package
# pointing at the outer directory, drop it so the real src/ingestion package
# resolves on next import.
_ing = sys.modules.get("ingestion")
if _ing is not None and not getattr(_ing, "__file__", None):
    # namespace package (no __init__); evict it
    del sys.modules["ingestion"]
