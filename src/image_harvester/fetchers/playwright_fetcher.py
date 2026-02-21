"""Optional Playwright-based page fetcher."""

from __future__ import annotations

import time

from ..models import FetchResult
from .base import BaseFetcher


class PlaywrightFetcher(BaseFetcher):
    """HTML fetcher using Playwright's sync API."""

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:  # pragma: no cover - import depends on optional dep
            raise RuntimeError(
                "Playwright 不可用。请先执行 `pip install -e \".[playwright]\"` 安装依赖。"
            ) from exc
        self._sync_playwright = sync_playwright

    def fetch(self, url: str, timeout_sec: float) -> FetchResult:
        started = time.perf_counter()
        timeout_ms = int(timeout_sec * 1000)
        try:
            with self._sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                response = page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
                status_code = response.status if response else None
                browser.close()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(
                url=url,
                ok=True,
                html=html,
                status_code=status_code,
                error=None,
                elapsed_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(
                url=url,
                ok=False,
                html=None,
                status_code=None,
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
