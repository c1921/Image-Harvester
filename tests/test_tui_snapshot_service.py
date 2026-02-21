from __future__ import annotations

import hashlib
import json
from pathlib import Path

from image_harvester.config import compute_job_id, run_config_json
from image_harvester.models import DownloadResult, FetchResult, RunConfig, utc_now_iso
from image_harvester.pipeline import ImageHarvesterPipeline
from image_harvester.state import StateStore
from image_harvester.tui.services import SnapshotService


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


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        url_template="https://example.test/gallery/{num}.html",
        start_num=1,
        end_num=1,
        output_dir=tmp_path / "downloads",
        state_db=tmp_path / "state.sqlite3",
        request_delay_sec=0.0,
        page_retries=0,
        image_retries=0,
        sequence_expand_enabled=False,
    )


def _html_for(*images: str) -> str:
    tags = "\n".join([f'<img src="{url}" />' for url in images])
    return f"<html><body><div class='gallerypic'>{tags}</div></body></html>"


def test_snapshot_service_reads_stats_events_and_pages(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    html_by_url = {
        "https://example.test/gallery/1.html": _html_for("https://img.test/1.jpg"),
    }
    job_id = compute_job_id(cfg)

    store = StateStore(cfg.state_db)
    try:
        pipeline = ImageHarvesterPipeline(
            config=cfg,
            store=store,
            fetcher=FakeFetcher(html_by_url),
            downloader=AlwaysSuccessDownloader(),
        )
        pipeline.run(job_id=job_id, config_json=run_config_json(cfg))
    finally:
        store.close()

    service = SnapshotService(cfg.state_db)
    jobs = service.list_jobs(limit=10)
    assert jobs
    assert jobs[0].job_id == job_id

    snapshot = service.get_snapshot(job_id, events_limit=20, failed_limit=20)
    assert snapshot is not None
    assert snapshot.job_id == job_id
    assert snapshot.stats["images"]["completed_images"] == 1
    assert len(snapshot.pages) == 1
    assert any(item["event_type"] == "job_start" for item in snapshot.events)


def test_snapshot_service_can_load_run_config_from_job(workspace_temp_dir: Path) -> None:
    cfg = _config(workspace_temp_dir)
    job_id = compute_job_id(cfg)
    store = StateStore(cfg.state_db)
    try:
        store.upsert_job(job_id, run_config_json(cfg), "running")
    finally:
        store.close()

    service = SnapshotService(cfg.state_db)
    latest = service.latest_job()
    assert latest is not None
    assert latest.job_id == job_id
    loaded = service.load_run_config_from_job(job_id)
    assert loaded is not None
    assert loaded.url_template == cfg.url_template
    assert loaded.state_db == cfg.state_db


def test_snapshot_service_load_run_config_fills_missing_state_db(
    workspace_temp_dir: Path,
) -> None:
    state_db = workspace_temp_dir / "state.sqlite3"
    payload = {
        "url_template": "https://example.test/gallery/{num}.html",
        "start_num": 1,
        "end_num": 3,
    }
    store = StateStore(state_db)
    try:
        store.upsert_job("job_missing_state_db", json.dumps(payload), "completed")
    finally:
        store.close()

    service = SnapshotService(state_db)
    fallback_db = workspace_temp_dir / "fallback.sqlite3"
    loaded = service.load_run_config_from_job(
        "job_missing_state_db",
        fallback_state_db=fallback_db,
    )
    assert loaded is not None
    assert loaded.state_db == fallback_db
    assert loaded.end_num == 3


def test_snapshot_service_load_run_config_returns_none_on_invalid_json(
    workspace_temp_dir: Path,
) -> None:
    state_db = workspace_temp_dir / "state.sqlite3"
    store = StateStore(state_db)
    try:
        store.upsert_job("job_bad_json", "{bad-json", "failed")
    finally:
        store.close()

    service = SnapshotService(state_db)
    assert service.load_run_config_from_job("job_bad_json") is None
