"""W5A Task 5 — W1 adapter tests: canonical prompt, dual-format validator,
and compiler-seam routing for scripts/wiki_generate_pages.py.

Covers:
- build_opus_prompt emits canonical GFM `[^N]` instructions (never legacy
  `^[article:...]`) and preserves image-handling instructions.
- validate_and_parse accepts BOTH canonical (typed sources[] + GFM) and
  legacy (string article:<hex> sources + ^[article:<hex>]) pages, and
  returns a structured evidence list + detected format.
- generate_one_entity builds an EvidencePack and routes the validated
  candidate through the shared compiler apply engine (WikiPatch), with
  image preservation, dry-run isolation, and suggestion routing for
  unexpectedly-existing targets.
- No new network calls are introduced.
"""
from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import frontmatter
import pytest

from scripts import wiki_generate_pages as wgp
from kb.wiki_compiler.models import page_digest

_TODAY = date(2026, 8, 11)

ARTICLE_HASH = "0123456789"  # valid 10-char hex
WEB_URL = "https://example.com/a"
IMG_MD = "![Architecture](/static/img/abc1234567/3.jpg)"
CHUNK_ID = "chunk-abcdef12"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _catalog(
    *,
    hashes=(ARTICLE_HASH,),
    web_urls=(WEB_URL,),
    include_builtin=True,
) -> list[dict]:
    cat: list[dict] = []
    for h in hashes:
        cat.append({
            "id": len(cat) + 1, "type": "article", "ref": h,
            "title": f"Article {h}", "url": f"https://example.com/{h}",
            "provenance": "lightrag-corpus",
        })
    for u in web_urls:
        cat.append({
            "id": len(cat) + 1, "type": "web", "ref": u,
            "title": "Web Source", "content": "web snippet",
            "provenance": "tavily-web",
        })
    if include_builtin:
        cat.append({
            "id": len(cat) + 1, "type": "builtin", "ref": None,
            "title": "Databricks Claude Opus 4.7 training knowledge",
            "provenance": "training-knowledge",
        })
    return cat


def _canonical_page_text(
    *,
    hashes=(ARTICLE_HASH,),
    web_urls=(WEB_URL,),
    confidence="high",
    body=None,
    include_builtin=False,
) -> str:
    sources: list[dict] = []
    for i, h in enumerate(hashes, start=1):
        sources.append({
            "id": i, "type": "article", "ref": h, "title": f"Article {h}",
            "provenance": "lightrag-corpus",
        })
    for i, u in enumerate(web_urls, start=len(hashes) + 1):
        sources.append({
            "id": i, "type": "web", "ref": u, "title": "Web Source",
            "provenance": "tavily-web",
        })
    if include_builtin:
        sources.append({
            "id": len(sources) + 1, "type": "builtin", "title": "Opus training knowledge",
            "provenance": "training-knowledge",
        })
    md = {
        "title": "Test Entity",
        "created": "2026-08-11",
        "last_updated": "2026-08-11",
        "sources": sources,
        "confidence_level": confidence,
    }
    if body is None:
        n = len(hashes) + len(web_urls)
        cites = "".join(f"[^{i}]" for i in range(1, n + 1))
        defs = "\n".join(
            [f"[^{i}]: **Article {h}** — {h} (lightrag-corpus)"
             for i, h in enumerate(hashes, start=1)]
            + [f"[^{i}]: **Web Source** — {u} (tavily-web)"
               for i, u in enumerate(web_urls, start=len(hashes) + 1)]
        )
        body = (
            "# Test Entity\n\n"
            f"Test Entity is an agent framework. {cites}\n\n"
            "## Definition / Overview\n\n"
            f"It does things. [^1]\n\n"
            "## References\n\n"
            f"{defs}\n"
        )
    return frontmatter.dumps(frontmatter.Post(body, **md))


def _legacy_page_text(*, hashes=(ARTICLE_HASH,), confidence="medium") -> str:
    md = {
        "title": "Test Entity",
        "created": "2026-08-11",
        "last_updated": "2026-08-11",
        "sources": [f"article:{h}" for h in hashes],
        "confidence_level": confidence,
    }
    body = (
        "# Test Entity\n\n"
        "Test Entity is an agent framework. "
        + "".join(f"^[article:{h}]" for h in hashes)
        + "\n"
    )
    return frontmatter.dumps(frontmatter.Post(body, **md))


def _chunk_article_map(*, hashes=(ARTICLE_HASH,)) -> dict[str, dict[str, str]]:
    return {
        CHUNK_ID: {
            "hash": hashes[0], "title": f"Article {hashes[0]}",
            "url": f"https://example.com/{hashes[0]}",
        }
    }


def _fake_apply(status="applied", suggestion_path=None):
    """Stand-in matching the REAL shared compiler engine contract:
    ``apply_patch(patch, *, wiki_root) -> dict`` with ``status`` in
    applied|conflict|suggestion|rejected."""
    calls: list[tuple] = []

    def _apply(patch, *, wiki_root):
        calls.append((patch, wiki_root))
        return {
            "status": status,
            "patch_id": patch.patch_id,
            "error": None,
            "suggestion_path": suggestion_path,
        }

    _apply.calls = calls
    return _apply


async def _run_generate(
    mocker,
    tmp_path,
    *,
    opus_output: str,
    lightrag_ctx: str = f"context {CHUNK_ID} …",
    tavily_results: list[dict] | None = None,
    tavily_key: str = "test-key",
    existing_page: str | None = None,
    apply_status="applied",
    suggestion_path=None,
    dry_run=False,
):
    """Drive generate_one_entity with all external call sites mocked."""
    output_dir = tmp_path / "wiki" / "entities"
    log_path = tmp_path / "wiki" / "log.md"
    if existing_page is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "test-entity.md").write_text(existing_page, encoding="utf-8")

    async def _fake_lightrag(entity_name: str) -> str:
        return lightrag_ctx

    # Default: one Tavily hit matching the canonical page fixture's web source
    if tavily_results is None:
        tavily_results = [{"url": WEB_URL, "title": "Web Source", "content": "web snippet"}]
    mocker.patch.object(wgp, "fetch_lightrag_context", new=_fake_lightrag)
    mocker.patch.object(wgp, "fetch_tavily_results", return_value=tavily_results)
    mocker.patch.object(wgp, "call_opus", return_value=opus_output)
    mocker.patch("scripts.wiki_generate_pages.requests.post",
                 side_effect=AssertionError("unexpected http call"))
    fake_apply = _fake_apply(status=apply_status, suggestion_path=suggestion_path)
    mocker.patch.object(wgp, "_compiler_engine", return_value=fake_apply)

    res = await wgp.generate_one_entity(
        entity_name="Test Entity",
        output_dir=output_dir,
        log_path=log_path,
        chunk_article_map=_chunk_article_map(),
        lightrag_dir=tmp_path / "lightrag",
        tavily_api_key=tavily_key,
        today=_TODAY,
        dry_run=dry_run,
    )
    return res, fake_apply, output_dir, log_path


# ---------------------------------------------------------------------------
# 1. Prompt emits canonical format
# ---------------------------------------------------------------------------


def test_prompts_canonical_format():
    """build_opus_prompt must instruct GFM [^N] citations + typed sources,
    never legacy ^[article:...], and keep image instructions."""
    catalog = _catalog()
    prompt = wgp.build_opus_prompt(
        entity_name="Test Entity",
        lightrag_context=f"ctx {CHUNK_ID}",
        tavily_results=[{"url": WEB_URL, "title": "Web Source", "content": "snippet"}],
        catalog=catalog,
        today=_TODAY,
    )
    assert "[^N]" in prompt, "prompt must teach GFM [^N] footnotes"
    assert "## References" in prompt, "prompt must require a References section"
    # The typed-sources frontmatter example is id-first canonical: the list
    # marker carries the positional id, `type` is a continuation key.
    assert "- id: 1" in prompt, "prompt must show typed sources frontmatter"
    assert "    type: article" in prompt
    assert "provenance: lightrag-corpus" in prompt
    assert "provenance: tavily-web" in prompt
    assert "Format is exactly `^[article:" not in prompt, "old legacy instruction must be gone"
    # The legacy form may only appear inside the deprecation warning, never as
    # an instruction to emit it.
    assert prompt.count("^[article:") <= 2, "legacy form leaks beyond the DO-NOT warning"
    assert "DO NOT use `[^N]`" not in prompt, "old anti-GFM instruction must be gone"
    # Image instructions preserved verbatim-ish
    assert "/static/img/" in prompt
    assert "PRESERVE" in prompt.upper() or "preserve" in prompt


# ---------------------------------------------------------------------------
# 2-4. Validator: canonical + legacy + evidence
# ---------------------------------------------------------------------------


def test_validates_canonical_success():
    """Canonical page (typed sources[] + [^N] + References) passes."""
    page = _canonical_page_text()
    res = wgp.validate_and_parse(page, _catalog())
    assert res["errors"] == [], res["errors"]
    assert res["post"] is not None
    assert res["format"] == "canonical"


def _canonical_with_sources(sources: list[dict]) -> str:
    """Canonical page text with an explicit sources list (for id tests)."""
    md = {
        "title": "Test Entity",
        "created": "2026-08-11",
        "last_updated": "2026-08-11",
        "sources": sources,
        "confidence_level": "high",
    }
    body = (
        "# Test Entity\n\n"
        "Test Entity is an agent framework. [^1]\n\n"
        "## References\n\n"
        f"[^1]: **Article {ARTICLE_HASH}** — {ARTICLE_HASH} (lightrag-corpus)\n"
    )
    return frontmatter.dumps(frontmatter.Post(body, **md))


def test_validator_requires_positional_source_id():
    """SCHEMA.md §1: every sources[] entry must carry a positional integer
    `id` (1-based, referenced inline as [^id]). The W1 validator must
    reject canonical pages that omit or misnumber it."""
    cat = _catalog()

    # id present and positional -> passes
    ok = _canonical_with_sources([{
        "id": 1, "type": "article", "ref": ARTICLE_HASH,
        "title": f"Article {ARTICLE_HASH}", "provenance": "lightrag-corpus",
    }])
    res = wgp.validate_and_parse(ok, cat)
    assert res["errors"] == [], res["errors"]

    # id omitted -> rejected
    no_id = _canonical_with_sources([{
        "type": "article", "ref": ARTICLE_HASH,
        "title": f"Article {ARTICLE_HASH}", "provenance": "lightrag-corpus",
    }])
    res = wgp.validate_and_parse(no_id, cat)
    assert any("id" in e for e in res["errors"]), res["errors"]

    # id misnumbered -> rejected
    wrong = _canonical_with_sources([{
        "id": 9, "type": "article", "ref": ARTICLE_HASH,
        "title": f"Article {ARTICLE_HASH}", "provenance": "lightrag-corpus",
    }])
    res = wgp.validate_and_parse(wrong, cat)
    assert any("id" in e for e in res["errors"]), res["errors"]

    # duplicate id -> rejected
    dup = _canonical_with_sources([
        {"id": 1, "type": "article", "ref": ARTICLE_HASH,
         "title": f"Article {ARTICLE_HASH}", "provenance": "lightrag-corpus"},
        {"id": 1, "type": "web", "ref": WEB_URL,
         "title": "Web Source", "provenance": "tavily-web"},
    ])
    res = wgp.validate_and_parse(dup, cat)
    assert any("id" in e for e in res["errors"]), res["errors"]


def test_prompt_instructs_positional_source_id():
    """The prompt must teach Opus that sources[] entries carry a positional
    `id` (1-based, in AVAILABLE SOURCES order) and that [^N] inline
    citations reference those ids."""
    catalog = _catalog()
    prompt = wgp.build_opus_prompt(
        entity_name="Test Entity",
        lightrag_context="ctx",
        tavily_results=[{"url": WEB_URL, "title": "Web Source", "content": "s"}],
        catalog=catalog,
        today=_TODAY,
    )
    # The rendered frontmatter example carries id as the first key
    assert "- id: 1" in prompt
    assert "- id: 2" in prompt
    # The frontmatter format instruction spells out the id contract
    fmt_section = prompt[prompt.index("Format per entry"):prompt.index("Do NOT add sources")]
    assert "`id:`" in fmt_section
    assert "1-based" in fmt_section
    assert "available sources" in fmt_section.lower()


def test_validates_legacy_still_passes():
    """Legacy page (string sources + ^[article:<hex>]) still passes."""
    page = _legacy_page_text()
    res = wgp.validate_and_parse(page, _catalog())
    assert res["errors"] == [], res["errors"]
    assert res["post"] is not None
    assert res["format"] == "legacy"


def test_validate_and_parse_returns_evidence_refs():
    """Result includes structured evidence list + format for engine compat."""
    cat = _catalog()
    res = wgp.validate_and_parse(_canonical_page_text(), cat)
    assert res["format"] == "canonical"
    assert res["evidence"], "canonical result must carry structured evidence"
    first = res["evidence"][0]
    assert first["type"] == "article"
    assert first["ref"] == ARTICLE_HASH
    assert first["title"] == f"Article {ARTICLE_HASH}"
    assert first["provenance"] == "lightrag-corpus"
    assert first["evidence_id"]

    res_legacy = wgp.validate_and_parse(_legacy_page_text(), cat)
    assert res_legacy["format"] == "legacy"
    assert res_legacy["evidence"], "legacy result must carry article evidence"
    assert res_legacy["evidence"][0]["ref"] == ARTICLE_HASH


def test_validates_canonical_rejects_hallucinated_article_hash():
    """Canonical page citing an article hash absent from catalog fails."""
    page = _canonical_page_text(hashes=("deadbeef00",))
    res = wgp.validate_and_parse(page, _catalog())
    assert res["errors"], "hash outside the trusted catalog must fail"
    assert any("catalog" in e for e in res["errors"])


def test_validates_canonical_rejects_unknown_footnote():
    """Canonical page citing [^9] with only 2 sources fails."""
    page = _canonical_page_text(body=(
        "# Test Entity\n\n"
        "Claim. [^9]\n\n"
        "## References\n\n"
        "[^9]: **Phantom** — x (lightrag-corpus)\n"
    ))
    res = wgp.validate_and_parse(page, _catalog())
    assert res["errors"]


def test_validates_canonical_rejects_mixed_legacy_citations():
    """Canonical sources + legacy ^[article:] body citation must fail."""
    page = _canonical_page_text(body=(
        "# Test Entity\n\n"
        f"Claim. [^1] and also ^[article:{ARTICLE_HASH}]\n\n"
        "## References\n\n"
        f"[^1]: **Article {ARTICLE_HASH}** — {ARTICLE_HASH} (lightrag-corpus)\n"
    ))
    res = wgp.validate_and_parse(page, _catalog())
    assert res["errors"], "mixed legacy citations in canonical page must fail"


# ---------------------------------------------------------------------------
# 5. generate_one_entity routes through compiler
# ---------------------------------------------------------------------------


def test_generate_one_entity_routes_through_compiler(mocker, tmp_path):
    """generate_one_entity builds an EvidencePack, creates a WikiPatch via the
    assembler, and routes it through the shared apply engine."""
    opus_out = _canonical_page_text()
    res, fake_apply, output_dir, log_path = asyncio.run(_run_generate(
        mocker, tmp_path, opus_output=opus_out,
    ))

    assert res["status"] == "ok"
    assert res["path"] == str(output_dir / "test-entity.md")
    assert res["errors"] == []
    assert len(fake_apply.calls) == 1
    patch, wiki_root = fake_apply.calls[0]
    assert patch.target_slug == "test-entity"
    assert patch.target_kind == "entity"
    assert patch.target_path.endswith("entities/test-entity.md")
    assert patch.operations[0].op == "CREATE_PAGE"
    # Candidate content (validated Opus page) rides the patch, not a re-render
    assert patch.operations[0].content == opus_out
    assert wiki_root == tmp_path / "wiki"
    # Real engine contract: apply_fn(patch, *, wiki_root) — the plan-era
    # known_article_hashes kwarg is gone (engine derives everything from the
    # patch; evidence is already embedded). The fake's keyword-only signature
    # rejects that kwarg with TypeError, so a regression here fails this test.
    # Engine compatibility: evidence is present on the patch
    assert any(ev.type == "article" and ev.ref == ARTICLE_HASH for ev in patch.evidence)
    # Log line still written
    log = log_path.read_text(encoding="utf-8")
    assert "test-entity.md" in log


# ---------------------------------------------------------------------------
# 6 + 9. Images preserved end-to-end
# ---------------------------------------------------------------------------


def test_generate_one_entity_preserves_images(mocker, tmp_path):
    """Image markdown from LightRAG context survives prompt + patch content."""
    ctx = f"context {CHUNK_ID} …\n\n{IMG_MD}\n\nmore text"
    opus_out = _canonical_page_text(body=(
        "# Test Entity\n\n"
        "Test Entity is an agent framework. [^1]\n\n"
        "## Architecture / Design\n\n"
        f"{IMG_MD}\n\n"
        "## References\n\n"
        f"[^1]: **Article {ARTICLE_HASH}** — {ARTICLE_HASH} (lightrag-corpus)\n"
    ))
    res, fake_apply, _, _ = asyncio.run(_run_generate(
        mocker, tmp_path, opus_output=opus_out, lightrag_ctx=ctx,
    ))
    assert res["status"] == "ok"
    patch = fake_apply.calls[0][0]
    assert IMG_MD in patch.operations[0].content


def test_wikipedia_image_preservation_edge_case(mocker, tmp_path):
    """Entity with many images: every image line survives prompt + page."""
    images = [f"![Diagram {i}](/static/img/abc1234567/{i}.jpg)" for i in range(1, 9)]
    ctx = f"context {CHUNK_ID} …\n\n" + "\n\n".join(images)
    prompt = wgp.build_opus_prompt(
        entity_name="Test Entity",
        lightrag_context=ctx,
        tavily_results=[],
        catalog=_catalog(),
        today=_TODAY,
    )
    for img in images:
        assert img in prompt, f"prompt lost image {img}"

    body_imgs = "\n\n".join(images)
    opus_out = _canonical_page_text(body=(
        "# Test Entity\n\n"
        "Test Entity is an agent framework. [^1]\n\n"
        "## Architecture / Design\n\n"
        f"{body_imgs}\n\n"
        "## References\n\n"
        f"[^1]: **Article {ARTICLE_HASH}** — {ARTICLE_HASH} (lightrag-corpus)\n"
    ))
    res, fake_apply, _, _ = asyncio.run(_run_generate(
        mocker, tmp_path, opus_output=opus_out, lightrag_ctx=ctx,
    ))
    assert res["status"] == "ok"
    content = fake_apply.calls[0][0].operations[0].content
    for img in images:
        assert img in content, f"patch lost image {img}"


# ---------------------------------------------------------------------------
# 7. dry_run unchanged
# ---------------------------------------------------------------------------


def test_generate_one_entity_dry_run_unchanged(mocker, tmp_path):
    """dry_run short-circuits: no fetchers, no compiler routing, no writes."""
    output_dir = tmp_path / "wiki" / "entities"
    log_path = tmp_path / "wiki" / "log.md"

    mocker.patch.object(wgp, "fetch_lightrag_context", new=AsyncMock(
        side_effect=AssertionError("dry run must not fetch")))
    mocker.patch.object(wgp, "fetch_tavily_results", side_effect=AssertionError("dry run must not fetch"))
    mocker.patch.object(wgp, "call_opus", side_effect=AssertionError("dry run must not call opus"))
    mocker.patch.object(wgp, "_compiler_engine", side_effect=AssertionError("dry run must not route"))

    res = asyncio.run(wgp.generate_one_entity(
        entity_name="Test Entity",
        output_dir=output_dir,
        log_path=log_path,
        chunk_article_map={},
        lightrag_dir=tmp_path / "lightrag",
        tavily_api_key="",
        today=_TODAY,
        dry_run=True,
    ))
    assert res["status"] == "ok"
    assert res["confidence"] == "dry-run"
    assert not (output_dir / "test-entity.md").exists()
    assert not log_path.exists()


# ---------------------------------------------------------------------------
# 8. No new network calls
# ---------------------------------------------------------------------------


def test_w1_no_new_network_calls(mocker, tmp_path):
    """Only the pre-existing fetch sites run; no new HTTP appears, and the
    module imports no new network client libraries."""
    import ast

    tree = ast.parse(open(wgp.__file__, encoding="utf-8").read())
    top_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            top_imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            top_imports.add((node.module or "").split(".")[0])
    forbidden = {"tavily", "langchain", "httpx", "openai", "google", "aiohttp", "websocket"}
    assert not (top_imports & forbidden), (
        f"new network client imports introduced: {top_imports & forbidden}"
    )
    # requests remains the only HTTP lib — call sites are exactly Tavily + Opus
    assert "requests" in top_imports

    opus_out = _canonical_page_text()
    ctx = f"context {CHUNK_ID} …"
    async def _fake_lightrag(entity_name: str) -> str:
        return ctx
    mocker.patch.object(wgp, "fetch_lightrag_context", new=_fake_lightrag)
    tavily_mock = mocker.patch.object(
        wgp, "fetch_tavily_results",
        return_value=[{"url": WEB_URL, "title": "Web Source", "content": "snippet"}],
    )
    opus_mock = mocker.patch.object(wgp, "call_opus", return_value=opus_out)
    http_mock = mocker.patch(
        "scripts.wiki_generate_pages.requests.post",
        side_effect=AssertionError("unexpected http call"))
    fake_apply = _fake_apply()
    mocker.patch.object(wgp, "_compiler_engine", return_value=fake_apply)

    res = asyncio.run(wgp.generate_one_entity(
        entity_name="Test Entity",
        output_dir=tmp_path / "wiki" / "entities",
        log_path=tmp_path / "wiki" / "log.md",
        chunk_article_map=_chunk_article_map(),
        lightrag_dir=tmp_path / "lightrag",
        tavily_api_key="test-key",
        today=_TODAY,
        dry_run=False,
    ))
    assert res["status"] == "ok"
    assert tavily_mock.call_count == 1
    assert opus_mock.call_count == 1
    http_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 10. Unexpected existing target → suggestion routing
# ---------------------------------------------------------------------------


def test_suggestion_writing_for_existing_page(mocker, tmp_path):
    """If the target page exists unexpectedly, the pack carries
    existing_page_path/digest, the patch is suggestion_only, and the
    existing file is never overwritten."""
    existing = _legacy_page_text()
    sugg_path = str(tmp_path / "wiki" / "_suggestions" / "test-entity-wpatch-abc.json")
    res, fake_apply, output_dir, _ = asyncio.run(_run_generate(
        mocker, tmp_path,
        opus_output=_canonical_page_text(),
        existing_page=existing,
        apply_status="suggestion",
        suggestion_path=sugg_path,
    ))

    assert res["status"] == "suggested"
    assert res["path"] == sugg_path
    assert len(fake_apply.calls) == 1
    patch, _ = fake_apply.calls[0]
    assert patch.policy_hint == "suggestion_only"
    assert patch.base_digest == page_digest(existing)
    assert patch.operations[0].op == "MERGE_SOURCES", (
        "existing-page pack must produce scoped update ops, not CREATE_PAGE"
    )
    # Never overwrite the existing page
    assert (output_dir / "test-entity.md").read_text(encoding="utf-8") == existing


def test_generate_one_entity_conflict_maps_to_failed(mocker, tmp_path):
    """A compiler conflict result must map to failed and never overwrite."""
    res, _, output_dir, _ = asyncio.run(_run_generate(
        mocker, tmp_path,
        opus_output=_canonical_page_text(),
        apply_status="conflict",
    ))
    assert res["status"] == "failed"
    assert res["errors"], "conflict must carry an error message"
