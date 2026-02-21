"""Configuration helpers for CLI + YAML input."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .models import RunConfig


def load_yaml_config(path: Path | None) -> dict[str, Any]:
    """Load YAML config or return empty dict when path is absent."""
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise ValueError("YAML 配置根节点必须是对象（mapping）。")
    return data


def build_run_config(raw: dict[str, Any]) -> RunConfig:
    """Construct RunConfig with normalized paths."""
    config = RunConfig(
        url_template=str(raw["url_template"]),
        start_num=int(raw["start_num"]),
        end_num=int(raw["end_num"]) if raw.get("end_num") is not None else None,
        selector=str(raw.get("selector", "div.gallerypic img")),
        output_dir=Path(raw.get("output_dir", "data/downloads")),
        state_db=Path(raw.get("state_db", "data/state.sqlite3")),
        engine=str(raw.get("engine", "requests")).lower(),
        resume=bool(raw.get("resume", True)),
        page_timeout_sec=float(raw.get("page_timeout_sec", 20.0)),
        image_timeout_sec=float(raw.get("image_timeout_sec", 30.0)),
        image_retries=int(raw.get("image_retries", 3)),
        page_retries=int(raw.get("page_retries", 2)),
        request_delay_sec=float(raw.get("request_delay_sec", 0.2)),
        stop_after_consecutive_page_failures=int(
            raw.get("stop_after_consecutive_page_failures", 5)
        ),
        playwright_fallback=bool(raw.get("playwright_fallback", False)),
        sequence_count_selector=str(raw.get("sequence_count_selector", "#tishi p span")),
        sequence_require_upper_bound=bool(raw.get("sequence_require_upper_bound", True)),
        sequence_probe_after_upper_bound=bool(
            raw.get("sequence_probe_after_upper_bound", False)
        ),
    )
    validate_run_config(config)
    return config


def validate_run_config(config: RunConfig) -> None:
    """Validate config values and raise ValueError on invalid input."""
    if "{num}" not in config.url_template:
        raise ValueError("url_template 必须包含 '{num}' 占位符。")
    if config.start_num < 0:
        raise ValueError("start_num 必须 >= 0")
    if config.end_num is not None and config.end_num < config.start_num:
        raise ValueError("end_num 必须 >= start_num")
    if config.engine not in {"requests", "playwright"}:
        raise ValueError("engine 必须是以下之一: requests, playwright")
    if config.image_retries < 0:
        raise ValueError("image_retries 必须 >= 0")
    if config.page_retries < 0:
        raise ValueError("page_retries 必须 >= 0")
    if config.stop_after_consecutive_page_failures < 1:
        raise ValueError("stop_after_consecutive_page_failures 必须 >= 1")
    if not config.selector.strip():
        raise ValueError("selector 不能为空。")
    if not config.sequence_count_selector.strip():
        raise ValueError("sequence_count_selector 不能为空。")


def compute_job_id(config: RunConfig) -> str:
    """Build stable job identifier from identity fields."""
    raw = json.dumps(config.as_job_identity(), sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"job_{digest}"


def run_config_json(config: RunConfig) -> str:
    """Serialize config as JSON for persistence."""
    payload = {
        "url_template": config.url_template,
        "start_num": config.start_num,
        "end_num": config.end_num,
        "selector": config.selector,
        "output_dir": str(config.output_dir),
        "state_db": str(config.state_db),
        "engine": config.engine,
        "resume": config.resume,
        "page_timeout_sec": config.page_timeout_sec,
        "image_timeout_sec": config.image_timeout_sec,
        "image_retries": config.image_retries,
        "page_retries": config.page_retries,
        "request_delay_sec": config.request_delay_sec,
        "stop_after_consecutive_page_failures": config.stop_after_consecutive_page_failures,
        "playwright_fallback": config.playwright_fallback,
        "sequence_count_selector": config.sequence_count_selector,
        "sequence_require_upper_bound": config.sequence_require_upper_bound,
        "sequence_probe_after_upper_bound": config.sequence_probe_after_upper_bound,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
