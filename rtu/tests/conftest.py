"""Pytest conftest for the RTU test suite."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATHS = [REPO_ROOT / "rtu" / "src", REPO_ROOT / "ingestion" / "src"]

for p in reversed(SRC_PATHS):
    s = str(p)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

# Evict stale namespace packages
for name in ("rtu", "ingestion"):
    mod = sys.modules.get(name)
    if mod is not None and not getattr(mod, "__file__", None):
        del sys.modules[name]
