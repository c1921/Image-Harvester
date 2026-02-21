"""Run-config form model + widget helpers for TUI."""

from __future__ import annotations

from typing import Any, Mapping

from ..config import build_run_config
from ..models import RunConfig

FORM_DEFAULTS: dict[str, Any] = {
    "url_template": "",
    "start_num": "1",
    "end_num": "",
    "selector": "div.gallerypic img",
    "output_dir": "data/downloads",
    "state_db": "data/state.sqlite3",
    "engine": "requests",
    "resume": True,
    "page_timeout_sec": "20.0",
    "image_timeout_sec": "30.0",
    "image_retries": "3",
    "page_retries": "2",
    "request_delay_sec": "0.2",
    "stop_after_consecutive_page_failures": "5",
    "playwright_fallback": False,
    "sequence_expand_enabled": True,
    "sequence_count_selector": "#tishi p span",
    "sequence_require_upper_bound": True,
}


def form_defaults() -> dict[str, Any]:
    """Return mutable defaults for run form fields."""
    return dict(FORM_DEFAULTS)


def build_run_config_from_form(payload: Mapping[str, object]) -> RunConfig:
    """Parse form payload into RunConfig with strict conversion."""
    raw: dict[str, Any] = {}

    raw["url_template"] = _required_text(payload, "url_template", "url_template")
    raw["start_num"] = _required_int(payload, "start_num", "start_num")
    raw["end_num"] = _optional_int(payload, "end_num", "end_num")
    raw["selector"] = _text_or_default(payload, "selector", str(FORM_DEFAULTS["selector"]))
    raw["output_dir"] = _text_or_default(payload, "output_dir", str(FORM_DEFAULTS["output_dir"]))
    raw["state_db"] = _text_or_default(payload, "state_db", str(FORM_DEFAULTS["state_db"]))
    raw["engine"] = _text_or_default(payload, "engine", str(FORM_DEFAULTS["engine"])).lower()
    raw["resume"] = _bool_or_default(payload, "resume", bool(FORM_DEFAULTS["resume"]))
    raw["page_timeout_sec"] = _required_float(payload, "page_timeout_sec", "page_timeout_sec")
    raw["image_timeout_sec"] = _required_float(payload, "image_timeout_sec", "image_timeout_sec")
    raw["image_retries"] = _required_int(payload, "image_retries", "image_retries")
    raw["page_retries"] = _required_int(payload, "page_retries", "page_retries")
    raw["request_delay_sec"] = _required_float(payload, "request_delay_sec", "request_delay_sec")
    raw["stop_after_consecutive_page_failures"] = _required_int(
        payload,
        "stop_after_consecutive_page_failures",
        "stop_after_consecutive_page_failures",
    )
    raw["playwright_fallback"] = _bool_or_default(
        payload,
        "playwright_fallback",
        bool(FORM_DEFAULTS["playwright_fallback"]),
    )
    raw["sequence_expand_enabled"] = _bool_or_default(
        payload,
        "sequence_expand_enabled",
        bool(FORM_DEFAULTS["sequence_expand_enabled"]),
    )
    raw["sequence_count_selector"] = _text_or_default(
        payload,
        "sequence_count_selector",
        str(FORM_DEFAULTS["sequence_count_selector"]),
    )
    raw["sequence_require_upper_bound"] = _bool_or_default(
        payload,
        "sequence_require_upper_bound",
        bool(FORM_DEFAULTS["sequence_require_upper_bound"]),
    )
    return build_run_config(raw)


def _required_text(payload: Mapping[str, object], field: str, label: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value:
        raise ValueError(f"{label} 不能为空。")
    return value


def _text_or_default(payload: Mapping[str, object], field: str, default: str) -> str:
    value = str(payload.get(field, "")).strip()
    return value or default


def _required_int(payload: Mapping[str, object], field: str, label: str) -> int:
    raw = str(payload.get(field, "")).strip()
    if not raw:
        raise ValueError(f"{label} 不能为空。")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是整数。") from exc


def _optional_int(payload: Mapping[str, object], field: str, label: str) -> int | None:
    raw = str(payload.get(field, "")).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是整数。") from exc


def _required_float(payload: Mapping[str, object], field: str, label: str) -> float:
    raw = str(payload.get(field, "")).strip()
    if not raw:
        raise ValueError(f"{label} 不能为空。")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是数字。") from exc


def _bool_or_default(payload: Mapping[str, object], field: str, default: bool) -> bool:
    value = payload.get(field, default)
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on", "y"}:
        return True
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    raise ValueError(f"{field} 必须是布尔值。")


try:  # pragma: no cover - UI class is covered by manual interaction
    from textual.app import ComposeResult
    from textual.containers import VerticalScroll
    from textual.widgets import Button, Checkbox, Input, Label, Select, Static

    class RunConfigForm(VerticalScroll):
        """Left-side full RunConfig form."""

        def compose(self) -> ComposeResult:
            defaults = form_defaults()
            yield Label("运行参数", classes="section-title")
            yield Label("URL 模板")
            yield Input(
                value=str(defaults["url_template"]),
                placeholder="https://example.com/{num}.html",
                id="url_template",
            )
            yield Label("起始页码 start_num")
            yield Input(value=str(defaults["start_num"]), id="start_num")
            yield Label("结束页码 end_num（可空）")
            yield Input(value=str(defaults["end_num"]), id="end_num")
            yield Label("CSS 选择器 selector")
            yield Input(value=str(defaults["selector"]), id="selector")
            yield Label("输出目录 output_dir")
            yield Input(value=str(defaults["output_dir"]), id="output_dir")
            yield Label("状态库 state_db")
            yield Input(value=str(defaults["state_db"]), id="state_db")
            yield Label("抓取引擎 engine")
            yield Select(
                options=[("requests", "requests"), ("playwright", "playwright")],
                value=str(defaults["engine"]),
                id="engine",
            )
            yield Checkbox("启用断点续跑 resume", value=bool(defaults["resume"]), id="resume")
            yield Label("页面超时秒 page_timeout_sec")
            yield Input(value=str(defaults["page_timeout_sec"]), id="page_timeout_sec")
            yield Label("图片超时秒 image_timeout_sec")
            yield Input(value=str(defaults["image_timeout_sec"]), id="image_timeout_sec")
            yield Label("图片重试 image_retries")
            yield Input(value=str(defaults["image_retries"]), id="image_retries")
            yield Label("页面重试 page_retries")
            yield Input(value=str(defaults["page_retries"]), id="page_retries")
            yield Label("请求间隔秒 request_delay_sec")
            yield Input(value=str(defaults["request_delay_sec"]), id="request_delay_sec")
            yield Label("连续失败停止阈值 stop_after_consecutive_page_failures")
            yield Input(
                value=str(defaults["stop_after_consecutive_page_failures"]),
                id="stop_after_consecutive_page_failures",
            )
            yield Checkbox(
                "启用 Playwright 回退 playwright_fallback",
                value=bool(defaults["playwright_fallback"]),
                id="playwright_fallback",
            )
            yield Checkbox(
                "启用序号扩展下载 sequence_expand_enabled",
                value=bool(defaults["sequence_expand_enabled"]),
                id="sequence_expand_enabled",
            )
            yield Label("序号上限选择器 sequence_count_selector")
            yield Input(
                value=str(defaults["sequence_count_selector"]),
                id="sequence_count_selector",
            )
            yield Checkbox(
                "要求解析上限 sequence_require_upper_bound",
                value=bool(defaults["sequence_require_upper_bound"]),
                id="sequence_require_upper_bound",
            )
            yield Button("开始任务", id="start-run", variant="primary")
            yield Static("", id="run-form-status")
            yield Static("", id="run-form-error")

        def get_payload(self) -> dict[str, object]:
            engine_widget = self.query_one("#engine", Select)
            engine_value = engine_widget.value
            engine = "" if engine_value == Select.BLANK else str(engine_value)
            return {
                "url_template": self.query_one("#url_template", Input).value,
                "start_num": self.query_one("#start_num", Input).value,
                "end_num": self.query_one("#end_num", Input).value,
                "selector": self.query_one("#selector", Input).value,
                "output_dir": self.query_one("#output_dir", Input).value,
                "state_db": self.query_one("#state_db", Input).value,
                "engine": engine,
                "resume": self.query_one("#resume", Checkbox).value,
                "page_timeout_sec": self.query_one("#page_timeout_sec", Input).value,
                "image_timeout_sec": self.query_one("#image_timeout_sec", Input).value,
                "image_retries": self.query_one("#image_retries", Input).value,
                "page_retries": self.query_one("#page_retries", Input).value,
                "request_delay_sec": self.query_one("#request_delay_sec", Input).value,
                "stop_after_consecutive_page_failures": self.query_one(
                    "#stop_after_consecutive_page_failures",
                    Input,
                ).value,
                "playwright_fallback": self.query_one("#playwright_fallback", Checkbox).value,
                "sequence_expand_enabled": self.query_one(
                    "#sequence_expand_enabled",
                    Checkbox,
                ).value,
                "sequence_count_selector": self.query_one("#sequence_count_selector", Input).value,
                "sequence_require_upper_bound": self.query_one(
                    "#sequence_require_upper_bound",
                    Checkbox,
                ).value,
            }

        def state_db_path_text(self) -> str:
            return self.query_one("#state_db", Input).value.strip()

        def set_error(self, message: str) -> None:
            self.query_one("#run-form-error", Static).update(message)

        def set_status(self, message: str) -> None:
            self.query_one("#run-form-status", Static).update(message)


except Exception:  # pragma: no cover - textual optional dependency
    RunConfigForm = None  # type: ignore[assignment]
