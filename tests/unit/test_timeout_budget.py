"""TIMEOUT-03: _compute_article_budget_s formula (D-09.03).

Pure-unit tests — no imports of heavy modules (lightrag, etc.). Verifies
formula is correct per PRD § TIMEOUT-03.

Formula: ``max(120 + 30 * chunk_count, 900)`` where
``chunk_count = max(1, len(full_content) // 4800)``.
"""
from __future__ import annotations


def _budget(content: str) -> int:
    # Import inside the test so a missing _compute_article_budget_s surfaces
    # as an AssertionError-shaped ImportError at call time, not collection time.
    from batch_ingest_from_spider import _compute_article_budget_s
    return _compute_article_budget_s(content)


def test_floor_for_empty_content() -> None:
    """Empty content -> chunk_count=1 -> max(120+30, 900) == 900."""
    assert _budget("") == 900


def test_floor_for_small_article() -> None:
    """Small article (<1 chunk_size) -> chunk_count=1 -> floor."""
    assert _budget("x" * 1000) == 900


def test_floor_for_mid_size() -> None:
    """20 chunks -> 120 + 600 = 720; below floor -> 900."""
    # 20 * 4800 = 96,000 chars
    assert _budget("x" * 96_000) == 900


def test_scales_above_floor() -> None:
    """50 chunks -> 120 + 1500 = 1620; above floor -> 1620."""
    # 50 * 4800 = 240,000 chars
    assert _budget("x" * 240_000) == 1620


def test_large_article() -> None:
    """100 chunks -> 120 + 3000 = 3120; above floor -> 3120."""
    # 100 * 4800 = 480,000 chars
    assert _budget("x" * 480_000) == 3120


def test_chunk_count_is_floored_at_1() -> None:
    """Content shorter than chunk_size still counts as 1 chunk."""
    # 1 char -> chunk_count = max(1, 0) = 1 -> 150 budget -> floor 900.
    assert _budget("x") == 900


# T1 (2026-05-13): image-aware budget tests.
# Hermes prod data: 60-image batch avg 24.5s/img; 34-image article = 933s actual.
# Formula: max(120 + 30*chunks + 30*images, 900). No upper cap.

_IMG_TOKEN = "![](https://example.com/img.png)"


def _body_with_images(text_chars: int, image_count: int) -> str:
    """Construct a body with ``text_chars`` of filler + ``image_count`` md image tokens."""
    return ("x" * text_chars) + ("\n" + _IMG_TOKEN) * image_count


def test_zero_images_no_change() -> None:
    """Body with 0 images uses pre-T1 formula. Regression guard."""
    # 50 chunks → 120 + 1500 + 0 = 1620 (matches pre-T1 test_scales_above_floor)
    assert _budget("x" * 240_000) == 1620


def test_few_images_under_floor() -> None:
    """5 images + small text → still hits 900s floor (no scale up)."""
    # 5 images × 30s = 150s. text=150 (1 chunk). total=300. max(300, 900) = 900.
    assert _budget(_body_with_images(1000, 5)) == 900


def test_34_image_article_covers_hermes_failure() -> None:
    """Hermes 2026-05-13 failure case: 34 images, ~10k body, took 933s actual.

    Pre-T1: max(120 + 30*2, 900) = 900 → timeout.
    Post-T1: max(120 + 60 + 34*30, 900) = max(1200, 900) = 1200 → covers 933s.
    """
    body = _body_with_images(10_000, 34)
    assert _budget(body) >= 1200, f"34-image budget too tight: {_budget(body)}"


def test_51_image_article_post_fix() -> None:
    """Original failed article: 51 images, ~10k body. Pre-T1 = 900, Post-T1 ≥ 1500."""
    body = _body_with_images(10_000, 51)
    expected = 120 + 30 * max(1, len(body) // 4800) + 30 * 51
    assert _budget(body) == max(expected, 900)
    assert _budget(body) >= 1500, "51-image article must have headroom above 900s floor"


def test_no_upper_cap_text_heavy() -> None:
    """100 chunks (text-only) → 3120s budget, no cap. Regression of pre-T1 behavior."""
    assert _budget("x" * 480_000) == 3120


def test_image_only_no_text_scaling() -> None:
    """0-chunk text + 30 images → max(120+30+900, 900) = 1050, no underflow."""
    body = _body_with_images(0, 30)
    # text term: 1 chunk → 150. image: 30*30 = 900. total: 1050. max(1050, 900) = 1050.
    assert _budget(body) == 1050


# T1-b1 (issue #2): disk fallback when body has no markdown image markers.
# WeChat post-vision-description bodies have ![](...)  stripped — regex
# returns 0. For re-ingestion paths the previous scrape left files under
# images/{md5(url)[:10]}/ on disk; the disk count is the source of truth.
# Note: fresh-article path (no prior scrape) gets disk_count=0 too — that's
# a known limitation deferred to v1.0.y (D2 schema column or post-scrape
# budget rerouting).

def test_disk_fallback_url_none_returns_zero(tmp_path, monkeypatch) -> None:
    """No url provided → no disk lookup → regex-only behavior."""
    from batch_ingest_from_spider import _count_images_in_body
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    # Empty body, no url. Disk lookup not attempted.
    assert _count_images_in_body("", url=None) == 0


def test_disk_fallback_missing_dir_returns_zero(tmp_path, monkeypatch) -> None:
    """url given but images/{hash}/ dir doesn't exist → 0 (fresh-article case)."""
    from batch_ingest_from_spider import _count_images_in_body
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    assert _count_images_in_body("", url="https://example.com/fresh") == 0


def test_disk_fallback_counts_image_files(tmp_path, monkeypatch) -> None:
    """url + body-no-markers + disk has 5 jpgs → returns 5."""
    import hashlib
    from batch_ingest_from_spider import _count_images_in_body

    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    url = "https://mp.weixin.qq.com/s/test123"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    # 5 image files + 1 non-image (should be ignored)
    for i in range(1, 6):
        (img_dir / f"{i}.jpg").write_bytes(b"fake")
    (img_dir / "metadata.json").write_text("{}")
    assert _count_images_in_body("body without image markers", url=url) == 5


def test_disk_fallback_mixed_extensions(tmp_path, monkeypatch) -> None:
    """Counts jpg/jpeg/png/webp/gif uniformly; ignores .json/.txt/etc."""
    import hashlib
    from batch_ingest_from_spider import _count_images_in_body

    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    url = "https://example.com/mixed"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    (img_dir / "1.jpg").write_bytes(b"")
    (img_dir / "2.JPG").write_bytes(b"")  # case insensitive ext
    (img_dir / "3.png").write_bytes(b"")
    (img_dir / "4.webp").write_bytes(b"")
    (img_dir / "5.gif").write_bytes(b"")
    (img_dir / "manifest.json").write_text("{}")
    (img_dir / "log.txt").write_text("")
    assert _count_images_in_body("", url=url) == 5


def test_regex_takes_precedence_over_disk(tmp_path, monkeypatch) -> None:
    """When body has markdown markers, regex wins (cheaper, source of truth for fresh).

    This protects the canonical RSS path where body retains ``![](...)`` —
    we should NOT silently fall back to disk if the body told us already.
    """
    import hashlib
    from batch_ingest_from_spider import _count_images_in_body

    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    url = "https://example.com/regex-wins"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    # Disk has 10 files...
    for i in range(1, 11):
        (img_dir / f"{i}.jpg").write_bytes(b"")
    # ...but body says 3 markdown images. Regex wins.
    body = "text " + ("\n" + _IMG_TOKEN) * 3
    assert _count_images_in_body(body, url=url) == 3


def test_compute_article_budget_with_url_kwarg(tmp_path, monkeypatch) -> None:
    """End-to-end: body has no markers, disk has 34 files → budget = max(120+30+34*30, 900) = 1200."""
    import hashlib
    from batch_ingest_from_spider import _compute_article_budget_s

    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    url = "https://mp.weixin.qq.com/s/issue2"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    for i in range(1, 35):
        (img_dir / f"{i}.jpg").write_bytes(b"")
    # Body: 1k chars (1 chunk), no image markers — same shape as Hermes id=65 case.
    body = "x" * 1000
    # text=120+30*1=150, image=34*30=1020, total=1170, max(1170, 900)=1170.
    assert _compute_article_budget_s(body, url=url) == 1170


def test_compute_article_budget_url_optional_back_compat(tmp_path) -> None:
    """url= kwarg defaults to None → disk lookup skipped → pre-T1-b1 behavior preserved."""
    from batch_ingest_from_spider import _compute_article_budget_s
    # No monkeypatch needed: url=None means disk path never accessed.
    body = _body_with_images(10_000, 34)
    # Regex finds 34 images → budget scales as before T1-b1.
    assert _compute_article_budget_s(body) >= 1200


def test_drain_layer2_queue_call_site_uses_dynamic_budget() -> None:
    """2026-05-08 regression: per-article timeout in _drain_layer2_queue
    MUST compute budget from body length, not hardcode _SINGLE_CHUNK_FLOOR_S.

    Pre-fix:
        effective_timeout = clamp_article_timeout(
            _SINGLE_CHUNK_FLOOR_S, remaining, BATCH_SAFETY_MARGIN_S
        )
    → 50-chunk articles (~1620s real need) all hit 900s timeout.

    Post-fix:
        article_budget = _compute_article_budget_s(body or "")
        effective_timeout = clamp_article_timeout(
            article_budget, remaining, BATCH_SAFETY_MARGIN_S
        )
    """
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent.parent / "batch_ingest_from_spider.py"
    content = src.read_text(encoding="utf-8")

    # Locate _drain_layer2_queue body
    drain_marker = "async def _drain_layer2_queue"
    drain_start = content.index(drain_marker)
    # End at the for-loop that starts the candidate iteration
    drain_end = content.index("iterate over candidate_rows", drain_start)
    drain_body = content[drain_start:drain_end]

    # Must call _compute_article_budget_s on the body
    assert "_compute_article_budget_s(body" in drain_body, (
        "_drain_layer2_queue must compute article budget from body length. "
        "Without this, large articles (50+ chunks) timeout at hardcoded 900s. "
        "See 2026-05-08 Hermes manual smoke (3/3 large articles failed)."
    )

    # Must NOT pass _SINGLE_CHUNK_FLOOR_S literal as the timeout arg to
    # clamp_article_timeout (the bug we just fixed). The constant may still
    # appear elsewhere as the formula's floor — that's fine.
    # Specifically check the clamp_article_timeout call uses article_budget.
    clamp_call_idx = drain_body.index("clamp_article_timeout(")
    # Read the next ~100 chars after the call opening
    clamp_call_snippet = drain_body[clamp_call_idx:clamp_call_idx + 200]
    assert "article_budget" in clamp_call_snippet, (
        "clamp_article_timeout in _drain_layer2_queue must receive "
        "article_budget (dynamic), not _SINGLE_CHUNK_FLOOR_S (hardcoded 900s)."
    )


# D2 (issue #2 follow-up): image_count kwarg takes priority over regex+disk.
# Hermes 2026-05-13 design review: scrape time persists len(manifest), the
# budget call reads it directly to avoid the body-stripped fresh-cron gap.

def test_image_count_kwarg_takes_precedence_over_regex() -> None:
    """Kwarg image_count=34 wins even when body has 5 markdown image markers."""
    from batch_ingest_from_spider import _compute_article_budget_s
    body = ("x" * 1000) + ("\n" + _IMG_TOKEN) * 5
    # If kwarg ignored: 1 chunk + 5 images = 120+30+150 = 300 -> floor 900
    # If kwarg honored: 1 chunk + 34 images = 120+30+1020 = 1170
    assert _compute_article_budget_s(body, image_count=34) == 1170


def test_image_count_kwarg_takes_precedence_over_disk(tmp_path, monkeypatch) -> None:
    """Kwarg image_count wins over T1-b1 disk count (md5 hash dir).

    Discriminating value: kwarg=50 makes total cleanly escape the 900s floor.
    If disk path used:    1 chunk + 10 images = 120+30+300 = 450 -> floor 900 (would NOT match 1650)
    If kwarg=50 honored:  1 chunk + 50 images = 120+30+1500 = 1650 (escapes floor cleanly)
    """
    import hashlib
    from batch_ingest_from_spider import _compute_article_budget_s
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(tmp_path))
    url = "https://example.com/kwarg-vs-disk"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    img_dir = tmp_path / "images" / h
    img_dir.mkdir(parents=True)
    for i in range(1, 11):
        (img_dir / f"{i}.jpg").write_bytes(b"")
    # body empty (1 chunk via max(1, ...)), disk has 10 jpgs.
    # kwarg=50 wins -> budget escapes floor -> asserts the discriminating shape.
    assert _compute_article_budget_s("", url=url, image_count=50) == 1650


def test_image_count_zero_falls_back_to_regex_disk() -> None:
    """2026-05-16 fix (260516-stl): kwarg=0 must fall back to regex/disk.

    Original semantic (`>= 0`) treated explicit 0 as authoritative — but for
    FRESH articles scanned today, articles.image_count=0 in DB at SELECT time
    even when scrape later downloads images. The 0 is STALE, not authoritative.

    By falling back to regex on the post-scrape body (which has accurate
    markdown markers from html2text), image-heavy fresh articles get correct
    budget instead of being capped at 900s floor.

    Body: 50 chunks + 51 markers. With kwarg=0 falling back, regex finds 51:
      120 + 30·50 + 30·51 = 3150.
    Same as kwarg=None default. Both must equal — proves kwarg=0 is no
    longer special-cased.
    """
    from batch_ingest_from_spider import _compute_article_budget_s
    body = ("x" * 240_000) + ("\n" + _IMG_TOKEN) * 51
    # kwarg=0 NOW falls back to regex(51) -> 3150 (was 1620 pre-fix)
    assert _compute_article_budget_s(body, image_count=0) == 3150
    # And matches kwarg=None (both go through fallback)
    assert _compute_article_budget_s(body, image_count=0) == _compute_article_budget_s(body)


def test_d2_fresh_article_stale_zero_falls_back() -> None:
    """REGRESSION 260516-stl: id=418 scenario — fresh article scanned today.

    DB articles.image_count=0 (DEFAULT for new row, scrape pipeline doesn't
    populate it before SELECT runs). Body has 54 markdown image markers
    after scrape. Pre-fix: budget=900 floor (used stale 0). Post-fix: falls
    back to regex, finds 54, budget = 120 + 30·4 + 30·54 = 1860.

    This regression test pins the exact id=418 case from 2026-05-15 burst
    goal failure: 54 images, 17638 char body (~4 chunks).
    """
    from batch_ingest_from_spider import _compute_article_budget_s
    body = ("x" * 17638) + ("\n" + _IMG_TOKEN) * 54
    actual = _compute_article_budget_s(body, image_count=0)
    # chunks = max(1, len(body) // 4800) = some value > 1
    # text_budget = 120 + 30 * chunks
    # image_budget via fallback regex = 30 * 54 = 1620
    # total = max(text + 1620, 900)
    assert actual > 1500, f"Expected fallback to scale (>1500), got {actual}"
    assert actual > 900, "Must escape 900s floor (the stale-0 bug)"


def test_image_count_none_falls_back_to_regex_or_disk() -> None:
    """Back-compat: image_count=None preserves T1 / T1-b1 regex+disk fallback.

    Old callers that don't pass image_count must keep working. Body with
    51 markers must still scale per pre-D2 formula.
    """
    from batch_ingest_from_spider import _compute_article_budget_s
    body = ("x" * 10_000) + ("\n" + _IMG_TOKEN) * 51
    # Same as test_51_image_article_post_fix: regex finds 51 -> >=1500
    assert _compute_article_budget_s(body, image_count=None) >= 1500


def test_n20_burst_stripped_markers_kwarg_rescue() -> None:
    """REGRESSION 260516-htm: 2026-05-15 N=20 burst id=777 / 939 / 943 / 967 / 1007.

    5 articles timed out at 900s despite having 28-112 images each. Hermes
    DB inspection found:
      - body persisted in DB as markdown (starts with '#  ...') BUT
      - markdown image markers count = 0 (stripped during scrape/persist)
      - HTML <img> tag count = 0 (no raw HTML markers either)
      - image_count column populated AFTER timeout (vision pipeline writes
        it post-fact via ingest_wechat.py:1273)

    At budget compute time (drain queue line 1836), `image_count_row` was
    the stale 0 from the initial SELECT (image_count column written later).
    Both fallback paths returned 0:
      - regex on body markers: 0 (stripped)
      - disk fallback: 0 (images downloaded later inside ingest_article)
    Formula returned 900 floor. ingest_article then ran for >900s on
    28-112 image vision pipeline → outer asyncio.wait_for fired.

    The outer-loop fix (260516-htm) refreshes image_count_row from
    ScrapeResult.images BEFORE queue append. The .images list is the
    pre-strip authoritative count. This test pins the formula-level
    behavior: when image_count kwarg is positive (from refreshed scrape
    data), absence of body markers no longer matters.

    Body shape: 9175 chars markdown WITHOUT ![](...) markers (id=777
    repro). Expected budget: 120 + 30*chunks + 30*70 = 120 + 60 + 2100.
    """
    from batch_ingest_from_spider import _compute_article_budget_s
    body = "# Heading\n\n" + ("x" * 9000) + "\n\n## Section\n"
    assert "![" not in body, "test fixture must have no markdown image markers"
    actual = _compute_article_budget_s(body, image_count=70)
    assert actual >= 2200, f"Expected ~2280s for 70-image article, got {actual}"
