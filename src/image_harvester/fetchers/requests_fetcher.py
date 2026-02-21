"""Requests-based static page fetcher."""

from __future__ import annotations

import time
import threading

import requests
from requests.adapters import HTTPAdapter

from ..models import FetchResult
from .base import BaseFetcher


class RequestsFetcher(BaseFetcher):
    """HTTP fetcher using requests.Session."""

    def __init__(self, *, pool_connections: int = 64, pool_maxsize: int = 64) -> None:
        self._pool_connections = pool_connections
        self._pool_maxsize = pool_maxsize
        self._local = threading.local()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )
        adapter = HTTPAdapter(
            pool_connections=self._pool_connections,
            pool_maxsize=self._pool_maxsize,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._build_session()
            self._local.session = session
        return session

    def fetch(self, url: str, timeout_sec: float) -> FetchResult:
        started = time.perf_counter()
        try:
            response = self._session().get(url, timeout=timeout_sec)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return FetchResult(
                url=url,
                ok=True,
                html=response.text,
                status_code=response.status_code,
                error=None,
                elapsed_ms=elapsed_ms,
            )
        except requests.RequestException as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return FetchResult(
                url=url,
                ok=False,
                html=None,
                status_code=status_code,
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
