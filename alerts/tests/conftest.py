"""Pytest conftest for alerts tests.

Inserts alerts/src at sys.path[0] so that 'alerts' resolves to the real
package rather than the outer namespace directory, and evicts a stale
namespace import if pytest's collection created one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATHS = [REPO_ROOT / "alerts" / "src", REPO_ROOT / "tools"]

for p in reversed(SRC_PATHS):
    s = str(p)
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)

_pkg = sys.modules.get("alerts")
if _pkg is not None and not getattr(_pkg, "__file__", None):
    del sys.modules["alerts"]
