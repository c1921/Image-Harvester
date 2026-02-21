"""Naming utilities for page directories and image files."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse


def source_id_from_page_url(page_url: str, page_num: int) -> str:
    """Extract source id from page URL's trailing numeric segment or fallback to page number."""
    parsed = urlparse(page_url)
    path = parsed.path.rstrip("/")
    last_segment = path.split("/")[-1] if path else ""
    match = re.search(r"(\d+)", last_segment)
    if match:
        return match.group(1)
    return str(page_num)


def _safe_filename(name: str) -> str:
    sanitized = re.sub(r"[<>:\"/\\|?*\x00-\x1F]", "_", name)
    sanitized = sanitized.strip().strip(".")
    return sanitized or "image.bin"


def page_dir_name(page_num: int, source_id: str) -> str:
    """Return page directory name using fixed convention."""
    _ = source_id
    return f"{page_num:06d}"


def image_file_name(image_index: int, image_url: str) -> str:
    """Return image file name using fixed convention and original basename."""
    _ = image_index
    parsed = urlparse(image_url)
    basename = Path(unquote(parsed.path)).name or "image.bin"
    basename = _safe_filename(basename)
    return basename
