---
phase: 04-knowledge-enrichment-zhihu
plan: 03
type: execute
wave: 2
depends_on: [04-00, 04-01]
files_modified:
  - enrichment/fetch_zhihu.py
  - tests/unit/test_fetch_zhihu.py
autonomous: true
requirements: [D-03, D-15]
must_haves:
  truths:
    - "enrichment/fetch_zhihu.py fetches a Zhihu answer URL and returns a cleaned markdown + image list"
    - "CLI: python -m enrichment.fetch_zhihu <zhihu_url> --hash <wechat_hash> --q-idx <N>"
    - "Writes $ENRICHMENT_DIR/<hash>/<q_idx>/zhihu.md + images/ via image_pipeline"
    - "Filters images with width < 100px (PRD §6.2)"
    - "Emits single-line JSON summary on stdout (D-03 contract)"
    - "Reuses existing CDP connection approach from ingest_wechat.py"
  artifacts:
    - path: "enrichment/fetch_zhihu.py"
      provides: "Zhihu answer fetcher + markdown extractor"
      exports: ["fetch_zhihu", "main"]
      min_lines: 100
    - path: "tests/unit/test_fetch_zhihu.py"
      provides: "Unit tests: parser, image filter, stdout contract, image namespacing"
      min_lines: 80
  key_links:
    - from: "enrichment/fetch_zhihu.py"
      to: "image_pipeline.download_images + describe_images"
      via: "module import"
      pattern: "from image_pipeline import"
    - from: "enrichment/fetch_zhihu.py"
      to: "$ENRICHMENT_DIR/<hash>/<q_idx>/zhihu.md"
      via: "save_markdown_with_images"
      pattern: "save_markdown_with_images"
---

<objective>
Build the Zhihu answer fetcher: given a Zhihu URL (from the `zhihu-haowen-enrich`
skill), fetch the page via CDP, extract the main answer body as markdown,
download and describe images, and write everything to a per-question
subdirectory under `$ENRICHMENT_DIR/<hash>/<q_idx>/`.

Purpose: This is the second Python helper the top-level Hermes skill calls.
One invocation per question, in sequence per D-02.

Output: `enrichment/fetch_zhihu.py` with a CLI entry point, reusing
`image_pipeline.py` from plan 01 for all image work. Unit tests for parser and
image filter.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-00-SUMMARY.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-01-SUMMARY.md
@ingest_wechat.py
@image_pipeline.py

<interfaces>
From image_pipeline (plan 01):

```python
def download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]
def describe_images(paths: list[Path]) -> dict[Path, str]
def localize_markdown(md, url_to_local, base_url="http://localhost:8765", article_hash="") -> str
def save_markdown_with_images(md: str, dest_dir: Path, metadata: dict) -> tuple[Path, Path]
```

From ingest_wechat.py: CDP connection pattern uses `playwright.connect_over_cdp(CDP_URL)`.
The MCP variant uses `_MCPClient` for URLs ending in `/mcp`.

PRD §6.2 image filter: skip images with width < 100px (author-icons, emoji, etc.)

**Zhihu CDN URL normalization:** Zhihu images use CDN format
`https://picX.zhimg.com/v2-{md5}_{size}.jpg`. Strip the `_{size}` suffix
(e.g., `_1440w`, `_250x0`) to request the full-resolution original. Then
download via `image_pipeline.download_images()`. CDN requires no
authentication or Referer header — direct HTTP GET works.

D-03 stdout contract for fetch_zhihu:
```
{"hash": "<wechat_hash>", "q_idx": <N>, "status": "ok", "md_path": "...", "image_count": N}
```
or error / skipped variants matching plan 02.

Zhihu URL shapes:
- `zhihu.com/question/<qid>/answer/<aid>`
- `zhuanlan.zhihu.com/p/<pid>`

For the Phase-4 Wave-2 unit tier, use saved Zhihu HTML fixtures (from
`tests/fixtures/sample_zhihu_page.html`) and mock CDP — live Zhihu calls happen
in the integration tier and the Hermes skill body, not here.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 3.1: enrichment/fetch_zhihu.py + unit tests</name>
  <files>enrichment/fetch_zhihu.py, tests/unit/test_fetch_zhihu.py</files>
  <read_first>
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §5 (CDP patterns) and §7 (image pipeline reuse)
    - image_pipeline.py (just-created API surface)
    - ingest_wechat.py lines 320-500 (`scrape_wechat_cdp` pattern — connect_over_cdp, new_page, content, close)
    - tests/fixtures/sample_zhihu_page.html (fixture shape)
  </read_first>
  <behavior>
    - Given a Zhihu URL and saved HTML fixture, parser extracts main answer body.
    - Images with width < 100px filtered out (per PRD §6.2).
    - Output path: `$ENRICHMENT_DIR/<hash>/<q_idx>/zhihu.md` + `$ENRICHMENT_DIR/<hash>/<q_idx>/images/<i>.jpg`.
    - Localized image URLs use pattern `http://localhost:8765/<hash>/zhihu_<q_idx>/<i>.jpg` (D-13 image namespacing — avoid collision with WeChat images).
    - CLI emits single-line JSON on stdout (<50KB per D-03).
    - CDP fetch is mocked in unit tests via dependency-injected fetcher callable.
  </behavior>
  <action>
    Create `enrichment/fetch_zhihu.py`:

    ```python
    """Fetch a Zhihu answer URL, extract markdown + images, write to disk.

    Part of Phase 4 enrichment pipeline. Called by the Hermes `enrich_article`
    skill once per question, after `/zhihu-haowen-enrich` yields a best-source URL.

    CLI:
        python -m enrichment.fetch_zhihu <url> --hash <wechat_hash> --q-idx <N>

    Design note: HTML fetch is pluggable (default uses Playwright CDP). For
    unit tests, callers pass a `html_fetcher` callable that returns the HTML
    string directly, bypassing CDP.
    """
    from __future__ import annotations

    import argparse
    import asyncio
    import json
    import logging
    import os
    import re
    import sys
    from pathlib import Path
    from typing import Awaitable, Callable

    from bs4 import BeautifulSoup
    import html2text

    from image_pipeline import (
        download_images, describe_images, localize_markdown, save_markdown_with_images,
    )

    logger = logging.getLogger(__name__)

    DEFAULT_BASE_DIR = Path(os.environ.get(
        "ENRICHMENT_DIR",
        str(Path.home() / ".hermes" / "omonigraph-vault" / "enrichment"),
    ))
    DEFAULT_TIMEOUT = int(os.environ.get("ENRICHMENT_ZHIHU_FETCH_TIMEOUT", "60"))
    DEFAULT_CDP_URL = os.environ.get("CDP_URL", "http://localhost:9223")
    MIN_IMAGE_WIDTH_PX = 100  # PRD §6.2


    # ───────────────────── HTML → Markdown ─────────────────────

    def _extract_main_content_html(raw_html: str) -> str:
        """Return the inner HTML of the main Zhihu answer body, or the whole
        document if the expected container is absent."""
        soup = BeautifulSoup(raw_html, "html.parser")
        # Zhihu answer body (both answer pages and zhuanlan)
        for selector in [".RichContent-inner", ".RichText", "article"]:
            node = soup.select_one(selector)
            if node:
                return str(node)
        return raw_html


    def _filter_small_images(html: str, min_width: int = MIN_IMAGE_WIDTH_PX) -> tuple[str, list[str]]:
        """Remove <img> tags with explicit width < min_width. Return (cleaned_html, kept_urls)."""
        soup = BeautifulSoup(html, "html.parser")
        kept = []
        for img in soup.find_all("img"):
            width = img.get("width") or img.get("data-width") or ""
            try:
                w = int(str(width).replace("px", "").strip())
            except (ValueError, TypeError):
                w = None
            if w is not None and w < min_width:
                img.decompose()
                continue
            src = img.get("data-original") or img.get("src") or ""
            if src.startswith("http"):
                kept.append(src)
        return str(soup), kept


    def html_to_markdown(raw_html: str) -> tuple[str, list[str]]:
        """Extract main content, filter small images, convert to markdown.
        Returns (markdown, kept_image_urls)."""
        main_html = _extract_main_content_html(raw_html)
        filtered_html, image_urls = _filter_small_images(main_html)
        h2t = html2text.HTML2Text()
        h2t.ignore_links = False
        return h2t.handle(filtered_html), image_urls


    # ───────────────────── Default CDP fetcher ─────────────────────

    async def _default_cdp_fetch(url: str, cdp_url: str = DEFAULT_CDP_URL,
                                 timeout_s: int = DEFAULT_TIMEOUT) -> str:
        """Real Playwright-CDP fetcher. Tests inject a stub instead."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(cdp_url)
            try:
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = await context.new_page()
                await page.goto(url, timeout=timeout_s * 1000)
                await page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
                return await page.content()
            finally:
                await browser.close()


    # ───────────────────── Main orchestration ─────────────────────

    async def fetch_zhihu(
        url: str,
        wechat_hash: str,
        q_idx: int,
        base_dir: Path = DEFAULT_BASE_DIR,
        html_fetcher: Callable[[str], Awaitable[str]] | None = None,
    ) -> dict:
        """Fetch a Zhihu URL, extract + describe images, write artifacts.

        Returns summary dict matching the stdout contract.
        """
        fetcher = html_fetcher or _default_cdp_fetch
        raw_html = await fetcher(url)
        md, image_urls = html_to_markdown(raw_html)

        out_dir = base_dir / wechat_hash / str(q_idx)
        images_dir = out_dir / "images"

        url_to_path = download_images(image_urls, images_dir)
        descriptions = describe_images(list(url_to_path.values()))

        # Namespace zhihu images under <hash>/zhihu_<q_idx>/<i>.jpg
        ns_hash = f"{wechat_hash}/zhihu_{q_idx}"
        md = localize_markdown(md, url_to_path, article_hash=ns_hash)

        # Append image reference blocks (match WeChat convention)
        processed = []
        for i, (src, path) in enumerate(url_to_path.items()):
            desc = descriptions.get(path, "")
            local_url = f"http://localhost:8765/{ns_hash}/{path.name}"
            md += f"\n\n[Image {i} Reference]: {local_url}\n[Image {i} Description]: {desc}\n"
            processed.append({"index": i, "description": desc, "local_url": local_url, "src": src})

        save_markdown_with_images(md, out_dir, {
            "url": url,
            "wechat_hash": wechat_hash,
            "q_idx": q_idx,
            "images": processed,
        })

        return {
            "hash": wechat_hash,
            "q_idx": q_idx,
            "status": "ok",
            "md_path": str(out_dir / "final_content.md"),
            "image_count": len(processed),
        }


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser()
        parser.add_argument("url", help="Zhihu answer URL")
        parser.add_argument("--hash", required=True, help="Parent WeChat article hash")
        parser.add_argument("--q-idx", type=int, required=True, help="Question index (0, 1, 2)")
        parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
        args = parser.parse_args(argv)

        try:
            summary = asyncio.run(fetch_zhihu(
                args.url, args.hash, args.q_idx, base_dir=Path(args.base_dir),
            ))
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({"hash": args.hash, "q_idx": args.q_idx,
                              "status": "error", "error": str(e)}))
            return 1

        print(json.dumps(summary))
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Create `tests/unit/test_fetch_zhihu.py`:

    ```python
    """Unit tests for enrichment.fetch_zhihu."""
    from __future__ import annotations
    import asyncio
    import json
    from pathlib import Path
    from unittest.mock import MagicMock
    import pytest
    from enrichment.fetch_zhihu import (
        fetch_zhihu, html_to_markdown, _filter_small_images, main,
    )


    @pytest.fixture(autouse=True)
    def _set_gemini_key(monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test")


    @pytest.mark.unit
    def test_small_image_filter_drops_sub_100px():
        html = """
            <div>
              <img src="http://a/big.jpg" width="400"/>
              <img src="http://b/small.jpg" width="50"/>
              <img src="http://c/unknown.jpg"/>
            </div>
        """
        cleaned, kept = _filter_small_images(html, min_width=100)
        assert "http://a/big.jpg" in kept
        assert "http://c/unknown.jpg" in kept   # no explicit width → keep
        assert "http://b/small.jpg" not in kept
        assert "small.jpg" not in cleaned


    @pytest.mark.unit
    def test_html_to_markdown_extracts_rich_content():
        html = '<html><body><div class="RichContent-inner"><p>Hello world</p></div><footer>ads</footer></body></html>'
        md, urls = html_to_markdown(html)
        assert "Hello world" in md
        assert "ads" not in md
        assert urls == []


    @pytest.mark.unit
    def test_fetch_zhihu_writes_expected_artifacts(tmp_path: Path, mocker):
        """End-to-end with mocked HTML fetcher + mocked image pipeline deps."""
        html_fixture = (Path(__file__).parent.parent / "fixtures" / "sample_zhihu_page.html").read_text(encoding="utf-8")

        async def fake_fetch(url): return html_fixture

        # Mock the Gemini describe + requests.get so no network touched
        mocker.patch("image_pipeline.requests.get", return_value=MagicMock(status_code=200, content=b"JPEG"))
        mocker.patch("image_pipeline.time.sleep")
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value.text = "stub description"
        mocker.patch("image_pipeline.genai.Client", return_value=mock_client)
        mocker.patch("image_pipeline.Image.open", return_value=MagicMock())

        summary = asyncio.run(fetch_zhihu(
            "https://zhihu.com/question/1/answer/2",
            wechat_hash="abc123",
            q_idx=0,
            base_dir=tmp_path,
            html_fetcher=fake_fetch,
        ))
        assert summary["status"] == "ok"
        assert summary["hash"] == "abc123"
        assert summary["q_idx"] == 0

        out_dir = tmp_path / "abc123" / "0"
        assert (out_dir / "final_content.md").exists()
        assert (out_dir / "metadata.json").exists()
        meta = json.loads((out_dir / "metadata.json").read_text(encoding="utf-8"))
        assert meta["wechat_hash"] == "abc123"
        assert meta["q_idx"] == 0


    @pytest.mark.unit
    def test_fetch_zhihu_image_namespacing(tmp_path: Path, mocker):
        """Images URLs in the enriched MD must use `<hash>/zhihu_<q_idx>/` prefix
        to avoid collision with WeChat images sharing the same <hash>."""
        html = '<div class="RichContent-inner"><img src="http://x/a.jpg" width="300"/></div>'
        async def fake_fetch(url): return html
        mocker.patch("image_pipeline.requests.get", return_value=MagicMock(status_code=200, content=b"JPEG"))
        mocker.patch("image_pipeline.time.sleep")
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value.text = "desc"
        mocker.patch("image_pipeline.genai.Client", return_value=mock_client)
        mocker.patch("image_pipeline.Image.open", return_value=MagicMock())

        asyncio.run(fetch_zhihu(
            "https://zhihu.com/q/1/a/2", wechat_hash="hh", q_idx=1,
            base_dir=tmp_path, html_fetcher=fake_fetch,
        ))
        md = (tmp_path / "hh" / "1" / "final_content.md").read_text(encoding="utf-8")
        # Must namespace under hh/zhihu_1/, not bare hh/
        assert "http://localhost:8765/hh/zhihu_1/0.jpg" in md
        assert "http://localhost:8765/hh/0.jpg" not in md


    @pytest.mark.unit
    def test_cli_error_path_returns_1(tmp_path: Path, mocker, capsys):
        mocker.patch("enrichment.fetch_zhihu._default_cdp_fetch",
                     side_effect=RuntimeError("cdp down"))
        rc = main(["https://zhihu.com/q/1/a/2", "--hash", "h", "--q-idx", "0",
                   "--base-dir", str(tmp_path)])
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["status"] == "error"
        assert "cdp down" in out["error"]


    @pytest.mark.unit
    def test_cli_stdout_under_50kb(tmp_path: Path, mocker, capsys):
        """D-03 stdout cap."""
        mocker.patch("enrichment.fetch_zhihu._default_cdp_fetch",
                     side_effect=RuntimeError("x"))
        main(["https://zhihu.com/q/1/a/2", "--hash", "h", "--q-idx", "0",
              "--base-dir", str(tmp_path)])
        line = capsys.readouterr().out.strip()
        assert len(line.encode("utf-8")) < 50000
        assert "\n" not in line
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/test_fetch_zhihu.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - File `enrichment/fetch_zhihu.py` exists and is importable
    - `grep -q "from image_pipeline import" enrichment/fetch_zhihu.py` succeeds
    - `grep -q "MIN_IMAGE_WIDTH_PX = 100" enrichment/fetch_zhihu.py` succeeds
    - `grep -q "def fetch_zhihu" enrichment/fetch_zhihu.py` succeeds
    - `grep -q "def main" enrichment/fetch_zhihu.py` succeeds
    - `grep -q "zhihu_" enrichment/fetch_zhihu.py` succeeds (image namespacing prefix present)
    - `grep -q "html_fetcher" enrichment/fetch_zhihu.py` succeeds (DI seam for testing)
    - `pytest tests/unit/test_fetch_zhihu.py -x -v` exits 0 with all 6 tests passing
    - `python -m enrichment.fetch_zhihu --help` exits 0
  </acceptance_criteria>
  <done>fetch_zhihu module complete; 6 unit tests pass; CLI entry point works</done>
</task>

</tasks>

<verification>
  - `pytest tests/unit/test_fetch_zhihu.py -x -v` green
  - `python -m enrichment.fetch_zhihu --help` returns usage
  - No direct overlap with image_pipeline code — all image work goes through the shared module
</verification>

<success_criteria>
- fetch_zhihu reuses image_pipeline (no duplicated image logic)
- Small-image filter enforces PRD §6.2 threshold
- D-03 stdout contract respected (single-line JSON, <50KB)
- Image URL namespacing prevents collision with WeChat images
- 6 unit tests green
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-03-SUMMARY.md`.
</output>
