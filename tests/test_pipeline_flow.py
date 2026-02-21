from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from image_harvester.config import compute_job_id, run_config_json
from image_harvester.models import DownloadResult, FetchResult, RunConfig, utc_now_iso
from image_harvester.pipeline import ImageHarvesterPipeline
from image_harvester.state import StateStore


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


class CrashOnSecondDownloader(AlwaysSuccessDownloader):
    def __init__(self) -> None:
        self.count = 0

    def download(
        self,
        url: str,
        destination: Path,
        timeout_sec: float,
        retries: int,
        delay_sec: float,
    ) -> DownloadResult:
        self.count += 1
        if self.count == 2:
            raise RuntimeError("simulated crash")
        return super().download(url, destination, timeout_sec, retries, delay_sec)


class FailOneDownloader(AlwaysSuccessDownloader):
    def __init__(self, needle: str) -> None:
        self.needle = needle

    def download(
        self,
        url: str,
        destination: Path,
        timeout_sec: float,
        retries: int,
        delay_sec: float,
    ) -> DownloadResult:
        if self.needle in url:
            return DownloadResult(
                ok=False,
                retries_used=retries,
                http_status=500,
                content_type=None,
                size_bytes=None,
                sha256=None,
                downloaded_at=None,
                error="simulated failed image",
            )
        return super().download(url, destination, timeout_sec, retries, delay_sec)


def _config(tmp_path: Path, **overrides: object) -> RunConfig:
    payload = {
        "url_template": "https://example.test/gallery/{num}.html",
        "start_num": 1,
        "end_num": 1,
        "output_dir": tmp_path / "downloads",
        "state_db": tmp_path / "state.sqlite3",
        "request_delay_sec": 0.0,
        "page_retries": 0,
        "image_retries": 0,
    }
    payload.update(overrides)
    return RunConfig(**payload)


def _html_for(*images: str) -> str:
    tags = "\n".join([f'<img src="{url}" />' for url in images])
    return f"<html><body><div class='gallerypic'>{tags}</div></body></html>"


def test_run_creates_metadata_and_respects_end_num(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir, end_num=2)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for(
            "https://img.test/1/a.jpg", "https://img.test/1/b.jpg"
        ),
        "https://example.test/gallery/2.html": _html_for(
            "https://img.test/2/a.jpg", "https://img.test/2/b.jpg"
        ),
    }
    store = StateStore(cfg.state_db)
    try:
        pipeline = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=AlwaysSuccessDownloader(),
        )
        job_id = compute_job_id(cfg)
        summary = pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
        assert summary["images"]["completed_images"] == 4

        page1_metadata = cfg.output_dir / "P000001_1" / "metadata.json"
        page2_metadata = cfg.output_dir / "P000002_2" / "metadata.json"
        assert page1_metadata.exists()
        assert page2_metadata.exists()

        metadata = json.loads(page1_metadata.read_text(encoding="utf-8"))
        assert {
            "job_id",
            "page_num",
            "page_url",
            "source_id",
            "selector",
            "engine",
            "images",
            "summary",
        }.issubset(metadata.keys())
        assert metadata["images"][0]["index"] == 1
        assert metadata["images"][0]["status"] == "completed"
    finally:
        store.close()


def test_resume_after_crash_without_manual_start(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for(
            "https://img.test/r/1.jpg", "https://img.test/r/2.jpg"
        )
    }
    store = StateStore(cfg.state_db)
    job_id = compute_job_id(cfg)
    try:
        pipeline1 = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=CrashOnSecondDownloader(),
        )
        with pytest.raises(RuntimeError):
            pipeline1.run(job_id=job_id, config_json=run_config_json(cfg))

        pipeline2 = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=AlwaysSuccessDownloader(),
        )
        summary = pipeline2.run(job_id=job_id, config_json=run_config_json(cfg))
        assert summary["images"]["completed_images"] == 2
        assert summary["images"]["failed_images"] == 0
    finally:
        store.close()


def test_no_end_num_stops_after_consecutive_failures(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir, end_num=None, stop_after_consecutive_page_failures=2)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for("https://img.test/x/1.jpg"),
    }
    store = StateStore(cfg.state_db)
    try:
        pipeline = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=AlwaysSuccessDownloader(),
        )
        job_id = compute_job_id(cfg)
        pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
        pages = store.list_pages(job_id)
        assert [p.status for p in pages] == ["completed", "failed_fetch", "failed_fetch"]
    finally:
        store.close()


def test_retry_failed_only_retries_failed_records(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for(
            "https://img.test/good.jpg", "https://img.test/bad.jpg"
        )
    }
    store = StateStore(cfg.state_db)
    job_id = compute_job_id(cfg)
    try:
        pipeline_run = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=FailOneDownloader("bad.jpg"),
        )
        pipeline_run.run(job_id=job_id, config_json=run_config_json(cfg))
        assert len(store.get_failed_images(job_id)) == 1

        pipeline_retry = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=AlwaysSuccessDownloader(),
        )
        retry_summary = pipeline_retry.retry_failed(job_id)
        assert retry_summary["retried"] == 1
        assert retry_summary["recovered"] == 1
        assert len(store.get_failed_images(job_id)) == 0
    finally:
        store.close()
