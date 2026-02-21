"""SQLite-backed persistence for jobs, pages, images, and events."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .models import ImageRecord, JobState, PageState, utc_now_iso


class StateStore:
    """Persistence layer for resumable harvesting jobs."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              config_json TEXT NOT NULL,
              started_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS pages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id TEXT NOT NULL,
              page_num INTEGER NOT NULL,
              page_url TEXT NOT NULL,
              source_id TEXT NOT NULL,
              status TEXT NOT NULL,
              last_completed_image_index INTEGER NOT NULL DEFAULT 0,
              image_count INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              started_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              finished_at TEXT,
              UNIQUE(job_id, page_num),
              FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS images (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              page_id INTEGER NOT NULL,
              image_index INTEGER NOT NULL,
              url TEXT NOT NULL,
              local_path TEXT NOT NULL,
              status TEXT NOT NULL,
              retries INTEGER NOT NULL DEFAULT 0,
              http_status INTEGER,
              content_type TEXT,
              size_bytes INTEGER,
              sha256 TEXT,
              downloaded_at TEXT,
              error TEXT,
              updated_at TEXT NOT NULL,
              UNIQUE(page_id, image_index),
              FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id TEXT NOT NULL,
              page_id INTEGER,
              event_type TEXT NOT NULL,
              message TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
              FOREIGN KEY(page_id) REFERENCES pages(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pages_job_id ON pages(job_id);
            CREATE INDEX IF NOT EXISTS idx_images_page_id ON images(page_id);
            CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
            CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
            """
        )
        self.conn.commit()

    def reset_job(self, job_id: str, config_json: str) -> None:
        """Delete previous state for a stable job id and recreate root record."""
        now = utc_now_iso()
        self.conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        self.conn.execute(
            """
            INSERT INTO jobs (job_id, status, config_json, started_at, updated_at, finished_at)
            VALUES (?, 'running', ?, ?, ?, NULL)
            """,
            (job_id, config_json, now, now),
        )
        self.conn.commit()

    def upsert_job(self, job_id: str, config_json: str, status: str) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO jobs (job_id, status, config_json, started_at, updated_at, finished_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(job_id) DO UPDATE SET
              status = excluded.status,
              config_json = excluded.config_json,
              updated_at = excluded.updated_at
            """,
            (job_id, status, config_json, now, now),
        )
        self.conn.commit()

    def set_job_status(self, job_id: str, status: str, finish: bool = False) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE jobs
            SET status = ?,
                updated_at = ?,
                finished_at = CASE WHEN ? THEN ? ELSE finished_at END
            WHERE job_id = ?
            """,
            (status, now, int(finish), now, job_id),
        )
        self.conn.commit()

    def get_job(self, job_id: str) -> JobState | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return JobState(
            job_id=row["job_id"],
            status=row["status"],
            config_json=row["config_json"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
        )

    def get_latest_job(self) -> JobState | None:
        row = self.conn.execute(
            "SELECT * FROM jobs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return JobState(
            job_id=row["job_id"],
            status=row["status"],
            config_json=row["config_json"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
        )

    def list_jobs(self) -> list[JobState]:
        rows = self.conn.execute("SELECT * FROM jobs ORDER BY started_at DESC").fetchall()
        return [
            JobState(
                job_id=row["job_id"],
                status=row["status"],
                config_json=row["config_json"],
                started_at=row["started_at"],
                updated_at=row["updated_at"],
                finished_at=row["finished_at"],
            )
            for row in rows
        ]

    def ensure_page(self, job_id: str, page_num: int, page_url: str, source_id: str) -> PageState:
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO pages (
              job_id, page_num, page_url, source_id, status,
              last_completed_image_index, image_count, error, started_at, updated_at, finished_at
            )
            VALUES (?, ?, ?, ?, 'pending', 0, 0, NULL, ?, ?, NULL)
            ON CONFLICT(job_id, page_num) DO UPDATE SET
              page_url = excluded.page_url,
              source_id = excluded.source_id,
              updated_at = excluded.updated_at
            """,
            (job_id, page_num, page_url, source_id, now, now),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM pages WHERE job_id = ? AND page_num = ?",
            (job_id, page_num),
        ).fetchone()
        assert row is not None
        return self._row_to_page(row)

    def get_page(self, job_id: str, page_num: int) -> PageState | None:
        row = self.conn.execute(
            "SELECT * FROM pages WHERE job_id = ? AND page_num = ?",
            (job_id, page_num),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    def get_page_by_id(self, page_id: int) -> PageState | None:
        row = self.conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_page(row)

    def list_pages(self, job_id: str) -> list[PageState]:
        rows = self.conn.execute(
            "SELECT * FROM pages WHERE job_id = ? ORDER BY page_num",
            (job_id,),
        ).fetchall()
        return [self._row_to_page(row) for row in rows]

    def update_page(
        self,
        page_id: int,
        *,
        status: str,
        last_completed_image_index: int | None = None,
        image_count: int | None = None,
        error: str | None = None,
        finish: bool = False,
    ) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE pages
            SET status = ?,
                last_completed_image_index = COALESCE(?, last_completed_image_index),
                image_count = COALESCE(?, image_count),
                error = ?,
                updated_at = ?,
                finished_at = CASE WHEN ? THEN ? ELSE finished_at END
            WHERE id = ?
            """,
            (
                status,
                last_completed_image_index,
                image_count,
                error,
                now,
                int(finish),
                now,
                page_id,
            ),
        )
        self.conn.commit()

    def upsert_page_images(
        self,
        page_id: int,
        items: list[tuple[int, str, str]],
    ) -> None:
        now = utc_now_iso()
        self.conn.executemany(
            """
            INSERT INTO images (
              page_id, image_index, url, local_path, status, retries, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', 0, ?)
            ON CONFLICT(page_id, image_index) DO UPDATE SET
              url = excluded.url,
              local_path = excluded.local_path,
              updated_at = excluded.updated_at
            """,
            [(page_id, idx, url, local_path, now) for idx, url, local_path in items],
        )
        self.conn.commit()

    def get_page_images(self, page_id: int) -> list[ImageRecord]:
        rows = self.conn.execute(
            "SELECT * FROM images WHERE page_id = ? ORDER BY image_index",
            (page_id,),
        ).fetchall()
        return [self._row_to_image(row) for row in rows]

    def update_image_running(self, image_id: int) -> None:
        now = utc_now_iso()
        self.conn.execute(
            "UPDATE images SET status = 'running', updated_at = ? WHERE id = ?",
            (now, image_id),
        )
        self.conn.commit()

    def update_image_result(
        self,
        image_id: int,
        *,
        status: str,
        retries: int,
        http_status: int | None,
        content_type: str | None,
        size_bytes: int | None,
        sha256: str | None,
        downloaded_at: str | None,
        error: str | None,
    ) -> None:
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE images
            SET status = ?,
                retries = ?,
                http_status = ?,
                content_type = ?,
                size_bytes = ?,
                sha256 = ?,
                downloaded_at = ?,
                error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                retries,
                http_status,
                content_type,
                size_bytes,
                sha256,
                downloaded_at,
                error,
                now,
                image_id,
            ),
        )
        self.conn.commit()

    def reset_running_to_pending(self, job_id: str) -> None:
        """Recover interrupted run by returning running rows back to pending."""
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE pages SET status = 'pending', updated_at = ?
            WHERE job_id = ? AND status = 'running'
            """,
            (now, job_id),
        )
        self.conn.execute(
            """
            UPDATE images SET status = 'pending', updated_at = ?
            WHERE page_id IN (SELECT id FROM pages WHERE job_id = ?)
              AND status = 'running'
            """,
            (now, job_id),
        )
        self.conn.commit()

    def add_event(self, job_id: str, event_type: str, message: str, page_id: int | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO events (job_id, page_id, event_type, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, page_id, event_type, message, utc_now_iso()),
        )
        self.conn.commit()

    def get_failed_images(self, job_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT i.*, p.page_num, p.page_url, p.source_id, p.id AS page_id
            FROM images i
            JOIN pages p ON p.id = i.page_id
            WHERE p.job_id = ? AND i.status = 'failed'
            ORDER BY p.page_num, i.image_index
        """
        params: list[Any] = [job_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def stats_for_job(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job is None:
            raise ValueError(f"未找到任务: {job_id}")
        page_totals = self.conn.execute(
            """
            SELECT
              COUNT(*) AS total_pages,
              SUM(CASE WHEN status IN ('completed', 'completed_with_failures') THEN 1 ELSE 0 END) AS done_pages,
              SUM(CASE WHEN status = 'failed_fetch' THEN 1 ELSE 0 END) AS failed_pages,
              SUM(CASE WHEN status = 'no_images' THEN 1 ELSE 0 END) AS empty_pages
            FROM pages WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        image_totals = self.conn.execute(
            """
            SELECT
              COUNT(*) AS total_images,
              SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_images,
              SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_images,
              SUM(CASE WHEN status IN ('pending', 'running') THEN 1 ELSE 0 END) AS remaining_images
            FROM images WHERE page_id IN (SELECT id FROM pages WHERE job_id = ?)
            """,
            (job_id,),
        ).fetchone()
        return {
            "job": {
                "job_id": job.job_id,
                "status": job.status,
                "started_at": job.started_at,
                "updated_at": job.updated_at,
                "finished_at": job.finished_at,
            },
            "pages": dict(page_totals) if page_totals else {},
            "images": dict(image_totals) if image_totals else {},
        }

    def list_events(self, job_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, page_id, event_type, message, created_at
            FROM events WHERE job_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _row_to_page(self, row: sqlite3.Row) -> PageState:
        return PageState(
            id=row["id"],
            job_id=row["job_id"],
            page_num=row["page_num"],
            page_url=row["page_url"],
            source_id=row["source_id"],
            status=row["status"],
            last_completed_image_index=row["last_completed_image_index"],
            image_count=row["image_count"],
            error=row["error"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
        )

    def _row_to_image(self, row: sqlite3.Row) -> ImageRecord:
        return ImageRecord(
            id=row["id"],
            page_id=row["page_id"],
            image_index=row["image_index"],
            url=row["url"],
            local_path=row["local_path"],
            status=row["status"],
            retries=row["retries"],
            http_status=row["http_status"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            downloaded_at=row["downloaded_at"],
            error=row["error"],
            updated_at=row["updated_at"],
        )
