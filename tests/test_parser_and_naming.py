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
    assert result.gallery_meta.title == ""
    assert result.gallery_meta.published_date == ""
    assert result.gallery_meta.tags == []
    assert result.gallery_meta.organizations == []
    assert result.gallery_meta.models == []


def test_naming_rules() -> None:
    assert source_id_from_page_url("https://a.example/gallery/1234.html", 77) == "1234"
    assert source_id_from_page_url("https://a.example/path/no-id", 77) == "77"
    assert page_dir_name(12, "98") == "000012"
    assert image_file_name(7, "https://a.example/cat/pic-01.jpg?token=x") == "pic-01.jpg"


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


def test_parse_image_urls_extracts_gallery_meta_fields() -> None:
    html = """
    <html>
      <body>
        <div class="gallery_jieshao">
          <h1>[YouMi]尤蜜荟 2024.07.10 Vol.1082 心妍小公主</h1>
          <p>2024-11-02</p>
          <p>
            <a href="/tags/i-cup.html">I-CUP</a>
            <a href="/tags/meijiao.html">美脚</a>
            <a href="/tags/jiudian.html">酒店</a>
          </p>
        </div>
        <div class="gallery_nav">
          <div class="gallery_nav_box">
            <div class="gallery_nav_box_left">
              <div class="gallery_renwu">
                <a href="/jigou/98.html"><div class="gallery_chuangzuo">机构</div></a>
                <div class="gallery_renwu_title"><a href="/jigou/98.html">尤蜜荟</a></div>
              </div>
              <div class="gallery_renwu">
                <a href="/mote/99.html"><div class="gallery_chujing">模特</div></a>
                <div class="gallery_renwu_title"><a href="/mote/99.html">李妍曦</a></div>
              </div>
            </div>
          </div>
        </div>
        <div class="gallerypic"><img src="/img/001.jpg" /></div>
      </body>
    </html>
    """
    result = parse_image_urls(html, "https://site.example/gallery/9.html", "div.gallerypic img")
    assert result.gallery_meta.title == "[YouMi]尤蜜荟 2024.07.10 Vol.1082 心妍小公主"
    assert result.gallery_meta.published_date == "2024-11-02"
    assert result.gallery_meta.tags == ["I-CUP", "美脚", "酒店"]
    assert result.gallery_meta.organizations == ["尤蜜荟"]
    assert result.gallery_meta.models == ["李妍曦"]


def test_parse_image_urls_extracts_multiple_people_by_role() -> None:
    html = """
    <html>
      <body>
        <div class="gallery_nav">
          <div class="gallery_renwu">
            <a><div class="gallery_chuangzuo">机构</div></a>
            <div class="gallery_renwu_title"><a>机构A</a></div>
          </div>
          <div class="gallery_renwu">
            <a><div class="gallery_chuangzuo">机构</div></a>
            <div class="gallery_renwu_title"><a>机构B</a></div>
          </div>
          <div class="gallery_renwu">
            <a><div class="gallery_chujing">模特</div></a>
            <div class="gallery_renwu_title"><a>模特A</a></div>
          </div>
          <div class="gallery_renwu">
            <a><div class="gallery_chujing">模特</div></a>
            <div class="gallery_renwu_title"><a>模特B</a></div>
          </div>
        </div>
        <div class="gallerypic"><img src="/img/001.jpg" /></div>
      </body>
    </html>
    """
    result = parse_image_urls(html, "https://site.example/gallery/9.html", "div.gallerypic img")
    assert result.gallery_meta.organizations == ["机构A", "机构B"]
    assert result.gallery_meta.models == ["模特A", "模特B"]
