from __future__ import annotations

from image_harvester.naming import image_file_name, page_dir_name, source_id_from_page_url
from image_harvester.parser import parse_gallery_upper_bound, parse_image_urls


def test_parse_image_urls_keeps_dom_order() -> None:
    html = """
    <html>
      <body>
        <div class="gallerypic">
          <img src="/img/002.jpg" />
          <img src="/img/001.jpg" />
          <img src="https://cdn.example.com/003.jpg" />
        </div>
      </body>
    </html>
    """
    result = parse_image_urls(html, "https://site.example/gallery/9.html", "div.gallerypic img")
    assert result.image_urls == [
        "https://site.example/img/002.jpg",
        "https://site.example/img/001.jpg",
        "https://cdn.example.com/003.jpg",
    ]


def test_naming_rules() -> None:
    assert source_id_from_page_url("https://a.example/gallery/1234.html", 77) == "1234"
    assert source_id_from_page_url("https://a.example/path/no-id", 77) == "77"
    assert page_dir_name(12, "98") == "P000012_98"
    assert image_file_name(7, "https://a.example/cat/pic-01.jpg?token=x") == "I0007_pic-01.jpg"


def test_parse_gallery_upper_bound_from_tishi_span() -> None:
    html = """
    <html>
      <body>
        <div id="tishi"><p>全本<span>61</span>张图片，欣赏完整作品</p></div>
      </body>
    </html>
    """
    assert parse_gallery_upper_bound(html, "#tishi p span") == 61


def test_parse_gallery_upper_bound_returns_none_when_missing() -> None:
    html = "<html><body><div>no count</div></body></html>"
    assert parse_gallery_upper_bound(html, "#tishi p span") is None
