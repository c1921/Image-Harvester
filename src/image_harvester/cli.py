"""Command-line interface for Image Harvester v2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import build_run_config, compute_job_id, load_yaml_config, run_config_json
from .fetchers import PlaywrightFetcher, RequestsFetcher
from .models import RunConfig
from .pipeline import ImageHarvesterPipeline
from .state import StateStore


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "run":
        _handle_run(args)
    elif args.command == "status":
        _handle_status(args)
    elif args.command == "retry-failed":
        _handle_retry_failed(args)
    elif args.command == "export-metadata":
        _handle_export_metadata(args)
    else:
        parser.error(f"未知命令: {args.command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="图片采集器 v2")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="运行基于模板的采集任务。")
    run_parser.add_argument("--config", type=Path, default=None, help="YAML 配置文件路径。")
    run_parser.add_argument(
        "--url-template",
        dest="url_template",
        default=None,
        help="页面 URL 模板，必须包含 {num} 占位符。",
    )
    run_parser.add_argument("--start-num", dest="start_num", type=int, default=None, help="起始页码（含）。")
    run_parser.add_argument("--end-num", dest="end_num", type=int, default=None, help="结束页码（含）。")
    run_parser.add_argument("--selector", default=None, help="提取图片链接的 CSS 选择器。")
    run_parser.add_argument("--output-dir", dest="output_dir", default=None, help="图片输出目录。")
    run_parser.add_argument("--state-db", dest="state_db", default=None, help="SQLite 状态库路径。")
    run_parser.add_argument(
        "--engine",
        default=None,
        choices=["requests", "playwright"],
        help="抓取引擎。",
    )
    run_parser.add_argument("--resume", dest="resume", action="store_true", help="启用断点续跑。")
    run_parser.add_argument("--no-resume", dest="resume", action="store_false", help="禁用断点续跑。")
    run_parser.set_defaults(resume=None)
    run_parser.add_argument(
        "--page-timeout-sec",
        dest="page_timeout_sec",
        type=float,
        default=None,
        help="页面抓取超时秒数。",
    )
    run_parser.add_argument(
        "--image-timeout-sec",
        dest="image_timeout_sec",
        type=float,
        default=None,
        help="图片下载超时秒数。",
    )
    run_parser.add_argument(
        "--image-retries",
        dest="image_retries",
        type=int,
        default=None,
        help="图片下载重试次数。",
    )
    run_parser.add_argument(
        "--page-retries",
        dest="page_retries",
        type=int,
        default=None,
        help="页面抓取重试次数。",
    )
    run_parser.add_argument(
        "--request-delay-sec",
        dest="request_delay_sec",
        type=float,
        default=None,
        help="请求间隔秒数。",
    )
    run_parser.add_argument(
        "--stop-after-consecutive-page-failures",
        dest="stop_after_consecutive_page_failures",
        type=int,
        default=None,
        help="未设置 --end-num 时，连续失败页达到该值后停止。",
    )
    run_parser.add_argument(
        "--playwright-fallback",
        dest="playwright_fallback",
        action="store_true",
        help="当解析不到图片时回退到 Playwright。",
    )
    run_parser.add_argument(
        "--no-playwright-fallback",
        dest="playwright_fallback",
        action="store_false",
        help="禁用 Playwright 回退。",
    )
    run_parser.set_defaults(playwright_fallback=None)

    status_parser = subparsers.add_parser("status", help="查看任务状态。")
    status_parser.add_argument(
        "--state-db",
        dest="state_db",
        default="data/state.sqlite3",
        help="SQLite 状态库路径。",
    )
    status_parser.add_argument("--job-id", dest="job_id", default=None, help="任务 ID，不传则取最新任务。")
    status_parser.add_argument(
        "--events-limit",
        dest="events_limit",
        type=int,
        default=10,
        help="返回事件条数上限。",
    )
    status_parser.add_argument(
        "--failed-limit",
        dest="failed_limit",
        type=int,
        default=20,
        help="返回失败图片样本条数上限。",
    )

    retry_parser = subparsers.add_parser("retry-failed", help="重试失败图片。")
    retry_parser.add_argument(
        "--state-db",
        dest="state_db",
        default="data/state.sqlite3",
        help="SQLite 状态库路径。",
    )
    retry_parser.add_argument("--job-id", dest="job_id", default=None, help="任务 ID，不传则取最新任务。")
    retry_parser.add_argument("--limit", type=int, default=None, help="最大重试条数。")
    retry_parser.add_argument(
        "--image-timeout-sec",
        dest="image_timeout_sec",
        type=float,
        default=None,
        help="图片下载超时秒数。",
    )
    retry_parser.add_argument(
        "--image-retries",
        dest="image_retries",
        type=int,
        default=None,
        help="图片下载重试次数。",
    )
    retry_parser.add_argument(
        "--request-delay-sec",
        dest="request_delay_sec",
        type=float,
        default=None,
        help="请求间隔秒数。",
    )

    export_parser = subparsers.add_parser(
        "export-metadata",
        help="导出任务级元数据汇总 JSON。",
    )
    export_parser.add_argument(
        "--state-db",
        dest="state_db",
        default="data/state.sqlite3",
        help="SQLite 状态库路径。",
    )
    export_parser.add_argument("--job-id", dest="job_id", default=None, help="任务 ID，不传则取最新任务。")
    export_parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/job_export.json"),
        help="导出 JSON 文件路径。",
    )

    return parser


def _handle_run(args: argparse.Namespace) -> None:
    yaml_data = load_yaml_config(args.config)
    merged = _merge_run_settings(args, yaml_data)

    if merged.get("url_template") is None:
        raise SystemExit("缺少必填项: --url-template（或 config.url_template）。")
    if merged.get("start_num") is None:
        raise SystemExit("缺少必填项: --start-num（或 config.start_num）。")

    run_config = build_run_config(merged)
    store = StateStore(run_config.state_db)
    try:
        fetcher, fallback_fetcher = _build_fetchers(run_config)
        pipeline = ImageHarvesterPipeline(
            config=run_config,
            store=store,
            fetcher=fetcher,
            fallback_fetcher=fallback_fetcher,
        )
        job_id = compute_job_id(run_config)
        summary = pipeline.run(job_id=job_id, config_json=run_config_json(run_config))
        result = {
            "job_id": job_id,
            "status": "ok",
            "summary": summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


def _handle_status(args: argparse.Namespace) -> None:
    store = StateStore(Path(args.state_db))
    try:
        job_id = args.job_id or _resolve_latest_job_id(store)
        if job_id is None:
            raise SystemExit("状态数据库中未找到任务。")
        stats = store.stats_for_job(job_id)
        failed = store.get_failed_images(job_id, limit=args.failed_limit)
        events = store.list_events(job_id, limit=args.events_limit)
        payload = {
            "job_id": job_id,
            "stats": stats,
            "failed_images_sample": [
                {
                    "page_num": item["page_num"],
                    "image_index": item["image_index"],
                    "url": item["url"],
                    "local_path": item["local_path"],
                    "error": item["error"],
                }
                for item in failed
            ],
            "events": list(reversed(events)),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        store.close()


def _handle_retry_failed(args: argparse.Namespace) -> None:
    store = StateStore(Path(args.state_db))
    try:
        job_id = args.job_id or _resolve_latest_job_id(store)
        if job_id is None:
            raise SystemExit("状态数据库中未找到任务。")
        run_config = _load_job_run_config_or_default(store, job_id, Path(args.state_db))
        pipeline = ImageHarvesterPipeline(
            config=run_config,
            store=store,
            fetcher=RequestsFetcher(),
        )
        summary = pipeline.retry_failed(
            job_id=job_id,
            limit=args.limit,
            timeout_sec=args.image_timeout_sec,
            retries=args.image_retries,
            delay_sec=args.request_delay_sec,
        )
        payload = {"job_id": job_id, "status": "ok", "retry_summary": summary}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        store.close()


def _handle_export_metadata(args: argparse.Namespace) -> None:
    store = StateStore(Path(args.state_db))
    try:
        job_id = args.job_id or _resolve_latest_job_id(store)
        if job_id is None:
            raise SystemExit("状态数据库中未找到任务。")
        run_config = _load_job_run_config_or_default(store, job_id, Path(args.state_db))
        pipeline = ImageHarvesterPipeline(
            config=run_config,
            store=store,
            fetcher=RequestsFetcher(),
        )
        output_path = pipeline.export_job_metadata(job_id=job_id, output_path=args.output)
        payload = {"job_id": job_id, "status": "ok", "output": str(output_path)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    finally:
        store.close()


def _merge_run_settings(args: argparse.Namespace, yaml_data: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    keys = [
        "url_template",
        "start_num",
        "end_num",
        "selector",
        "output_dir",
        "state_db",
        "engine",
        "resume",
        "page_timeout_sec",
        "image_timeout_sec",
        "image_retries",
        "page_retries",
        "request_delay_sec",
        "stop_after_consecutive_page_failures",
        "playwright_fallback",
    ]
    for key in keys:
        cli_value = getattr(args, key)
        if cli_value is not None:
            merged[key] = cli_value
        elif key in yaml_data:
            merged[key] = yaml_data[key]
    return merged


def _build_fetchers(run_config: RunConfig):
    if run_config.engine == "requests":
        primary = RequestsFetcher()
        fallback = None
        if run_config.playwright_fallback:
            try:
                fallback = PlaywrightFetcher()
            except RuntimeError as exc:
                print(f"警告: Playwright 回退已禁用: {exc}", file=sys.stderr)
        return primary, fallback
    if run_config.engine == "playwright":
        return PlaywrightFetcher(), None
    raise ValueError(f"不支持的引擎: {run_config.engine}")


def _resolve_latest_job_id(store: StateStore) -> str | None:
    latest = store.get_latest_job()
    return latest.job_id if latest else None


def _load_job_run_config_or_default(
    store: StateStore,
    job_id: str,
    state_db: Path,
) -> RunConfig:
    job = store.get_job(job_id)
    if job is None:
        raise SystemExit(f"未找到任务: {job_id}")
    try:
        raw = json.loads(job.config_json)
        if "state_db" not in raw:
            raw["state_db"] = str(state_db)
        return build_run_config(raw)
    except Exception:
        return build_run_config(
            {
                "url_template": "https://example.com/{num}",
                "start_num": 0,
                "state_db": str(state_db),
            }
        )
