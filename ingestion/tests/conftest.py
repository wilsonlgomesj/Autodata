"""Shared pytest fixtures and sys.path setup for the ingestion test suite."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
INGESTION_SRC = REPO_ROOT / "ingestion" / "src"
TOOLS_DIR = REPO_ROOT / "tools"

for path in (INGESTION_SRC, TOOLS_DIR):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)
