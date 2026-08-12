"""W5B Task 4 tests: normal evolution worker — queue scan, source-aware
hydration, strict one-call semantic evaluator, CLI plumbing.

Behavior anchors from docs/superpowers/plans/2026-08-12-omnigraph-wiki-v2-w5b-autonomous-evolution.md
Task 4 (lines 554-714) and the W5B design doc (§7, §9):

- missing `evolution` behaves pending; pending due immediately; retry
  before `next_retry_at` skipped; at/after due; terminal statuses skipped;
- `--limit N` counts eligible attempts, not terminal/skipped files;
- the suggestion file itself is the worker identity (no timestamp files);
- `--dry-run` never mutates suggestion bytes and never lazily writes a
  missing pending evolution state;
- source-aware hydration via kb.wiki_articles (local-only, no network);
- strict semantic parser: JSON object, decision in {APPLY, RETRY, REJECT},
  APPLY requires non-empty sections with heading+content; no confidence
  policy channel;
- citation mapping mirrors the W5A `_merge_sources()` append ids
  (len(existing_sources)+1...) and legacy `^[article:<ref>]` tokens;
- exactly one DeepSeek call per evaluated suggestion; provider/parse
  failure -> retryable semantic result; deepseek import stays lazy.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kb.wiki_articles import canonical_article_ref
from kb.wiki_compiler.models import (
    EvidenceRef,
    PatchOperation,
    WikiPatch,
    page_digest,
)

_EPOCH = "2026-08-11T00:00:00Z"

FRESH_EVOLUTION = {
    "status": "pending",
    "attempts": 0,
    "next_retry_at": None,
    "last_evaluated_at": None,
    "last_decision": None,
    "last_reason": None,
    "applied_patch_id": None,
}

CANONICAL_PAGE = """---
title: 'Python Debugging'
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
  - id: 1
    type: article
    ref: 'abcdef1234'
    title: 'Existing Source'
    provenance: lightrag-corpus
confidence_level: low
---

# Python Debugging

## Definition / Overview

Old section body [^1]

## References

[^1]: **Existing Source** — abcdef1234 (lightrag-corpus)
"""

LEGACY_PAGE = """---
title: 'Python Debugging'
created: '2026-05-20'
last_updated: '2026-05-20'
sources:
  - article:abcdef1234
confidence_level: low
---

# Python Debugging

## Definition / Overview

Old section body ^[article:abcdef1234]
"""


def _ref(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:10]


@pytest.fixture
def wiki_root(tmp_path: Path) -> Path:
    """Repo-shaped tmp wiki root (kb/wiki/{entities,_suggestions})."""
    root = tmp_path / "repo"
    (root / "kb" / "wiki" / "entities").mkdir(parents=True)
    (root / "kb" / "wiki" / "_suggestions").mkdir(parents=True)
    return root


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory DB with production-shaped article tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            title_translated TEXT,
            body TEXT,
            summary TEXT,
            content_hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT,
            summary TEXT,
            content_hash TEXT
        )
        """
    )
    return conn


def _make_patch(
    *,
    slug: str = "python-debugging",
    patch_id: str = "wpatch-w5b-t4-0001",
    evidence: tuple | None = None,
    target_path: str | None = None,
) -> WikiPatch:
    """Build a valid suggestion-bound WikiPatch (UPSERT_SECTION).

    ``target_path`` defaults to the real W3 contract shape — the
    wiki-relative ``entities/<slug>.md`` form produced by
    ``engine_ready_patch`` (the suggestion serializer stores the
    engine-ready patch, whose target paths are relative to the wiki
    directory, not the repo root)."""
    if evidence is None:
        evidence = (
            EvidenceRef(
                evidence_id="e1", type="article", ref="abcdef1234",
                title="abcdef1234", provenance="lightrag-corpus",
                metadata={"source": "rss"},
            ),
        )
    ops = (
        PatchOperation(
            op="UPSERT_SECTION", section="Definition / Overview",
            content="Suggested body [^1]", metadata=None,
        ),
    )
    return WikiPatch(
        patch_schema_version=1,
        patch_id=patch_id,
        target_slug=slug,
        target_path=target_path or f"entities/{slug}.md",
        target_kind="entity",
        base_digest=page_digest(CANONICAL_PAGE),
        trigger="test",
        evidence_pack_id="pack-1",
        operations=ops,
        evidence=evidence,
        policy_hint="suggestion_only",
        reason="test patch",
        created_at=_EPOCH,
        compiler_version="v2.0-w5a",
    )


def _write_page(wiki_root: Path, slug: str, content: str) -> Path:
    target = wiki_root / "kb" / "wiki" / "entities" / f"{slug}.md"
    target.write_text(content, encoding="utf-8")
    return target


def _write_suggestion(
    wiki_root: Path,
    patch: WikiPatch,
    *,
    evolution: dict | None = None,
) -> Path:
    """Write a suggestion JSON in the engine's exact payload shape.

    ``evolution`` omitted -> the W5A-era payload shape (no evolution key),
    i.e. a missing evolution state that must behave as pending.
    """
    path = wiki_root / "kb" / "wiki" / "_suggestions" / f"{patch.target_slug}-{patch.patch_id}.json"
    payload = {
        "patch": patch.to_dict(),
        "policy_hint": "suggestion_only",
        "reason": patch.reason,
        "suggested_content": "Suggested body [^1]\n",
        "patch_id": patch.patch_id,
        "target_slug": patch.target_slug,
        "operations": [o.__dict__ for o in patch.operations],
        "evidence": [e.__dict__ for e in patch.evidence],
    }
    if evolution is not None:
        payload["evolution"] = evolution
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _retry_state(*, attempts: int, next_retry_at: str | None) -> dict:
    return {
        "status": "retry",
        "attempts": attempts,
        "next_retry_at": next_retry_at,
        "last_evaluated_at": "2026-08-12T02:00:00Z",
        "last_decision": "retry",
        "last_reason": "transient LLM failure",
        "applied_patch_id": None,
    }


def _terminal_state(status: str) -> dict:
    return {
        "status": status,
        "attempts": 3,
        "next_retry_at": None,
        "last_evaluated_at": "2026-08-12T02:00:00Z",
        "last_decision": status,
        "last_reason": "terminal",
        "applied_patch_id": None if status != "applied" else "wpatch-applied-1",
    }


# ---------------------------------------------------------------------------
# 4.1 queue/state: helpers
# ---------------------------------------------------------------------------

def test_default_evolution_state_matches_design_7() -> None:
    """``default_evolution_state`` returns exactly the design §7 fresh
    object (status=pending, attempts=0, every lifecycle field null) and a
    fresh copy per call."""
    from scripts.wiki_evolve import default_evolution_state

    assert default_evolution_state() == FRESH_EVOLUTION
    a = default_evolution_state()
    a["attempts"] = 99
    assert default_evolution_state()["attempts"] == 0


def test_is_due_missing_pending_and_retry_timing() -> None:
    """Missing `evolution` behaves pending (due immediately); pending is due
    immediately; retry before ``next_retry_at`` is skipped, at/after due."""
    from scripts.wiki_evolve import is_due

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    # missing evolution (None) -> pending -> due immediately
    assert is_due(None, now) is True
    # pending -> due immediately
    assert is_due({"status": "pending", "attempts": 0, "next_retry_at": None}, now) is True
    # retry before next_retry_at -> skipped
    before = _retry_state(attempts=1, next_retry_at="2026-08-13T06:00:00Z")
    assert is_due(before, now) is False
    # retry exactly at next_retry_at -> due
    at = _retry_state(attempts=1, next_retry_at="2026-08-12T12:00:00Z")
    assert is_due(at, now) is True
    # retry after next_retry_at -> due
    after = _retry_state(attempts=2, next_retry_at="2026-08-12T06:00:00Z")
    assert is_due(after, now) is True


def test_is_due_terminal_statuses_skipped() -> None:
    """rejected/applied/superseded are terminal: never due again."""
    from scripts.wiki_evolve import is_due

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    for status in ("rejected", "applied", "superseded"):
        assert is_due(_terminal_state(status), now) is False, status


def test_retry_delay_schedule() -> None:
    """attempt 1 -> +1 day; attempt 2 -> +3 days; attempt >=3 -> +7 days."""
    from scripts.wiki_evolve import retry_delay

    assert retry_delay(1) == timedelta(days=1)
    assert retry_delay(2) == timedelta(days=3)
    assert retry_delay(3) == timedelta(days=7)
    assert retry_delay(7) == timedelta(days=7)
    # zero/negative attempts are before any real attempt: minimal delay
    assert retry_delay(0) == timedelta(days=1)


# ---------------------------------------------------------------------------
# 4.1 queue/state: worker scan
# ---------------------------------------------------------------------------

def test_worker_scan_sorted_deterministic_and_eligibility(wiki_root: Path) -> None:
    """Dry-run worker scans ``kb/wiki/_suggestions/*.json`` in sorted order;
    missing evolution behaves pending (eligible), retry-before and terminal
    states are skipped, and nothing is written."""
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    p_pending = _write_suggestion(  # missing evolution -> pending
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa")
    )
    p_terminal = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-bbb"),
        evolution=_terminal_state("rejected"),
    )
    p_notdue = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-ccc"),
        evolution=_retry_state(attempts=1, next_retry_at="2099-01-01T00:00:00Z"),
    )

    report = run_worker(wiki_root, now=now, dry_run=True)

    assert report["scanned"] == 3
    assert report["eligible"] == [str(p_pending)]
    assert sorted(report["skipped"]) == sorted([str(p_terminal), str(p_notdue)])
    assert report["attempted"] == [str(p_pending)]
    assert report["outcomes"] == {}


def test_worker_limit_counts_eligible_attempts_only(wiki_root: Path) -> None:
    """``--limit N`` caps eligible attempts in sorted order — terminal and
    skipped files never count toward the limit."""
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    # two terminal files
    _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa"),
        evolution=_terminal_state("applied"),
    )
    _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-bbb"),
        evolution=_terminal_state("superseded"),
    )
    # three eligible (missing evolution -> pending)
    p_ccc = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-ccc"))
    p_ddd = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-ddd"))
    p_eee = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-eee"))

    report = run_worker(wiki_root, now=now, dry_run=True, limit=2)
    assert report["scanned"] == 5
    assert report["attempted"] == [str(p_ccc), str(p_ddd)]  # first 2 eligible, sorted
    assert len(report["skipped"]) == 2  # the terminal files
    assert report["outcomes"] == {}

    # without a limit every eligible file is attempted
    unlimited = run_worker(wiki_root, now=now, dry_run=True)
    assert unlimited["attempted"] == [str(p_ccc), str(p_ddd), str(p_eee)]


def test_dry_run_no_mutation_no_lazy_state_no_new_files(wiki_root: Path) -> None:
    """Dry-run: suggestion bytes byte-for-byte untouched, no lazily written
    pending evolution state for W5A-era payloads, and no new timestamp
    files — the suggestion file itself is the worker identity."""
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    p_w5a = _write_suggestion(  # W5A-era payload: no evolution key
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa")
    )
    p_retry = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-bbb"),
        evolution=_retry_state(attempts=1, next_retry_at="2026-08-12T06:00:00Z"),
    )
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    report = run_worker(wiki_root, now=now, dry_run=True)

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert set(after) == set(before), "worker must never create new files"
    for name, data in before.items():
        assert after[name] == data, f"suggestion bytes changed: {name}"
    # the missing pending evolution state was NOT lazily written
    assert "evolution" not in json.loads(p_w5a.read_text(encoding="utf-8"))
    assert json.loads(p_retry.read_text(encoding="utf-8"))["evolution"]["status"] == "retry"
    assert report["outcomes"] == {}


# ---------------------------------------------------------------------------
# 4.2 source-aware hydration
# ---------------------------------------------------------------------------

def test_hydration_rss_evidence_real_title_text_ref_metadata(conn: sqlite3.Connection) -> None:
    """Given an old W3-style suggestion evidence (title == bare ref
    placeholder, metadata source rss), hydration replaces the placeholder
    with the local real title and body/summary text; the canonical ref and
    the source metadata are preserved."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import hydrate_evidence

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)

    evidence = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref, title=ref,
            provenance="lightrag-corpus", metadata={"source": "rss"},
        ),
    )
    result = hydrate_evidence(evidence, index)

    assert result["status"] == "ready"
    hydrated = result["evidence"]
    assert len(hydrated) == 1
    assert hydrated[0]["title"] == "Real RSS Title"  # placeholder replaced
    assert hydrated[0]["text"] == "Real RSS summary body."  # local body/summary
    assert hydrated[0]["ref"] == ref  # canonical ref unchanged
    assert hydrated[0]["metadata"] == {"source": "rss"}  # source metadata preserved
    assert hydrated[0]["type"] == "article"


def test_hydration_source_less_evidence_unambiguous_resolves_ambiguous_retries(
    conn: sqlite3.Connection,
) -> None:
    """Old W3 evidence without ``metadata.source`` resolves only when exactly
    one local row matches the ref; multiple matches produce an explicit
    retryable ambiguity outcome — the worker never guesses."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import hydrate_evidence

    url = "https://example.com/shared-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "RSS Copy", "RSS summary.", "a" * 32),
    )
    index = load_article_index(conn)
    evidence = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref, title=ref,
            provenance="lightrag-corpus", metadata={},
        ),
    )

    # unambiguous single match (source-less) -> ready
    result = hydrate_evidence(evidence, index)
    assert result["status"] == "ready"
    assert result["evidence"][0]["title"] == "RSS Copy"
    assert result["evidence"][0]["metadata"] == {}

    # same ref now ingested from a second source -> ambiguous -> retry
    conn.execute(
        "INSERT INTO articles (id, url, title, body, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Articles Copy", "Articles body.", "b" * 32),
    )
    index2 = load_article_index(conn)
    result2 = hydrate_evidence(evidence, index2)
    assert result2["status"] == "retry"
    assert "ambiguous" in result2["reason"]

    # no local row at all -> missing -> retry
    result3 = hydrate_evidence(evidence, {})
    assert result3["status"] == "retry"
    assert "missing local evidence" in result3["reason"]


def test_hydration_fixed_character_caps_enforced(conn: sqlite3.Connection) -> None:
    """MAX_ARTICLE_CHARS truncates each article body and
    MAX_TOTAL_EVIDENCE_CHARS caps the combined evidence budget (earlier
    evidence keeps its full capped text, later items are trimmed) — the
    only caps, no token-budget framework."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import (
        MAX_ARTICLE_CHARS,
        MAX_TOTAL_EVIDENCE_CHARS,
        hydrate_evidence,
    )

    long_body = "z" * (MAX_ARTICLE_CHARS + 500)
    for i in range(5):
        url = f"https://example.com/cap-article-{i}"
        conn.execute(
            "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
            (i + 1, url, f"Cap Article {i}", long_body, f"{i}" * 32),
        )
    index = load_article_index(conn)
    evidence = tuple(
        EvidenceRef(
            evidence_id=f"e{i}", type="article", ref=_ref(f"https://example.com/cap-article-{i}"),
            title=f"Cap Article {i}", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        )
        for i in range(5)
    )

    result = hydrate_evidence(evidence, index)

    assert result["status"] == "ready"
    texts = [e["text"] for e in result["evidence"]]
    # per-article cap
    assert texts[0] == long_body[:MAX_ARTICLE_CHARS]
    assert len(texts[0]) == MAX_ARTICLE_CHARS
    # total cap: 5 x MAX_ARTICLE_CHARS > MAX_TOTAL_EVIDENCE_CHARS, so the
    # last item is trimmed to nothing; earlier items keep their capped text
    assert [len(t) for t in texts] == [MAX_ARTICLE_CHARS] * 4 + [0]
    assert sum(len(t) for t in texts) <= MAX_TOTAL_EVIDENCE_CHARS


def test_hydration_is_local_only_no_network_imports(conn: sqlite3.Connection, monkeypatch) -> None:
    """Hydration is a pure local path: with every network-capable module
    poisoned in ``sys.modules`` (import would raise), hydration still works
    — proving no web/Tavily/provider call can happen during hydration."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import hydrate_evidence

    url = "https://example.com/rss/local-only"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Local Title", "Local summary.", "y" * 32),
    )
    index = load_article_index(conn)
    evidence = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref, title=ref,
            provenance="lightrag-corpus", metadata={"source": "rss"},
        ),
    )

    poisoned = {}
    for mod in ("lib.llm_deepseek", "openai", "httpx", "requests", "tavily"):
        poisoned[mod] = sys.modules.get(mod)
        sys.modules[mod] = None  # any import of this module now raises
    try:
        result = hydrate_evidence(evidence, index)
    finally:
        for mod, saved in poisoned.items():
            if saved is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = saved

    assert result["status"] == "ready"
    assert result["evidence"][0]["title"] == "Local Title"


def test_worker_evaluates_with_exactly_one_call_and_fresh_page(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A hydration-ready suggestion is evaluated with exactly one injected
    provider call; the prompt carries the current page read FRESH from disk
    (the payload's ``suggested_content`` is never used as authority), and
    the outcome is reported without writing anything."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import SYSTEM_PROMPT, run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    evidence = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref, title=ref,
            provenance="lightrag-corpus", metadata={"source": "rss"},
        ),
    )
    patch = _make_patch(patch_id="wpatch-w5b-t4-aaa", evidence=evidence)
    path = _write_suggestion(wiki_root, patch)
    # poison the payload's suggested_content: it must never reach the prompt
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["suggested_content"] = "STALE SUGGESTED CONTENT, NOT the authority"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # the page on disk is the authority
    _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    before = path.read_bytes()

    calls: list[tuple[str, str | None]] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append((prompt, system_prompt))
        return json.dumps({
            "decision": "APPLY",
            "reason": "evidence supports",
            "sections": [{"heading": "Definition / Overview", "content": "New body [^1]"}],
        })

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["attempted"] == [str(path)]
    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "evaluated"
    assert outcome["decision"] == "APPLY"
    assert outcome["reason"] == "evidence supports"
    assert len(outcome["sections"]) == 1
    assert len(calls) == 1, "exactly one evaluator call per eligible suggestion"
    prompt, system_prompt = calls[0]
    assert system_prompt == SYSTEM_PROMPT
    assert "Old section body [^1]" in prompt  # fresh disk page, not suggested_content
    assert "STALE SUGGESTED CONTENT" not in prompt
    assert "Real RSS Title" in prompt  # hydrated real title
    assert "Real RSS summary body." in prompt
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_provider_exception_retryable_exactly_one_call(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A provider exception/timeout is a retryable outcome: exactly one
    call was made, no retry inside the same attempt, no second judge, and
    nothing is written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    before = path.read_bytes()

    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        raise RuntimeError("provider timeout")

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "retry"
    assert "evaluator call failed" in outcome["reason"]
    assert len(calls) == 1, "no second call after a provider failure"
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_malformed_evaluator_output_retryable_exactly_one_call(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """Malformed evaluator output is a retryable outcome: exactly one call
    was made, the strict parser's rejection is surfaced (no immediate
    repeat, no second judge), and nothing is written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    before = path.read_bytes()

    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return "```markdown\nSome prose, not JSON\n```"

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "retry"
    assert "malformed evaluator response" in outcome["reason"]
    assert len(calls) == 1, "no immediate repeat after a malformed response"
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_missing_current_page_retryable_no_provider_call(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A suggestion whose target page cannot be read fresh from disk is a
    retryable pre-evaluation outcome — the evaluator is never invoked and
    nothing is written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    # NOTE: no page is written on disk — the target entity is missing
    before = path.read_bytes()

    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "retry"
    assert "cannot read current page" in outcome["reason"]
    assert calls == [], "no provider call when the current page is unreadable"
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_malicious_target_slug_reads_only_valid_target_path_page(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A serialized patch whose ``target_slug`` is a path-traversal string
    but whose compiler-validated ``target_path`` is benign must evaluate
    ONLY against the ``target_path`` page: the injected evaluator prompt
    carries the valid page's marker and NEVER content from the file the
    malicious slug would resolve to outside the page tree (WikiPatch
    validates ``target_path`` but not ``target_slug`` — the payload is
    untrusted input)."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    # Adversarial payload: the suggestion filename / scan identity stays
    # benign, but the serialized patch's target_slug (NOT validated by
    # WikiPatch) escapes the page tree — 4 `..` from
    # kb/wiki/entities/ resolves to wiki_root.parent/outside-secret.md.
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["patch"]["target_slug"] = "../../../../outside-secret"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # The valid target_path page exists on disk; an "external" file sits
    # exactly where the malicious slug would resolve.
    _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    secret = wiki_root.parent / "outside-secret.md"
    secret.write_text(
        "TOPSECRET EXTERNAL MARKER, never part of the wiki\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    calls: list[tuple[str, str | None]] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append((prompt, system_prompt))
        return json.dumps({
            "decision": "APPLY",
            "reason": "evidence supports",
            "sections": [{"heading": "Definition / Overview", "content": "New body [^1]"}],
        })

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["attempted"] == [str(path)]
    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "evaluated"
    assert len(calls) == 1, "exactly one evaluator call per eligible suggestion"
    prompt, system_prompt = calls[0]
    assert "Old section body [^1]" in prompt, (
        "the current-page read must use the compiler-validated target_path page"
    )
    assert "TOPSECRET EXTERNAL MARKER" not in prompt, (
        "a malicious target_slug must never read outside the target_path page"
    )
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_w3_wiki_relative_target_path_reads_real_page_once(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A W3-era suggestion whose serialized patch carries the WIKI-RELATIVE
    ``target_path="entities/<slug>.md"`` form (no ``kb/wiki/`` prefix) is
    resolved against the ACTUAL wiki root (``<wiki_root>/kb/wiki``) even
    when the CLI ``wiki_root`` is the repo root: the evaluator receives
    the REAL page exactly once, and a same-named decoy at the repo root
    (where the un-normalized resolution would land) is never read."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        target_path=f"entities/{_make_patch().target_slug}.md",  # W3 wiki-relative form
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    # Decoy exactly where the un-normalized repo-root resolution lands
    # (<wiki_root>/entities/<slug>.md — outside kb/wiki).
    decoy_dir = wiki_root / "entities"
    decoy_dir.mkdir()
    decoy = decoy_dir / f"{patch.target_slug}.md"
    decoy.write_text(
        "WRONG LOCATION DECOY, must never reach the evaluator\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    calls: list[tuple[str, str | None]] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append((prompt, system_prompt))
        return json.dumps({
            "decision": "APPLY",
            "reason": "evidence supports",
            "sections": [{"heading": "Definition / Overview", "content": "New body [^1]"}],
        })

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["attempted"] == [str(path)]
    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "evaluated"
    assert outcome["decision"] == "APPLY"
    assert len(calls) == 1, "exactly one evaluator call per eligible suggestion"
    prompt, _ = calls[0]
    assert "Old section body [^1]" in prompt, (
        "the W3 wiki-relative target_path must read the REAL page under kb/wiki"
    )
    assert "WRONG LOCATION DECOY" not in prompt, (
        "a repo-root decoy must never be read for a wiki-relative target_path"
    )
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_outside_wiki_root_target_path_integrity_no_evaluator(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A serialized patch whose WikiPatch-valid ``target_path`` (non-absolute,
    no ``..``, ends ``.md``) resolves OUTSIDE the actual wiki root (e.g.
    ``scripts/secret.md`` -> ``<wiki_root>/scripts/secret.md`` while the
    wiki tree is ``<wiki_root>/kb/wiki``) is a NON-ATTEMPT integrity
    descriptor — the outside file is never read, the evaluator is never
    called, and nothing is written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        target_path="scripts/secret.md",  # WikiPatch-valid, but outside kb/wiki
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    # The "secret" file sits exactly where the un-normalized repo-root
    # resolution would read it — outside the wiki tree.
    secret = wiki_root / "scripts" / "secret.md"
    secret.parent.mkdir()
    secret.write_text(
        "TOPSECRET EXTERNAL MARKER, never part of the wiki\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    calls: list[tuple[str, str | None]] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append((prompt, system_prompt))
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "integrity"
    assert outcome["attempt"] is False
    assert "outside the wiki root" in outcome["reason"]
    assert "scripts/secret.md" in outcome["reason"]
    assert calls == [], "an outside-root target path must never reach the evaluator"
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_symlink_escape_target_path_integrity_sibling_evaluated(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A serialized patch whose WikiPatch-valid ``target_path`` names an
    in-root ``entities/<slug>.md`` path that is a SYMLINK to a file outside
    the wiki root must be a NON-ATTEMPT integrity descriptor: the
    containment check resolves the FINAL path (following the symlink), so
    the external content is never read and never reaches the evaluator —
    and a later hydration-ready valid sibling is still evaluated exactly
    once with nothing written (a naive in-name-only containment check
    would exfiltrate the external file into the DeepSeek prompt)."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    evidence = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref, title=ref,
            provenance="lightrag-corpus", metadata={"source": "rss"},
        ),
    )
    # Corrupt-first: patch id 'aaa' sorts before 'bbb'. Both suggestions
    # are hydration-ready so the corrupt one reaches the target-path
    # containment gate (hydration runs BEFORE the page read).
    p_bad = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa", evidence=evidence)
    )
    p_ok = _write_suggestion(
        wiki_root,
        _make_patch(
            slug="python-debugging-zzz",
            patch_id="wpatch-w5b-t4-bbb",
            evidence=evidence,
        ),
    )
    # The unique exfiltration marker lives OUTSIDE kb/wiki (fixture
    # tmp boundary, same shape as the outside-root target test).
    external = wiki_root.parent / "exfil-marker.md"
    external.write_text(
        "TOPSECRET EXFIL MARKER, never part of the wiki\n",
        encoding="utf-8",
    )
    # The in-root target path itself is a symlink to that external file:
    # by NAME it sits inside the wiki root; only a resolved-path
    # containment check can reject it.
    escaped = wiki_root / "kb" / "wiki" / "entities" / "python-debugging.md"
    escaped.symlink_to(external)
    _write_page(wiki_root, "python-debugging-zzz", CANONICAL_PAGE)
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    before_pages = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "entities").glob("*.md"))
    }
    before_external = external.read_bytes()

    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["scanned"] == 2
    bad_outcome = report["outcomes"][str(p_bad)]
    assert bad_outcome["status"] == "integrity"
    assert bad_outcome["attempt"] is False
    assert "outside the wiki root" in bad_outcome["reason"]
    assert "entities/python-debugging.md" in bad_outcome["reason"]
    # the symlink target was eligible (missing evolution -> pending) but
    # its outcome is a NON-ATTEMPT integrity descriptor; the valid sibling
    # is still attempted and processed normally
    assert report["attempted"] == [str(p_bad), str(p_ok)]
    assert report["outcomes"][str(p_ok)]["status"] == "evaluated"
    assert len(calls) == 1, "only the valid sibling may reach the evaluator"
    assert "TOPSECRET EXFIL MARKER" not in calls[0], (
        "a symlink escape must never leak external content into the prompt"
    )
    assert "Old section body [^1]" in calls[0], (
        "the single evaluator call must read the valid sibling's real page"
    )

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    after_pages = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "entities").glob("*.md"))
    }
    assert after == before, "worker must not write any suggestion"
    assert after_pages == before_pages, "worker must not write any page"
    assert external.read_bytes() == before_external, "external file unchanged"
    assert escaped.is_symlink(), "the escaped target must not be replaced"
    assert "evolution" not in json.loads(p_bad.read_text(encoding="utf-8"))
    assert "evolution" not in json.loads(p_ok.read_text(encoding="utf-8"))


def test_module_import_keeps_provider_import_lazy() -> None:
    """Importing ``scripts.wiki_evolve`` must NOT import the network-capable
    provider modules: in a fresh interpreter with those modules poisoned in
    ``sys.modules`` (import would raise), the module import still succeeds
    — the provider import is function-local."""
    import subprocess

    code = (
        "import sys\n"
        "for _mod in ('lib.llm_deepseek', 'openai', 'httpx', 'requests', 'tavily'):\n"
        "    sys.modules[_mod] = None\n"
        "import scripts.wiki_evolve\n"
        "print('import-ok')\n"
    )
    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr
    assert "import-ok" in proc.stdout


def test_worker_without_complete_reaches_lazy_provider_import(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """Without an injected ``complete`` the worker reaches the provider
    import only at evaluation time: with the network-capable modules
    poisoned, that lazy import failure surfaces as a retryable outcome —
    no crash, no write, and the provider import is proven call-time-local."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-aaa",
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    before = path.read_bytes()

    poisoned = {}
    for mod in ("lib.llm_deepseek", "openai", "httpx", "requests", "tavily"):
        poisoned[mod] = sys.modules.get(mod)
        sys.modules[mod] = None  # any import of this module now raises
    try:
        report = run_worker(wiki_root, now=now, index=index)
    finally:
        for mod, saved in poisoned.items():
            if saved is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = saved

    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "retry"
    assert "evaluator call failed" in outcome["reason"]
    assert "lib.llm_deepseek" in outcome["reason"], (
        "the lazy provider import must be the attempted call path"
    )
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_missing_local_evidence_retryable_no_provider_call(
    wiki_root: Path,
) -> None:
    """A suggestion whose article evidence has no local record produces an
    explicit retryable worker pre-evaluation outcome — the evaluator (the
    single allowed DeepSeek call) is never invoked, no state is persisted,
    and the suggestion file stays byte-for-byte untouched."""
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    path = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa"))
    before = path.read_bytes()

    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return '{"decision": "APPLY", "sections": [{"heading": "X", "content": "Y"}]}'

    report = run_worker(wiki_root, now=now, index={}, complete=complete)

    assert report["attempted"] == [str(path)]
    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "retry"
    assert "missing local evidence" in outcome["reason"]
    assert calls == [], "no provider call for a hydration-failed suggestion"
    assert path.read_bytes() == before
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_worker_malformed_suggestion_payload_integrity_descriptor(
    wiki_root: Path,
) -> None:
    """A malformed suggestion payload (unparseable JSON, or JSON that is not
    an object) yields a non-attempt integrity descriptor instead of crashing
    the scan; valid siblings are still classified and nothing is written."""
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    bad = wiki_root / "kb" / "wiki" / "_suggestions" / "broken-aaa.json"
    bad.write_text("{not json", encoding="utf-8")
    not_object = wiki_root / "kb" / "wiki" / "_suggestions" / "broken-bbb.json"
    not_object.write_text("[1, 2, 3]", encoding="utf-8")
    p_ok = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-ccc"))
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    report = run_worker(wiki_root, now=now, index={}, dry_run=True)

    assert report["scanned"] == 3
    assert report["eligible"] == [str(p_ok)]
    assert report["attempted"] == [str(p_ok)]
    bad_outcome = report["outcomes"][str(bad)]
    assert bad_outcome["status"] == "integrity"
    assert bad_outcome["attempt"] is False
    assert "malformed suggestion payload" in bad_outcome["reason"]
    assert report["outcomes"][str(not_object)]["status"] == "integrity"
    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert after == before, "integrity classification must not write anything"


def test_worker_malformed_retry_timestamp_integrity_scan_continues(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A suggestion whose retry state carries a MALFORMED ``next_retry_at``
    timestamp is a non-attempt integrity descriptor in BOTH dry-run and
    normal mode — the eligibility parse never crashes the scan, never
    calls the evaluator, never writes; a later valid suggestion is still
    classified (dry-run) and processed (normal mode)."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    p_bad = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa"),
        evolution=_retry_state(attempts=1, next_retry_at="not-a-timestamp"),
    )
    p_ok = _write_suggestion(
        wiki_root,
        _make_patch(
            patch_id="wpatch-w5b-t4-bbb",
            evidence=(
                EvidenceRef(
                    evidence_id="e1", type="article", ref=ref, title=ref,
                    provenance="lightrag-corpus", metadata={"source": "rss"},
                ),
            ),
        ),
    )
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    # dry-run: the malformed state is an integrity descriptor, the valid
    # sibling is still classified, nothing is written
    report = run_worker(wiki_root, now=now, dry_run=True)
    assert report["scanned"] == 2
    bad_outcome = report["outcomes"][str(p_bad)]
    assert bad_outcome["status"] == "integrity"
    assert bad_outcome["attempt"] is False
    assert "malformed suggestion payload" in bad_outcome["reason"]
    assert report["eligible"] == [str(p_ok)]
    assert report["attempted"] == [str(p_ok)]

    # normal mode: the malformed file is never attempted, the valid
    # sibling still scans, and the evaluator is never called
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    _write_page(wiki_root, "python-debugging", CANONICAL_PAGE)  # valid sibling's page
    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report2 = run_worker(wiki_root, now=now, index=index, complete=complete)
    assert report2["outcomes"][str(p_bad)]["status"] == "integrity"
    assert report2["attempted"] == [str(p_ok)]
    # the valid sibling is processed normally (its evidence resolves)
    assert report2["outcomes"][str(p_ok)]["status"] == "evaluated"
    assert len(calls) == 1, "only the valid sibling may reach the evaluator"

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert after == before, "integrity classification must not write anything"
    assert "evolution" not in json.loads(p_ok.read_text(encoding="utf-8"))


def test_worker_incomplete_serialized_patch_integrity_scan_continues(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A suggestion whose serialized ``patch`` object is a dict that cannot
    construct a :class:`WikiPatch` (incomplete payload) is a non-attempt
    integrity descriptor in NORMAL mode — ``WikiPatch.from_dict`` failures
    never crash the worker, never reach the evaluator, never write; a
    later valid suggestion is still processed."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    p_bad = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa")
    )
    # Adversarial payload: rewrite ONLY the serialized patch object to an
    # incomplete dict (exercises the real from_dict untrusted-input path).
    payload = json.loads(p_bad.read_text(encoding="utf-8"))
    payload["patch"] = {"patch_id": "incomplete"}
    p_bad.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    p_ok = _write_suggestion(
        wiki_root,
        _make_patch(
            patch_id="wpatch-w5b-t4-bbb",
            evidence=(
                EvidenceRef(
                    evidence_id="e1", type="article", ref=ref, title=ref,
                    provenance="lightrag-corpus", metadata={"source": "rss"},
                ),
            ),
        ),
    )
    _write_page(wiki_root, "python-debugging", CANONICAL_PAGE)
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["scanned"] == 2
    bad_outcome = report["outcomes"][str(p_bad)]
    assert bad_outcome["status"] == "integrity"
    assert bad_outcome["attempt"] is False
    assert "malformed suggestion payload" in bad_outcome["reason"]
    # the broken file was eligible (missing evolution -> pending) but its
    # outcome is a NON-ATTEMPT integrity descriptor; the valid sibling is
    # still attempted and processed normally
    assert report["attempted"] == [str(p_bad), str(p_ok)]
    assert report["outcomes"][str(p_ok)]["status"] == "evaluated"
    assert len(calls) == 1, "only the valid sibling may reach the evaluator"

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert after == before, "integrity classification must not write anything"
    assert "evolution" not in json.loads(p_ok.read_text(encoding="utf-8"))


def test_worker_non_dict_patch_item_attribute_error_integrity_scan_continues(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A suggestion whose serialized ``patch.operations`` contains a NON-DICT
    item (e.g. a bare string) makes ``WikiPatch.from_dict`` raise an
    ``AttributeError`` from the model's post-init invariant checks. That
    exception must be contained as a non-attempt integrity descriptor, never
    crash the worker: a later valid hydration-ready sibling is still
    processed exactly once and nothing is written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    p_bad = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa")
    )
    # Adversarial payload: rewrite ONLY the serialized patch's operations
    # list with a non-dict item (exercises the real from_dict
    # untrusted-input path; the model post-init then raises AttributeError).
    payload = json.loads(p_bad.read_text(encoding="utf-8"))
    payload["patch"]["operations"] = ["junk"]
    p_bad.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    p_ok = _write_suggestion(
        wiki_root,
        _make_patch(
            patch_id="wpatch-w5b-t4-bbb",
            evidence=(
                EvidenceRef(
                    evidence_id="e1", type="article", ref=ref, title=ref,
                    provenance="lightrag-corpus", metadata={"source": "rss"},
                ),
            ),
        ),
    )
    _write_page(wiki_root, "python-debugging", CANONICAL_PAGE)
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["scanned"] == 2
    bad_outcome = report["outcomes"][str(p_bad)]
    assert bad_outcome["status"] == "integrity"
    assert bad_outcome["attempt"] is False
    assert "malformed suggestion payload" in bad_outcome["reason"]
    # the broken file was eligible (missing evolution -> pending) but its
    # outcome is a NON-ATTEMPT integrity descriptor; the valid sibling is
    # still attempted and processed normally
    assert report["attempted"] == [str(p_bad), str(p_ok)]
    assert report["outcomes"][str(p_ok)]["status"] == "evaluated"
    assert len(calls) == 1, "only the valid sibling may reach the evaluator"

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert after == before, "integrity classification must not write anything"
    assert "evolution" not in json.loads(p_ok.read_text(encoding="utf-8"))


def test_worker_non_dict_evidence_metadata_fail_closed_sibling_evaluated(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A corrupt-first eligible suggestion whose serialized article evidence
    carries a NON-DICT ``metadata`` (e.g. a bare string) must fail closed
    BEFORE the evaluator, never crash the worker: the malformed metadata
    normalizes away, the unmatched ref becomes a retryable missing-evidence
    outcome, and a later valid hydration-ready sibling is still evaluated
    exactly once with nothing written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    p_bad = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa")
    )
    # Adversarial payload: rewrite ONLY the serialized evidence's metadata
    # with a non-dict string (exercises the real from_dict untrusted-input
    # path — EvidenceRef validates type/ref but not metadata, so the patch
    # deserializes cleanly and only hydration ever sees the corrupt field).
    payload = json.loads(p_bad.read_text(encoding="utf-8"))
    payload["patch"]["evidence"][0]["metadata"] = "oops"
    p_bad.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    p_ok = _write_suggestion(
        wiki_root,
        _make_patch(
            patch_id="wpatch-w5b-t4-bbb",
            evidence=(
                EvidenceRef(
                    evidence_id="e1", type="article", ref=ref, title=ref,
                    provenance="lightrag-corpus", metadata={"source": "rss"},
                ),
            ),
        ),
    )
    _write_page(wiki_root, "python-debugging", CANONICAL_PAGE)
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)
    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["scanned"] == 2
    bad_outcome = report["outcomes"][str(p_bad)]
    # Fail-closed BEFORE the evaluator: the corrupt metadata normalizes to
    # no source, so the unmatched ref is a retryable missing-evidence
    # outcome — never a crash and never an evaluator call.
    assert bad_outcome["status"] == "retry"
    assert "missing local evidence" in bad_outcome["reason"]
    assert "abcdef1234" in bad_outcome["reason"]
    assert report["attempted"] == [str(p_bad), str(p_ok)]
    assert report["outcomes"][str(p_ok)]["status"] == "evaluated"
    assert len(calls) == 1, "only the valid sibling may reach the evaluator"

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert after == before, "worker must not write anything"
    assert "evolution" not in json.loads(p_ok.read_text(encoding="utf-8"))


def test_worker_corrupt_utf8_current_page_retryable_sibling_evaluated(
    wiki_root: Path,
    conn: sqlite3.Connection,
) -> None:
    """A static current page containing invalid UTF-8 bytes is a retryable
    pre-evaluation outcome, never a worker crash: the corrupt-first eligible
    suggestion returns the existing page-read retry descriptor with NO
    evaluator call, and a later hydration-ready valid sibling is still
    evaluated exactly once with nothing written."""
    from kb.wiki_articles import load_article_index
    from scripts.wiki_evolve import run_worker

    now = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)
    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    conn.execute(
        "INSERT INTO rss_articles (id, url, title, summary, content_hash) VALUES (?, ?, ?, ?, ?)",
        (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
    )
    index = load_article_index(conn)

    # Both suggestions carry hydration-ready evidence so they reach the
    # current-page read (hydration runs BEFORE the page read).
    evidence = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref, title=ref,
            provenance="lightrag-corpus", metadata={"source": "rss"},
        ),
    )
    # Corrupt-first: patch id 'aaa' sorts before 'bbb' lexicographically.
    p_bad = _write_suggestion(
        wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa", evidence=evidence)
    )
    p_ok = _write_suggestion(
        wiki_root,
        _make_patch(
            slug="python-debugging-zzz",
            patch_id="wpatch-w5b-t4-bbb",
            evidence=evidence,
        ),
    )
    # The corrupt target page exists INSIDE the wiki root but carries
    # invalid UTF-8 bytes (static corruption/encoding damage on disk).
    bad_page = wiki_root / "kb" / "wiki" / "entities" / "python-debugging.md"
    bad_page.write_bytes(
        b"---\ntitle: 'Corrupt'\n---\n\n# Corrupt\n\n\xff\xfe damaged bytes\n"
    )
    _write_page(wiki_root, "python-debugging-zzz", CANONICAL_PAGE)
    before = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    before_pages = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "entities").glob("*.md"))
    }

    calls: list[str] = []

    async def complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append(prompt)
        return json.dumps({"decision": "REJECT", "reason": "should not run"})

    report = run_worker(wiki_root, now=now, index=index, complete=complete)

    assert report["scanned"] == 2
    assert report["attempted"] == [str(p_bad), str(p_ok)]
    bad_outcome = report["outcomes"][str(p_bad)]
    # Existing page-read retry descriptor: corrupt bytes are a read
    # failure, never a crash and never an evaluator call.
    assert bad_outcome["status"] == "retry"
    assert "cannot read current page" in bad_outcome["reason"]
    assert "python-debugging" in bad_outcome["reason"]
    assert report["outcomes"][str(p_ok)]["status"] == "evaluated"
    assert len(calls) == 1, "only the valid sibling may reach the evaluator"

    after = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    after_pages = {
        p.name: p.read_bytes()
        for p in sorted((wiki_root / "kb" / "wiki" / "entities").glob("*.md"))
    }
    assert after == before, "worker must not write any suggestion"
    assert after_pages == before_pages, "worker must not write any page"
    assert "evolution" not in json.loads(p_bad.read_text(encoding="utf-8"))
    assert "evolution" not in json.loads(p_ok.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 4.3 strict semantic result parser
# ---------------------------------------------------------------------------

def test_parse_semantic_result_valid_apply_retry_reject() -> None:
    """The parser accepts exactly one JSON object whose decision is in
    {APPLY, RETRY, REJECT}: APPLY carries its non-empty sections through,
    RETRY/REJECT need no sections."""
    from scripts.wiki_evolve import parse_semantic_result

    raw = json.dumps({
        "decision": "APPLY",
        "reason": "evidence supports",
        "sections": [
            {"heading": "Definition / Overview", "content": "New body [^1]"},
            {"heading": "Deployment Notes", "content": "Extra body."},
        ],
    })
    result = parse_semantic_result(raw)
    assert result["decision"] == "APPLY"
    assert result["reason"] == "evidence supports"
    assert result["sections"] == [
        {"heading": "Definition / Overview", "content": "New body [^1]"},
        {"heading": "Deployment Notes", "content": "Extra body."},
    ]

    retry = parse_semantic_result(json.dumps({"decision": "RETRY", "reason": "later"}))
    assert retry["decision"] == "RETRY"
    reject = parse_semantic_result(json.dumps({"decision": "REJECT", "reason": "no"}))
    assert reject["decision"] == "REJECT"


def test_parse_semantic_result_missing_or_unknown_decision_rejected() -> None:
    """Missing or unknown decision is malformed — the decision field is the
    only accepted policy channel."""
    from scripts.wiki_evolve import SemanticParseError, parse_semantic_result

    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({"sections": []}))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({"decision": "MAYBE"}))
    with pytest.raises(SemanticParseError):
        parse_semantic_result("[1, 2, 3]")


def test_parse_semantic_result_apply_requires_nonempty_sections() -> None:
    """APPLY without sections, with empty sections, or with a section
    missing heading/content (or non-string values) is malformed."""
    from scripts.wiki_evolve import SemanticParseError, parse_semantic_result

    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({"decision": "APPLY", "reason": "r"}))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({"decision": "APPLY", "sections": []}))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({"decision": "APPLY", "sections": [{}]}))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({
            "decision": "APPLY",
            "sections": [{"heading": "  ", "content": "body"}],
        }))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({
            "decision": "APPLY",
            "sections": [{"heading": "H", "content": ""}],
        }))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({
            "decision": "APPLY",
            "sections": [{"heading": 42, "content": "body"}],
        }))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({
            "decision": "APPLY",
            "sections": [{"heading": "H", "content": ["not", "a", "string"]}],
        }))


def test_parse_semantic_result_strips_one_outer_code_fence() -> None:
    """A single outer ```json/``` code fence around the JSON object is
    stripped; unclosed or doubled fences and fenced prose stay malformed."""
    from scripts.wiki_evolve import SemanticParseError, parse_semantic_result

    fenced = (
        "```json\n"
        + json.dumps({
            "decision": "APPLY",
            "sections": [{"heading": "H", "content": "body"}],
        })
        + "\n```"
    )
    result = parse_semantic_result(fenced)
    assert result["decision"] == "APPLY"

    fenced_plain = '```\n{"decision": "REJECT", "reason": "r"}\n```'
    assert parse_semantic_result(fenced_plain)["decision"] == "REJECT"

    # unclosed fence -> malformed
    with pytest.raises(SemanticParseError):
        parse_semantic_result('```json\n{"decision": "REJECT"}')
    # doubled outer fence -> malformed (only ONE outer fence may be stripped)
    with pytest.raises(SemanticParseError):
        parse_semantic_result(
            '```json\n```json\n{"decision": "REJECT"}\n```\n```'
        )
    # fenced markdown prose (not JSON) -> malformed
    with pytest.raises(SemanticParseError):
        parse_semantic_result("```markdown\nSome prose, not JSON\n```")


def test_parse_semantic_result_rejects_h1_full_page_frontmatter_source_yaml() -> None:
    """APPLY sections must be H2 section bodies only: H1 headings, H1/full
    page content, frontmatter fences and source-YAML are all malformed."""
    from scripts.wiki_evolve import SemanticParseError, parse_semantic_result

    def apply_with(content: str, heading: str = "Definition / Overview") -> str:
        return json.dumps({
            "decision": "APPLY",
            "sections": [{"heading": heading, "content": content}],
        })

    # H1 heading is not H2-safe
    with pytest.raises(SemanticParseError):
        parse_semantic_result(apply_with("body", heading="# Python Debugging"))
    # H1 line inside the content = full-page attempt
    with pytest.raises(SemanticParseError):
        parse_semantic_result(apply_with("# Python Debugging\n\nbody"))
    # frontmatter fence inside the content
    with pytest.raises(SemanticParseError):
        parse_semantic_result(apply_with("---\ntitle: 'X'\n---\n\nbody"))
    # source-YAML block inside the content
    with pytest.raises(SemanticParseError):
        parse_semantic_result(
            apply_with("body\n\nsources:\n  - id: 1\n    type: article\n    ref: abc")
        )
    # frontmatter scalar keys at the start (no fence)
    with pytest.raises(SemanticParseError):
        parse_semantic_result(
            apply_with("title: 'Python Debugging'\ncreated: '2026-05-20'\n\nbody")
        )


def test_parse_semantic_result_rejects_duplicate_section_headings() -> None:
    """Duplicate (case/space-insensitive) section headings are malformed —
    they would make the update order ambiguous."""
    from scripts.wiki_evolve import SemanticParseError, parse_semantic_result

    raw = json.dumps({
        "decision": "APPLY",
        "sections": [
            {"heading": "Definition / Overview", "content": "First body"},
            {"heading": "definition / overview", "content": "Second body"},
        ],
    })
    with pytest.raises(SemanticParseError):
        parse_semantic_result(raw)

    # distinct headings are fine
    ok = json.dumps({
        "decision": "APPLY",
        "sections": [
            {"heading": "Definition / Overview", "content": "First body"},
            {"heading": "Deployment Notes", "content": "Second body"},
        ],
    })
    assert len(parse_semantic_result(ok)["sections"]) == 2


def test_parse_semantic_result_rejects_numeric_confidence_or_score() -> None:
    """Numeric confidence/score fields are not accepted as a second policy
    channel — such payloads are malformed."""
    from scripts.wiki_evolve import SemanticParseError, parse_semantic_result

    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({
            "decision": "APPLY",
            "confidence": 0.95,
            "sections": [{"heading": "H", "content": "body"}],
        }))
    with pytest.raises(SemanticParseError):
        parse_semantic_result(json.dumps({
            "decision": "REJECT",
            "reason": "no",
            "score": 7,
        }))
    # a decision-only payload stays valid
    ok = parse_semantic_result(json.dumps({"decision": "RETRY", "reason": "later"}))
    assert ok["decision"] == "RETRY"


# ---------------------------------------------------------------------------
# 4.4 citation mapping + prompt
# ---------------------------------------------------------------------------

def test_build_citation_map_canonical_matches_compiler_merge() -> None:
    """Predicted canonical citation tokens match the actual W5A
    ``_merge_sources`` append ids: evidence already present keeps its
    existing id; new evidence gets ``len(existing_sources)+1...`` in
    evidence order — the mapping cannot drift from the compiler."""
    from kb.wiki_compiler.engine import _merge_sources, _split_frontmatter
    from scripts.wiki_evolve import build_citation_map

    evidence = (
        EvidenceRef(
            evidence_id="e0", type="article", ref="abcdef1234",
            title="Existing Source", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        ),
        EvidenceRef(
            evidence_id="e1", type="article", ref="9999999999",
            title="New One", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        ),
        EvidenceRef(
            evidence_id="e2", type="article", ref="8888888888",
            title="New Two", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        ),
    )

    mapping = build_citation_map(CANONICAL_PAGE, evidence)
    assert [m["token"] for m in mapping] == ["[^1]", "[^2]", "[^3]"]
    assert [m["ref"] for m in mapping] == ["abcdef1234", "9999999999", "8888888888"]

    # drift check against the compiler's actual merge result
    merged = _merge_sources(CANONICAL_PAGE, evidence)
    fm, _ = _split_frontmatter(merged)
    assigned = {
        s["ref"]: s["id"]
        for s in fm["sources"]
        if isinstance(s, dict) and s.get("ref") is not None
    }
    # The compiler writes ids as YAML scalars, which the frontmatter
    # parser reads back as strings — compare against the actual values.
    assert assigned["abcdef1234"] == "1"  # existing entry untouched
    assert assigned["9999999999"] == "2"  # len(sources)+1
    assert assigned["8888888888"] == "3"  # len(sources)+2
    for entry in mapping:
        assert entry["token"] == f"[^{assigned[entry['ref']]}]"


def test_build_citation_map_legacy_matches_compiler_merge() -> None:
    """Legacy article-only pages map every article ref to its exact
    ``^[article:<ref>]`` token — the same form the W5A ``_merge_sources``
    path appends, so ids cannot drift."""
    from kb.wiki_compiler.engine import _merge_sources, _split_frontmatter
    from scripts.wiki_evolve import build_citation_map

    evidence = (
        EvidenceRef(
            evidence_id="e0", type="article", ref="abcdef1234",
            title="Existing Source", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        ),
        EvidenceRef(
            evidence_id="e1", type="article", ref="9999999999",
            title="New One", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        ),
        EvidenceRef(
            evidence_id="e2", type="web", ref="https://example.com/doc",
            title="A Web Source", provenance="web",
            metadata={},
        ),
    )

    mapping = build_citation_map(LEGACY_PAGE, evidence)
    # article-only mapping: the web evidence cannot be expressed in legacy
    # format and is omitted
    assert [m["token"] for m in mapping] == ["^[article:abcdef1234]", "^[article:9999999999]"]
    assert [m["type"] for m in mapping] == ["article", "article"]

    # drift check against the compiler's actual legacy merge result
    # (article-only: legacy format cannot express web sources, so the
    # compiler's own merge skips such evidence entirely)
    article_only = tuple(ev for ev in evidence if ev.type == "article")
    merged = _merge_sources(LEGACY_PAGE, article_only)
    fm, _ = _split_frontmatter(merged)
    assert fm["sources"] == ["article:abcdef1234", "article:9999999999"]
    for entry in mapping:
        assert entry["ref"] is not None
        assert entry["token"] == f"^[article:{entry['ref']}]"


def test_build_prompt_contract_questions_and_exact_tokens() -> None:
    """The evaluator prompt presents the current page, the hydrated
    evidence (real titles/texts) with exact citation tokens from the
    compiler-parity map, and asks exactly the four approved questions;
    it is a pure deterministic function of its inputs."""
    from scripts.wiki_evolve import build_prompt

    evidence = [
        {
            "evidence_id": "e0", "type": "article", "ref": "abcdef1234",
            "title": "Existing Source", "text": "Body of existing source.",
            "metadata": {"source": "rss"},
        },
        {
            "evidence_id": "e1", "type": "article", "ref": "9999999999",
            "title": "New One", "text": "Body of new article.",
            "metadata": {"source": "rss"},
        },
    ]
    sections = [
        {"heading": "Definition / Overview", "content": "New body [^1]"},
        {"heading": "Deployment Notes", "content": "Extra detail [^2]."},
    ]

    prompt = build_prompt(
        current_page=CANONICAL_PAGE, evidence=evidence, sections=sections
    )

    # the fresh current page is the authority
    assert "# Python Debugging" in prompt
    assert "Old section body [^1]" in prompt
    # hydrated real titles and texts
    assert "Existing Source" in prompt
    assert "Body of existing source." in prompt
    assert "New One" in prompt
    assert "Body of new article." in prompt
    # exact citation tokens per ref
    assert "abcdef1234" in prompt and "[^1]" in prompt
    assert "9999999999" in prompt and "[^2]" in prompt
    # the four approved questions only
    for question in (
        "supported by the supplied evidence",
        "unjustified deletion",
        "materially more accurate",
        "contradiction",
    ):
        assert question in prompt, question
    # deterministic given the same inputs
    again = build_prompt(current_page=CANONICAL_PAGE, evidence=evidence, sections=sections)
    assert again == prompt


def test_citation_collision_same_ref_two_sources_single_retained_payload() -> None:
    """Compiler parity when the SAME article ref arrives under two sources
    (wechat + rss): ``_merge_sources`` deduplicates canonical typed
    sources by ``(type, ref)`` only, so it retains exactly ONE source and
    appends a single id. The map and prompt must be source-aware the same
    way:

    (a) canonical map/compiler produce exactly one retained source id for
        the same article ref across sources (the first evidence item is
        the retained one);
    (b) the prompt carries exactly ONE evidence payload with the exact
        ``[^?]`` token of the retained citation — no misleading second
        RSS payload, no invented unique citation for a source the compiler
        will not retain (Task 2 non-alias contract);
    (c) the evaluator still makes exactly one call for the colliding
        evidence — no caller/evaluator side effects;
    (d) plain compiler-compatible ``(type, ref)`` projection only — no
        tokenizer/source framework.
    """
    from kb.wiki_compiler.engine import _merge_sources, _split_frontmatter
    from scripts.wiki_evolve import (
        build_citation_map,
        build_prompt,
        evaluate_suggestion,
    )

    ref = "9999999999"  # NOT on CANONICAL_PAGE yet — collides across sources
    evidence_refs = (
        EvidenceRef(
            evidence_id="e1", type="article", ref=ref,
            title="WeChat Article Title", provenance="lightrag-corpus",
            metadata={"source": "wechat"},
        ),
        EvidenceRef(
            evidence_id="e2", type="article", ref=ref,
            title="RSS Article Title", provenance="lightrag-corpus",
            metadata={"source": "rss"},
        ),
    )
    evidence = [
        {
            "evidence_id": "e1", "type": "article", "ref": ref,
            "title": "WeChat Article Title", "text": "WeChat body text.",
            "metadata": {"source": "wechat"},
        },
        {
            "evidence_id": "e2", "type": "article", "ref": ref,
            "title": "RSS Article Title", "text": "RSS body text.",
            "metadata": {"source": "rss"},
        },
    ]
    sections = [{"heading": "Definition / Overview", "content": "New body [^2]"}]

    # (a) compiler parity: exactly one retained source, first item wins
    mapping = build_citation_map(CANONICAL_PAGE, evidence_refs)
    collisions = [m for m in mapping if m["ref"] == ref]
    assert len(collisions) == 1, (
        "the compiler retains ONE source for the same (type, ref) — the map "
        "must not hand the second item its own citation id"
    )
    assert collisions[0]["token"] == "[^2]"  # len(existing sources) + 1
    merged = _merge_sources(CANONICAL_PAGE, evidence_refs)
    fm, _ = _split_frontmatter(merged)
    retained = [
        s for s in fm["sources"] if isinstance(s, dict) and s.get("ref") == ref
    ]
    assert len(retained) == 1, "compiler appends exactly one source entry"
    assert retained[0]["id"] == "2"
    assert retained[0]["title"] == "WeChat Article Title", (
        "the FIRST evidence item is the retained one"
    )
    assert collisions[0]["token"] == f"[^{retained[0]['id']}]"

    # (b) prompt: exactly one payload, exact retained token, no second RSS
    prompt = build_prompt(
        current_page=CANONICAL_PAGE, evidence=evidence, sections=sections
    )
    assert "WeChat Article Title" in prompt
    assert "RSS Article Title" not in prompt, (
        "no misleading second payload for a source the compiler will not retain"
    )
    assert prompt.count(ref) == 1, (
        "the ref appears in exactly one evidence payload"
    )
    assert f"ref: {ref} — exact citation token: [^2]" in prompt
    assert "[^3]" not in prompt, (
        "no invented citation id for the dropped source"
    )

    # (c) evaluator: still exactly one call for the colliding evidence
    calls: list[str] = []

    async def complete(prompt_text: str, system_prompt: str | None = None) -> str:
        calls.append(prompt_text)
        return json.dumps({
            "decision": "APPLY",
            "reason": "evidence supports",
            "sections": [{"heading": "Definition / Overview", "content": "New body [^2]"}],
        })

    result = asyncio.run(evaluate_suggestion(
        current_page=CANONICAL_PAGE, evidence=evidence, sections=sections,
        complete=complete,
    ))
    assert result["status"] == "evaluated"
    assert len(calls) == 1, "the collision fix must not add evaluator calls"
    assert "RSS Article Title" not in calls[0]


def test_evaluate_suggestion_boundary_exactly_one_call_and_retry() -> None:
    """Task 4.5 boundary: ``evaluate_suggestion`` makes EXACTLY ONE
    injected provider call per attempt and never repeats inside the same
    attempt. Three independent calls in one boundary test:

    1) valid APPLY JSON -> ``status == "evaluated"`` with the parsed
       decision; the single call received ``SYSTEM_PROMPT`` and the
       prompt carries the hydrated evidence's exact citation token
       context;
    2) provider raises -> ``status == "retry"``, exactly one call made;
    3) provider returns malformed JSON -> ``status == "retry"``, exactly
       one call made.

    Retry is a later-scheduled-run outcome, never a same-attempt loop;
    the evaluator neither writes anything nor persists state (Task 5)."""
    from scripts.wiki_evolve import SYSTEM_PROMPT, evaluate_suggestion

    evidence = [
        {
            "evidence_id": "e0", "type": "article", "ref": "abcdef1234",
            "title": "Existing Source", "text": "Body of existing source.",
            "metadata": {"source": "rss"},
        },
    ]
    sections = [{"heading": "Definition / Overview", "content": "New body [^1]"}]

    # 1) valid APPLY JSON -> evaluated, parsed decision, one call with
    #    SYSTEM_PROMPT and citation-token context in the prompt
    ok_calls: list[tuple[str, str | None]] = []

    async def ok_complete(prompt: str, system_prompt: str | None = None) -> str:
        ok_calls.append((prompt, system_prompt))
        return json.dumps({
            "decision": "APPLY",
            "reason": "evidence supports",
            "sections": [{"heading": "Definition / Overview", "content": "New body [^1]"}],
        })

    result = asyncio.run(evaluate_suggestion(
        current_page=CANONICAL_PAGE, evidence=evidence, sections=sections,
        complete=ok_complete,
    ))
    assert result["status"] == "evaluated"
    assert result["decision"] == "APPLY"
    assert result["reason"] == "evidence supports"
    assert len(result["sections"]) == 1
    assert len(ok_calls) == 1, "exactly one provider call for a valid response"
    prompt, system_prompt = ok_calls[0]
    assert system_prompt == SYSTEM_PROMPT
    assert "ref: abcdef1234" in prompt
    assert "[^1]" in prompt  # exact citation token context for the evidence

    # 2) provider raises -> retryable outcome, exactly one call (no repeat)
    boom_calls: list[str] = []

    async def boom_complete(prompt: str, system_prompt: str | None = None) -> str:
        boom_calls.append(prompt)
        raise RuntimeError("provider timeout")

    result = asyncio.run(evaluate_suggestion(
        current_page=CANONICAL_PAGE, evidence=evidence, sections=sections,
        complete=boom_complete,
    ))
    assert result["status"] == "retry"
    assert "evaluator call failed" in result["reason"]
    assert len(boom_calls) == 1, "no second call after a provider failure"

    # 3) malformed JSON -> retryable outcome, exactly one call (no repeat)
    junk_calls: list[str] = []

    async def junk_complete(prompt: str, system_prompt: str | None = None) -> str:
        junk_calls.append(prompt)
        return "```markdown\nSome prose, not JSON\n```"

    result = asyncio.run(evaluate_suggestion(
        current_page=CANONICAL_PAGE, evidence=evidence, sections=sections,
        complete=junk_complete,
    ))
    assert result["status"] == "retry"
    assert "malformed evaluator response" in result["reason"]
    assert len(junk_calls) == 1, "no immediate repeat after a malformed response"


# ---------------------------------------------------------------------------
# 4.6 CLI shell
# ---------------------------------------------------------------------------

def _run_cli(*args: str, cwd: Path):
    """Run the script in a subprocess (same interpreter as pytest)."""
    import subprocess

    script = Path(__file__).resolve().parents[2] / "scripts" / "wiki_evolve.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_cli_help_lists_all_options(wiki_root: Path) -> None:
    """``--help`` exits 0 and documents every supported option."""
    proc = _run_cli("--help", cwd=wiki_root)
    assert proc.returncode == 0, proc.stderr
    for option in ("--dry-run", "--limit", "--wiki-root", "--db-path", "--bootstrap-existing"):
        assert option in proc.stdout, option


def test_cli_dry_run_prints_json_report_and_writes_nothing(wiki_root: Path) -> None:
    """``--dry-run --wiki-root <root>`` prints the JSON scan report and
    leaves the suggestion files byte-for-byte untouched."""
    p = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa"))
    before = {
        q.name: q.read_bytes()
        for q in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }

    proc = _run_cli("--dry-run", "--wiki-root", str(wiki_root), cwd=wiki_root)

    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["scanned"] == 1
    assert report["eligible"] == [str(p)]
    assert report["attempted"] == [str(p)]
    assert report["outcomes"] == {}
    after = {
        q.name: q.read_bytes()
        for q in sorted((wiki_root / "kb" / "wiki" / "_suggestions").glob("*.json"))
    }
    assert after == before


def test_cli_normal_mode_missing_db_exits_nonzero_without_mutation(
    wiki_root: Path,
) -> None:
    """Normal mode with a nonexistent ``--db-path`` exits nonzero with an
    explicit error and must not create the DB file or touch suggestions —
    no fake success, no silent side effects."""
    p = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa"))
    before = p.read_bytes()
    missing_db = wiki_root / "no-such.db"

    proc = _run_cli(
        "--wiki-root", str(wiki_root), "--db-path", str(missing_db), cwd=wiki_root
    )

    assert proc.returncode != 0
    assert "database not found" in proc.stderr
    assert not missing_db.exists(), "sqlite3.connect must never create the DB"
    assert p.read_bytes() == before


def test_cli_normal_mode_reaches_real_provider_lazy_import_once(
    wiki_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Normal CLI mode with a hydration-ready suggestion must reach the real
    provider through ``evaluate_suggestion``'s lazy import — never an
    artificial CLI stub: exactly one provider call, an evaluated outcome is
    printed, and nothing is written (no Wiki/suggestion mutation).

    The network-capable ``lib.llm_deepseek`` module is substituted in
    ``sys.modules`` by a recording fake BEFORE ``main()`` runs; the
    worker's function-local ``from lib.llm_deepseek import
    deepseek_model_complete`` then binds the fake — proving the CLI default
    path flows through the same lazy import seam as the library API (Task 4
    contract: exactly one call per suggestion, no second call).
    """
    import types

    from scripts.wiki_evolve import SYSTEM_PROMPT, main

    url = "https://example.com/rss/evolution-post"
    ref = _ref(url)
    db_path = tmp_path / "kol_scan.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE articles ("
            "id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
            "title_translated TEXT, body TEXT, summary TEXT, content_hash TEXT)"
        )
        conn.execute(
            "CREATE TABLE rss_articles ("
            "id INTEGER PRIMARY KEY, url TEXT, title TEXT, "
            "summary TEXT, content_hash TEXT)"
        )
        conn.execute(
            "INSERT INTO rss_articles (id, url, title, summary, content_hash)"
            " VALUES (?, ?, ?, ?, ?)",
            (1, url, "Real RSS Title", "Real RSS summary body.", "x" * 32),
        )
        conn.commit()
    finally:
        conn.close()
    assert db_path.is_file()

    calls: list[tuple[str, str | None]] = []

    async def fake_complete(prompt: str, system_prompt: str | None = None) -> str:
        calls.append((prompt, system_prompt))
        return json.dumps({
            "decision": "APPLY",
            "reason": "evidence supports",
            "sections": [{"heading": "Definition / Overview", "content": "New body [^1]"}],
        })

    monkeypatch.setitem(
        sys.modules,
        "lib.llm_deepseek",
        types.SimpleNamespace(deepseek_model_complete=fake_complete),
    )

    patch = _make_patch(
        patch_id="wpatch-w5b-t4-cli",
        evidence=(
            EvidenceRef(
                evidence_id="e1", type="article", ref=ref, title=ref,
                provenance="lightrag-corpus", metadata={"source": "rss"},
            ),
        ),
    )
    path = _write_suggestion(wiki_root, patch)
    page = _write_page(wiki_root, patch.target_slug, CANONICAL_PAGE)
    before_sugg = path.read_bytes()
    before_page = page.read_bytes()

    rc = main(["--wiki-root", str(wiki_root), "--db-path", str(db_path)])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["attempted"] == [str(path)]
    outcome = report["outcomes"][str(path)]
    assert outcome["status"] == "evaluated"
    assert outcome["decision"] == "APPLY"
    assert len(calls) == 1, "normal CLI must make exactly one provider call"
    assert calls[0][1] == SYSTEM_PROMPT, (
        "the CLI default path must go through evaluate_suggestion's lazy import"
    )
    assert path.read_bytes() == before_sugg
    assert page.read_bytes() == before_page
    assert "evolution" not in json.loads(path.read_text(encoding="utf-8"))


def test_cli_bootstrap_existing_explicit_deferral_both_forms(wiki_root: Path) -> None:
    """``--bootstrap-existing`` PARSES and exits NONZERO with one stable
    neutral stderr message in both flag forms (alone and combined with
    ``--dry-run``) — Task 4 exposes the explicit deferred/unsupported
    behavior without implementing Task 6 and without faking success: no
    scan report is printed, the DB is never opened or created, and the
    suggestion/page bytes stay byte-for-byte identical."""
    p = _write_suggestion(wiki_root, _make_patch(patch_id="wpatch-w5b-t4-aaa"))
    page = _write_page(wiki_root, "python-debugging", CANONICAL_PAGE)
    before_sugg = p.read_bytes()
    before_page = page.read_bytes()
    db_path = wiki_root / "data" / "kol_scan.db"
    assert not db_path.exists()

    proc_alone = _run_cli(
        "--bootstrap-existing", "--wiki-root", str(wiki_root), cwd=wiki_root
    )
    proc_with_dry_run = _run_cli(
        "--bootstrap-existing", "--dry-run", "--wiki-root", str(wiki_root),
        cwd=wiki_root,
    )

    for proc in (proc_alone, proc_with_dry_run):
        assert proc.returncode != 0, "deferral must exit nonzero, never fake success"
        assert proc.stderr.strip() == (
            "--bootstrap-existing is not implemented (Task 6 owns historical bootstrap)"
        ), "one stable neutral stderr message"
        assert proc.stdout == "", "deferral must not print a fake scan report"

    assert p.read_bytes() == before_sugg
    assert page.read_bytes() == before_page
    assert not db_path.exists(), "the DB must never be opened or created"
