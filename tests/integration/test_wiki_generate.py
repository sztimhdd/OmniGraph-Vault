"""Wiki page generation integration test (W1 deliverable, legacy SCHEMA format).

Mocks the 3 sources (LightRAG context fetch, Tavily web search, Opus call)
so the test is fast and deterministic — no LightRAG init, no real LLM, no
network. Real end-to-end exercised by running `scripts/wiki_generate_pages.py`.

Citation format follows kb/wiki/SCHEMA.md (legacy single-type):
  Inline:        ^[article:<10-char-hex>]
  Frontmatter:   sources: list of strings 'article:<hex>'
  Web/builtin:   listed in body `## Further Reading` section, NOT inline-cited
"""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import date
from pathlib import Path

import frontmatter
import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_FAKE_LIGHTRAG_CTX = """\
[Entities]
OpenClaw is a Tauri-based AI desktop assistant. Source chunks: chunk-aaa1234567ee01,
chunk-bbb9876543ff02

[Chunks]
chunk-aaa1234567ee01: OpenClaw uses a 5-layer architecture...
chunk-bbb9876543ff02: The skill loader is central to OpenClaw...
"""

_FAKE_TAVILY_RESULTS = [
    {
        "url": "https://github.com/example/openclaw",
        "title": "OpenClaw GitHub README",
        "content": "OpenClaw is an open-source AI desktop assistant...",
    },
]

_FAKE_OPUS_OUTPUT = """\
---
title: OpenClaw
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
  - article:16e23156b6
  - article:e965180f9d
confidence_level: medium
---

# OpenClaw

## Definition

**OpenClaw** is a Tauri-based AI desktop assistant ^[article:16e23156b6]. It
implements a 5-layer agent architecture ^[article:e965180f9d].

## Architecture

The five layers are skill loader, gateway router, LLM dispatcher, memory store,
and observability bus ^[article:16e23156b6]. Each layer has a defined contract
^[article:e965180f9d].

## Cross-references

- [[hermes-agent]]

## Further Reading

- [OpenClaw GitHub README](https://github.com/example/openclaw) — official repo
"""


def _fake_chunk_article_map() -> dict[str, dict[str, str]]:
    return {
        "chunk-aaa1234567ee01": {"hash": "16e23156b6", "title": "KOL OpenClaw deep-dive", "url": "http://x"},
        "chunk-bbb9876543ff02": {"hash": "e965180f9d", "title": "Hermes/OpenClaw comparison", "url": "http://y"},
    }


@pytest.mark.integration
def test_one_entity_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks all 3 sources + Opus call; verifies orchestration end-to-end."""
    from scripts import wiki_generate_pages as wgp

    async def _fake_lr_ctx(entity_name: str) -> str:
        assert entity_name == "OpenClaw"
        return _FAKE_LIGHTRAG_CTX

    def _fake_tavily(entity_name: str, api_key: str) -> list[dict]:
        assert api_key == "tvly-fake-test-key"
        return _FAKE_TAVILY_RESULTS

    def _fake_opus(prompt: str) -> str:
        assert "OpenClaw" in prompt
        assert "^[article:" in prompt or "AVAILABLE ARTICLES" in prompt
        return _FAKE_OPUS_OUTPUT

    monkeypatch.setattr(wgp, "fetch_lightrag_context", _fake_lr_ctx)
    monkeypatch.setattr(wgp, "fetch_tavily_results", _fake_tavily)
    monkeypatch.setattr(wgp, "call_opus", _fake_opus)

    out_dir = tmp_path / "entities"
    log_path = tmp_path / "log.md"

    res = asyncio.run(
        wgp.generate_one_entity(
            entity_name="OpenClaw",
            output_dir=out_dir,
            log_path=log_path,
            chunk_article_map=_fake_chunk_article_map(),
            lightrag_dir=tmp_path / "fake_lightrag",
            tavily_api_key="tvly-fake-test-key",
            today=date(2026, 5, 20),
            dry_run=False,
        )
    )

    assert res["status"] == "ok", f"generation failed: {res['errors']}"
    assert res["sources"] == 2, f"expected 2 article sources in frontmatter, got {res['sources']}"

    out_path = out_dir / "openclaw.md"
    assert out_path.exists()

    post = frontmatter.load(out_path)
    required = {"title", "created", "last_updated", "sources", "confidence_level"}
    assert required.issubset(post.metadata.keys())
    assert post["title"] == "OpenClaw"

    # Sources is list of strings 'article:<hex>' per legacy SCHEMA
    sources = post.metadata["sources"]
    assert sorted(sources) == sorted(["article:16e23156b6", "article:e965180f9d"])

    # Body has ^[article:<hex>] citations matching frontmatter
    body_hashes = re.findall(r"\^\[article:([a-f0-9]{10})\]", post.content)
    assert set(body_hashes) == {"16e23156b6", "e965180f9d"}

    # Web URLs surface in Further Reading, not citations
    assert "## Further Reading" in post.content
    assert "https://github.com/example/openclaw" in post.content
    assert "[^1]" not in post.content  # NOT GFM footnote form

    assert log_path.exists()
    assert "generated entities/openclaw.md" in log_path.read_text(encoding="utf-8")


@pytest.mark.integration
def test_dry_run_skips_llm(tmp_path: Path) -> None:
    from scripts import wiki_generate_pages as wgp

    out_dir = tmp_path / "entities"
    log_path = tmp_path / "log.md"

    res = asyncio.run(
        wgp.generate_one_entity(
            entity_name="Hermes",
            output_dir=out_dir,
            log_path=log_path,
            chunk_article_map={},
            lightrag_dir=tmp_path / "fake",
            tavily_api_key="",
            today=date(2026, 5, 20),
            dry_run=True,
        )
    )

    assert res["status"] == "ok"
    assert res["confidence"] == "dry-run"
    assert not (out_dir / "hermes.md").exists()


@pytest.mark.integration
def test_validation_rejects_uncited_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opus output without ^[article:<hex>] citations triggers retries; max=0 fails fast."""
    from scripts import wiki_generate_pages as wgp

    async def _fake_lr_ctx(entity_name: str) -> str:
        return _FAKE_LIGHTRAG_CTX

    def _fake_tavily(entity_name: str, api_key: str) -> list[dict]:
        return _FAKE_TAVILY_RESULTS

    def _fake_opus_no_citations(prompt: str) -> str:
        return (
            "---\n"
            "title: Foo\n"
            "created: '2026-05-20'\n"
            "last_updated: '2026-05-20'\n"
            "sources:\n"
            "  - article:16e23156b6\n"
            "confidence_level: medium\n"
            "---\n\n"
            "# Foo\n\nThis page has no inline citations.\n"
        )

    monkeypatch.setattr(wgp, "fetch_lightrag_context", _fake_lr_ctx)
    monkeypatch.setattr(wgp, "fetch_tavily_results", _fake_tavily)
    monkeypatch.setattr(wgp, "call_opus", _fake_opus_no_citations)

    out_dir = tmp_path / "entities"
    log_path = tmp_path / "log.md"

    res = asyncio.run(
        wgp.generate_one_entity(
            entity_name="Foo",
            output_dir=out_dir,
            log_path=log_path,
            chunk_article_map=_fake_chunk_article_map(),
            lightrag_dir=tmp_path / "fake",
            tavily_api_key="tvly-fake",
            today=date(2026, 5, 20),
            dry_run=False,
            max_retries=0,
        )
    )

    assert res["status"] == "failed"
    assert any("no ^[article" in e for e in res["errors"])
    assert not (out_dir / "foo.md").exists()
