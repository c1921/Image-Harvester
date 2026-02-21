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


def pytest_configure(config: pytest.Config) -> None:
    """Pre-create cache_dir to avoid flaky tempdir creation on Windows."""
    configured = config.getini("cache_dir")
    if not configured:
        return
    cache_dir = Path(configured)
    if not cache_dir.is_absolute():
        cache_dir = Path(config.rootpath) / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)


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
