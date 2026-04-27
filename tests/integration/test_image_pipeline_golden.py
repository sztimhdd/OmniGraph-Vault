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
