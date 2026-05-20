"""W4 wiki_inject fallthrough tests — pin observable behavior."""
from __future__ import annotations

import asyncio
from pathlib import Path

from kb.services.wiki_inject import extract_main_entity, resolve_wiki_context


def _write_page(
    path: Path,
    *,
    last_updated: str = "2026-05-19",
    citations: list[str] | None = None,
) -> None:
    cites = citations or []
    body = "\n".join(f"Claim about it ^[article:{h}]" for h in cites) or "Body."
    src_lines = "\n".join(f"  - article:{h}" for h in cites) or "  []"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "title: Test\n"
        "created: 2026-05-19\n"
        f"last_updated: {last_updated}\n"
        "sources:\n"
        f"{src_lines}\n"
        "confidence_level: high\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_extract_main_entity_basic(tmp_path: Path) -> None:
    entities = tmp_path / "entities"
    entities.mkdir()
    (entities / "openclaw.md").write_text("x", encoding="utf-8")
    (entities / "hermes-agent.md").write_text("x", encoding="utf-8")
    assert extract_main_entity("Tell me about OpenClaw", tmp_path) == "openclaw"
    assert extract_main_entity("hermes agent capabilities", tmp_path) == "hermes-agent"
    assert extract_main_entity("Random unrelated query", tmp_path) is None


def test_falls_through_when_wiki_missing(tmp_path: Path) -> None:
    (tmp_path / "entities").mkdir()
    result = asyncio.run(resolve_wiki_context("What is OpenClaw?", tmp_path, 180))
    assert result == ""


def test_returns_context_block_when_page_valid(tmp_path: Path) -> None:
    page = tmp_path / "entities" / "openclaw.md"
    _write_page(page, last_updated="2026-05-19", citations=["abcdef0123"])
    result = asyncio.run(
        resolve_wiki_context(
            "What is OpenClaw?",
            tmp_path,
            180,
            known_article_hashes=frozenset({"abcdef0123"}),
        )
    )
    assert result.startswith("<wiki_context>\n")
    assert result.endswith("</wiki_context>\n\n")
    assert "Claim" in result


def test_falls_through_when_stale(tmp_path: Path) -> None:
    page = tmp_path / "entities" / "openclaw.md"
    _write_page(page, last_updated="2020-01-01", citations=["abcdef0123"])
    result = asyncio.run(
        resolve_wiki_context(
            "What is OpenClaw?",
            tmp_path,
            30,
            known_article_hashes=frozenset({"abcdef0123"}),
        )
    )
    assert result == ""


def test_falls_through_when_unresolved_citation(tmp_path: Path) -> None:
    page = tmp_path / "entities" / "openclaw.md"
    _write_page(page, last_updated="2026-05-19", citations=["ffffffffff"])
    result = asyncio.run(
        resolve_wiki_context(
            "What is OpenClaw?",
            tmp_path,
            180,
            known_article_hashes=frozenset({"abcdef0123"}),
        )
    )
    assert result == ""
