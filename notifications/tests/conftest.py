"""Pytest conftest for notifications tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATHS = [REPO_ROOT / "notifications" / "src"]

for p in reversed(SRC_PATHS):
    s = str(p)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

_pkg = sys.modules.get("notifications")
if _pkg is not None and not getattr(_pkg, "__file__", None):
    del sys.modules["notifications"]
