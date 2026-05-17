"""kb-v2.1-8-quick (260516-img) — preserve WeChat lazy-load image inline positions.

Pure unit tests on process_content() in ingest_wechat.py with synthetic HTML
fixtures. No network; no DB; no fixtures-from-disk. Tests assert on the
substring + ordering of the markdown output and on the contents of the
collected image-URL list.

WeChat lazy-load pattern under test:
    <img data-src="<real-url>" src="data:image/svg+xml,...placeholder">

Pre-fix, html2text saw only the data-URI placeholder in src and produced
unusable ``![](data:...)`` markdown — losing the real URL AND its inline
position. Post-fix, BeautifulSoup mutates ``img['src'] = data-src`` (when
src is missing or a data-URI) BEFORE handing the soup to html2text,
preserving inline ``![](real-url)`` markdown.
"""
import re

from ingest_wechat import process_content


def test_data_src_promoted_when_src_is_data_uri_placeholder():
    """data-src real URL replaces data-URI placeholder src."""
    html = (
        '<p>before</p>'
        '<img data-src="https://mmbiz.qpic.cn/foo.jpg" '
        'src="data:image/svg+xml,...placeholder"/>'
        '<p>after</p>'
    )
    md, imgs = process_content(html)
    assert "![](https://mmbiz.qpic.cn/foo.jpg)" in md
    assert "data:image/svg+xml" not in md
    assert imgs == ["https://mmbiz.qpic.cn/foo.jpg"]


def test_data_src_used_when_src_missing():
    """data-src promoted when no src attribute exists at all."""
    html = '<p>x</p><img data-src="https://x.jpg"/><p>y</p>'
    md, imgs = process_content(html)
    assert "![](https://x.jpg)" in md
    assert imgs == ["https://x.jpg"]


def test_valid_src_preserved_unchanged_no_data_src():
    """Regression guard: a valid http(s) src with no data-src is untouched."""
    html = '<p>x</p><img src="https://valid.com/img.jpg"/><p>y</p>'
    md, imgs = process_content(html)
    assert "![](https://valid.com/img.jpg)" in md
    assert imgs == ["https://valid.com/img.jpg"]


def test_valid_src_not_overwritten_by_data_src():
    """Regression guard: valid http(s) src wins over a competing data-src."""
    html = (
        '<p>x</p>'
        '<img src="https://valid.com/a.jpg" data-src="https://other.com/b.jpg"/>'
        '<p>y</p>'
    )
    md, imgs = process_content(html)
    assert "![](https://valid.com/a.jpg)" in md
    assert "https://other.com/b.jpg" not in md
    # data-src is still collected as a *fallback* only when src is absent;
    # here src is valid, so the collected URL must be src, not data-src.
    assert imgs == ["https://valid.com/a.jpg"]


def test_multi_image_article_inline_positions_preserved():
    """3-image WeChat-style article: inline ``![](url)`` interleaved with paragraphs."""
    html = (
        '<article>'
        '<p>Para A.</p>'
        '<p><img data-src="https://mmbiz.qpic.cn/img1.jpg" '
        'src="data:image/svg+xml,placeholder"/></p>'
        '<p>Para B.</p>'
        '<p><img data-src="https://mmbiz.qpic.cn/img2.jpg" '
        'src="data:image/svg+xml,placeholder"/></p>'
        '<p>Para C.</p>'
        '<p><img data-src="https://mmbiz.qpic.cn/img3.jpg" '
        'src="data:image/svg+xml,placeholder"/></p>'
        '</article>'
    )
    md, imgs = process_content(html)

    # 3 inline image markdown links produced
    inline_count = len(re.findall(r"!\[.*?\]\(https://mmbiz\.qpic\.cn/img\d\.jpg\)", md))
    assert inline_count == 3, f"expected 3 inline image links, got {inline_count}\n{md}"

    # Each image is collected
    assert imgs == [
        "https://mmbiz.qpic.cn/img1.jpg",
        "https://mmbiz.qpic.cn/img2.jpg",
        "https://mmbiz.qpic.cn/img3.jpg",
    ]

    # Inline order: Para A → img1 → Para B → img2 → Para C → img3
    pos_para_a = md.index("Para A.")
    pos_img1 = md.index("https://mmbiz.qpic.cn/img1.jpg")
    pos_para_b = md.index("Para B.")
    pos_img2 = md.index("https://mmbiz.qpic.cn/img2.jpg")
    pos_para_c = md.index("Para C.")
    pos_img3 = md.index("https://mmbiz.qpic.cn/img3.jpg")
    assert pos_para_a < pos_img1 < pos_para_b < pos_img2 < pos_para_c < pos_img3


def test_idempotent_on_already_fixed_html():
    """Re-running on already-valid src is a no-op (output identical)."""
    fixed_html = '<p>x</p><img src="https://mmbiz.qpic.cn/foo.jpg"/><p>y</p>'
    md1, imgs1 = process_content(fixed_html)
    md2, imgs2 = process_content(fixed_html)
    assert md1 == md2
    assert imgs1 == imgs2
    assert "![](https://mmbiz.qpic.cn/foo.jpg)" in md1


def test_relative_src_not_collected_in_images_list():
    """Regression guard: only http(s) URLs collected for download, not relative paths."""
    html = '<p>x</p><img src="/relative/path.jpg"/><p>y</p>'
    md, imgs = process_content(html)
    assert imgs == []
    # Markdown still emits the relative reference (html2text behavior preserved);
    # this test asserts only that the image-URL collection list is empty.
