"""Main harvesting pipeline."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .downloader import ImageDownloader, file_sha256
from .fetchers.base import BaseFetcher
from .models import FetchResult, RunConfig, utc_now_iso
from .naming import image_file_name, page_dir_name, source_id_from_page_url
from .parser import parse_image_urls
from .state import StateStore


class ImageHarvesterPipeline:
    """Pipeline that performs template-batch harvesting with resume support."""

    def __init__(
        self,
        config: RunConfig,
        store: StateStore,
        fetcher: BaseFetcher,
        downloader: ImageDownloader | None = None,
        fallback_fetcher: BaseFetcher | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.fetcher = fetcher
        self.fallback_fetcher = fallback_fetcher
        self.downloader = downloader or ImageDownloader()

    def run(self, job_id: str, config_json: str) -> dict[str, Any]:
        """Run main harvesting flow."""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        if self.config.resume:
            self.store.upsert_job(job_id, config_json, "running")
            self.store.reset_running_to_pending(job_id)
        else:
            self.store.reset_job(job_id, config_json)

        self.store.add_event(job_id, "job_start", "任务开始")
        consecutive_page_failures = 0
        page_num = self.config.start_num

        try:
            while True:
                if self.config.end_num is not None and page_num > self.config.end_num:
                    break

                page_url = self.config.url_template.format(num=page_num)
                source_id = source_id_from_page_url(page_url, page_num)
                page_state = self.store.ensure_page(job_id, page_num, page_url, source_id)

                if self.config.resume and page_state.status in {
                    "completed",
                    "completed_with_failures",
                    "no_images",
                }:
                    page_num += 1
                    continue

                page_ok = self._process_page(job_id=job_id, page_num=page_num, page_url=page_url)
                if page_ok:
                    consecutive_page_failures = 0
                else:
                    consecutive_page_failures += 1

                if (
                    self.config.end_num is None
                    and consecutive_page_failures
                    >= self.config.stop_after_consecutive_page_failures
                ):
                    self.store.add_event(
                        job_id,
                        "stop_threshold",
                        (
                            "因连续页面失败而停止: "
                            f"{consecutive_page_failures}"
                        ),
                    )
                    break

                page_num += 1
                if self.config.request_delay_sec > 0:
                    time.sleep(self.config.request_delay_sec)

            self.store.set_job_status(job_id, "completed", finish=True)
            self.store.add_event(job_id, "job_end", "任务完成")
            return self.store.stats_for_job(job_id)
        except Exception as exc:
            self.store.set_job_status(job_id, "failed", finish=True)
            self.store.add_event(job_id, "job_failed", f"未处理异常: {exc}")
            raise

    def retry_failed(
        self,
        job_id: str,
        *,
        limit: int | None = None,
        timeout_sec: float | None = None,
        retries: int | None = None,
        delay_sec: float | None = None,
    ) -> dict[str, Any]:
        """Retry failed images for an existing job."""
        timeout = timeout_sec if timeout_sec is not None else self.config.image_timeout_sec
        retry_count = retries if retries is not None else self.config.image_retries
        delay = delay_sec if delay_sec is not None else self.config.request_delay_sec

        failed_images = self.store.get_failed_images(job_id, limit=limit)
        retried = 0
        recovered = 0
        failed_again = 0
        touched_pages: set[int] = set()

        for row in failed_images:
            retried += 1
            touched_pages.add(int(row["page_id"]))
            image_path = Path(str(row["local_path"]))
            result = self.downloader.download(
                url=str(row["url"]),
                destination=image_path,
                timeout_sec=timeout,
                retries=retry_count,
                delay_sec=delay,
            )
            if result.ok:
                recovered += 1
                self.store.update_image_result(
                    int(row["id"]),
                    status="completed",
                    retries=result.retries_used,
                    http_status=result.http_status,
                    content_type=result.content_type,
                    size_bytes=result.size_bytes,
                    sha256=result.sha256,
                    downloaded_at=result.downloaded_at,
                    error=None,
                )
            else:
                failed_again += 1
                self.store.update_image_result(
                    int(row["id"]),
                    status="failed",
                    retries=result.retries_used,
                    http_status=result.http_status,
                    content_type=result.content_type,
                    size_bytes=result.size_bytes,
                    sha256=result.sha256,
                    downloaded_at=result.downloaded_at,
                    error=result.error,
                )

        for page_id in touched_pages:
            self._refresh_page_status(page_id)
            self._write_page_metadata_by_id(job_id, page_id)

        self.store.add_event(
            job_id,
            "retry_failed",
            (
                "重试失败图片完成: "
                f"retried={retried}, recovered={recovered}, failed_again={failed_again}"
            ),
        )

        return {
            "retried": retried,
            "recovered": recovered,
            "failed_again": failed_again,
        }

    def export_job_metadata(self, job_id: str, output_path: Path) -> Path:
        """Export task-level metadata summary JSON."""
        stats = self.store.stats_for_job(job_id)
        pages = self.store.list_pages(job_id)
        payload_pages: list[dict[str, Any]] = []
        for page in pages:
            images = self.store.get_page_images(page.id)
            payload_pages.append(
                {
                    "page_num": page.page_num,
                    "page_url": page.page_url,
                    "source_id": page.source_id,
                    "status": page.status,
                    "image_count": page.image_count,
                    "last_completed_image_index": page.last_completed_image_index,
                    "failed_images": sum(1 for img in images if img.status == "failed"),
                    "metadata_path": str(
                        self.config.output_dir
                        / page_dir_name(page.page_num, page.source_id)
                        / "metadata.json"
                    ),
                }
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": utc_now_iso(),
            "job": stats["job"],
            "totals": {
                "pages": stats.get("pages", {}),
                "images": stats.get("images", {}),
            },
            "pages": payload_pages,
        }
        self._atomic_write_json(output_path, payload)
        return output_path

    def _process_page(self, job_id: str, page_num: int, page_url: str) -> bool:
        source_id = source_id_from_page_url(page_url, page_num)
        page_state = self.store.ensure_page(job_id, page_num, page_url, source_id)
        self.store.update_page(page_state.id, status="running", error=None)
        self.store.add_event(job_id, "page_start", f"页面 {page_num} 开始处理", page_id=page_state.id)

        fetch_result = self._fetch_with_retries(self.fetcher, page_url, self.config.page_retries)
        if not fetch_result.ok or not fetch_result.html:
            self.store.update_page(
                page_state.id,
                status="failed_fetch",
                image_count=0,
                error=fetch_result.error,
                finish=True,
            )
            self.store.add_event(
                job_id,
                "page_fetch_failed",
                f"页面 {page_num} 抓取失败: {fetch_result.error}",
                page_id=page_state.id,
            )
            return False

        parse_result = parse_image_urls(fetch_result.html, page_url, self.config.selector)
        if (
            not parse_result.image_urls
            and self.config.playwright_fallback
            and self.fallback_fetcher is not None
        ):
            fallback_result = self._fetch_with_retries(self.fallback_fetcher, page_url, retries=0)
            if fallback_result.ok and fallback_result.html:
                parse_result = parse_image_urls(
                    fallback_result.html,
                    page_url,
                    self.config.selector,
                )

        if not parse_result.image_urls:
            self.store.update_page(
                page_state.id,
                status="no_images",
                image_count=0,
                last_completed_image_index=0,
                finish=True,
            )
            self._write_page_metadata_by_id(job_id, page_state.id)
            self.store.add_event(
                job_id,
                "page_no_images",
                f"页面 {page_num} 解析到 0 张图片",
                page_id=page_state.id,
            )
            return False

        page_dir = self.config.output_dir / page_dir_name(page_num, source_id)
        tuples: list[tuple[int, str, str]] = []
        for idx, image_url in enumerate(parse_result.image_urls, start=1):
            local_path = page_dir / image_file_name(idx, image_url)
            tuples.append((idx, image_url, str(local_path)))

        self.store.upsert_page_images(page_state.id, tuples)
        self.store.update_page(page_state.id, status="running", image_count=len(tuples))
        page_images = self.store.get_page_images(page_state.id)

        for image in page_images:
            if image.status in {"completed", "failed"}:
                continue
            destination = Path(image.local_path)

            if destination.exists() and destination.is_file() and destination.stat().st_size > 0:
                self.store.update_image_result(
                    image.id,
                    status="completed",
                    retries=image.retries,
                    http_status=200,
                    content_type=None,
                    size_bytes=destination.stat().st_size,
                    sha256=file_sha256(destination),
                    downloaded_at=utc_now_iso(),
                    error=None,
                )
                self.store.update_page(
                    page_state.id,
                    status="running",
                    last_completed_image_index=image.image_index,
                    image_count=len(tuples),
                )
                continue

            self.store.update_image_running(image.id)
            result = self.downloader.download(
                url=image.url,
                destination=destination,
                timeout_sec=self.config.image_timeout_sec,
                retries=self.config.image_retries,
                delay_sec=self.config.request_delay_sec,
            )

            if result.ok:
                self.store.update_image_result(
                    image.id,
                    status="completed",
                    retries=result.retries_used,
                    http_status=result.http_status,
                    content_type=result.content_type,
                    size_bytes=result.size_bytes,
                    sha256=result.sha256,
                    downloaded_at=result.downloaded_at,
                    error=None,
                )
                self.store.update_page(
                    page_state.id,
                    status="running",
                    last_completed_image_index=image.image_index,
                    image_count=len(tuples),
                )
            else:
                self.store.update_image_result(
                    image.id,
                    status="failed",
                    retries=result.retries_used,
                    http_status=result.http_status,
                    content_type=result.content_type,
                    size_bytes=result.size_bytes,
                    sha256=result.sha256,
                    downloaded_at=result.downloaded_at,
                    error=result.error,
                )
                self.store.add_event(
                    job_id,
                    "image_failed",
                    (
                        f"页面 {page_num} 第 {image.image_index} 张图片重试后仍失败: "
                        f"{result.error}"
                    ),
                    page_id=page_state.id,
                )

        self._refresh_page_status(page_state.id)
        self._write_page_metadata_by_id(job_id, page_state.id)
        page_state_after = self.store.get_page(job_id, page_num)
        assert page_state_after is not None
        return page_state_after.status in {"completed", "completed_with_failures"}

    def _fetch_with_retries(self, fetcher: BaseFetcher, url: str, retries: int) -> FetchResult:
        attempts = retries + 1
        result: FetchResult | None = None
        for attempt in range(1, attempts + 1):
            result = fetcher.fetch(url, timeout_sec=self.config.page_timeout_sec)
            if result.ok and result.html:
                return result
            if attempt < attempts and self.config.request_delay_sec > 0:
                time.sleep(self.config.request_delay_sec)
        assert result is not None
        return result

    def _refresh_page_status(self, page_id: int) -> None:
        page = self.store.get_page_by_id(page_id)
        if page is None:
            return
        images = self.store.get_page_images(page_id)
        if not images:
            self.store.update_page(page_id, status="no_images", image_count=0, finish=True)
            return

        completed = [img for img in images if img.status == "completed"]
        failed = [img for img in images if img.status == "failed"]
        pending_or_running = [
            img for img in images if img.status in {"pending", "running"}
        ]
        max_completed_idx = max((img.image_index for img in completed), default=0)

        if pending_or_running:
            self.store.update_page(
                page_id,
                status="running",
                image_count=len(images),
                last_completed_image_index=max_completed_idx,
            )
            return

        final_status = "completed" if len(failed) == 0 else "completed_with_failures"
        self.store.update_page(
            page_id,
            status=final_status,
            image_count=len(images),
            last_completed_image_index=max_completed_idx,
            finish=True,
        )

    def _write_page_metadata_by_id(self, job_id: str, page_id: int) -> None:
        page = self.store.get_page_by_id(page_id)
        if page is None:
            return
        images = self.store.get_page_images(page_id)
        page_output_dir = self.config.output_dir / page_dir_name(page.page_num, page.source_id)
        page_output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = page_output_dir / "metadata.json"

        payload_images: list[dict[str, Any]] = []
        for image in images:
            payload_images.append(
                {
                    "index": image.image_index,
                    "url": image.url,
                    "local_path": image.local_path,
                    "status": image.status,
                    "retries": image.retries,
                    "http_status": image.http_status,
                    "content_type": image.content_type,
                    "size_bytes": image.size_bytes,
                    "sha256": image.sha256,
                    "downloaded_at": image.downloaded_at,
                    "error": image.error,
                }
            )

        started_at = page.started_at
        ended_at = page.finished_at or utc_now_iso()
        duration_sec = self._duration_seconds(started_at, ended_at)
        success_count = sum(1 for img in images if img.status == "completed")
        failed_count = sum(1 for img in images if img.status == "failed")

        payload = {
            "job_id": job_id,
            "page_num": page.page_num,
            "page_url": page.page_url,
            "source_id": page.source_id,
            "selector": self.config.selector,
            "engine": self.config.engine,
            "images": payload_images,
            "summary": {
                "total_count": len(images),
                "success_count": success_count,
                "failed_count": failed_count,
                "status": page.status,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_sec": duration_sec,
            },
        }
        self._atomic_write_json(metadata_path, payload)

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def _duration_seconds(self, started_at: str, ended_at: str) -> float:
        try:
            start = time.mktime(time.strptime(started_at[:19], "%Y-%m-%dT%H:%M:%S"))
            end = time.mktime(time.strptime(ended_at[:19], "%Y-%m-%dT%H:%M:%S"))
            return max(0.0, end - start)
        except Exception:
            return 0.0
