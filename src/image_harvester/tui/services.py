"""Backend services used by the Textual TUI."""

from __future__ import annotations

import copy
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

from ..config import build_run_config, compute_job_id, run_config_json
from ..fetchers import PlaywrightFetcher, RequestsFetcher
from ..fetchers.base import BaseFetcher
from ..models import JobState, PageState, RunConfig, utc_now_iso
from ..pipeline import ImageHarvesterPipeline
from ..state import StateStore


FetcherBuilder = Callable[[RunConfig], tuple[BaseFetcher, BaseFetcher | None, list[str]]]


def build_fetchers_for_config(
    run_config: RunConfig,
) -> tuple[BaseFetcher, BaseFetcher | None, list[str]]:
    """Create primary/fallback fetchers for a run config."""
    warnings: list[str] = []
    if run_config.engine == "requests":
        primary: BaseFetcher = RequestsFetcher()
        fallback: BaseFetcher | None = None
        if run_config.playwright_fallback:
            try:
                fallback = PlaywrightFetcher()
            except RuntimeError as exc:
                warnings.append(f"Playwright 回退已禁用: {exc}")
        return primary, fallback, warnings

    if run_config.engine == "playwright":
        return PlaywrightFetcher(), None, warnings

    raise ValueError(f"不支持的引擎: {run_config.engine}")


@dataclass(slots=True)
class WorkerSnapshot:
    """Public worker state for UI polling."""

    job_id: str
    status: str
    error: str | None
    summary: dict[str, Any] | None
    warnings: list[str]
    started_at: str | None
    finished_at: str | None


class RunWorker:
    """Run one harvesting job in a background thread."""

    def __init__(
        self,
        run_config: RunConfig,
        *,
        fetcher_builder: FetcherBuilder = build_fetchers_for_config,
        downloader: Any | None = None,
    ) -> None:
        self.run_config = run_config
        self.job_id = compute_job_id(run_config)
        self._fetcher_builder = fetcher_builder
        self._downloader = downloader
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._status = "idle"
        self._error: str | None = None
        self._summary: dict[str, Any] | None = None
        self._warnings: list[str] = []
        self._started_at: str | None = None
        self._finished_at: str | None = None

    def start(self) -> None:
        """Start worker once. Raises if already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("已有任务在运行中。")
            self._status = "running"
            self._error = None
            self._summary = None
            self._warnings = []
            self._started_at = utc_now_iso()
            self._finished_at = None

        self._thread = threading.Thread(
            target=self._run,
            name=f"harvester-runner-{self.job_id}",
            daemon=True,
        )
        self._thread.start()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait until worker finishes."""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def is_running(self) -> bool:
        """Return True when worker thread is active."""
        thread = self._thread
        return bool(thread and thread.is_alive())

    def snapshot(self) -> WorkerSnapshot:
        """Get thread-safe state snapshot for UI."""
        with self._lock:
            summary = copy.deepcopy(self._summary)
            warnings = list(self._warnings)
            return WorkerSnapshot(
                job_id=self.job_id,
                status=self._status,
                error=self._error,
                summary=summary,
                warnings=warnings,
                started_at=self._started_at,
                finished_at=self._finished_at,
            )

    def _run(self) -> None:
        store = StateStore(self.run_config.state_db)
        try:
            fetcher, fallback_fetcher, warnings = self._fetcher_builder(self.run_config)
            with self._lock:
                self._warnings.extend(warnings)

            pipeline = ImageHarvesterPipeline(
                config=self.run_config,
                store=store,
                fetcher=fetcher,
                downloader=self._downloader,
                fallback_fetcher=fallback_fetcher,
            )
            summary = pipeline.run(job_id=self.job_id, config_json=run_config_json(self.run_config))
        except Exception as exc:
            with self._lock:
                self._status = "failed"
                self._error = str(exc)
                self._finished_at = utc_now_iso()
            return
        finally:
            store.close()

        with self._lock:
            self._status = "completed"
            self._summary = summary
            self._finished_at = utc_now_iso()


@dataclass(slots=True)
class JobSnapshot:
    """State snapshot used by monitoring panels."""

    job_id: str
    stats: dict[str, Any]
    events: list[dict[str, Any]]
    failed_images: list[dict[str, Any]]
    pages: list[PageState]


class SnapshotService:
    """Read-only helpers for polling run state from SQLite."""

    def __init__(self, state_db: Path) -> None:
        self.state_db = state_db

    @contextmanager
    def _store(self) -> Iterator[StateStore]:
        store = StateStore(self.state_db)
        try:
            yield store
        finally:
            store.close()

    def list_jobs(self, *, limit: int = 50) -> list[JobState]:
        """List latest jobs with optional limit."""
        with self._store() as store:
            jobs = store.list_jobs()
        if limit < 1:
            return []
        return jobs[:limit]

    def latest_job(self) -> JobState | None:
        """Return latest job record."""
        with self._store() as store:
            return store.get_latest_job()

    def latest_job_id(self) -> str | None:
        """Return latest job id or None."""
        latest = self.latest_job()
        return latest.job_id if latest else None

    def load_run_config_from_job(
        self,
        job_id: str,
        *,
        fallback_state_db: Path | None = None,
    ) -> RunConfig | None:
        """Parse RunConfig from persisted job config JSON."""
        with self._store() as store:
            job = store.get_job(job_id)
        if job is None:
            return None

        try:
            payload = json.loads(job.config_json)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        state_db = fallback_state_db or self.state_db
        if not payload.get("state_db"):
            payload["state_db"] = str(state_db)

        try:
            return build_run_config(payload)
        except Exception:
            return None

    def get_snapshot(
        self,
        job_id: str,
        *,
        events_limit: int = 100,
        failed_limit: int = 50,
    ) -> JobSnapshot | None:
        """Load a full read-model snapshot for one job."""
        with self._store() as store:
            if store.get_job(job_id) is None:
                return None
            stats = store.stats_for_job(job_id)
            events = store.list_events(job_id, limit=events_limit)
            failed = store.get_failed_images(job_id, limit=failed_limit)
            pages = sorted(
                store.list_pages(job_id),
                key=lambda page: (page.updated_at or "", page.page_num),
                reverse=True,
            )
        return JobSnapshot(
            job_id=job_id,
            stats=stats,
            events=events,
            failed_images=failed,
            pages=pages,
        )
