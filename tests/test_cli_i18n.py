from __future__ import annotations

from pathlib import Path

import pytest

from image_harvester.cli import _build_parser, _handle_run, _handle_status


def test_cli_help_is_chinese() -> None:
    parser = _build_parser()
    help_text = parser.format_help()
    assert "图片采集器 v2" in help_text
    assert "运行基于模板的采集任务。" in help_text


def test_run_missing_url_template_uses_chinese_message() -> None:
    parser = _build_parser()
    args = parser.parse_args(["run", "--start-num", "1"])
    with pytest.raises(SystemExit) as exc:
        _handle_run(args)
    assert str(exc.value) == "缺少必填项: --url-template（或 config.url_template）。"


def test_status_no_jobs_uses_chinese_message() -> None:
    parser = _build_parser()
    db_path = Path("state_i18n_test.sqlite3")
    if db_path.exists():
        db_path.unlink()
    args = parser.parse_args(["status", "--state-db", str(db_path)])
    try:
        with pytest.raises(SystemExit) as exc:
            _handle_status(args)
        assert str(exc.value) == "状态数据库中未找到任务。"
    finally:
        if db_path.exists():
            db_path.unlink()
