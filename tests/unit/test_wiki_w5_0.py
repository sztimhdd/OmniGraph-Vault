"""W5-0 regression tests: hash contract, convergence protection, health checker.

These tests anchor the observable behavior introduced or corrected in W5-0:
  - C1: batch_hashes use 10-char MD5 (article-identity contract)
  - C5: W1-rich pages protected from W3 overwrite (convergence)

W5A Task 4 (2026-08-11): convergence protection moved from the W1-richness
heuristic to the shared compiler engine — ANY existing page is classified
``suggestion_only`` for substantive updates, so the heuristic
(``_page_is_w1_rich``) was deleted. The apply-suggestion tests below now
anchor the new behavioral contract: existing pages are never overwritten
and updates become deterministic structured JSON suggestions
(``_suggestions/<slug>-<patch-id>.json``), while new pages are created
canonically (typed ``sources[]`` + GFM footnotes).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from kb.wiki_compiler.models import page_digest
from kb.wiki_update import apply_suggestion_atomic
from scripts.wiki_health import run_health


# ── C1 regression: article-identity hash contract ──

def test_batch_hashes_are_10_char_md5():
    """batch_ingest_from_spider must use 10-char MD5(url) not 16-char SHA256."""
    import hashlib
    url = "https://mp.weixin.qq.com/s/test"
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    assert len(h) == 10
    assert all(c in "0123456789abcdef" for c in h)

    # Checkpoint hash (different domain) stays 16-char for file I/O
    from lib.checkpoint import get_article_hash
    ckpt = get_article_hash(url)
    assert len(ckpt) == 16
    assert ckpt != h


# ── C5 regression: W1-rich page protection (W5A: engine-policy anchored) ──

_RICH_PAGE = """---
title: "Hermes"
created: "2026-05-20"
last_updated: "2026-05-20"
sources:
  - type: article
    ref: "aaaaaaaaaa"
    title: "aaaaaaaaaa"
    provenance: w3-entity-buffer
  - type: article
    ref: "bbbbbbbbbb"
    title: "bbbbbbbbbb"
    provenance: w3-entity-buffer
  - type: article
    ref: "cccccccccc"
    title: "cccccccccc"
    provenance: w3-entity-buffer
confidence_level: high
---

# Hermes

## Definition / Overview

A detailed W1 synthesis paragraph with three citations. [^1][^2][^3]

## References

[^1]: **aaaaaaaaaa** — aaaaaaaaaa (w3-entity-buffer)
[^2]: **bbbbbbbbbb** — bbbbbbbbbb (w3-entity-buffer)
[^3]: **cccccccccc** — cccccccccc (w3-entity-buffer)
""" + ("\n\n" + "X" * 500)


def _seed_db(hashes: list[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    for h in hashes:
        conn.execute("INSERT INTO articles VALUES (?)", (h,))
    conn.commit()
    return conn


def test_apply_suggestion_existing_page_becomes_structured_suggestion(tmp_path: Path):
    """W5A: updating an existing page never overwrites it — the shared engine
    classifies it suggestion_only and persists a deterministic structured
    suggestion JSON. No timestamped .md suggestions under W5A."""
    wiki_root = tmp_path / "wiki"
    entities_dir = wiki_root / "entities"
    entities_dir.mkdir(parents=True)
    (entities_dir / "hermes.md").write_text(_RICH_PAGE, encoding="utf-8")
    before = page_digest(_RICH_PAGE)

    conn = _seed_db(["aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc"])

    suggestion = {
        "type": "update",
        "entity_slug": "hermes",
        "page_path": str(entities_dir / "hermes.md"),
        "content": "legacy placeholder body (ignored under W5A)",
        "source_articles": ["aaaaaaaabb"],
    }
    result = apply_suggestion_atomic(suggestion, conn, wiki_root=wiki_root)
    # Not applied — saved as a structured suggestion for later processing.
    assert result is False
    assert page_digest((entities_dir / "hermes.md").read_text(encoding="utf-8")) == before

    sugg_dir = wiki_root / "_suggestions"
    assert sugg_dir.exists()
    suggestions = list(sugg_dir.glob("hermes-wpatch-*.json"))
    assert len(suggestions) == 1
    assert list(sugg_dir.glob("*.md")) == []  # timestamped .md format retired
    payload = json.loads(suggestions[0].read_text(encoding="utf-8"))
    assert payload["target_slug"] == "hermes"
    assert payload["patch_id"].startswith("wpatch-")
    assert "suggested_content" in payload


def test_apply_suggestion_creates_new_page_canonically(tmp_path: Path):
    """W5A: new pages are created by the shared compiler in canonical format
    (typed sources[] + GFM citations), not legacy placeholders."""
    wiki_root = tmp_path / "wiki"
    entities_dir = wiki_root / "entities"
    entities_dir.mkdir(parents=True)

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    conn.commit()

    suggestion = {
        "type": "new",
        "entity_slug": "new-entity",
        "page_path": str(entities_dir / "new-entity.md"),
        "content": "legacy placeholder (ignored under W5A)",
        "source_articles": ["0000000000"],
    }
    result = apply_suggestion_atomic(suggestion, conn, wiki_root=wiki_root)
    # New pages get created via engine auto_apply.
    assert result is True
    page = entities_dir / "new-entity.md"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "    type: article" in text
    assert "^[article:" not in text
    # New-page creation never produces a suggestion file.
    assert not (wiki_root / "_suggestions").exists()


# ── C2 regression: health checker detects bad fixtures ──

def test_health_checker_detects_missing_frontmatter(tmp_path: Path):
    """Bad page with missing frontmatter fields returns errors."""
    entities = tmp_path / "entities"
    entities.mkdir(parents=True)
    (entities / "bad.md").write_text("""---
title: Bad
---
No required fields.
""", encoding="utf-8")
    findings = run_health(tmp_path)
    assert len(findings["errors"]) >= 1
    assert any("missing frontmatter" in e for e in findings["errors"])


def test_health_checker_detects_broken_wikilink(tmp_path: Path):
    """Page linking to nonexistent target returns warn."""
    entities = tmp_path / "entities"
    entities.mkdir(parents=True)
    (entities / "linker.md").write_text("""---
title: Linker
created: 2026-06-01
last_updated: 2026-06-01
sources: []
confidence_level: low
---

See [[nonexistent-target]] for more.
""", encoding="utf-8")
    findings = run_health(tmp_path)
    assert any("broken wikilink" in w for w in findings["warns"])


def test_health_checker_clean_passes(tmp_path: Path):
    """Clean page with correct fields returns no errors."""
    entities = tmp_path / "entities"
    entities.mkdir(parents=True)
    (entities / "clean.md").write_text("""---
title: Clean Page
created: 2026-06-01
last_updated: 2026-08-01
sources:
  - id: 1
    type: article
    ref: 0000000000
    title: Source
confidence_level: high
---

# Clean Page

Body text. [^1]
""", encoding="utf-8")
    findings = run_health(tmp_path)
    assert len(findings["errors"]) == 0
    assert findings["summary"]["pages_checked"] == 1


# ── FINDING 1 regression: entity buffer path resolution ──

def test_canonical_buffer_path_is_first(monkeypatch):
    """Canonical ~/.hermes/omonigraph-vault/entity_buffer is first in search order."""
    # Reload module after monkeypatching env
    import importlib
    import kb.wiki_update as wu

    # Simulate production: OMNIGRAPH_BASE_DIR unset
    monkeypatch.delenv("OMNIGRAPH_BASE_DIR", raising=False)
    importlib.reload(wu)
    assert wu.DEFAULT_BUFFER_DIRS[0].name == "entity_buffer"
    assert ".hermes" in str(wu.DEFAULT_BUFFER_DIRS[0])
    assert "omonigraph-vault" in str(wu.DEFAULT_BUFFER_DIRS[0])


def test_canonical_buffer_respects_env_override(monkeypatch, tmp_path: Path):
    """When OMNIGRAPH_BASE_DIR is set, canonical buffer uses it."""
    import importlib
    import kb.wiki_update as wu

    custom_base = tmp_path / "custom-omnigraph"
    custom_base.mkdir()
    monkeypatch.setenv("OMNIGRAPH_BASE_DIR", str(custom_base))
    importlib.reload(wu)
    assert str(wu.DEFAULT_BUFFER_DIRS[0]) == str(custom_base / "entity_buffer")


def test_buffer_search_finds_canonical_entities(monkeypatch, tmp_path: Path):
    """generate_wiki_suggestions uses canonical buffer when entities exist there."""
    import importlib
    import kb.wiki_update as wu

    # Set up canonical buffer with one entity
    buf_dir = tmp_path / "prod-buffer"
    buf_dir.mkdir(parents=True)
    monkeypatch.setattr(wu, "DEFAULT_BUFFER_DIRS", [buf_dir])

    # Create entity buffer for a hash
    hash10 = "aaaaaaaaab"
    entities = {"raw_entities": [{"name": "Test Entity"}, {"name": "Another Thing"}]}
    (buf_dir / f"{hash10}_entities.json").write_text(json.dumps(entities))

    # Seed DB with matching hash
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO articles VALUES (?)", (hash10,))
    conn.commit()

    suggestions = wu.generate_wiki_suggestions(
        [hash10],
        wiki_root=tmp_path / "wiki",
        db_conn=conn,
        min_frequency=1,
    )
    assert len(suggestions) == 2  # one per entity name
    slugs = {s["entity_slug"] for s in suggestions}
    assert "test-entity" in slugs
    assert "another-thing" in slugs


def test_buffer_not_found_still_falls_back_to_local(monkeypatch, tmp_path: Path):
    """When canonical buffer has no matching file, local dirs are tried."""
    import importlib
    import kb.wiki_update as wu

    canonical = tmp_path / "canonical-empty"
    canonical.mkdir()
    local_buf = tmp_path / "local-buf"
    local_buf.mkdir(parents=True)

    monkeypatch.setattr(wu, "DEFAULT_BUFFER_DIRS", [canonical, local_buf])

    hash10 = "bbbbbbbbbc"
    entities = {"raw_entities": [{"name": "Local Entity"}]}
    (local_buf / f"{hash10}_entities.json").write_text(json.dumps(entities))

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO articles VALUES (?)", (hash10,))
    conn.commit()

    suggestions = wu.generate_wiki_suggestions(
        [hash10],
        wiki_root=tmp_path / "wiki",
        db_conn=conn,
        min_frequency=1,
    )
    assert len(suggestions) == 1
    assert suggestions[0]["entity_slug"] == "local-entity"
