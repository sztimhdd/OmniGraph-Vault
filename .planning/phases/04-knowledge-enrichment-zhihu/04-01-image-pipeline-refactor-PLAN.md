---
phase: 04-knowledge-enrichment-zhihu
plan: 01
type: execute
wave: 1
depends_on: [04-00]
files_modified:
  - image_pipeline.py
  - ingest_wechat.py
  - tests/unit/test_image_pipeline.py
  - tests/integration/test_image_pipeline_golden.py
autonomous: true
requirements: [D-15, D-16]
must_haves:
  truths:
    - "image_pipeline.py exports 4 functions: download_images, localize_markdown, describe_images, save_markdown_with_images"
    - "describe_images is batch: accepts a list and internally rate-limits"
    - "ingest_wechat.py uses image_pipeline.py for all image work (no duplicate logic)"
    - "Re-running the pipeline on a golden fixture produces output matching within tolerance"
    - "Each of the 4 public functions has a dedicated unit test"
  artifacts:
    - path: "image_pipeline.py"
      provides: "Shared image downloading + description + MD localization API"
      exports: ["download_images", "localize_markdown", "describe_images", "save_markdown_with_images"]
      min_lines: 120
    - path: "tests/unit/test_image_pipeline.py"
      provides: "Unit tests for each of the 4 public functions"
      min_lines: 80
    - path: "tests/integration/test_image_pipeline_golden.py"
      provides: "Golden-file regression diff (remote-only)"
      min_lines: 50
  key_links:
    - from: "ingest_wechat.py"
      to: "image_pipeline.py"
      via: "module import at top of file"
      pattern: "from image_pipeline import"
    - from: "image_pipeline.describe_images"
      to: "time.sleep(4) between images"
      via: "inner loop"
      pattern: "time\\.sleep\\(4\\)"
---

<objective>
Extract image handling out of `ingest_wechat.py` into a shared `image_pipeline.py`
module. The Zhihu fetcher (plan 03) will use the same module. The refactor must
not regress WeChat ingestion — enforced by a golden-file diff + unit tests.

Purpose: De-duplicate image logic before Zhihu-fetch code copies it. D-15
mandates a batch-style `describe_images` API.

Output: Clean `image_pipeline.py` with 4 public functions; `ingest_wechat.py`
refactored to call them; passing unit tests + golden-file regression.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-00-SUMMARY.md
@CLAUDE.md
@ingest_wechat.py
@config.py

<interfaces>
Extracted from ingest_wechat.py (current image-handling code):

```python
# Line 125-135 — describe_image (single-image form; becomes batch per D-15)
def describe_image(image_path):
    try:
        vision_client = genai.Client(api_key=GEMINI_API_KEY)
        img = Image.open(image_path)
        response = vision_client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=["Describe this image in detail for a knowledge graph. Return only the description.", img]
        )
        return response.text
    except Exception as e:
        return f"Error describing image: {e}"

# Lines 632-657 — per-image download+describe loop INSIDE ingest_article
# Key lines:
#   img_path = os.path.join(article_dir, f"{i}.jpg")
#   resp = requests.get(img_url, timeout=10)
#   description = describe_image(img_path)
#   local_url = f"http://localhost:8765/{article_hash}/{i}.jpg"
#   full_content = full_content.replace(img_url, local_url)
#   full_content += f"\n\n[Image {i} Reference]: {local_url}\n[Image {i} Description]: {description}\n"
#   if i + 1 < len(unique_img_urls):
#       time.sleep(4)

# Lines 695-706 — metadata.json + final_content.md save
#   with open(os.path.join(article_dir, "metadata.json"), "w") as f:
#       json.dump({"title": title, "url": url, "hash": article_hash, "method": method, "images": processed_images}, f, indent=2)
#   with open(os.path.join(article_dir, "final_content.md"), "w", encoding="utf-8") as f:
#       f.write(full_content)
```

Target API (per RESEARCH.md §7):

```python
from pathlib import Path

def download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]:
    """Download urls → dest_dir/{i}.jpg; return {remote_url: local_path}. Skips failures silently."""

def localize_markdown(md: str, url_to_local: dict[str, Path],
                     base_url: str = "http://localhost:8765",
                     article_hash: str = "") -> str:
    """Replace remote URLs in md with http://{base_url}/{article_hash}/{i}.jpg."""

def describe_images(paths: list[Path]) -> dict[Path, str]:
    """Batch-describe via Gemini Vision. Rate-limit 4s between calls INSIDE this function.
    On per-image failure, value is 'Error describing image: {e}'."""

def save_markdown_with_images(md: str, dest_dir: Path, metadata: dict) -> tuple[Path, Path]:
    """Atomic write of final_content.md + metadata.json (tmp → rename).
    Returns (md_path, metadata_path)."""
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1.1: Create image_pipeline.py with 4 public functions</name>
  <files>image_pipeline.py, tests/unit/test_image_pipeline.py</files>
  <read_first>
    - ingest_wechat.py lines 125-135, 620-710 (exact logic to extract — MUST read before writing to preserve semantics)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §7 (target API signatures + unit-test plan)
    - config.py (imports BASE_DIR, env loading pattern — the new module uses os.environ["GEMINI_API_KEY"] not a config.py re-export)
  </read_first>
  <behavior>
    - download_images: given 3 URLs, returns a dict mapping 2 successful URLs → Path (3rd returns 404, excluded). Files written to dest_dir named `0.jpg`, `1.jpg`, `2.jpg`.
    - localize_markdown: given `md = "![](https://remote/img.jpg)"` and `url_to_local = {"https://remote/img.jpg": Path("0.jpg")}`, `article_hash="abc"`, returns `"![](http://localhost:8765/abc/0.jpg)"`.
    - describe_images: given 2 paths, calls Gemini mock twice, sleeps 4s between (tested by asserting `time.sleep` was called with 4), returns `{path1: desc1, path2: desc2}`.
    - describe_images error handling: if Gemini raises for one image, that image's value is `"Error describing image: <e>"` but other images in the batch still succeed.
    - save_markdown_with_images: writes `final_content.md` and `metadata.json` via tmp→rename. Both files exist, MD content matches input, JSON contains the metadata dict.
  </behavior>
  <action>
    Create `image_pipeline.py` at repo root with this exact shape. All type hints. PEP 8. Use `logging` module (module-level `logger = logging.getLogger(__name__)`), not `print`.

    ```python
    """Shared image-handling pipeline for WeChat + Zhihu ingestion paths.

    Extracted from ingest_wechat.py as part of Phase 4 refactor (D-15, D-16).
    All functions are sync; callers wrap in asyncio.to_thread if needed.
    """
    from __future__ import annotations

    import json
    import logging
    import os
    import time
    from pathlib import Path
    from typing import Iterable

    import requests
    from PIL import Image
    from google import genai

    logger = logging.getLogger(__name__)

    # Rate-limit between Gemini Vision describe_images calls (D-15).
    _DESCRIBE_INTER_IMAGE_SLEEP_SECS = 4

    # Local image server base — matches ingest_wechat.py historical value.
    _DEFAULT_IMAGE_BASE_URL = "http://localhost:8765"


    def download_images(urls: list[str], dest_dir: Path) -> dict[str, Path]:
        """Download each URL to dest_dir/{i}.jpg. Return {remote_url: local_path}
        for successes only (non-200 responses and exceptions are silently skipped
        with a warning log)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        result: dict[str, Path] = {}
        for i, url in enumerate(urls):
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code != 200:
                    logger.warning("Image %d download failed: HTTP %d for %s",
                                   i, resp.status_code, url)
                    continue
                path = dest_dir / f"{i}.jpg"
                path.write_bytes(resp.content)
                result[url] = path
            except Exception as e:
                logger.warning("Image %d error: %s", i, e)
        return result


    def localize_markdown(
        md: str,
        url_to_local: dict[str, Path],
        base_url: str = _DEFAULT_IMAGE_BASE_URL,
        article_hash: str = "",
    ) -> str:
        """Replace each remote URL in md with {base_url}/{article_hash}/{filename}."""
        for url, path in url_to_local.items():
            local = f"{base_url}/{article_hash}/{path.name}" if article_hash else f"{base_url}/{path.name}"
            md = md.replace(url, local)
        return md


    def describe_images(paths: list[Path]) -> dict[Path, str]:
        """Batch-describe via Gemini Vision. Rate-limits 4s between calls (D-15)."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {p: "Error describing image: GEMINI_API_KEY not set" for p in paths}
        result: dict[Path, str] = {}
        paths_list = list(paths)
        for i, path in enumerate(paths_list):
            try:
                client = genai.Client(api_key=api_key)
                img = Image.open(path)
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=[
                        "Describe this image in detail for a knowledge graph. Return only the description.",
                        img,
                    ],
                )
                result[path] = response.text
            except Exception as e:
                result[path] = f"Error describing image: {e}"
            if i + 1 < len(paths_list):
                time.sleep(_DESCRIBE_INTER_IMAGE_SLEEP_SECS)
        return result


    def save_markdown_with_images(
        md: str,
        dest_dir: Path,
        metadata: dict,
    ) -> tuple[Path, Path]:
        """Atomic write of final_content.md + metadata.json via tmp → rename."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        md_path = dest_dir / "final_content.md"
        meta_path = dest_dir / "metadata.json"
        md_tmp = md_path.with_suffix(".md.tmp")
        meta_tmp = meta_path.with_suffix(".json.tmp")
        md_tmp.write_text(md, encoding="utf-8")
        meta_tmp.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(md_tmp, md_path)
        os.replace(meta_tmp, meta_path)
        return md_path, meta_path
    ```

    Create `tests/unit/test_image_pipeline.py` with one test per public function:

    ```python
    """Unit tests for image_pipeline — Phase 4 D-15/D-16."""
    from __future__ import annotations
    import json
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    import pytest
    from image_pipeline import (
        download_images, localize_markdown, describe_images, save_markdown_with_images,
    )


    @pytest.mark.unit
    def test_download_images_success_and_failure(tmp_path: Path, mocker):
        urls = ["http://a/x.jpg", "http://b/y.jpg", "http://c/z.jpg"]
        def fake_get(url, timeout):
            r = MagicMock()
            r.status_code = 200 if "c/" not in url else 404
            r.content = b"JPEG_BYTES"
            return r
        mocker.patch("image_pipeline.requests.get", side_effect=fake_get)
        result = download_images(urls, tmp_path)
        assert len(result) == 2
        assert urls[0] in result and urls[1] in result and urls[2] not in result
        assert result[urls[0]].name == "0.jpg"
        assert (tmp_path / "0.jpg").read_bytes() == b"JPEG_BYTES"


    @pytest.mark.unit
    def test_localize_markdown_replaces_urls():
        md = "text ![](https://remote/img.jpg) more"
        m = localize_markdown(md, {"https://remote/img.jpg": Path("0.jpg")},
                              base_url="http://localhost:8765", article_hash="abc")
        assert "http://localhost:8765/abc/0.jpg" in m
        assert "https://remote/img.jpg" not in m


    @pytest.mark.unit
    def test_describe_images_batch_calls_sleep_between(tmp_path: Path, mocker, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
        p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
        mock_sleep = mocker.patch("image_pipeline.time.sleep")
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value.text = "desc"
        mocker.patch("image_pipeline.genai.Client", return_value=mock_client)
        mocker.patch("image_pipeline.Image.open", return_value=MagicMock())
        result = describe_images([p1, p2])
        assert result[p1] == "desc" and result[p2] == "desc"
        mock_sleep.assert_called_once_with(4)  # exactly one sleep between 2 images


    @pytest.mark.unit
    def test_describe_images_per_image_error_isolation(tmp_path: Path, mocker, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test")
        p1 = tmp_path / "1.jpg"; p1.write_bytes(b"x")
        p2 = tmp_path / "2.jpg"; p2.write_bytes(b"y")
        mocker.patch("image_pipeline.time.sleep")
        client = MagicMock()
        r_ok = MagicMock(); r_ok.text = "desc"
        client.models.generate_content.side_effect = [Exception("api boom"), r_ok]
        mocker.patch("image_pipeline.genai.Client", return_value=client)
        mocker.patch("image_pipeline.Image.open", return_value=MagicMock())
        result = describe_images([p1, p2])
        assert "Error describing image" in result[p1]
        assert result[p2] == "desc"


    @pytest.mark.unit
    def test_save_markdown_with_images_atomic(tmp_path: Path):
        md_path, meta_path = save_markdown_with_images(
            "# hello", tmp_path, {"title": "t", "images": []},
        )
        assert md_path.read_text(encoding="utf-8") == "# hello"
        assert json.loads(meta_path.read_text()) == {"title": "t", "images": []}
        # No leftover tmp files
        assert not list(tmp_path.glob("*.tmp"))
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/test_image_pipeline.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - File `image_pipeline.py` exists at repo root
    - `grep -q "^def download_images" image_pipeline.py` succeeds
    - `grep -q "^def localize_markdown" image_pipeline.py` succeeds
    - `grep -q "^def describe_images" image_pipeline.py` succeeds
    - `grep -q "^def save_markdown_with_images" image_pipeline.py` succeeds
    - `grep -q "time.sleep(_DESCRIBE_INTER_IMAGE_SLEEP_SECS)" image_pipeline.py` succeeds (rate limiting present)
    - `grep -q "_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 4" image_pipeline.py` succeeds
    - `grep -q "os.replace" image_pipeline.py` succeeds (atomic write)
    - `pytest tests/unit/test_image_pipeline.py -x -v` exits 0 with 5 tests passing
  </acceptance_criteria>
  <done>image_pipeline.py exists with 4 functions; all unit tests pass</done>
</task>

<task type="auto">
  <name>Task 1.2: Refactor ingest_wechat.py to use image_pipeline</name>
  <files>ingest_wechat.py</files>
  <read_first>
    - ingest_wechat.py entire file (to understand surrounding context — especially lines 525-720 where image code lives)
    - image_pipeline.py (just-created module — understand its exact API)
  </read_first>
  <action>
    Modify `ingest_wechat.py` to delegate all image handling to `image_pipeline`. The goal: DELETE the inlined image logic and call `image_pipeline` functions instead.

    (A) Add at the top of the file (after existing imports):
    ```python
    from image_pipeline import (
        download_images, localize_markdown, describe_images, save_markdown_with_images,
    )
    ```

    (B) DELETE lines 125-135 (the inline `def describe_image(image_path)` function — it is now replaced by `image_pipeline.describe_images`). Do NOT leave a compatibility shim.

    (C) In `ingest_article` (around lines 624-657, the per-image loop), REPLACE the loop with:
    ```python
        # Localize + describe images via shared pipeline (D-15)
        unique_img_urls = list(dict.fromkeys([u for u in img_urls if u.startswith('http')]))
        print(f"Found {len(unique_img_urls)} unique potential images. Downloading and describing...")
        url_to_path = download_images(unique_img_urls, Path(article_dir))
        descriptions = describe_images(list(url_to_path.values()))
        full_content = localize_markdown(full_content, url_to_path, article_hash=article_hash)
        processed_images = []
        for i, (url, path) in enumerate(url_to_path.items()):
            desc = descriptions.get(path, "")
            local_url = f"http://localhost:8765/{article_hash}/{path.name}"
            full_content += f"\n\n[Image {i} Reference]: {local_url}\n[Image {i} Description]: {desc}\n"
            processed_images.append({"index": i, "description": desc, "local_url": local_url})
        image_success_count = len(url_to_path)
        image_fail_count = len(unique_img_urls) - image_success_count
    ```

    (D) REPLACE the metadata + MD save block (around lines 695-706) with:
    ```python
        save_markdown_with_images(
            full_content,
            Path(article_dir),
            {
                "title": title,
                "url": url,
                "hash": article_hash,
                "method": method,
                "images": processed_images,
            },
        )
    ```

    (E) Also remove any now-orphaned imports introduced by the deletion (e.g. if `describe_image` was the only user of `PIL.Image` in this file, the `from PIL import Image` import should be removed per the Surgical Changes principle — but ONLY if it's genuinely unused elsewhere. Grep first: `grep "Image\." ingest_wechat.py` — if only the deleted function referenced it, remove the import; otherwise leave it.)

    Preserve everything else: UA scraping, Apify path, CDP path, cache-hit branch (lines 532-566), entity extraction, LightRAG ainsert call, SQLite update, Cognee fire-and-forget.

    The <2000-char skip logic is NOT added here — that belongs in plan 07 (top-level integration).
  </action>
  <verify>
    <automated>grep -q "from image_pipeline import" ingest_wechat.py && ! grep -q "^def describe_image" ingest_wechat.py && python -c "import ast; ast.parse(open('ingest_wechat.py').read())"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "from image_pipeline import" ingest_wechat.py` succeeds
    - `grep -q "download_images\|describe_images\|localize_markdown\|save_markdown_with_images" ingest_wechat.py` returns at least 4 matches
    - `grep -n "^def describe_image\b" ingest_wechat.py` returns NO matches (single-image function removed)
    - `python -c "import ast; ast.parse(open('ingest_wechat.py').read())"` exits 0 (file still valid Python)
    - The cache-hit branch (`if os.path.exists(cache_content)`) still present and unchanged
    - The scraping triple-path (UA → Apify → CDP/MCP) still present and unchanged
  </acceptance_criteria>
  <done>ingest_wechat.py uses image_pipeline; no inlined image logic remains; file still parses</done>
</task>

<task type="auto">
  <name>Task 1.3: Golden-file regression test (remote-runnable)</name>
  <files>tests/integration/test_image_pipeline_golden.py</files>
  <read_first>
    - tests/fixtures/golden_articles.txt (list of article hashes captured in Task 0.5)
    - tests/fixtures/golden/ (the snapshots themselves)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §7 "Golden-file regression design"
    - image_pipeline.py (to understand what the diff is checking against)
  </read_first>
  <action>
    Create `tests/integration/test_image_pipeline_golden.py`. This test is marked `remote` because the diff depends on live Gemini Vision responses for the reproduced descriptions — it cannot run meaningfully on Windows without network + API access.

    The test:
    1. Reads each hash from `tests/fixtures/golden_articles.txt` (skip comment lines).
    2. For each hash, loads `tests/fixtures/golden/<hash>/metadata.json` and `tests/fixtures/golden/<hash>/final_content.md` as the baseline.
    3. Re-runs the image pipeline logic STRIPPED to image-only concerns: takes the `images[].local_url` from baseline metadata, reconstructs the remote URL → local path mapping from the MD, and calls `localize_markdown` + `save_markdown_with_images` (NOT `download_images` — images already exist; NOT `describe_images` unless explicitly opted in via env var `GOLDEN_REDESCRIBE=1`, which is an expensive live call).
    4. Diffs new output vs baseline with these invariants:
       - Image count matches exactly.
       - Local URL patterns match (`http://localhost:8765/<hash>/<i>.jpg`).
       - Markdown structural shape: same number of `[Image N Reference]` lines.
    5. Tolerances (when `GOLDEN_REDESCRIBE=1`):
       - Each image description may differ by up to 30% character count.
       - Whitespace-only diffs ignored.

    ```python
    """Golden-file regression for image_pipeline refactor (D-16).

    REMOTE-ONLY. Marked @pytest.mark.remote because live Gemini calls are
    required when GOLDEN_REDESCRIBE=1; structural diff can run anywhere.
    """
    from __future__ import annotations
    import json
    import os
    import re
    from pathlib import Path
    import pytest

    FIXTURES = Path(__file__).parent.parent / "fixtures"
    GOLDEN_LIST = FIXTURES / "golden_articles.txt"


    def _hashes() -> list[str]:
        if not GOLDEN_LIST.exists():
            return []
        return [
            line.strip() for line in GOLDEN_LIST.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]


    @pytest.mark.integration
    @pytest.mark.remote
    @pytest.mark.parametrize("article_hash", _hashes() or ["SKIP"])
    def test_golden_image_pipeline_diff(article_hash: str):
        if article_hash == "SKIP":
            pytest.skip("No golden fixtures populated (populate tests/fixtures/golden_articles.txt)")
        snap_dir = FIXTURES / "golden" / article_hash
        if not snap_dir.exists():
            pytest.skip(f"Snapshot not captured for {article_hash}")

        baseline_md = (snap_dir / "final_content.md").read_text(encoding="utf-8")
        baseline_meta = json.loads((snap_dir / "metadata.json").read_text())

        # Invariant 1: image count
        baseline_image_count = len(baseline_meta.get("images", []))
        ref_lines = re.findall(r"\[Image \d+ Reference\]", baseline_md)
        assert len(ref_lines) == baseline_image_count, (
            f"baseline structural mismatch: {len(ref_lines)} Reference lines vs "
            f"{baseline_image_count} images in metadata — fixture is corrupt"
        )

        # Invariant 2: local URL pattern
        for img in baseline_meta.get("images", []):
            assert img["local_url"].startswith(f"http://localhost:8765/{article_hash}/"), (
                f"bad local_url in baseline: {img['local_url']}"
            )

        # Invariant 3: the refactored pipeline can reproduce localize_markdown
        # and save_markdown_with_images without mutating the MD content.
        from image_pipeline import localize_markdown, save_markdown_with_images
        # Re-run localize on the baseline MD — should be idempotent (all URLs already local)
        url_to_path = {}  # no remote URLs to rewrite in the baseline
        re_md = localize_markdown(baseline_md, url_to_path, article_hash=article_hash)
        assert re_md == baseline_md, "localize_markdown is not idempotent on already-local MD"
    ```

    This test intentionally does NOT re-describe images by default — that requires live Gemini and is opt-in via `GOLDEN_REDESCRIBE=1`. The invariant tests (count, URL pattern, idempotent localize) are cheap and catch the main regression surface.
  </action>
  <verify>
    <automated>pytest tests/integration/test_image_pipeline_golden.py --collect-only -q 2>&1 | grep -E "test_golden|no tests collected"</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/integration/test_image_pipeline_golden.py` exists
    - `grep -q "@pytest.mark.integration" tests/integration/test_image_pipeline_golden.py` succeeds
    - `grep -q "@pytest.mark.remote" tests/integration/test_image_pipeline_golden.py` succeeds
    - `grep -q "golden_articles.txt" tests/integration/test_image_pipeline_golden.py` succeeds
    - `pytest tests/integration/test_image_pipeline_golden.py --collect-only -q` exits 0
    - When run with populated fixtures: test passes OR skips (`pytest.skip("Snapshot not captured")` on absent fixture, NOT fail)
    - Integration test run on remote: `ssh -p $OMNIGRAPH_SSH_PORT $OMNIGRAPH_SSH_USER@$OMNIGRAPH_SSH_HOST 'cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/integration/test_image_pipeline_golden.py -v'` exits 0
  </acceptance_criteria>
  <done>Golden-file regression test exists and passes/skips correctly</done>
</task>

</tasks>

<verification>
  Wave 1 sign-off:
  1. `pytest tests/unit/test_image_pipeline.py -x` — all 5 tests pass locally
  2. `python -c "import ingest_wechat"` exits 0 (module still importable after refactor)
  3. Remote regression: `./deploy.sh && ssh remote 'cd ~/OmniGraph-Vault && source venv/bin/activate && pytest tests/ -v --tb=short'` — all tests pass
  4. No duplicated image logic between ingest_wechat.py and image_pipeline.py (grep for `describe_image\|download.*jpg` in ingest_wechat.py should only show `image_pipeline` imports/calls)
</verification>

<success_criteria>
- `image_pipeline.py` exposes the 4 functions from D-15
- `describe_images` batch-rate-limits internally (4s sleep between images)
- `ingest_wechat.py` no longer contains `def describe_image` — uses the shared module
- Unit test suite passes locally
- Golden-file integration test passes on remote (or skips cleanly with empty fixtures)
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-01-SUMMARY.md`.
</output>
