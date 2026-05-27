---
phase: ir-2-real-layer2-and-fullbody-scoring
plan: 02
type: execute
wave: 2
depends_on:
  - "ir-2-00"
files_modified:
  - tests/unit/test_article_filter.py
autonomous: true
requirements:
  - LF-2.8

must_haves:
  truths:
    - "tests/unit/test_article_filter.py is EXTENDED (not rewritten) with Layer 2 tests pinning LF-2.8's 6 cases. Existing 8 Layer 1 tests remain untouched and continue to pass."
    - "Layer 2 test names map 1:1 to LF-2.8 cases: test_layer2_batch_of_5_persists_all (LF-2.8.a happy path 'ok'/'reject'); test_layer2_timeout_all_null (LF-2.8.b); test_layer2_partial_json_all_null (LF-2.8.c); test_layer2_row_count_mismatch_all_null (LF-2.8.d); test_layer2_prompt_version_bump_invalidates_prior (LF-2.8.e); test_layer2_reject_writes_ingestions_skipped (LF-2.8.f integration-shape, calls drain helper indirectly via mock conn)."
    - "All Layer 2 tests use pytest + monkeypatch on lib.llm_deepseek.deepseek_model_complete — no real network, no real DEEPSEEK_API_KEY beyond the dummy needed for module import."
    - "Decision rule (relevant=true AND depth_score>=2 → 'ok', else 'reject') is exercised by the happy-path test through 5 article scenarios spanning all four buckets from the spike report."
    - "pytest tests/unit/test_article_filter.py exits 0 with N/N PASS where N >= 14 (8 Layer 1 + 6 Layer 2). Full unit suite does not regress baseline."
  artifacts:
    - path: "tests/unit/test_article_filter.py"
      provides: "Combined Layer 1 (8 tests, ir-1) + Layer 2 (6+ tests, ir-2) suite. Module docstring extended to map LF-2.8 cases."
      min_lines: 350
      contains: "def test_layer2_batch_of_5_persists_all"
  key_links:
    - from: "tests/unit/test_article_filter.py"
      to: "lib.article_filter.layer2_full_body_score / persist_layer2_verdicts / FilterResult / ArticleWithBody / PROMPT_VERSION_LAYER2"
      via: "import + monkeypatch on DeepSeek dependency"
      pattern: "from lib.article_filter import"
    - from: "tests/unit/test_article_filter.py (test_layer2_prompt_version_bump_invalidates_prior)"
      to: "lib.article_filter.PROMPT_VERSION_LAYER2 + persist_layer2_verdicts behavior"
      via: "import for prompt-version round-trip verification"
      pattern: "PROMPT_VERSION_LAYER2"
---

<objective>
Wave 2 (parallel-able with ir-2-01): extend `tests/unit/test_article_filter.py` with LF-2.8's 6 Layer 2 unit tests. The 8 existing Layer 1 tests (from ir-1-02) stay in place. New tests follow the same monkeypatch + `:memory:` SQLite pattern, swapping the LLM dependency at `lib.llm_deepseek.deepseek_model_complete` import path.

Output: combined Layer 1 + Layer 2 unit suite, ≥14 tests, all GREEN. Coverage on `lib/article_filter.py` stays ≥80%.
</objective>

<execution_context>
@.planning/REQUIREMENTS-v3.5-Ingest-Refactor.md
@.planning/phases/ir-2-real-layer2-and-fullbody-scoring/ir-2-00-PLAN.md
@.planning/phases/ir-2-real-layer2-and-fullbody-scoring/ir-2-01-PLAN.md
</execution_context>

<context>
@CLAUDE.md
</context>

<interfaces>
<!-- Symbols under test (post ir-2-00) -->
```python
ArticleWithBody  # already exists from ir-1
FilterResult     # already exists
PROMPT_VERSION_LAYER2 = "layer2_v0_20260507"
LAYER2_BATCH_SIZE = 5
LAYER2_TIMEOUT_SEC = 60
LAYER2_BODY_TRUNCATION_CHARS = 8000

async def layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]
def persist_layer2_verdicts(conn, articles, results) -> None
```

<!-- Test fixture pattern: monkeypatch the LLM dependency at the import-resolution
     site. Because layer2_full_body_score imports lib.llm_deepseek inside the
     function body, tests must monkeypatch the module-level symbol BEFORE calling: -->

```python
monkeypatch.setattr(
    "lib.llm_deepseek.deepseek_model_complete",
    fake_async_llm,
)
```

<!-- LF-2.8.f integration-shape test: instead of importing the entire ingest
     loop (heavy), the test directly drives a mock _drain_layer2_queue-like
     fixture: persists a 'reject' verdict via persist_layer2_verdicts, then
     verifies the SQL UPDATE landed correctly. The actual drain helper is
     covered by ir-2-01 wiring's commit message + indirect coverage via the
     close-out smoke. The unit test pins ONLY the persistence + verdict
     contract. -->
</interfaces>

<tasks>

<task type="auto" tdd="false">
  <name>Task 3.1: Extend tests/unit/test_article_filter.py with Layer 2 cases</name>
  <read_first>
    - tests/unit/test_article_filter.py (current ir-1-02 8-test shape)
    - lib/article_filter.py post ir-2-00 (full file)
    - .planning/REQUIREMENTS-v3.5-Ingest-Refactor.md § LF-2.8 (the 6 cases)
    - .scratch/layer2-validation-20260507-210423.md § "Sample list" (4-bucket structure for happy-path scenarios)
  </read_first>
  <files>tests/unit/test_article_filter.py</files>
  <behavior>
    - Module docstring extended to map LF-2.8 cases (a-f) to test names.
    - Imports gain `ArticleWithBody`, `LAYER2_BATCH_SIZE`, `PROMPT_VERSION_LAYER2`, `layer2_full_body_score`, `persist_layer2_verdicts`.
    - Helpers add `_with_body(i, body=..., ...)` builder and `_setup_articles_with_layer2(conn)` schema fixture (both layer1 + layer2 columns present, since persist_layer2_verdicts mirrors the layer1 helper but writes layer2_* cols).
    - 6+ Layer 2 tests added at the bottom of the file (after the existing layer1 tests). Each test follows the existing monkeypatch + `:memory:` pattern.
    - Existing 8 layer1 tests are NOT modified.
  </behavior>
  <action>
**Concrete edit instructions for `tests/unit/test_article_filter.py`:**

1. **Update module docstring** to add Layer 2 mapping after the existing LF-1.9 mapping:

```python
"""LF-1.9 + LF-2.8 unit tests for lib.article_filter Layer 1 / Layer 2.

Layer 1 (LF-1.9) test mapping (REQUIREMENTS § LF-1.9):
    a-e) ... (existing) ...

Layer 2 (LF-2.8) test mapping (REQUIREMENTS § LF-2.8):
    a) test_layer2_batch_of_5_persists_all
       — happy path: 5-article batch spanning all 4 spike buckets;
         decision rule (relevant && depth>=2 → 'ok', else 'reject')
         applied; verdicts persisted to articles.layer2_*
    b) test_layer2_timeout_all_null
       — asyncio.TimeoutError → all results verdict=None reason='timeout'
    c) test_layer2_partial_json_all_null
       — LLM returns truncated JSON → all NULL reason='non_json'
    d) test_layer2_row_count_mismatch_all_null
       — LLM returns 4 entries for 5 inputs → all NULL reason='row_count_mismatch'
    e) test_layer2_prompt_version_bump_invalidates_prior
       — bumping PROMPT_VERSION_LAYER2 in test fixture forces re-eval semantics
         (verified via persist round-trip + manual SQL re-select)
    f) test_layer2_reject_writes_skipped_via_persist_round_trip
       — persist_layer2_verdicts writes verdict='reject' correctly; downstream
         ingest-loop wiring (ir-2-01) performs the ingestions(status='skipped')
         INSERT — that wiring is covered by close-out smoke, this test pins
         only the persistence contract for the reject case.

Tests use pytest-asyncio mode='auto' (configured in pyproject.toml) so plain
async def test_... is auto-discovered. Layer 1 LLM monkeypatched at
lib.vertex_gemini_complete.vertex_gemini_model_complete; Layer 2 LLM
monkeypatched at lib.llm_deepseek.deepseek_model_complete. No network, no
credentials beyond DEEPSEEK_API_KEY=dummy for module import.
"""
```

2. **Update imports** to include Layer 2 symbols:

```python
from lib.article_filter import (
    ArticleMeta,
    ArticleWithBody,
    FilterResult,
    LAYER1_BATCH_SIZE,
    LAYER2_BATCH_SIZE,
    PROMPT_VERSION_LAYER1,
    PROMPT_VERSION_LAYER2,
    layer1_pre_filter,
    layer2_full_body_score,
    persist_layer1_verdicts,
    persist_layer2_verdicts,
)
```

3. **Add helpers AFTER the existing `_setup_articles_table` helper**:

```python
def _with_body(i: int, body: str | None = None, source: str = "wechat") -> ArticleWithBody:
    return ArticleWithBody(
        id=i,
        source=source,  # type: ignore[arg-type]
        title=f"article {i}",
        body=body if body is not None else f"Body content for article {i}.",
    )


def _setup_articles_with_layer2(conn: sqlite3.Connection) -> None:
    """Schema with both layer1_* and layer2_* columns for round-trip tests."""
    conn.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL, layer1_reason TEXT NULL,
            layer1_at TEXT NULL, layer1_prompt_version TEXT NULL,
            layer2_verdict TEXT NULL, layer2_reason TEXT NULL,
            layer2_at TEXT NULL, layer2_prompt_version TEXT NULL
        );
        CREATE TABLE rss_articles (
            id INTEGER PRIMARY KEY,
            title TEXT,
            layer1_verdict TEXT NULL, layer1_reason TEXT NULL,
            layer1_at TEXT NULL, layer1_prompt_version TEXT NULL,
            layer2_verdict TEXT NULL, layer2_reason TEXT NULL,
            layer2_at TEXT NULL, layer2_prompt_version TEXT NULL
        );
        """
    )
```

4. **Add 6 Layer 2 tests AT THE END of the file**:

```python
# ============================================================
# LF-2.8 — Layer 2 unit tests
# ============================================================

# ----------------- LF-2.8.a — happy-path 5-article batch -------------------

async def test_layer2_batch_of_5_persists_all(monkeypatch) -> None:
    arts = [
        _with_body(383, body="架构源码解读 + 推理算法详解 + 数学推导..."),
        _with_body(336, body="我用 DeepSeek + Claude Code 写了个工具，分享体验..."),
        _with_body(535, body="QT5 + OpenCV4.8 + 深度学习路线图..."),
        _with_body(625, body="CLAUDE.md 最佳实践指南：实战配置 + 案例拆解..."),
        _with_body(693, body="读完 Kimi 新论文：MoE 路由 + KV cache 优化深度解读..."),
    ]

    # LLM returns: ok / reject / reject / ok / ok per spike-style decision rule
    response = json.dumps([
        {"id": 383, "depth_score": 3, "relevant": True,  "reason": "架构深度解读"},
        {"id": 336, "depth_score": 1, "relevant": True,  "reason": "工具体验软文,无机制"},
        {"id": 535, "depth_score": 1, "relevant": False, "reason": "CV路线图,命中视觉规则"},
        {"id": 625, "depth_score": 2, "relevant": True,  "reason": "实战配置指南"},
        {"id": 693, "depth_score": 3, "relevant": True,  "reason": "MoE推理深度解读"},
    ], ensure_ascii=False)

    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(response=response),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == 5
    expected_verdicts = ["ok", "reject", "reject", "ok", "ok"]
    actual_verdicts = [r.verdict for r in results]
    assert actual_verdicts == expected_verdicts, (
        f"expected {expected_verdicts}, got {actual_verdicts}"
    )
    assert all(r.prompt_version == PROMPT_VERSION_LAYER2 for r in results)

    # Persist + verify
    conn = sqlite3.connect(":memory:")
    _setup_articles_with_layer2(conn)
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)", (a.id, a.title))
    conn.commit()

    persist_layer2_verdicts(conn, arts, results)

    rows = conn.execute(
        "SELECT id, layer2_verdict, layer2_prompt_version FROM articles ORDER BY id"
    ).fetchall()
    persisted = {r[0]: (r[1], r[2]) for r in rows}
    for a, expected_verdict in zip(arts, expected_verdicts):
        v, pv = persisted[a.id]
        assert v == expected_verdict
        assert pv == PROMPT_VERSION_LAYER2


# ----------------- LF-2.8.b — timeout → all NULL ---------------------------

async def test_layer2_timeout_all_null(monkeypatch) -> None:
    arts = [_with_body(i) for i in range(1, 4)]

    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(raise_exc=asyncio.TimeoutError()),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == 3
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "timeout" for r in results)
    assert all(r.prompt_version == PROMPT_VERSION_LAYER2 for r in results)


# ----------------- LF-2.8.c — partial / non-JSON → all NULL ---------------

async def test_layer2_partial_json_all_null(monkeypatch) -> None:
    arts = [_with_body(i) for i in range(1, 6)]

    truncated_response = '[{"id": 1, "depth_score": 2, "relevant": true'
    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(response=truncated_response),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == 5
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "non_json" for r in results)


# ----------------- LF-2.8.d — row count mismatch → all NULL ----------------

async def test_layer2_row_count_mismatch_all_null(monkeypatch) -> None:
    arts = [_with_body(i) for i in range(1, LAYER2_BATCH_SIZE + 1)]  # 5

    short_response = json.dumps([
        {"id": i, "depth_score": 2, "relevant": True, "reason": "x"}
        for i in range(1, LAYER2_BATCH_SIZE)  # 4 entries — one short
    ], ensure_ascii=False)
    monkeypatch.setattr(
        "lib.llm_deepseek.deepseek_model_complete",
        _fake_llm_factory(response=short_response),
    )

    results = await layer2_full_body_score(arts)
    assert len(results) == LAYER2_BATCH_SIZE
    assert all(r.verdict is None for r in results)
    assert all(r.reason == "row_count_mismatch" for r in results)


# ----------------- LF-2.8.e — prompt_version bump invalidates -------------

def test_layer2_prompt_version_bump_invalidates_prior() -> None:
    """Persisting with current PROMPT_VERSION_LAYER2 + then re-reading shows
    that an older row (different prompt_version) would be re-selected by an
    SQL predicate of the form layer2_verdict IS NULL OR layer2_prompt_version
    IS NOT current. This test verifies the persist + read invariant; the
    actual SQL predicate lives in batch_ingest_from_spider candidate selection
    (ir-2-01 scope, exercised by close-out smoke + integration tests)."""
    conn = sqlite3.connect(":memory:")
    _setup_articles_with_layer2(conn)

    arts = [_with_body(10), _with_body(11)]
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)", (a.id, a.title))
    conn.commit()

    # Manually simulate a row tagged with an OLD prompt version.
    conn.execute(
        "UPDATE articles SET layer2_verdict = 'ok', layer2_prompt_version = 'old_v0' WHERE id = 10"
    )
    conn.commit()

    # Persist the SECOND row with the CURRENT version.
    results = [
        FilterResult(verdict="ok", reason="x", prompt_version=PROMPT_VERSION_LAYER2),
        FilterResult(verdict="reject", reason="y", prompt_version=PROMPT_VERSION_LAYER2),
    ]
    persist_layer2_verdicts(conn, arts, results)

    # Selection rule: rows with NULL OR different prompt_version need re-eval.
    re_eval_sql = """
        SELECT id FROM articles
        WHERE layer2_verdict IS NULL
           OR layer2_prompt_version IS NOT ?
        ORDER BY id
    """
    re_eval_ids = [r[0] for r in conn.execute(re_eval_sql, (PROMPT_VERSION_LAYER2,))]
    # Only id=10 has stale version; id=11 was just persisted with current.
    assert re_eval_ids == [10]


# ----------------- LF-2.8.f — reject persists correctly --------------------

def test_layer2_reject_writes_skipped_via_persist_round_trip() -> None:
    """persist_layer2_verdicts writes verdict='reject' to articles.layer2_verdict.
    The downstream ingest-loop wiring (ir-2-01 _drain_layer2_queue) reads the
    persisted verdict and writes ingestions(status='skipped') — that wiring
    is integration-tested via the close-out smoke. This unit test pins ONLY
    the persistence contract for reject-shape FilterResults."""
    conn = sqlite3.connect(":memory:")
    _setup_articles_with_layer2(conn)
    arts = [_with_body(20), _with_body(21)]
    for a in arts:
        conn.execute("INSERT INTO articles(id, title) VALUES (?, ?)", (a.id, a.title))
    conn.commit()

    results = [
        FilterResult(verdict="reject", reason="软文,无机制",
                     prompt_version=PROMPT_VERSION_LAYER2),
        FilterResult(verdict="ok", reason="架构解读",
                     prompt_version=PROMPT_VERSION_LAYER2),
    ]
    persist_layer2_verdicts(conn, arts, results)

    rows = conn.execute(
        "SELECT id, layer2_verdict, layer2_reason FROM articles ORDER BY id"
    ).fetchall()
    assert rows[0] == (20, "reject", "软文,无机制")
    assert rows[1] == (21, "ok", "架构解读")


# ----------------- regression — empty batch returns [] ---------------------

async def test_layer2_empty_batch_no_op() -> None:
    results = await layer2_full_body_score([])
    assert results == []


# ----------------- regression — over-size batch raises ---------------------

async def test_layer2_over_max_raises() -> None:
    arts = [_with_body(i) for i in range(LAYER2_BATCH_SIZE + 2)]  # 7
    with pytest.raises(ValueError, match="Layer 2 batch size"):
        await layer2_full_body_score(arts)
```

**HARD CONSTRAINTS:**
- Tests MUST NOT make real LLM calls — every Layer 2 test that hits `layer2_full_body_score` monkeypatches `lib.llm_deepseek.deepseek_model_complete`.
- Tests MUST NOT modify any of the 8 existing Layer 1 tests.
- Tests MUST run on existing pytest config (`asyncio_mode = "auto"`); do NOT add markers; do NOT add deps.
- The test file requires `DEEPSEEK_API_KEY=dummy` env to be set (because lib/article_filter eagerly imports lib package which eagerly imports lib.llm_deepseek which raises on import without the key). This matches the existing pytest invocation pattern from ir-1-02.
  </action>
  <verify>
    <automated>DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/test_article_filter.py -v --tb=short 2>&1 | tail -30</automated>
  </verify>
  <acceptance_criteria>
    - File contains all 8 Layer 1 test names UNCHANGED (test_filter_result_is_frozen_three_field, test_layer1_batch_of_30_persists_all, test_layer1_timeout_all_null, test_layer1_partial_json_all_null, test_layer1_row_count_mismatch_all_null, test_layer1_prompt_version_bump_invalidates_prior, test_layer1_empty_batch_no_op, test_layer1_over_max_raises).
    - File contains the 6 LF-2.8 mapped Layer 2 tests + 2 regression tests = 8 new tests.
    - `DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/test_article_filter.py -v` exits 0 with 16 passed.
    - File min_lines >= 350.
  </acceptance_criteria>
  <done>LF-2.8 fully delivered. The 8 Layer 1 tests stay green. Combined Layer 1 + Layer 2 unit suite covers the contract.</done>
</task>

</tasks>

<verification>
After Task 3.1 lands:

```bash
# Combined Layer 1 + Layer 2 suite
DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/test_article_filter.py -v --tb=short

# Full unit suite — must not regress
DEEPSEEK_API_KEY=dummy python -m pytest tests/unit/ -q
```
</verification>

<commit_message>
test(ir-2): LF-2.8 6-case Layer 2 unit suite

Extend tests/unit/test_article_filter.py with LF-2.8's 6 Layer 2 cases plus
2 regressions (empty + over-max). Existing 8 Layer 1 tests (LF-1.9) stay
unchanged and continue to pass.

New tests monkeypatch lib.llm_deepseek.deepseek_model_complete (matching
ir-2-00's import-on-call pattern). No network, no real DEEPSEEK_API_KEY.
SQLite tests use :memory: DB with extended schema (both layer1_* and
layer2_* columns).

Decision rule (relevant=true AND depth_score>=2 → 'ok', else 'reject') is
exercised in the happy-path test by 5 articles spanning the 4 spike buckets:
deep technical (id=383, depth=3, ok), AI software/shallow (id=336, depth=1,
reject), off-topic CV (id=535, relevant=false, reject), borderline keep
(id=625, depth=2, ok), borderline depth-3 (id=693, depth=3, ok).

REQs: LF-2.8
Phase: v3.5-Ingest-Refactor / ir-2 / plan 02
Depends-on: ir-2-00 (lib/article_filter Layer 2 contract); cross-ref ir-2-01
for the persist round-trip integration coverage.
</commit_message>
