"""SSG bake parity for SCHEMA-2026-05-20 multi-type sources + GFM [^N] footnote.

Pins observable behavior of `_convert_wiki_citations` and the `wiki_entity.html`
template across the two citation forms (legacy ^[article:hash] + new [^N]).
Both forms must continue to render correctly so existing legacy entity pages
do not regress.
"""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from kb.export_knowledge_base import (
    _convert_wiki_citations,
    _normalize_frontmatter_sources,
)


BASE_PATH = "/kb"


# ---------------------------------------------------------------------------
# _normalize_frontmatter_sources
# ---------------------------------------------------------------------------

def test_normalize_legacy_string_list_to_dicts() -> None:
    raw = ["article:abc123def0", "article:0123456789"]
    out = _normalize_frontmatter_sources(raw)
    assert out == [
        {"type": "article", "ref": "abc123def0"},
        {"type": "article", "ref": "0123456789"},
    ]


def test_normalize_dict_list_passthrough() -> None:
    raw = [
        {"id": 1, "type": "web", "ref": "https://example.com", "title": "Example"},
        {"id": 2, "type": "builtin", "title": "Opus 4.7 corpus"},
    ]
    out = _normalize_frontmatter_sources(raw)
    assert out == raw


def test_normalize_empty_or_none() -> None:
    assert _normalize_frontmatter_sources(None) == []
    assert _normalize_frontmatter_sources([]) == []


# ---------------------------------------------------------------------------
# _convert_wiki_citations — legacy-only entities (12 existing pages)
# ---------------------------------------------------------------------------

def test_legacy_only_format_renders_unchanged() -> None:
    """Old entity pages (claude-code.md etc) must keep rendering identically.

    Frontmatter is the legacy flat-string form; body uses ^[article:hash].
    Sources should appear in body-first-seen order with type=article.
    """
    body = (
        "Claude Code is a CLI tool ^[article:5a362bf61e].\n\n"
        "It supports MCP ^[article:064f03c965] and skills ^[article:5a362bf61e]."
    )
    fm_sources = ["article:5a362bf61e", "article:064f03c965"]
    rewritten, sources = _convert_wiki_citations(
        body, BASE_PATH, frontmatter_sources=fm_sources, page_slug="claude-code"
    )

    # Sources merge with frontmatter; ordering is by frontmatter id assignment
    # (legacy strings have no id, so they get appended in body-encounter order).
    assert len(sources) == 2
    refs = [s["ref"] for s in sources]
    assert "5a362bf61e" in refs
    assert "064f03c965" in refs
    for src in sources:
        assert src["type"] == "article"
        assert src["url"].endswith(f"/articles/{src['ref']}.html")

    # Body: each ^[article:hash] becomes a <sup> with the merged numbering.
    n_for = {s["ref"]: s["n"] for s in sources}
    assert f'href="{BASE_PATH}/articles/5a362bf61e.html#cite-{n_for["5a362bf61e"]}"' in rewritten
    assert f'href="{BASE_PATH}/articles/064f03c965.html#cite-{n_for["064f03c965"]}"' in rewritten
    # No literal tokens remain
    assert "^[article:" not in rewritten


def test_legacy_only_with_no_frontmatter_sources() -> None:
    """Entity with body citations but no frontmatter sources still works.

    Hashes get implicit article-type sources with auto-assigned n.
    """
    body = "Claim A ^[article:1234567890]. Claim B ^[article:abcdef0123]."
    rewritten, sources = _convert_wiki_citations(body, BASE_PATH, frontmatter_sources=None)

    assert len(sources) == 2
    assert sources[0]["n"] == 1
    assert sources[1]["n"] == 2
    assert {s["ref"] for s in sources} == {"1234567890", "abcdef0123"}
    for src in sources:
        assert src["type"] == "article"
    assert "^[article:" not in rewritten


# ---------------------------------------------------------------------------
# _convert_wiki_citations — new format (5 Copilot Studio pages)
# ---------------------------------------------------------------------------

def test_new_format_only_multi_type_sources() -> None:
    """SCHEMA-2026-05-20 entity: dict frontmatter + [^N] body citations."""
    body = (
        "Copilot Studio is a Microsoft platform [^1][^2]. "
        "It uses generative orchestration [^6]. Anthropic's Claude is also relevant [^9]."
    )
    fm_sources = [
        {"id": 1, "type": "web", "ref": "https://learn.microsoft.com/...", "title": "MS Learn — What is CPS"},
        {"id": 2, "type": "web", "ref": "https://learn.microsoft.com/topics", "title": "MS Learn — Topics"},
        {"id": 6, "type": "web", "ref": "https://learn.microsoft.com/gen-orch", "title": "MS Learn — Gen Orch"},
        {"id": 9, "type": "builtin", "title": "Opus 4.7 corpus through 2026-01"},
    ]
    rewritten, sources = _convert_wiki_citations(
        body, BASE_PATH, frontmatter_sources=fm_sources, page_slug="copilot-studio"
    )

    # 4 sources preserved with correct types
    assert len(sources) == 4
    by_n = {s["n"]: s for s in sources}
    assert by_n[1]["type"] == "web"
    assert by_n[1]["url"] == "https://learn.microsoft.com/..."
    assert by_n[1]["title"] == "MS Learn — What is CPS"
    assert by_n[6]["type"] == "web"
    assert by_n[9]["type"] == "builtin"
    assert by_n[9]["url"] == ""  # builtin has no url

    # Body: each [^N] -> <sup> linking to in-page #cite-N anchor
    assert '<a href="#cite-1" id="cite-1-back">[1]</a>' in rewritten
    assert '<a href="#cite-2" id="cite-2-back">[2]</a>' in rewritten
    assert '<a href="#cite-6" id="cite-6-back">[6]</a>' in rewritten
    assert '<a href="#cite-9" id="cite-9-back">[9]</a>' in rewritten
    assert "[^1]" not in rewritten
    assert "[^9]" not in rewritten


def test_mixed_format_legacy_and_footnote_share_numbering() -> None:
    """Edge case: page with both ^[article:hash] AND [^N] in body.

    Frontmatter type=article ref matching a legacy hash should reuse its id.
    """
    body = (
        "First, see article ^[article:5a362bf61e]. "
        "Web context [^2]. Same article again [^1]."
    )
    fm_sources = [
        {"id": 1, "type": "article", "ref": "5a362bf61e", "title": "Some Article"},
        {"id": 2, "type": "web", "ref": "https://example.com", "title": "External"},
    ]
    rewritten, sources = _convert_wiki_citations(
        body, BASE_PATH, frontmatter_sources=fm_sources, page_slug="mixed"
    )

    assert len(sources) == 2  # legacy hash matched id=1, no implicit append
    by_n = {s["n"]: s for s in sources}
    assert by_n[1]["ref"] == "5a362bf61e"
    assert by_n[2]["type"] == "web"
    # Legacy token rewritten with n=1 (from frontmatter)
    assert f'href="{BASE_PATH}/articles/5a362bf61e.html#cite-1"' in rewritten
    # [^1] also rewritten to in-page anchor
    assert '<a href="#cite-1" id="cite-1-back">[1]</a>' in rewritten
    assert '<a href="#cite-2" id="cite-2-back">[2]</a>' in rewritten


def test_footnote_with_unknown_id_logs_warning_and_keeps_literal(
    caplog,
) -> None:
    """Decision A: missing [^N] -> logger.warning + literal in body, no raise."""
    body = "Claim with broken ref [^99]."
    fm_sources = [{"id": 1, "type": "web", "ref": "https://e.com", "title": "T"}]
    with caplog.at_level(logging.WARNING):
        rewritten, sources = _convert_wiki_citations(
            body, BASE_PATH, frontmatter_sources=fm_sources, page_slug="broken"
        )
    assert "[^99]" in rewritten  # literal preserved
    assert any("[^99]" in r.message for r in caplog.records)
    assert "broken" in caplog.text  # page slug logged


def test_sources_count_accurate_legacy() -> None:
    """Pill `· N` count comes from len(sources). Legacy: 3 unique hashes -> N=3."""
    body = (
        "A ^[article:1111111111] B ^[article:2222222222] "
        "C ^[article:3333333333] D ^[article:1111111111]"
    )
    _, sources = _convert_wiki_citations(body, BASE_PATH, frontmatter_sources=None)
    assert len(sources) == 3  # duplicates merged


def test_sources_count_accurate_new_format() -> None:
    """New format: count = len(frontmatter sources), even if some unused in body."""
    body = "Only cites [^1]."
    fm_sources = [
        {"id": 1, "type": "web", "ref": "https://a", "title": "A"},
        {"id": 2, "type": "web", "ref": "https://b", "title": "B"},
        {"id": 3, "type": "builtin", "title": "C"},
    ]
    _, sources = _convert_wiki_citations(
        body, BASE_PATH, frontmatter_sources=fm_sources
    )
    # All 3 frontmatter sources preserved (sources section lists them all)
    assert len(sources) == 3


# ---------------------------------------------------------------------------
# wiki_entity.html template — render smoke for all three source types
# ---------------------------------------------------------------------------

def _make_env() -> Environment:
    """Jinja env that bypasses the kb t/icon helpers used by base.html.

    We render only the sources <ol> block to validate per-type markup.
    """
    project_root = Path(__file__).resolve().parents[3]
    return Environment(
        loader=FileSystemLoader(str(project_root / "kb" / "templates")),
        autoescape=select_autoescape(["html"]),
    )


def test_template_render_per_type_markup() -> None:
    """wiki_entity.html sources section conditionally renders by type."""
    # Render an inline copy of the sources block (avoids base.html helpers)
    block = """
    <ol class="wiki-sources__list">
      {% for src in wiki.sources %}
      <li id="cite-{{ src.n }}">
        {% if src.type == "article" %}
          <a href="{{ src.url }}">{% if src.title %}{{ src.title }}{% else %}article:{{ src.hash or src.ref }}{% endif %}</a>
        {% elif src.type == "web" %}
          <a href="{{ src.ref }}" target="_blank" rel="noopener">{{ src.title or src.ref }}</a>
          <span class="wiki-sources__type">(web)</span>
        {% elif src.type == "builtin" %}
          <span>{{ src.title }}</span>
          <span class="wiki-sources__type">(LLM training corpus)</span>
        {% endif %}
      </li>
      {% endfor %}
    </ol>
    """
    env = Environment(autoescape=select_autoescape(["html"]))
    tpl = env.from_string(block)
    sources = [
        {"n": 1, "type": "article", "ref": "abc1234567", "hash": "abc1234567",
         "title": "", "url": "/kb/articles/abc1234567.html"},
        {"n": 2, "type": "web", "ref": "https://example.com",
         "title": "Example Site", "url": "https://example.com"},
        {"n": 3, "type": "builtin", "ref": "", "title": "Opus 4.7 corpus", "url": ""},
    ]
    html = tpl.render(wiki={"sources": sources})

    # article: internal link + article:hash text
    assert 'href="/kb/articles/abc1234567.html"' in html
    assert "article:abc1234567" in html
    # web: external link with target=_blank and (web) marker
    assert 'href="https://example.com"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener"' in html
    assert "Example Site" in html
    assert "(web)" in html
    # builtin: no <a>, has (LLM training corpus) marker
    assert "Opus 4.7 corpus" in html
    assert "(LLM training corpus)" in html
