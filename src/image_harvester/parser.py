"""HTML parser for ordered image extraction."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import ParseResult


def parse_image_urls(html: str, page_url: str, selector: str) -> ParseResult:
    """Extract image URLs in page DOM order using a CSS selector."""
    soup = BeautifulSoup(html, "html.parser")
    image_urls: list[str] = []
    for img in soup.select(selector):
        src = img.get("src")
        if not src:
            continue
        image_urls.append(urljoin(page_url, src))
    return ParseResult(page_url=page_url, selector=selector, image_urls=image_urls)
