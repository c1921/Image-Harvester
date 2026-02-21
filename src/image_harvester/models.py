"""Core datatypes used across pipeline, state, and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """Return UTC timestamp in ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class RunConfig:
    """Runtime configuration for a harvesting job."""

    url_template: str
    start_num: int
    end_num: int | None = None
    selector: str = "div.gallerypic img"
    output_dir: Path = Path("data/downloads")
    state_db: Path = Path("data/state.sqlite3")
    engine: str = "requests"
    resume: bool = True
    page_timeout_sec: float = 20.0
    image_timeout_sec: float = 30.0
    image_retries: int = 3
    page_retries: int = 2
    request_delay_sec: float = 0.2
    stop_after_consecutive_page_failures: int = 5
    playwright_fallback: bool = False
    sequence_count_selector: str = "#tishi p span"
    sequence_require_upper_bound: bool = True
    sequence_probe_after_upper_bound: bool = False

    def as_job_identity(self) -> dict[str, Any]:
        """Subset used to derive stable job identifier."""
        return {
            "url_template": self.url_template,
            "selector": self.selector,
            "output_dir": str(self.output_dir),
            "engine": self.engine,
            "sequence_count_selector": self.sequence_count_selector,
            "sequence_require_upper_bound": self.sequence_require_upper_bound,
            "sequence_probe_after_upper_bound": self.sequence_probe_after_upper_bound,
        }


@dataclass(slots=True)
class JobState:
    """Task-level persisted state."""

    job_id: str
    status: str
    config_json: str
    started_at: str
    updated_at: str
    finished_at: str | None = None


@dataclass(slots=True)
class PageState:
    """Page-level persisted state."""

    id: int
    job_id: str
    page_num: int
    page_url: str
    source_id: str
    status: str
    last_completed_image_index: int
    image_count: int
    error: str | None
    started_at: str
    updated_at: str
    finished_at: str | None


@dataclass(slots=True)
class ImageRecord:
    """Image-level persisted state and metadata."""

    id: int
    page_id: int
    image_index: int
    url: str
    local_path: str
    status: str
    retries: int
    http_status: int | None
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    downloaded_at: str | None
    error: str | None
    updated_at: str


@dataclass(slots=True)
class FetchResult:
    """Result of fetching a page."""

    url: str
    ok: bool
    html: str | None
    status_code: int | None
    error: str | None
    elapsed_ms: int
    fetched_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class GalleryPageMeta:
    """Structured page metadata extracted from gallery description/navigation."""

    title: str = ""
    published_date: str = ""
    tags: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseResult:
    """Result of parsing image URLs from page HTML."""

    page_url: str
    selector: str
    image_urls: list[str]
    gallery_meta: GalleryPageMeta = field(default_factory=GalleryPageMeta)


@dataclass(slots=True)
class DownloadResult:
    """Result of downloading one image."""

    ok: bool
    retries_used: int
    http_status: int | None
    content_type: str | None
    size_bytes: int | None
    sha256: str | None
    downloaded_at: str | None
    error: str | None
