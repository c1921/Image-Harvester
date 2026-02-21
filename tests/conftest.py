"""Test bootstrap."""

from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path
from typing import Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def workspace_temp_dir() -> Iterator[Path]:
    """Create temp dir under workspace to avoid OS temp permission issues."""
    base = ROOT / "manual-temp-tests"
    base.mkdir(parents=True, exist_ok=True)
    case_dir = base / f"case-{uuid.uuid4().hex[:8]}"
    case_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield case_dir
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)
