"""Unit tests for kb/wiki_lint.py — W3 of llm-wiki-integration.

Tests pin observable behavior with hand-computed expectations
(per feedback_test_mirrors_impl.md). No formula re-imported from impl.
"""
from datetime import date
from pathlib import Path

import pytest

from kb.wiki_lint import (
    lint_backlink_validity,
    lint_citation_integrity,
    lint_contradicts_existing,
    lint_staleness,
    log_lint_failure,
)


def test_unresolved_citation(tmp_path: Path) -> None:
    """Legacy ^[article:<hex>] form: hash MUST resolve in corpus."""
    page = tmp_path / "p.md"
    page.write_text(
        "OpenClaw shipped ^[article:1234567890].\n"
        "Hermes followed ^[article:deadbeef00].\n",
        encoding="utf-8",
    )
    failures = lint_citation_integrity(page, known_article_hashes={"1234567890"})
    assert failures == ["^[article:deadbeef00]"]


def test_footnote_citation_resolves_via_frontmatter(tmp_path: Path) -> None:
    """New [^N] form: every N must match a frontmatter sources[].id; type=article ref must be in corpus."""
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "title: Test\n"
        "sources:\n"
        "  - id: 1\n"
        "    type: article\n"
        "    ref: 1234567890\n"
        "    title: Real corpus article\n"
        "  - id: 2\n"
        "    type: web\n"
        "    ref: https://example.com\n"
        "    title: External page\n"
        "  - id: 3\n"
        "    type: builtin\n"
        "    title: Opus training\n"
        "---\n\n"
        "Citation to corpus article [^1].\n"
        "Citation to web page [^2].\n"
        "Citation to builtin [^3].\n"
        "Citation to nowhere [^99].\n",
        encoding="utf-8",
    )
    failures = lint_citation_integrity(page, known_article_hashes={"1234567890"})
    # [^1], [^2], [^3] all resolve. [^99] fails as id-not-in-frontmatter.
    assert len(failures) == 1
    assert "[^99]" in failures[0]


def test_footnote_article_ref_must_be_in_corpus(tmp_path: Path) -> None:
    """type=article frontmatter entry whose ref isn't in corpus → flagged."""
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "title: Test\n"
        "sources:\n"
        "  - id: 1\n"
        "    type: article\n"
        "    ref: deadbeef00\n"
        "    title: Hallucinated corpus article\n"
        "---\n\n"
        "Body cites the made-up article [^1].\n",
        encoding="utf-8",
    )
    failures = lint_citation_integrity(page, known_article_hashes={"1234567890"})
    assert any("not in corpus" in f for f in failures)


def test_contradicts_existing(tmp_path: Path) -> None:
    existing = tmp_path / "openclaw.md"
    existing.write_text("OpenClaw Project was founded in 2024.\n", encoding="utf-8")
    suggestion = "OpenClaw Project was founded in 2026."
    failures = lint_contradicts_existing(suggestion, existing)
    assert len(failures) >= 1
    assert "2024" in failures[0] and "2026" in failures[0]


def test_backlink_validity(tmp_path: Path) -> None:
    (tmp_path / "entities").mkdir()
    (tmp_path / "entities" / "hermes-agent.md").write_text("stub", encoding="utf-8")
    suggestion = "See [[hermes-agent]] and [[unknown-entity]]."
    failures = lint_backlink_validity(suggestion, tmp_path)
    assert failures == ["unknown-entity"]


def test_staleness_check(tmp_path: Path) -> None:
    page = tmp_path / "old.md"
    page.write_text(
        "---\ntitle: Old\nlast_updated: 2024-01-01\n---\nbody\n",
        encoding="utf-8",
    )
    today = date(2026, 5, 19)
    fails_short = lint_staleness(page, max_days=180, today=today)
    assert len(fails_short) == 1 and "stale" in fails_short[0]
    fails_long = lint_staleness(page, max_days=10000, today=today)
    assert fails_long == []


def test_log_lint_failure_appends_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_path = tmp_path / "out.jsonl"
    import kb.wiki_lint as wl

    monkeypatch.setattr(wl, "JSONL_LOG_PATH", log_path)
    log_lint_failure({"page_path": "x.md", "lint_name": "citation", "failures": ["^[article:0000000000]"]})
    log_lint_failure({"page_path": "y.md", "lint_name": "backlink", "failures": ["dangling"]})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json
    obj0 = json.loads(lines[0])
    assert obj0["lint_name"] == "citation" and "ts" in obj0
