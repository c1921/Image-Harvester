"""HTML parser for ordered image extraction."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import GalleryPageMeta, ParseResult


def parse_image_urls(html: str, page_url: str, selector: str) -> ParseResult:
    """Extract image URLs in page DOM order using a CSS selector."""
    soup = BeautifulSoup(html, "html.parser")
    image_urls: list[str] = []
    for img in soup.select(selector):
        src = img.get("src")
        if not src:
            continue
        image_urls.append(urljoin(page_url, src))
    return ParseResult(
        page_url=page_url,
        selector=selector,
        image_urls=image_urls,
        gallery_meta=_parse_gallery_meta(soup),
    )


def parse_gallery_upper_bound(html: str, selector: str) -> int | None:
    """Extract expected image upper-bound count from a page text node."""
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(selector)
    if node is None:
        return None
    text = node.get_text(strip=True)
    match = re.search(r"(\d+)", text)
    if match is None:
        return None
    value = int(match.group(1))
    return value if value > 0 else None


def _parse_gallery_meta(soup: BeautifulSoup) -> GalleryPageMeta:
    title = ""
    published_date = ""
    tags: list[str] = []

    intro = soup.select_one("div.gallery_jieshao")
    if intro is not None:
        title_node = intro.select_one("h1")
        if title_node is not None:
            title = title_node.get_text(strip=True)

        published_date = _extract_published_date(
            [node.get_text(" ", strip=True) for node in intro.select("p")]
        )
        tags = _stable_unique(
            [
                node.get_text(strip=True)
                for node in intro.select("p a")
                if node.get_text(strip=True)
            ]
        )

    return GalleryPageMeta(
        title=title,
        published_date=published_date,
        tags=tags,
        organizations=_extract_people_by_role(soup, "机构"),
        models=_extract_people_by_role(soup, "模特"),
    )


def _extract_published_date(texts: list[str]) -> str:
    for text in texts:
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
        if match is not None:
            return match.group(0)
    return ""


def _extract_people_by_role(soup: BeautifulSoup, role: str) -> list[str]:
    names: list[str] = []
    for card in soup.select("div.gallery_nav .gallery_renwu"):
        role_node = card.select_one(".gallery_chuangzuo, .gallery_chujing")
        if role_node is None:
            continue

        role_text = role_node.get_text(strip=True)
        if not role_text:
            classes = role_node.get("class") or []
            if "gallery_chuangzuo" in classes:
                role_text = "机构"
            elif "gallery_chujing" in classes:
                role_text = "模特"

        if role_text != role:
            continue

        name_node = card.select_one(".gallery_renwu_title a")
        if name_node is None:
            continue
        name = name_node.get_text(strip=True)
        if name:
            names.append(name)
    return _stable_unique(names)


def _stable_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
