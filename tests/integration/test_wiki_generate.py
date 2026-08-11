"""Wiki page generation integration test (W1 deliverable, canonical SCHEMA format).

Mocks the 3 sources (LightRAG context fetch, Tavily web search, Opus call)
and the shared compiler apply engine so the test is fast and deterministic —
no LightRAG init, no real LLM, no network. Real end-to-end exercised by
running `scripts/wiki_generate_pages.py`.

Citation format follows kb/wiki/SCHEMA.md (W5A canonical):
  Inline:        GFM footnotes [^N] with definitions in `## References`
  Frontmatter:   sources: typed list of dicts (type/ref/title/provenance)
  Web/builtin:   first-class citable sources (no legacy ^[article:<hex>])
"""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import date
from pathlib import Path

import frontmatter
import pytest

from kb.wiki_compiler.models import page_digest


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
  - id: 1
    type: article
    ref: "16e23156b6"
    title: "KOL OpenClaw deep-dive"
    provenance: lightrag-corpus
  - id: 2
    type: article
    ref: "e965180f9d"
    title: "Hermes/OpenClaw comparison"
    provenance: lightrag-corpus
confidence_level: medium
---

# OpenClaw

## Definition

**OpenClaw** is a Tauri-based AI desktop assistant [^1]. It
implements a 5-layer agent architecture [^2].

## Architecture

The five layers are skill loader, gateway router, LLM dispatcher, memory store,
and observability bus [^1]. Each layer has a defined contract [^2].

## Cross-references

- [[hermes-agent]]

## References

[^1]: **KOL OpenClaw deep-dive** — 16e23156b6 (lightrag-corpus)
[^2]: **Hermes/OpenClaw comparison** — e965180f9d (lightrag-corpus)
"""


def _fake_chunk_article_map() -> dict[str, dict[str, str]]:
    return {
        "chunk-aaa1234567ee01": {"hash": "16e23156b6", "title": "KOL OpenClaw deep-dive", "url": "http://x"},
        "chunk-bbb9876543ff02": {"hash": "e965180f9d", "title": "Hermes/OpenClaw comparison", "url": "http://y"},
    }


def _fake_apply_engine(out_dir: Path, applied_paths: list[Path]):
    """Sync stand-in matching the REAL shared compiler engine contract:
    ``apply_patch(patch, *, wiki_root) -> dict`` with ``status`` in
    applied|conflict|suggestion|rejected. Writes the page like the engine
    would for a CREATE_PAGE auto-apply."""
    calls: list[tuple] = []

    def _apply(patch, *, wiki_root):
        calls.append((patch, wiki_root))
        target = Path(wiki_root) / patch.target_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch.operations[0].content, encoding="utf-8")
        applied_paths.append(target)
        return {
            "status": "applied",
            "patch_id": patch.patch_id,
            "error": None,
            "suggestion_path": None,
        }

    _apply.calls = calls
    return _apply


@pytest.mark.integration
def test_one_entity_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks all 3 sources + Opus call; verifies canonical orchestration
    end-to-end and that the page routes through the compiler seam."""
    from scripts import wiki_generate_pages as wgp

    async def _fake_lr_ctx(entity_name: str) -> str:
        assert entity_name == "OpenClaw"
        return _FAKE_LIGHTRAG_CTX

    def _fake_tavily(entity_name: str, api_key: str) -> list[dict]:
        assert api_key == "tvly-fake-test-key"
        return _FAKE_TAVILY_RESULTS

    def _fake_opus(prompt: str) -> str:
        assert "OpenClaw" in prompt
        assert "AVAILABLE SOURCES" in prompt
        assert "[^N]" in prompt
        assert "^[article:" not in prompt  # legacy form never instructed
        return _FAKE_OPUS_OUTPUT

    monkeypatch.setattr(wgp, "fetch_lightrag_context", _fake_lr_ctx)
    monkeypatch.setattr(wgp, "fetch_tavily_results", _fake_tavily)
    monkeypatch.setattr(wgp, "call_opus", _fake_opus)
    monkeypatch.setattr(
        "scripts.wiki_generate_pages.requests.post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected http call")))

    out_dir = tmp_path / "entities"
    log_path = tmp_path / "log.md"
    applied: list[Path] = []
    fake_apply = _fake_apply_engine(out_dir, applied)
    monkeypatch.setattr(wgp, "_compiler_engine", lambda: fake_apply)

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

    # Routed through the compiler: one WikiPatch, CREATE_PAGE, candidate content
    assert len(fake_apply.calls) == 1
    patch, wiki_root = fake_apply.calls[0]
    assert patch.operations[0].op == "CREATE_PAGE"
    assert patch.operations[0].content == _FAKE_OPUS_OUTPUT
    # Real engine contract: apply_fn(patch, *, wiki_root) — no plan-era kwargs
    assert wiki_root == tmp_path

    out_path = out_dir / "openclaw.md"
    assert out_path.exists()
    assert applied == [out_path]

    post = frontmatter.load(out_path)
    required = {"title", "created", "last_updated", "sources", "confidence_level"}
    assert required.issubset(post.metadata.keys())
    assert post["title"] == "OpenClaw"

    # Sources is a typed list of dicts per canonical SCHEMA, with positional
    # `id` (SCHEMA.md §1) as the first key of every entry.
    sources = post.metadata["sources"]
    assert isinstance(sources, list) and all(isinstance(s, dict) for s in sources)
    assert [s["id"] for s in sources] == [1, 2]
    assert [s["ref"] for s in sources] == ["16e23156b6", "e965180f9d"]
    assert all(s["type"] == "article" for s in sources)
    assert all(s["provenance"] == "lightrag-corpus" for s in sources)

    # Body has GFM [^N] citations; no legacy ^[article:<hex>] anywhere
    body_hashes = re.findall(r"\^\[article:([a-f0-9]{10})\]", post.content)
    assert body_hashes == []
    assert "[^1]" in post.content and "[^2]" in post.content
    assert "## References" in post.content
    assert re.search(r"\[\^1\]:", post.content)

    assert log_path.exists()
    assert "generated entities/openclaw.md" in log_path.read_text(encoding="utf-8")


@pytest.mark.integration
def test_one_entity_real_engine_writes_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UNSTUBBED W1 seam test: ``_compiler_engine`` is NOT monkeypatched —
    the real ``kb.wiki_compiler.engine.apply_patch`` runs end-to-end. This
    test dies if the seam breaks (plan-era kwargs, wrong result shape, or
    status-vocabulary mismatch). Only the 3 evidence sources are mocked.

    Regression for the adversarial review BLOCKER: W1 previously passed
    ``known_article_hashes=...`` (TypeError on every run) and read the
    result as an attribute object (always 'rejected').
    """
    from scripts import wiki_generate_pages as wgp

    async def _fake_lr_ctx(entity_name: str) -> str:
        assert entity_name == "OpenClaw"
        return _FAKE_LIGHTRAG_CTX

    def _fake_tavily(entity_name: str, api_key: str) -> list[dict]:
        assert api_key == "tvly-fake-test-key"
        return _FAKE_TAVILY_RESULTS

    def _fake_opus(prompt: str) -> str:
        assert "OpenClaw" in prompt
        return _FAKE_OPUS_OUTPUT

    monkeypatch.setattr(wgp, "fetch_lightrag_context", _fake_lr_ctx)
    monkeypatch.setattr(wgp, "fetch_tavily_results", _fake_tavily)
    monkeypatch.setattr(wgp, "call_opus", _fake_opus)
    monkeypatch.setattr(
        "scripts.wiki_generate_pages.requests.post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected http call")))

    out_dir = tmp_path / "entities"
    out_dir.mkdir(parents=True, exist_ok=True)  # engine resolves the target under wiki_root
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

    assert res["status"] == "ok", f"real engine seam failed: {res['errors']}"
    assert res["errors"] == []

    # The real engine wrote the page under wiki_root (tmp_path), not the fake.
    out_path = out_dir / "openclaw.md"
    assert out_path.exists(), "real engine apply must write the page file"

    post = frontmatter.load(out_path)
    sources = post.metadata["sources"]
    assert isinstance(sources, list) and all(isinstance(s, dict) for s in sources)
    assert [s["id"] for s in sources] == [1, 2], (
        "SCHEMA.md positional sources id must survive the full W1 pipeline"
    )
    assert [s["ref"] for s in sources] == ["16e23156b6", "e965180f9d"]
    assert all(s["type"] == "article" for s in sources)
    assert all(s["provenance"] == "lightrag-corpus" for s in sources)

    # Body carries GFM [^N] citations with matching definitions
    assert "[^1]" in post.content and "[^2]" in post.content
    assert "## References" in post.content
    assert re.search(r"\[\^1\]:", post.content) and re.search(r"\[\^2\]:", post.content)
    assert re.findall(r"\^\[article:([a-f0-9]{10})\]", post.content) == []

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
    """Opus output without citations triggers retries; max=0 fails fast."""
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
            "  - id: 1\n"
            "    type: article\n"
            "    ref: \"16e23156b6\"\n"
            "    title: \"KOL OpenClaw deep-dive\"\n"
            "    provenance: lightrag-corpus\n"
            "confidence_level: medium\n"
            "---\n\n"
            "# Foo\n\n"
            "This page has no inline citations.\n"
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
    assert any("no [^N] GFM citations" in e for e in res["errors"])
    assert not (out_dir / "foo.md").exists()
