---
phase: ir-1-real-layer1-and-kol-ingest-wiring
plan: 02
type: execute
wave: 2
depends_on:
  - "ir-1-00"
files_modified:
  - tests/unit/test_article_filter.py
autonomous: true
requirements:
  - LF-1.9

must_haves:
  truths:
    - "tests/unit/test_article_filter.py is REWRITTEN end-to-end. The 7 placeholder tests from V35-FOUND-01 are deleted. The new file pins LF-1.9's 5 cases plus a sixth (interface contract / dataclass-frozen check) for symmetry"
    - "All 5 LF-1.9 cases use pytest + monkeypatch to swap the LLM dependency (vertex_gemini_model_complete OR gemini_model_complete) so tests never call out to network. No real network requests, no real API keys"
    - "Each test name maps 1:1 to LF-1.9: test_layer1_batch_of_30_persists_all (LF-1.9.a) / test_layer1_timeout_all_null (LF-1.9.b) / test_layer1_partial_json_all_null (LF-1.9.c) / test_layer1_row_count_mismatch_all_null (LF-1.9.d) / test_layer1_prompt_version_bump_invalidates_prior (LF-1.9.e)"
    - "test_layer1_prompt_version_bump_invalidates_prior asserts the candidate-SELECT predicate behavior, not just the constant — it inserts a fixture row with layer1_prompt_version='old_version' and verifies _build_topic_filter_query's SQL re-selects it (this crosses into ir-1-01's deliverable; the test is owned here per LF-1.9.e mapping)"
    - "Tests run cleanly without DEEPSEEK_API_KEY, OMNIGRAPH_GEMINI_KEY, or any LLM credential — all LLM calls are monkeypatched"
    - "pytest -x tests/unit/test_article_filter.py exits 0 with 5/5 PASS. The full unit suite (`pytest tests/unit/`) does not regress on the v3.4 baseline pass count (modulo ir-1-00/ir-1-01 changes)"
  artifacts:
    - path: "tests/unit/test_article_filter.py"
      provides: "LF-1.9 5-test set replacing the V35-FOUND-01 placeholder contract tests"
      min_lines: 200
      contains: "def test_layer1_batch_of_30_persists_all"
      contains_must_not: "def test_layer1_returns_filter_result\n"
  key_links:
    - from: "tests/unit/test_article_filter.py"
      to: "lib.article_filter.layer1_pre_filter / persist_layer1_verdicts / FilterResult / ArticleMeta / PROMPT_VERSION_LAYER1"
      via: "import + monkeypatch on LLM dependency"
      pattern: "from lib.article_filter import"
    - from: "tests/unit/test_article_filter.py"
      to: "batch_ingest_from_spider._build_topic_filter_query (for prompt_version bump test)"
      via: "import for SQL predicate verification"
      pattern: "from batch_ingest_from_spider import _build_topic_filter_query"
---

<objective>
Wave 2 (parallel-able with ir-1-01): rewrite `tests/unit/test_article_filter.py` to LF-1.9's 5-test set. Delete the V35-FOUND-01 placeholder tests (their shape is no longer valid). New tests use pytest + monkeypatch for LLM swap; no network; no credentials.

Output: `tests/unit/test_article_filter.py` with 5 LF-1.9 tests, all GREEN against ir-1-00's `lib/article_filter.py` and ir-1-01's `_build_topic_filter_query`. Full unit suite stays at or above the pre-ir-1 baseline pass count.
</objective>

<execution_context>
@.planning/PROJECT-v3.5-Ingest-Refactor.md
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/ir-1-00-PLAN.md
@.planning/phases/ir-1-real-layer1-and-kol-ingest-wiring/ir-1-01-PLAN.md
</execution_context>

<context>
@CLAUDE.md
</context>

<interfaces>
<!-- Symbols under test -->
```python
# lib/article_filter.py (ir-1-00 output):
ArticleMeta, ArticleWithBody, FilterResult
PROMPT_VERSION_LAYER1, LAYER1_BATCH_SIZE, LAYER1_TIMEOUT_SEC
async def layer1_pre_filter(articles: list[ArticleMeta]) -> list[FilterResult]
def persist_layer1_verdicts(conn, articles, results) -> None

# batch_ingest_from_spider.py (ir-1-01 output):
def _build_topic_filter_query(topics: list[str]) -> tuple[str, tuple[str, ...]]
```

<!-- Test fixture pattern: monkeypatch the LLM dependency at the import site
     in lib.article_filter. Because layer1_pre_filter does the import inside
     the function body (`from lib.vertex_gemini_complete import ...`), tests
     monkeypatch the module-level symbol BEFORE calling layer1_pre_filter:

     monkeypatch.setattr(
         "lib.vertex_gemini_complete.vertex_gemini_model_complete",
         fake_async_llm,
     )
     monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")

     This route is preferred (Vertex Gemini is the production-deployed path
     on Hermes per STATE-v3.5-Ingest-Refactor.md § Current Hermes Operational
     State). Legacy lib.gemini_model_complete is not exercised in these tests
     (it is the local-dev fallback only). -->
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 3.1: Rewrite tests/unit/test_article_filter.py</name>
  <read_first>
    - tests/unit/test_article_filter.py (current 99-line placeholder test set — to be deleted)
    - lib/article_filter.py post ir-1-00 (full file)
    - batch_ingest_from_spider.py post ir-1-01 (specifically `_build_topic_filter_query`)
    - .planning/REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-1.9 (the 5 cases)
  </read_first>
  <files>tests/unit/test_article_filter.py</files>
  <behavior>
    - Module docstring describes the 5 LF-1.9 cases + maps each to a test name
    - Helper `_meta(...)` builds an ArticleMeta with sensible defaults
    - Helper `_fake_llm_factory(*, response: str, raise_exc: BaseException | None = None)` returns an async function suitable for monkeypatch
    - Test file uses `pytest` + `pytest.mark.asyncio` (or `asyncio.run` per current repo convention — check tests/unit/ for prior async tests)
    - Tests are deterministic — no real time / no network / no real DB. SQLite tests use `:memory:` connections
  </behavior>
  <action>
**Replace `tests/unit/test_article_filter.py` entirely** with this content:

```python
"""LF-1.9 unit tests for lib.article_filter.layer1_pre_filter.

Test mapping (REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-1.9):

    a) test_layer1_batch_of_30_persists_all
       — happy path: 30-article batch, all verdicts returned, persisted to DB
    b) test_layer1_timeout_all_null
       — asyncio.TimeoutError → all 30 results have verdict=None, reason='timeout'
    c) test_layer1_partial_json_all_null
       — LLM returns truncated JSON → all 30 results NULL, reason='partial_json'
    d) test_layer1_row_count_mismatch_all_null
       — LLM returns 29 entries for 30 inputs → all NULL, reason='row_count_mismatch'
    e) test_layer1_prompt_version_bump_invalidates_prior
       — _build_topic_filter_query SQL re-selects rows whose layer1_prompt_version
         differs from the current PROMPT_VERSION_LAYER1 constant

Plus one structural test for the FilterResult dataclass (frozen + 3-field shape).

These supersede the 7 placeholder tests committed by V35-FOUND-01 (260507-lai)
which pinned the now-removed `passed: bool` shape.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import FrozenInstanceError

import pytest

from lib.article_filter import (
    ArticleMeta,
    FilterResult,
    LAYER1_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    layer1_pre_filter,
    persist_layer1_verdicts,
)


# ----------------------------- helpers -------------------------------------

def _meta(i: int, source: str = "wechat") -> ArticleMeta:
    return ArticleMeta(
        id=i,
        source=source,  # type: ignore[arg-type]
        title=f"article {i}",
        summary=f"summary {i}",
        content_length=None,
    )


def _fake_llm_factory(
    *,
    response: str | None = None,
    raise_exc: BaseException | None = None,
):
    """Return an async function suitable for monkeypatching the LLM call."""
    async def _fake(prompt, **kwargs):  # noqa: ANN001
        if raise_exc is not None:
            raise raise_exc
        return response

    return _fake


def _setup_articles_table(conn: sqlite3.Connection) -> None:
    """Create the minimal articles + rss_articles schema needed for persistence
    tests. Mirrors data/kol_scan.db column subset relevant to layer1_*."""
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL,
            layer1_reason TEXT NULL,
            layer1_at TEXT NULL,
            layer1_prompt_version TEXT NULL
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL,
            layer1_reason TEXT NULL,
            layer1_at TEXT NULL,
            layer1_prompt_version TEXT NULL
        );
        """
    )


# ------------------ structural test (dataclass) ----------------------------

def test_filter_result_is_frozen_three_field() -> None:
    """FilterResult is frozen and has the post-ir-1 3-field shape."""
    r = FilterResult(verdict="candidate", reason="ok", prompt_version="v")
    assert r.verdict == "candidate"
    assert r.reason == "ok"
    assert r.prompt_version == "v"
    with pytest.raises(FrozenInstanceError):
        r.verdict = "reject"  # type: ignore[misc]


# ----------------- LF-1.9.a — happy-path 30-batch --------------------------

@pytest.mark.asyncio
async def test_layer1_batch_of_30_persists_all(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, LAYER1_BATCH_SIZE + 1)]

    response = json.dumps([
        {"id": i, "source": "wechat",
         "verdict": "candidate" if i % 3 == 0 else "reject",
         "reason": "test_reason"}
        for i in range(1, LAYER1_BATCH_SIZE + 1)
    ], ensure_ascii=False)

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(response=response),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == LAYER1_BATCH_SIZE
    assert all(r.verdict in ("candidate", "reject") for r in results)
    assert all(r.prompt_version == PROMPT_VERSION_LAYER1 for r in results)

    # Persist + verify rows in :memory: DB
    conn = sqlite3.connect(":memory:")
    _setup_articles_table(conn)
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)",
                     (a.id, a.title))
    conn.commit()

    persist_layer1_verdicts(conn, arts, results)

    # Every row should have a non-NULL verdict + matching prompt_version
    rows = conn.execute(
        "SELECT id, layer1_verdict, layer1_prompt_version FROM articles"
    ).fetchall()
    assert len(rows) == LAYER1_BATCH_SIZE
    for _id, verdict, pv in rows:
        assert verdict in ("candidate", "reject")
        assert pv == PROMPT_VERSION_LAYER1


# ----------------- LF-1.9.b — timeout → all NULL ---------------------------

@pytest.mark.asyncio
async def test_layer1_timeout_all_null(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, 6)]

    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(raise_exc=asyncio.TimeoutError()),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == 5
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "timeout" for r in results)
    assert all(r.prompt_version == PROMPT_VERSION_LAYER1 for r in results)


# ----------------- LF-1.9.c — partial JSON → all NULL ----------------------

@pytest.mark.asyncio
async def test_layer1_partial_json_all_null(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, 11)]

    truncated_response = '[{"id": 1, "source": "wechat", "verdict": "candidate"'  # broken
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(response=truncated_response),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == 10
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "non_json" for r in results)


# ----------------- LF-1.9.d — row count mismatch → all NULL ----------------

@pytest.mark.asyncio
async def test_layer1_row_count_mismatch_all_null(monkeypatch) -> None:
    arts = [_meta(i) for i in range(1, LAYER1_BATCH_SIZE + 1)]  # 30 articles

    short_response = json.dumps([
        {"id": i, "source": "wechat", "verdict": "candidate", "reason": "x"}
        for i in range(1, LAYER1_BATCH_SIZE)  # 29 entries — one missing
    ], ensure_ascii=False)
    monkeypatch.setenv("OMNIGRAPH_LLM_PROVIDER", "vertex_gemini")
    monkeypatch.setattr(
        "lib.vertex_gemini_complete.vertex_gemini_model_complete",
        _fake_llm_factory(response=short_response),
    )

    results = await layer1_pre_filter(arts)
    assert len(results) == LAYER1_BATCH_SIZE
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "row_count_mismatch" for r in results)


# ----------------- LF-1.9.e — prompt_version bump re-selects ---------------

def test_layer1_prompt_version_bump_invalidates_prior() -> None:
    """Candidate SQL re-selects rows whose layer1_prompt_version != current."""
    from batch_ingest_from_spider import _build_topic_filter_query

    sql, params = _build_topic_filter_query([])
    assert "layer1_verdict IS NULL" in sql
    assert "layer1_prompt_version" in sql
    assert params[0] == PROMPT_VERSION_LAYER1

    # Behavioral check: simulate a row with stale prompt_version is still
    # candidate-selected (prompt_version mismatch path).
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            account_id INTEGER REFERENCES accounts(id),
            title TEXT, url TEXT, body TEXT, digest TEXT,
            layer1_verdict TEXT NULL, layer1_reason TEXT NULL,
            layer1_at TEXT NULL, layer1_prompt_version TEXT NULL
        );
        CREATE TABLE ingestions (article_id INTEGER, status TEXT);
        INSERT INTO accounts VALUES (1, 'acct');
        INSERT INTO articles(id, account_id, title, url, body, digest,
                             layer1_verdict, layer1_prompt_version)
            VALUES (10, 1, 't', 'u', '', 'd',
                    'candidate', 'old_prompt_version_v0');
        INSERT INTO articles(id, account_id, title, url, body, digest)
            VALUES (11, 1, 't2', 'u2', '', 'd2');
        """
    )
    rows = list(conn.execute(sql, params))
    ids = sorted(r[0] for r in rows)
    # Both rows are candidates: id=10 because prompt_version differs;
    # id=11 because layer1_verdict is NULL.
    assert ids == [10, 11]


# ----------------- regression — empty batch returns [] ---------------------

@pytest.mark.asyncio
async def test_layer1_empty_batch_no_op() -> None:
    results = await layer1_pre_filter([])
    assert results == []


# ----------------- regression — over-size batch raises ---------------------

@pytest.mark.asyncio
async def test_layer1_over_max_raises() -> None:
    arts = [_meta(i) for i in range(LAYER1_BATCH_SIZE + 5)]
    with pytest.raises(ValueError, match="Layer 1 batch size"):
        await layer1_pre_filter(arts)
```

**HARD CONSTRAINTS:**
- Tests MUST NOT make real LLM calls — every test that hits `layer1_pre_filter` monkeypatches the LLM symbol
- Tests MUST NOT require any environment credential (`DEEPSEEK_API_KEY` / `OMNIGRAPH_GEMINI_KEY` / `OMNIGRAPH_LLM_PROVIDER`)
- Tests MUST run on the existing pytest config — do NOT add `pytest.ini` entries; do NOT add new dependencies
- The `pytest-asyncio` package MUST already be a dev-dep on this repo (verify with `grep asyncio pyproject.toml requirements*.txt 2>&1`); if not, FAIL FAST and surface to operator before continuing — adding the dep is a separate decision
- DO NOT keep any of the 7 V35-FOUND-01 placeholder tests
  </action>
  <verify>
    <automated>grep -q "pytest-asyncio\|pytest_asyncio" requirements*.txt pyproject.toml 2>/dev/null || (echo "WARN: pytest-asyncio dep not found in requirements/pyproject; verify availability before running tests"; exit 0)</automated>
    <automated>python -m pytest tests/unit/test_article_filter.py -v --tb=short -x 2>&1 | tail -20</automated>
  </verify>
  <acceptance_criteria>
    - File `tests/unit/test_article_filter.py` contains all 7 test functions named in the action body
    - File does NOT contain literal `def test_layer1_returns_filter_result` (old V35-FOUND-01 test deleted)
    - File does NOT contain literal `passed=True` (old shape gone)
    - `python -m pytest tests/unit/test_article_filter.py -v -x` exits 0 with 7/7 PASS
    - `python -m pytest tests/unit/ -q` does NOT regress: completed tests count >= v3.4 baseline (record baseline before edit; compare after)
  </acceptance_criteria>
  <done>LF-1.9 fully delivered. The 7 V35-FOUND-01 placeholder tests are replaced with 5 LF-1.9 cases + 1 dataclass shape test + 2 regression tests (empty / over-max).</done>
</task>

</tasks>

<verification>
After Task 3.1 lands:

```bash
# Targeted suite — must be GREEN
python -m pytest tests/unit/test_article_filter.py -v --tb=short

# Full unit suite — must not regress
python -m pytest tests/unit/ -q 2>&1 | tail -5

# Coverage gate (CLAUDE.md global rule: 80%+ on lib/article_filter.py)
python -m pytest tests/unit/test_article_filter.py --cov=lib.article_filter --cov-report=term-missing 2>&1 | tail -15
# Expect coverage ≥ 80% on lib/article_filter.py
```
</verification>

<commit_message>
test(ir-1): LF-1.9 5-case Layer 1 unit suite

Replace 7 V35-FOUND-01 placeholder tests with LF-1.9's 5 cases plus 1
dataclass shape test plus 2 regressions (empty + over-max). All tests
monkeypatch the LLM dependency; no network, no credentials. SQLite
tests use :memory: DB. Coverage ≥80% on lib/article_filter.py.

REQs: LF-1.9
Phase: v3.5-Ingest-Refactor / ir-1 / plan 02
Depends-on: ir-1-00 (lib/article_filter contract); cross-references
ir-1-01 for the prompt_version bump test.
</commit_message>
