"""Textual TUI entrypoint."""

from __future__ import annotations

from pathlib import Path

from ..models import RunConfig
from .forms import RunConfigForm, build_run_config_from_form, payload_from_run_config
from .services import RunWorker, SnapshotService

_TEXTUAL_IMPORT_ERROR: Exception | None = None
try:  # pragma: no cover - import path depends on optional dependency
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, DataTable, Footer, Header, Static

    from .widgets import EventsTable, FailedImagesTable, JobsTable, PagesTable, StatsPanel
except Exception as exc:  # pragma: no cover - optional dependency not installed
    _TEXTUAL_IMPORT_ERROR = exc


if _TEXTUAL_IMPORT_ERROR is None:

    class HarvesterTUIApp(App[None]):
        """Terminal UI for running and monitoring jobs."""

        CSS = """
        Screen {
            layout: vertical;
        }

        #body {
            layout: horizontal;
            height: 1fr;
        }

        #left-panel {
            width: 42%;
            min-width: 40;
            border: round $primary;
            padding: 0 1;
        }

        #right-panel {
            width: 58%;
            border: round $secondary;
            padding: 0 1;
        }

        .section-title {
            text-style: bold;
            margin-top: 1;
        }

        #jobs-table {
            height: 8;
        }

        #stats-panel {
            height: 7;
            border: tall $accent;
            padding: 0 1;
        }

        #pages-table {
            height: 10;
        }

        #events-table {
            height: 12;
        }

        #failed-table {
            height: 10;
        }

        #status-bar {
            height: 1;
            padding: 0 1;
            background: $surface;
            color: $text;
        }

        #run-form-status {
            color: $text;
        }

        #run-form-error {
            color: $error;
            text-style: bold;
        }
        """
        BINDINGS = [
            ("q", "quit", "退出"),
            ("r", "refresh", "刷新"),
        ]
        TITLE = "Image Harvester TUI"
        SUB_TITLE = "运行 + 实时监控 + 历史任务"

        def __init__(self) -> None:
            super().__init__()
            self._worker: RunWorker | None = None
            self._snapshot_service: SnapshotService | None = None
            self._snapshot_db: Path | None = None
            self._selected_job_id: str | None = None
            self._last_worker_status: str | None = None
            self._last_warning_fingerprint: str | None = None
            self._quit_guard_armed = False
            self._auto_restore_done = False

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="body"):
                with Vertical(id="left-panel"):
                    if RunConfigForm is None:  # pragma: no cover - guarded by import
                        yield Static("Textual 表单组件不可用。", id="run-form-error")
                    else:
                        yield RunConfigForm(id="run-form")
                with VerticalScroll(id="right-panel"):
                    yield Static("任务历史", classes="section-title")
                    yield JobsTable(id="jobs-table")
                    yield Static("任务概览", classes="section-title")
                    yield StatsPanel("未选择任务。", id="stats-panel")
                    yield Static("页面状态", classes="section-title")
                    yield PagesTable(id="pages-table")
                    yield Static("最近事件", classes="section-title")
                    yield EventsTable(id="events-table")
                    yield Static("失败样本", classes="section-title")
                    yield FailedImagesTable(id="failed-table")
            yield Static("就绪", id="status-bar")
            yield Footer()

        def on_mount(self) -> None:
            self._auto_restore_latest_job_on_mount()
            self._refresh_all()
            self.set_interval(1.0, self._refresh_all)

        def action_refresh(self) -> None:
            self._refresh_all()

        def action_quit(self) -> None:
            if self._worker and self._worker.is_running():
                if not self._quit_guard_armed:
                    self._quit_guard_armed = True
                    self._set_status("检测到运行中任务。首版不支持取消，再按一次 q 强制退出。")
                    return
            self.exit()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id != "start-run":
                return
            self._start_run_from_form()

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            if event.data_table.id != "jobs-table":
                return
            row_key = getattr(event.row_key, "value", event.row_key)
            job_id = str(row_key)
            if not job_id:
                return
            self._selected_job_id = job_id
            self._refresh_selected_snapshot()
            self._set_status(f"已切换到任务: {job_id}")

        def _start_run_from_form(self) -> None:
            if self._worker and self._worker.is_running():
                self._set_status("已有任务在运行中，请等待完成后再启动。")
                return

            form = self._form()
            if form is None:
                self._set_status("表单组件不可用。")
                return

            try:
                run_config = build_run_config_from_form(form.get_payload())
            except ValueError as exc:
                form.set_error(str(exc))
                self._set_status(f"配置错误: {exc}")
                return

            if self._start_run_with_config(run_config, started_message=None):
                self._refresh_all()

        def _start_run_with_config(
            self,
            run_config: RunConfig,
            *,
            started_message: str | None,
        ) -> bool:
            if self._worker and self._worker.is_running():
                self._set_status("已有任务在运行中，请等待完成后再启动。")
                return False

            form = self._form()
            if form is not None:
                form.set_error("")

            worker = RunWorker(run_config)
            try:
                worker.start()
            except Exception as exc:
                if form is not None:
                    form.set_error(str(exc))
                self._set_status(f"启动失败: {exc}")
                return False

            self._worker = worker
            self._selected_job_id = worker.job_id
            self._last_worker_status = None
            self._last_warning_fingerprint = None
            self._quit_guard_armed = False
            self._sync_snapshot_service(force=True, state_db=run_config.state_db)
            if form is not None:
                form.set_status(f"当前任务: {worker.job_id}")
            if started_message:
                self._set_status(started_message)
            else:
                self._set_status(f"任务已启动: {worker.job_id}")
            return True

        def _auto_restore_latest_job_on_mount(self) -> None:
            if self._auto_restore_done:
                return
            self._auto_restore_done = True

            self._sync_snapshot_service(force=True)
            service = self._snapshot_service
            if service is None:
                return

            latest = service.latest_job()
            if latest is None:
                return

            fallback_db = self._snapshot_db or Path("data/state.sqlite3")
            run_config = service.load_run_config_from_job(
                latest.job_id,
                fallback_state_db=fallback_db,
            )
            if run_config is None:
                self._set_status(f"无法恢复上次任务配置: {latest.job_id}")
                return

            form = self._form()
            if form is not None:
                form.set_payload(payload_from_run_config(run_config))
                form.set_error("")
                form.set_status(f"已回填上次任务配置: {latest.job_id}")

            self._selected_job_id = latest.job_id
            self._sync_snapshot_service(force=True, state_db=run_config.state_db)

            if latest.status == "running":
                self._start_run_with_config(
                    run_config,
                    started_message=f"检测到中断任务，已自动续跑: {latest.job_id}",
                )
            else:
                self._set_status(f"已回填上次任务配置: {latest.job_id}")

        def _refresh_all(self) -> None:
            self._sync_worker_state()
            self._sync_snapshot_service()
            self._refresh_job_list()
            self._refresh_selected_snapshot()

        def _sync_worker_state(self) -> None:
            if self._worker is None:
                self._last_worker_status = None
                return

            snapshot = self._worker.snapshot()
            if snapshot.status != self._last_worker_status:
                if snapshot.status == "running":
                    self._set_status(f"任务运行中: {snapshot.job_id}")
                elif snapshot.status == "completed":
                    self._set_status(f"任务完成: {snapshot.job_id}")
                elif snapshot.status == "failed":
                    self._set_status(f"任务失败: {snapshot.error}")
                self._last_worker_status = snapshot.status

            if snapshot.status != "running":
                self._quit_guard_armed = False

            if snapshot.warnings:
                fingerprint = " | ".join(snapshot.warnings)
                if fingerprint != self._last_warning_fingerprint:
                    self._set_status(f"告警: {snapshot.warnings[-1]}")
                    self._last_warning_fingerprint = fingerprint

        def _sync_snapshot_service(self, *, force: bool = False, state_db: Path | None = None) -> None:
            if self._worker and self._worker.is_running():
                target_db = self._worker.run_config.state_db
            else:
                target_db = state_db or self._state_db_from_form()

            if not force and self._snapshot_service is not None and self._snapshot_db == target_db:
                return

            self._snapshot_db = target_db
            self._snapshot_service = SnapshotService(target_db)
            if self._selected_job_id is None and self._snapshot_service is not None:
                self._selected_job_id = self._snapshot_service.latest_job_id()

        def _refresh_job_list(self) -> None:
            jobs_table = self.query_one("#jobs-table", JobsTable)
            if self._snapshot_service is None:
                jobs_table.set_jobs([])
                return

            try:
                jobs = self._snapshot_service.list_jobs(limit=50)
            except Exception as exc:
                self._set_status(f"读取任务列表失败: {exc}")
                jobs_table.set_jobs([])
                return

            jobs_table.set_jobs(jobs)
            if self._selected_job_id is None and jobs:
                self._selected_job_id = jobs[0].job_id

            if self._selected_job_id is None:
                return
            for index, job in enumerate(jobs):
                if job.job_id == self._selected_job_id:
                    try:
                        jobs_table.move_cursor(row=index, column=0)
                    except Exception:
                        pass
                    break

        def _refresh_selected_snapshot(self) -> None:
            stats_panel = self.query_one("#stats-panel", StatsPanel)
            pages_table = self.query_one("#pages-table", PagesTable)
            events_table = self.query_one("#events-table", EventsTable)
            failed_table = self.query_one("#failed-table", FailedImagesTable)

            if self._snapshot_service is None:
                stats_panel.set_snapshot(None)
                pages_table.set_pages([])
                events_table.set_events([])
                failed_table.set_failed_images([])
                return

            if self._selected_job_id is None:
                self._selected_job_id = self._snapshot_service.latest_job_id()
            if self._selected_job_id is None:
                stats_panel.set_snapshot(None)
                pages_table.set_pages([])
                events_table.set_events([])
                failed_table.set_failed_images([])
                return

            try:
                snapshot = self._snapshot_service.get_snapshot(
                    self._selected_job_id,
                    events_limit=100,
                    failed_limit=50,
                )
            except Exception as exc:
                self._set_status(f"读取任务详情失败: {exc}")
                return

            if snapshot is None:
                stats_panel.set_snapshot(None)
                pages_table.set_pages([])
                events_table.set_events([])
                failed_table.set_failed_images([])
                return

            stats_panel.set_snapshot(snapshot.stats)
            pages_table.set_pages(snapshot.pages)
            events_table.set_events(snapshot.events)
            failed_table.set_failed_images(snapshot.failed_images)

        def _state_db_from_form(self) -> Path:
            form = self._form()
            if form is None:
                return Path("data/state.sqlite3")
            state_db_text = form.state_db_path_text()
            if not state_db_text:
                return Path("data/state.sqlite3")
            return Path(state_db_text)

        def _form(self) -> RunConfigForm | None:
            if RunConfigForm is None:
                return None
            return self.query_one("#run-form", RunConfigForm)

        def _set_status(self, message: str) -> None:
            self.query_one("#status-bar", Static).update(message)
            form = self._form()
            if form is not None:
                form.set_status(message)

else:

    class HarvesterTUIApp:  # pragma: no cover - fallback class for missing dependency
        """Fallback placeholder when Textual is unavailable."""

        def run(self) -> None:
            raise RuntimeError(
                "Textual 不可用。请先执行 `pip install -e \".[tui]\"` 安装 TUI 依赖。"
            )


def main() -> None:
    """CLI entry for `harvester-tui`."""
    if _TEXTUAL_IMPORT_ERROR is not None:
        raise SystemExit(
            "Textual 不可用。请先执行 `pip install -e \".[tui]\"` 安装 TUI 依赖。"
        )
    HarvesterTUIApp().run()
