"""Reusable Textual widgets for TUI dashboards."""

from __future__ import annotations

from typing import Sequence

from textual.widgets import DataTable, Static

from ..models import JobState, PageState


def _fmt_ts(value: str | None) -> str:
    if not value:
        return "-"
    return value[:19].replace("T", " ")


def _short(text: str | None, limit: int) -> str:
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


class StatsPanel(Static):
    """Job totals and image/page progress summary."""

    def set_snapshot(self, stats: dict | None) -> None:
        if not stats:
            self.update("未选择任务。")
            return

        job = stats.get("job", {})
        pages = stats.get("pages", {})
        images = stats.get("images", {})
        lines = [
            f"任务: {job.get('job_id', '-')}",
            f"状态: {job.get('status', '-')}",
            f"开始: {_fmt_ts(job.get('started_at'))}",
            f"结束: {_fmt_ts(job.get('finished_at'))}",
            (
                "页面: total={total} done={done} failed={failed} empty={empty}".format(
                    total=pages.get("total_pages", 0),
                    done=pages.get("done_pages", 0),
                    failed=pages.get("failed_pages", 0),
                    empty=pages.get("empty_pages", 0),
                )
            ),
            (
                "图片: total={total} ok={ok} failed={failed} remaining={remaining}".format(
                    total=images.get("total_images", 0),
                    ok=images.get("completed_images", 0),
                    failed=images.get("failed_images", 0),
                    remaining=images.get("remaining_images", 0),
                )
            ),
        ]
        self.update("\n".join(lines))


class JobsTable(DataTable):
    """Recent jobs list table."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("job_id", "status", "started_at", "finished_at")

    def set_jobs(self, jobs: Sequence[JobState]) -> None:
        self.clear(columns=False)
        for job in jobs:
            self.add_row(
                job.job_id,
                job.status,
                _fmt_ts(job.started_at),
                _fmt_ts(job.finished_at),
                key=job.job_id,
            )


class PagesTable(DataTable):
    """Per-page status summary table."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("page", "status", "progress", "error")

    def set_pages(self, pages: Sequence[PageState]) -> None:
        self.clear(columns=False)
        for page in pages:
            progress = f"{page.last_completed_image_index}/{page.image_count}"
            self.add_row(
                str(page.page_num),
                page.status,
                progress,
                _short(page.error, 60),
                key=f"page-{page.id}",
            )


class EventsTable(DataTable):
    """Recent events for selected job."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("time", "event", "page_id", "message")

    def set_events(self, events: Sequence[dict]) -> None:
        self.clear(columns=False)
        for item in events:
            self.add_row(
                _fmt_ts(str(item.get("created_at", ""))),
                str(item.get("event_type", "-")),
                str(item.get("page_id", "-")),
                _short(str(item.get("message", "")), 90),
                key=f"event-{item.get('id', 'x')}",
            )


class FailedImagesTable(DataTable):
    """Failed image sample table."""

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("page", "index", "url", "error")

    def set_failed_images(self, failed_images: Sequence[dict]) -> None:
        self.clear(columns=False)
        for item in failed_images:
            self.add_row(
                str(item.get("page_num", "-")),
                str(item.get("image_index", "-")),
                _short(str(item.get("url", "")), 60),
                _short(str(item.get("error", "")), 60),
                key=f"failed-{item.get('id', 'x')}",
            )
