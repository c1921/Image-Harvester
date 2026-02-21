"""Image downloader with retry and metadata collection."""

from __future__ import annotations

import hashlib
import random
import threading
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from .models import DownloadResult, utc_now_iso


class _AdaptiveRateLimiter:
    """Thread-safe token bucket with simple adaptive rate control."""

    def __init__(self, *, rate: float, burst: int) -> None:
        self._capacity = float(max(1, burst))
        self._tokens = self._capacity
        self._base_rate = max(0.1, rate)
        self._current_rate = self._base_rate
        self._min_rate = min(1.0, self._base_rate)
        self._max_rate = max(self._base_rate, self._base_rate * 2.0)
        self._success_count = 0
        self._last_refill = time.monotonic()
        self._last_adjust = self._last_refill
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            sleep_for = 0.0
            with self._lock:
                now = time.monotonic()
                self._refill_locked(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                shortage = 1.0 - self._tokens
                sleep_for = shortage / max(0.1, self._current_rate)
            if sleep_for > 0:
                time.sleep(sleep_for)

    def report_success(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._refill_locked(now)
            self._success_count += 1
            # Keep increasing rate gradually while the server is healthy.
            if now - self._last_adjust >= 30.0:
                self._current_rate = min(self._max_rate, self._current_rate * 1.1)
                self._success_count = 0
                self._last_adjust = now

    def report_throttled(self) -> None:
        with self._lock:
            self._current_rate = max(self._min_rate, self._current_rate * 0.7)
            self._success_count = 0
            self._last_adjust = time.monotonic()

    def _refill_locked(self, now: float) -> None:
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._current_rate)
        self._last_refill = now


class ImageDownloader:
    """HTTP image downloader."""

    def __init__(
        self,
        *,
        max_requests_per_sec: float = 20.0,
        max_burst: int = 30,
        backoff_base_sec: float = 0.5,
        backoff_max_sec: float = 8.0,
        pool_connections: int = 64,
        pool_maxsize: int = 64,
        chunk_size: int = 65536,
    ) -> None:
        self._backoff_base_sec = max(0.0, backoff_base_sec)
        self._backoff_max_sec = max(self._backoff_base_sec, backoff_max_sec)
        self._chunk_size = max(4096, chunk_size)
        self._pool_connections = max(1, pool_connections)
        self._pool_maxsize = max(1, pool_maxsize)
        self._local = threading.local()
        self._limiter = _AdaptiveRateLimiter(
            rate=max_requests_per_sec,
            burst=max_burst,
        )

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

    def _retry_delay(self, *, attempt: int, delay_sec: float, http_status: int | None) -> float:
        if http_status in {429, 503}:
            base = max(delay_sec, self._backoff_base_sec)
            backoff = min(self._backoff_max_sec, base * (2 ** (attempt - 1)))
            return backoff * random.uniform(0.8, 1.2)
        if delay_sec > 0:
            return delay_sec
        if self._backoff_base_sec <= 0:
            return 0.0
        return min(self._backoff_max_sec, self._backoff_base_sec * (2 ** (attempt - 1)))

    def download(
        self,
        url: str,
        destination: Path,
        timeout_sec: float,
        retries: int,
        delay_sec: float,
    ) -> DownloadResult:
        """Download one image with retries and return structured result."""
        attempts = retries + 1
        last_error: str | None = None
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._limiter.acquire()
                with self._session().get(url, timeout=timeout_sec, stream=True) as response:
                    last_status = response.status_code
                    response.raise_for_status()

                    destination.parent.mkdir(parents=True, exist_ok=True)
                    hasher = hashlib.sha256()
                    size_bytes = 0

                    with destination.open("wb") as fp:
                        for chunk in response.iter_content(chunk_size=self._chunk_size):
                            if not chunk:
                                continue
                            fp.write(chunk)
                            hasher.update(chunk)
                            size_bytes += len(chunk)

                self._limiter.report_success()

                return DownloadResult(
                    ok=True,
                    retries_used=attempt - 1,
                    http_status=response.status_code,
                    content_type=response.headers.get("Content-Type"),
                    size_bytes=size_bytes,
                    sha256=hasher.hexdigest(),
                    downloaded_at=utc_now_iso(),
                    error=None,
                )
            except requests.RequestException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code is not None:
                    last_status = status_code
                if status_code in {429, 503}:
                    self._limiter.report_throttled()
                last_error = str(exc)
                if attempt < attempts:
                    wait_sec = self._retry_delay(
                        attempt=attempt,
                        delay_sec=delay_sec,
                        http_status=status_code,
                    )
                    if wait_sec > 0:
                        time.sleep(wait_sec)
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts:
                    wait_sec = self._retry_delay(
                        attempt=attempt,
                        delay_sec=delay_sec,
                        http_status=None,
                    )
                    if wait_sec > 0:
                        time.sleep(wait_sec)

        return DownloadResult(
            ok=False,
            retries_used=retries,
            http_status=last_status,
            content_type=None,
            size_bytes=None,
            sha256=None,
            downloaded_at=None,
            error=last_error,
        )


def file_sha256(path: Path) -> str:
    """Compute SHA-256 for an existing file."""
    hasher = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(8192), b""):
            if chunk:
                hasher.update(chunk)
    return hasher.hexdigest()
