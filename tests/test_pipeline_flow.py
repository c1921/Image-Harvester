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
    return (
        "<html><body>"
        f"<div id='tishi'><p>全本<span>{len(images)}</span>张图片，欣赏完整作品</p></div>"
        f"<div class='gallerypic'>{tags}</div>"
        "</body></html>"
    )


def _html_without_upper(*images: str) -> str:
    tags = "\n".join([f'<img src="{url}" />' for url in images])
    return f"<html><body><div class='gallerypic'>{tags}</div></body></html>"


def _html_for_sequence(total: int, *images: str) -> str:
    tags = "\n".join([f'<img src="{url}" />' for url in images])
    return (
        "<html><body>"
        f"<div id='tishi'><p>全本<span>{total}</span>张图片，欣赏完整作品</p></div>"
        f"<div class='gallerypic'>{tags}</div>"
        "</body></html>"
    )


def _html_for_with_meta(*images: str) -> str:
    tags = "\n".join([f'<img src="{url}" />' for url in images])
    return (
        "<html><body>"
        "<div class='gallery_jieshao'>"
        "<h1>[YouMi]尤蜜荟 2024.07.10 Vol.1082 心妍小公主</h1>"
        "<p>2024-11-02</p>"
        "<p>"
        "<a href='/tags/i-cup.html'>I-CUP</a>"
        "<a href='/tags/meijiao.html'>美脚</a>"
        "<a href='/tags/jiudian.html'>酒店</a>"
        "</p>"
        "</div>"
        "<div class='gallery_nav'>"
        "<div class='gallery_renwu'>"
        "<a href='/jigou/98.html'><div class='gallery_chuangzuo'>机构</div></a>"
        "<div class='gallery_renwu_title'><a href='/jigou/98.html'>尤蜜荟</a></div>"
        "</div>"
        "<div class='gallery_renwu'>"
        "<a href='/mote/99.html'><div class='gallery_chujing'>模特</div></a>"
        "<div class='gallery_renwu_title'><a href='/mote/99.html'>李妍曦</a></div>"
        "</div>"
        "</div>"
        f"<div id='tishi'><p>全本<span>{len(images)}</span>张图片，欣赏完整作品</p></div>"
        f"<div class='gallerypic'>{tags}</div>"
        "</body></html>"
    )


def test_run_creates_metadata_and_respects_end_num(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir, end_num=2)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for_with_meta(
            "https://img.test/1/001.jpg", "https://img.test/1/002.jpg"
        ),
        "https://example.test/gallery/2.html": _html_for(
            "https://img.test/2/001.jpg", "https://img.test/2/002.jpg"
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

        page1_metadata = cfg.output_dir / "000001" / "metadata.json"
        page2_metadata = cfg.output_dir / "000002" / "metadata.json"
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
            "summary",
        }.issubset(metadata.keys())
        assert {"title", "published_date", "tags", "organizations", "models"}.issubset(
            metadata.keys()
        )
        assert "images" not in metadata
        assert metadata["title"] == "[YouMi]尤蜜荟 2024.07.10 Vol.1082 心妍小公主"
        assert metadata["published_date"] == "2024-11-02"
        assert metadata["tags"] == ["I-CUP", "美脚", "酒店"]
        assert metadata["organizations"] == ["尤蜜荟"]
        assert metadata["models"] == ["李妍曦"]
        assert metadata["summary"]["total_count"] == 2
        assert metadata["summary"]["success_count"] == 2
        assert metadata["summary"]["failed_count"] == 0
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
        "https://example.test/gallery/1.html": _html_for_with_meta(
            "https://img.test/r/001.jpg", "https://img.test/r/002.jpg"
        )
    }
    store = StateStore(cfg.state_db)
    job_id = compute_job_id(cfg)
    try:
        pipeline_run = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=FailOneDownloader("/002.jpg"),
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
        metadata = json.loads((cfg.output_dir / "000001" / "metadata.json").read_text("utf-8"))
        assert metadata["title"] == "[YouMi]尤蜜荟 2024.07.10 Vol.1082 心妍小公主"
        assert metadata["published_date"] == "2024-11-02"
        assert metadata["tags"] == ["I-CUP", "美脚", "酒店"]
        assert metadata["organizations"] == ["尤蜜荟"]
        assert metadata["models"] == ["李妍曦"]
    finally:
        store.close()


def test_sequence_expand_marks_completed_at_upper_bound_by_default(
    workspace_temp_dir: Path,
) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for_sequence(
            6,
            "https://img.test/x/001.jpg",
            "https://img.test/x/002.jpg",
            "https://img.test/x/003.jpg",
        ),
    }
    store = StateStore(cfg.state_db)
    try:
        pipeline = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=FailOneDownloader("/007.jpg"),
        )
        job_id = compute_job_id(cfg)
        summary = pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
        assert summary["images"]["completed_images"] == 6
        page = store.get_page(job_id, 1)
        assert page is not None
        assert page.status == "completed"
        events = store.list_events(job_id, limit=50)
        assert not any(e["event_type"].startswith("sequence_probe_") for e in events)
    finally:
        store.close()


def test_sequence_expand_can_probe_after_upper_bound_when_enabled(
    workspace_temp_dir: Path,
) -> None:
    cfg = _config(workspace_temp_dir, sequence_probe_after_upper_bound=True)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for_sequence(
            6,
            "https://img.test/x/001.jpg",
            "https://img.test/x/002.jpg",
            "https://img.test/x/003.jpg",
        ),
    }
    store = StateStore(cfg.state_db)
    try:
        pipeline = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=FailOneDownloader("/007.jpg"),
        )
        job_id = compute_job_id(cfg)
        summary = pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
        assert summary["images"]["completed_images"] == 6
        page = store.get_page(job_id, 1)
        assert page is not None
        assert page.status == "completed"
        events = store.list_events(job_id, limit=50)
        assert any(e["event_type"] == "sequence_probe_end" for e in events)
    finally:
        store.close()


def test_sequence_expand_marks_page_failed_when_not_reaching_upper_bound(
    workspace_temp_dir: Path,
) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for_sequence(
            6,
            "https://img.test/y/001.jpg",
            "https://img.test/y/002.jpg",
            "https://img.test/y/003.jpg",
        ),
    }
    store = StateStore(cfg.state_db)
    try:
        pipeline = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=FailOneDownloader("/005.jpg"),
        )
        job_id = compute_job_id(cfg)
        pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
        page = store.get_page(job_id, 1)
        assert page is not None
        assert page.status == "failed_fetch"
        events = store.list_events(job_id, limit=50)
        assert any(e["event_type"] == "sequence_incomplete_failed" for e in events)
    finally:
        store.close()


def test_sequence_expand_requires_upper_bound_when_enabled(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_without_upper("https://img.test/z/001.jpg"),
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
        page = store.get_page(job_id, 1)
        assert page is not None
        assert page.status == "failed_fetch"
        assert page.image_count == 0
        events = store.list_events(job_id, limit=50)
        assert any(e["event_type"] == "sequence_upper_bound_missing" for e in events)
        metadata = json.loads((cfg.output_dir / "000001" / "metadata.json").read_text("utf-8"))
        assert "images" not in metadata
        assert metadata["title"] == ""
        assert metadata["published_date"] == ""
        assert metadata["tags"] == []
        assert metadata["organizations"] == []
        assert metadata["models"] == []
    finally:
        store.close()


def test_sequence_expand_fails_when_seed_missing(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for_sequence(
            6,
            "https://img.test/z/cover.jpg",
            "https://img.test/z/poster.jpg",
            "https://img.test/z/thumb.jpg",
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
        pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
        page = store.get_page(job_id, 1)
        assert page is not None
        assert page.status == "failed_fetch"
        assert page.image_count == 0
        events = store.list_events(job_id, limit=50)
        assert any(e["event_type"] == "sequence_seed_missing" for e in events)
    finally:
        store.close()
