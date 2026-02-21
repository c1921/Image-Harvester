from __future__ import annotations

import hashlib
from pathlib import Path

from image_harvester.models import DownloadResult, FetchResult, RunConfig, utc_now_iso
from image_harvester.tui.services import RunWorker


class FakeFetcher:
    def __init__(self, html_by_url: dict[str, str]) -> None:
        self.html_by_url = html_by_url

    def fetch(self, url: str, timeout_sec: float) -> FetchResult:
        html = self.html_by_url.get(url)
        if html is None:
            return FetchResult(
                url=url,
                ok=False,
                html=None,
                status_code=404,
                error="not found",
                elapsed_ms=1,
            )
        return FetchResult(
            url=url,
            ok=True,
            html=html,
            status_code=200,
            error=None,
            elapsed_ms=1,
        )


class AlwaysSuccessDownloader:
    def download(
        self,
        url: str,
        destination: Path,
        timeout_sec: float,
        retries: int,
        delay_sec: float,
    ) -> DownloadResult:
        payload = url.encode("utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return DownloadResult(
            ok=True,
            retries_used=0,
            http_status=200,
            content_type="image/jpeg",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            downloaded_at=utc_now_iso(),
            error=None,
        )


class CrashDownloader:
    def download(
        self,
        url: str,
        destination: Path,
        timeout_sec: float,
        retries: int,
        delay_sec: float,
    ) -> DownloadResult:
        raise RuntimeError("simulated downloader crash")


def _config(tmp_path: Path, **overrides: object) -> RunConfig:
    payload: dict[str, object] = {
        "url_template": "https://example.test/gallery/{num}.html",
        "start_num": 1,
        "end_num": 1,
        "output_dir": tmp_path / "downloads",
        "state_db": tmp_path / "state.sqlite3",
        "request_delay_sec": 0.0,
        "page_retries": 0,
        "image_retries": 0,
        "sequence_expand_enabled": False,
    }
    payload.update(overrides)
    return RunConfig(**payload)


def _html_for(*images: str) -> str:
    tags = "\n".join([f'<img src="{url}" />' for url in images])
    return f"<html><body><div class='gallerypic'>{tags}</div></body></html>"


def test_worker_runs_pipeline_to_completed(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for("https://img.test/1.jpg"),
    }
    worker = RunWorker(
        cfg,
        fetcher_builder=lambda _: (FakeFetcher(html_by_url), None, []),
        downloader=AlwaysSuccessDownloader(),
    )
    worker.start()
    assert worker.wait(timeout=5.0)
    snapshot = worker.snapshot()
    assert snapshot.status == "completed"
    assert snapshot.error is None
    assert snapshot.summary is not None
    assert snapshot.summary["images"]["completed_images"] == 1


def test_worker_reports_failure_when_pipeline_raises(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for("https://img.test/boom.jpg"),
    }
    worker = RunWorker(
        cfg,
        fetcher_builder=lambda _: (FakeFetcher(html_by_url), None, []),
        downloader=CrashDownloader(),
    )
    worker.start()
    assert worker.wait(timeout=5.0)
    snapshot = worker.snapshot()
    assert snapshot.status == "failed"
    assert "simulated downloader crash" in (snapshot.error or "")
