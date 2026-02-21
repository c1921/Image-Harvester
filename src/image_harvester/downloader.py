"""Image downloader with retry and metadata collection."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from .models import DownloadResult, utc_now_iso


class ImageDownloader:
    """HTTP image downloader."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )

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
                response = self.session.get(url, timeout=timeout_sec, stream=True)
                last_status = response.status_code
                response.raise_for_status()

                destination.parent.mkdir(parents=True, exist_ok=True)
                hasher = hashlib.sha256()
                size_bytes = 0

                with destination.open("wb") as fp:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        fp.write(chunk)
                        hasher.update(chunk)
                        size_bytes += len(chunk)

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
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts and delay_sec > 0:
                    time.sleep(delay_sec)

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
