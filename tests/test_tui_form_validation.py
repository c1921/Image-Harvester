from __future__ import annotations

import pytest

from image_harvester.models import RunConfig
from image_harvester.tui.forms import (
    build_run_config_from_form,
    form_defaults,
    payload_from_run_config,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload = form_defaults()
    payload.update(
        {
            "url_template": "https://example.test/gallery/{num}.html",
            "start_num": "1",
        }
    )
    payload.update(overrides)
    return payload


def test_form_builds_valid_run_config() -> None:
    config = build_run_config_from_form(_payload(end_num=""))
    assert config.url_template.endswith("{num}.html")
    assert config.start_num == 1
    assert config.end_num is None
    assert config.engine == "requests"
    assert config.sequence_expand_enabled is True
    assert config.sequence_count_selector == "#tishi p span"


def test_form_requires_url_template() -> None:
    with pytest.raises(ValueError) as exc:
        build_run_config_from_form(_payload(url_template=""))
    assert str(exc.value) == "url_template 不能为空。"


def test_form_rejects_invalid_start_num_type() -> None:
    with pytest.raises(ValueError) as exc:
        build_run_config_from_form(_payload(start_num="abc"))
    assert str(exc.value) == "start_num 必须是整数。"


def test_form_rejects_end_num_smaller_than_start_num() -> None:
    with pytest.raises(ValueError) as exc:
        build_run_config_from_form(_payload(start_num="5", end_num="3"))
    assert str(exc.value) == "end_num 必须 >= start_num"


def test_form_requires_num_placeholder_in_url_template() -> None:
    with pytest.raises(ValueError) as exc:
        build_run_config_from_form(_payload(url_template="https://example.test/gallery/page.html"))
    assert str(exc.value) == "url_template 必须包含 '{num}' 占位符。"


def test_payload_from_run_config_uses_form_shape() -> None:
    cfg = RunConfig(
        url_template="https://example.test/gallery/{num}.html",
        start_num=2,
        end_num=None,
        engine="requests",
    )
    payload = payload_from_run_config(cfg)
    assert payload["url_template"] == "https://example.test/gallery/{num}.html"
    assert payload["start_num"] == "2"
    assert payload["end_num"] == ""
    assert payload["engine"] == "requests"
    assert payload["sequence_expand_enabled"] is True
