"""Helpers for building sequential image URLs from a seed URL."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


def extract_sequence_seed(image_url: str) -> tuple[str, int, str, int] | None:
    """Extract (base_path, number_width, extension, start_index) from URL."""
    parsed = urlsplit(image_url)
    match = re.search(r"^(.*?/)(\d+)\.([A-Za-z0-9]{2,5})$", parsed.path)
    if match is None:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    base_path = origin + match.group(1)
    number_text = match.group(2)
    extension = match.group(3)
    start_index = int(number_text)
    if start_index < 1:
        return None
    return base_path, len(number_text), extension, start_index


def build_sequence_url(base_path: str, number_width: int, extension: str, index: int) -> str:
    """Build one image URL using fixed-width number formatting."""
    return f"{base_path}{index:0{number_width}d}.{extension}"
