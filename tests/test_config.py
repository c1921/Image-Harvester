from __future__ import annotations

import pytest

from image_harvester.config import build_run_config


def test_build_run_config_validates_template_placeholder() -> None:
    with pytest.raises(ValueError, match="占位符"):
        build_run_config({"url_template": "https://x/no-placeholder", "start_num": 1})


def test_build_run_config_validates_range_boundary() -> None:
    with pytest.raises(ValueError, match="end_num 必须 >= start_num"):
        build_run_config(
            {
                "url_template": "https://x/{num}",
                "start_num": 5,
                "end_num": 4,
            }
        )


def test_build_run_config_sets_sequence_defaults() -> None:
    config = build_run_config({"url_template": "https://x/{num}", "start_num": 1})
    assert config.sequence_count_selector == "#tishi p span"
    assert config.sequence_require_upper_bound is True
    assert config.sequence_probe_after_upper_bound is False


def test_build_run_config_sets_parallel_defaults() -> None:
    config = build_run_config({"url_template": "https://x/{num}", "start_num": 1})
    assert config.page_workers == 4
    assert config.image_workers == 48
    assert config.max_requests_per_sec == 80.0
    assert config.max_burst == 120
    assert config.db_batch_size == 300
    assert config.continue_on_image_failure is True


def test_build_run_config_validates_parallel_limits() -> None:
    with pytest.raises(ValueError, match="page_workers 必须 >= 1"):
        build_run_config(
            {
                "url_template": "https://x/{num}",
                "start_num": 1,
                "page_workers": 0,
            }
        )
