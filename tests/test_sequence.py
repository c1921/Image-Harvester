from __future__ import annotations

from image_harvester.sequence import build_sequence_url, extract_sequence_seed


def test_extract_sequence_seed_from_numbered_url() -> None:
    parsed = extract_sequence_seed("https://oss.example.com/img/77163/001.jpg")
    assert parsed == ("https://oss.example.com/img/77163/", 3, "jpg", 1)


def test_extract_sequence_seed_rejects_non_numbered_filename() -> None:
    assert extract_sequence_seed("https://oss.example.com/img/77163/cover.jpg") is None


def test_build_sequence_url_keeps_padding_width() -> None:
    url = build_sequence_url("https://oss.example.com/img/77163/", 3, "jpg", 12)
    assert url == "https://oss.example.com/img/77163/012.jpg"
