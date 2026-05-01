# Plan 09-00 — Timeout Layer

**Phase:** 9 — Timeout Control + LightRAG State Management
**REQs covered:** TIMEOUT-01, TIMEOUT-02, TIMEOUT-03
**Dependencies:** none (Phase 8 complete; self-contained — no shared files with 09-01)
**Wave:** 1 (can run in parallel with 09-01 if file ownership allows; see § Parallelism note)

---

## Summary

Deliver three deterministic timeout controls so single-chunk and single-article runaways cannot
stall the ingestion pipeline: LightRAG per-chunk `LLM_TIMEOUT=600` via env export at the top of
every entry-point script (D-09.01), DeepSeek `AsyncOpenAI` client-side `timeout=120.0` (D-09.02),
and a chunk-scaled outer `asyncio.wait_for` budget `max(120 + 30 × chunk_count, 900)` in
`batch_ingest_from_spider.ingest_article` replacing the hardcoded `1200` (D-09.03).

---

## Canonical Refs

- `.planning/phases/09-timeout-state-management/09-PRD.md` — primary acceptance criteria
- `.planning/phases/09-timeout-state-management/09-CONTEXT.md` — D-09.01, D-09.02, D-09.03
- `.planning/REQUIREMENTS.md` — TIMEOUT-01, TIMEOUT-02, TIMEOUT-03
- `venv/Lib/site-packages/lightrag/lightrag.py:432` — LightRAG reads `LLM_TIMEOUT` env at
  dataclass-definition time
- `venv/Lib/site-packages/lightrag/constants.py:100` — `DEFAULT_LLM_TIMEOUT = 180`
- `lib/llm_deepseek.py:89` — `_client = AsyncOpenAI(api_key=_API_KEY, base_url=...)` — TIMEOUT-02
  target
- `batch_ingest_from_spider.py:73-99` — `ingest_article` contains
  `asyncio.wait_for(..., timeout=1200)` — TIMEOUT-03 target
- `tests/unit/test_lightrag_llm.py` — DeepSeek test scaffolding (mock patterns, monkeypatch
  env-reset fixture)

---

## Files to modify

| File                                               | Why                                                                                   |
| -------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `lib/llm_deepseek.py`                              | Add `timeout=120.0` kwarg to `AsyncOpenAI(...)` constructor (D-09.02)                 |
| `batch_ingest_from_spider.py`                      | Replace `timeout=1200` with chunk-scaled budget (D-09.03) + add `LLM_TIMEOUT` env export at module top (D-09.01) |
| `ingest_wechat.py`                                 | Add `os.environ.setdefault("LLM_TIMEOUT", "600")` at the TOP of the file (D-09.01)   |
| `run_uat_ingest.py`                                | Add `os.environ.setdefault("LLM_TIMEOUT", "600")` at the TOP of the file (D-09.01)   |
| `tests/unit/test_lightrag_llm.py` (extend)         | Add DeepSeek client timeout assertion                                                 |
| `tests/unit/test_timeout_budget.py` (NEW)          | Pure-unit tests for `_compute_article_budget_s` helper                                |
| `tests/unit/test_lightrag_timeout.py` (NEW)        | `LLM_TIMEOUT` env-var-respected test (re-imports LightRAG)                            |

---

## Interface Contract

This plan introduces ONE new public helper that Plan 09-01 MAY call:

```python
# batch_ingest_from_spider.py (NEW helper, module-level)

def _compute_article_budget_s(full_content: str, chunk_size_chars: int = 4800) -> int:
    """Outer asyncio.wait_for budget for per-article ingest.

    Formula (D-09.03): max(120 + 30 * chunk_count, 900).

    chunk_count = max(1, len(full_content) // chunk_size_chars).
    chunk_size_chars=4800 approximates LightRAG's default 1200-token chunks.

    Inner per-chunk LLM timeout is independent: LLM_TIMEOUT=600 (D-09.01).
    """
    chunk_count = max(1, len(full_content) // chunk_size_chars)
    return max(120 + 30 * chunk_count, 900)
```

Also preserved (unchanged signature): `deepseek_model_complete`, `AsyncOpenAI._client`.

---

## Tasks

### Task 1 — TIMEOUT-01: Export `LLM_TIMEOUT=600` at entry-point tops

**File:** `ingest_wechat.py`, `run_uat_ingest.py`, `batch_ingest_from_spider.py`

**Change:**

Add at the TOP of each file (before any other import that may transitively import `lightrag`):

```python
import os
os.environ.setdefault("LLM_TIMEOUT", "600")
```

Rationale (code comment at each site):

```python
# D-09.01: LightRAG reads LLM_TIMEOUT at dataclass-definition time
# (lightrag/lightrag.py:432: `default=int(os.getenv("LLM_TIMEOUT", 180))`).
# Must be set BEFORE `from lightrag import ...` anywhere in the import chain.
# setdefault preserves any explicit override from shell env or ~/.hermes/.env.
```

Placement constraints:

- `ingest_wechat.py`: immediately after `import os` (line 1 area), before line 25's
  `from lightrag.lightrag import LightRAG, QueryParam`.
- `run_uat_ingest.py`: immediately after `import os` (line 6), adjacent to the existing
  `os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"` pattern (line 17).
- `batch_ingest_from_spider.py`: immediately after `import os` (line 28), before any import that
  transitively loads LightRAG (line 47 `from lib import INGESTION_LLM, generate_sync` does NOT
  import LightRAG, but line 482 `from ingest_wechat import get_rag` (late) DOES — setting at
  module top is still the correct place for a late import to see the env var at its import time).

**Test (NEW `tests/unit/test_lightrag_timeout.py`):**

```python
"""TIMEOUT-01: LightRAG respects LLM_TIMEOUT env var.

Verifies D-09.01: LightRAG's `default_llm_timeout` is initialized from
`os.getenv("LLM_TIMEOUT", 180)` at class-definition time. Therefore the test
MUST set the env var BEFORE importing/re-importing `lightrag.lightrag`.
"""
from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_lightrag_env(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    # Drop any cached lightrag modules so dataclass fields re-initialize.
    for mod_name in list(sys.modules):
        if mod_name == "lightrag" or mod_name.startswith("lightrag."):
            sys.modules.pop(mod_name, None)


def test_default_llm_timeout_reads_env_300(monkeypatch):
    """LLM_TIMEOUT=300 env var propagates to LightRAG.default_llm_timeout."""
    monkeypatch.setenv("LLM_TIMEOUT", "300")
    import lightrag.lightrag as lr
    # Reload so the @dataclass field default re-evaluates os.getenv.
    importlib.reload(lr)
    # default_llm_timeout is a dataclass field default; read via field().
    # Using the class directly (no instantiation needed to read field default):
    import dataclasses
    fields = {f.name: f for f in dataclasses.fields(lr.LightRAG)}
    assert fields["default_llm_timeout"].default == 300


def test_default_llm_timeout_unset_falls_back_to_180(monkeypatch):
    """Without LLM_TIMEOUT, LightRAG uses its internal DEFAULT_LLM_TIMEOUT (180)."""
    # (fixture already deletes LLM_TIMEOUT)
    import lightrag.lightrag as lr
    import importlib
    importlib.reload(lr)
    import dataclasses
    fields = {f.name: f for f in dataclasses.fields(lr.LightRAG)}
    assert fields["default_llm_timeout"].default == 180


def test_production_entry_points_set_default_600():
    """Smoke: ingest_wechat.py and batch_ingest_from_spider.py set LLM_TIMEOUT=600."""
    # Scan source for the setdefault line — avoids importing heavy modules.
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]  # repo root
    for target in ("ingest_wechat.py", "batch_ingest_from_spider.py", "run_uat_ingest.py"):
        src = (root / target).read_text(encoding="utf-8")
        assert 'setdefault("LLM_TIMEOUT", "600")' in src, \
            f"{target} missing LLM_TIMEOUT=600 setdefault (D-09.01)"
```

**Rollback:** `git revert <commit-hash>` — removes the 3 `setdefault` lines; LightRAG falls back
to its internal 180s default. No cascading impact.

---

### Task 2 — TIMEOUT-02: DeepSeek `AsyncOpenAI` client timeout=120.0

**File:** `lib/llm_deepseek.py` (line 89)

**Change:**

```python
# BEFORE (line 89):
_client: AsyncOpenAI = AsyncOpenAI(api_key=_API_KEY, base_url=_DEEPSEEK_BASE_URL)

# AFTER:
# D-09.02 (TIMEOUT-02): 120s request timeout prevents single-chunk runaway.
# Outer per-article budget (D-09.03) scales with chunk_count; this inner
# timeout kills any ONE chat.completions.create call that exceeds 120s so the
# outer budget has room to retry or fail cleanly.
_DEEPSEEK_TIMEOUT_S = 120.0
_client: AsyncOpenAI = AsyncOpenAI(
    api_key=_API_KEY,
    base_url=_DEEPSEEK_BASE_URL,
    timeout=_DEEPSEEK_TIMEOUT_S,
)
```

**Idiom choice:** pass `timeout=120.0` as a bare float (the `openai>=1.0` SDK accepts this and
interprets it as total request timeout). Planner verified the idiom by inspecting
`lib/llm_deepseek.py`'s existing import `from openai import AsyncOpenAI` — no `httpx` import
currently, so the simple float form keeps the import surface minimal (Surgical Changes).

**Test (extend `tests/unit/test_lightrag_llm.py`):**

Add at end of file:

```python
# ---------------------------------------------------------------------------
# D-09.02 / TIMEOUT-02: AsyncOpenAI client-side timeout=120.0
# ---------------------------------------------------------------------------


def test_deepseek_client_has_120s_timeout():
    """Module-level _client is constructed with timeout=120.0 (D-09.02)."""
    import lib.llm_deepseek as ld
    # AsyncOpenAI exposes the timeout on the underlying httpx client.
    # The openai SDK stores `timeout` on `self.timeout` (the initial value
    # passed to __init__); use getattr fallback for cross-version safety.
    client_timeout = getattr(ld._client, "timeout", None)
    # Normalize: accept float 120.0 OR httpx.Timeout(120.0) OR NOT_GIVEN sentinel with
    # a 120-second total elsewhere. Assert the observable: pass-through float.
    if isinstance(client_timeout, (int, float)):
        assert client_timeout == 120.0
    else:
        # httpx.Timeout case: the `read` attribute is 120.0.
        assert getattr(client_timeout, "read", None) == 120.0 or \
               getattr(client_timeout, "timeout", None) == 120.0
```

**Rollback:** `git revert <commit-hash>` — client falls back to SDK default timeout (typically
10min). No breaking API contract.

---

### Task 3 — TIMEOUT-03: Chunk-scaled `asyncio.wait_for` budget

**File:** `batch_ingest_from_spider.py` (lines 73–99)

**Change:**

1. Add the `_compute_article_budget_s` helper at module scope (after imports, before
   `ingest_article`):

```python
# D-09.03 (TIMEOUT-03): per-article outer budget formula.
# Inner LightRAG per-chunk LLM timeout is LLM_TIMEOUT=600 (D-09.01) — set via
# setdefault at top of file.
_CHUNK_SIZE_CHARS = 4800   # ~1200 tokens × 4 chars/token; LightRAG default chunk size
_BASE_BUDGET_S = 120
_PER_CHUNK_S = 30
_SINGLE_CHUNK_FLOOR_S = 900  # guarantees one slow 800s DeepSeek chunk completes


def _compute_article_budget_s(full_content: str) -> int:
    """Compute outer asyncio.wait_for budget for an article (D-09.03).

    Two-layer timeout semantics:
      - Outer (this budget): governs whole-article ingest call.
      - Inner (LLM_TIMEOUT=600 via D-09.01): governs each per-chunk LLM call.

    Formula: max(BASE + PER_CHUNK * chunk_count, FLOOR).

    chunk_count is derived from len(full_content) / _CHUNK_SIZE_CHARS (floor).
    Linear scaling matters more than exact token math; ~4800 chars ≈ 1200 tokens
    ≈ LightRAG's default chunk_token_size.
    """
    chunk_count = max(1, len(full_content) // _CHUNK_SIZE_CHARS)
    return max(_BASE_BUDGET_S + _PER_CHUNK_S * chunk_count, _SINGLE_CHUNK_FLOOR_S)
```

2. **Complication resolution (per D-09.03):** `ingest_article(url, dry_run, rag)` at line 73
   currently wraps the ENTIRE `ingest_wechat.ingest_article(url, rag=rag)` call — which includes
   scrape + image-download + ainsert. `full_content` is not known at the wrap site. **Plan
   decision (option c from CONTEXT):** use `_SINGLE_CHUNK_FLOOR_S` (900s) as the conservative
   budget for the scrape-+-ingest wrap site. Exact per-chunk scaling happens in Plan 09-01 or
   Phase 10's refactor where scrape/ingest are decoupled. For v3.1 gate, 900s floor + 600s
   per-chunk inner timeout + DeepSeek 120s client timeout is sufficient — the PRD's success
   criterion 3 uses a 5s budget to prove rollback, which the floor doesn't affect.

   Rewrite the `asyncio.wait_for` call:

```python
# BEFORE (lines 88-91):
        await asyncio.wait_for(
            ingest_wechat.ingest_article(url, rag=rag),
            timeout=1200,
        )

# AFTER:
        # D-09.03: 900s floor covers a worst-case single-chunk 800s DeepSeek call.
        # When Plan 09-01 / Phase 10 decouple scrape from ingest, the inner
        # rag.ainsert wrap can use the chunk-count-aware budget via
        # _compute_article_budget_s(full_content). For now, floor suffices.
        await asyncio.wait_for(
            ingest_wechat.ingest_article(url, rag=rag),
            timeout=_SINGLE_CHUNK_FLOOR_S,
        )
```

   Also update the logging on line 94:

```python
# BEFORE:
    except asyncio.TimeoutError:
        logger.warning("TIMEOUT (600s) — skipping: %s", url[:80])

# AFTER:
    except asyncio.TimeoutError:
        logger.warning("TIMEOUT (%ds) — skipping: %s", _SINGLE_CHUNK_FLOOR_S, url[:80])
```

**Test (NEW `tests/unit/test_timeout_budget.py`):**

```python
"""TIMEOUT-03: _compute_article_budget_s formula (D-09.03).

Pure-unit tests — no imports of heavy modules (lightrag, etc.). Verifies
formula is correct per PRD § TIMEOUT-03.
"""
from __future__ import annotations

import pytest


def _budget(content: str) -> int:
    # Import inside the test so a missing _compute_article_budget_s surfaces
    # as an AssertionError, not a collection-time ImportError.
    from batch_ingest_from_spider import _compute_article_budget_s
    return _compute_article_budget_s(content)


def test_floor_for_empty_content():
    """Empty content → chunk_count=1 → max(120+30, 900) == 900."""
    assert _budget("") == 900


def test_floor_for_small_article():
    """Small article (<1 chunk_size) → chunk_count=1 → floor."""
    assert _budget("x" * 1000) == 900


def test_floor_for_mid_size():
    """20 chunks → 120 + 600 = 720; below floor → 900."""
    # 20 * 4800 = 96,000 chars
    assert _budget("x" * 96_000) == 900


def test_scales_above_floor():
    """50 chunks → 120 + 1500 = 1620; above floor → 1620."""
    # 50 * 4800 = 240,000 chars
    assert _budget("x" * 240_000) == 1620


def test_large_article():
    """100 chunks → 120 + 3000 = 3120; above floor → 3120."""
    # 100 * 4800 = 480,000 chars
    assert _budget("x" * 480_000) == 3120


def test_chunk_count_is_floored_at_1():
    """Content shorter than chunk_size still counts as 1 chunk."""
    # 1 char → chunk_count = max(1, 0) = 1 → 150 budget → floor 900.
    assert _budget("x") == 900
```

**Rollback:** `git revert <commit-hash>` — restores hardcoded `timeout=1200` and the old
WARNING message. Helper function `_compute_article_budget_s` is removed; no other files
depend on it yet (Plan 09-01 may start consuming it in Phase 10 work — if so, revert ordering
matters; see § Rollback ordering below).

---

## Verification

Run from repo root on Windows:

```bash
# 1. Phase 9 Plan 09-00 tests
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_lightrag_llm.py \
    tests/unit/test_timeout_budget.py \
    tests/unit/test_lightrag_timeout.py \
    -v

# Expected: all tests pass. New tests count: 3 (LightRAG env) + 6 (budget) + 1 (DeepSeek timeout) = 10.

# 2. Phase 8 regression (MANDATORY — must remain 22 green)
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/ -v -k "phase8 or image_pipeline or IMG"

# Expected: 22/22 green (no regressions).

# 3. Full unit suite regression
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v

# Expected: previously-green count + 10 new tests from this plan.

# 4. Smoke import (ensures LLM_TIMEOUT export at file top doesn't break anything)
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('OK')"

# Expected: prints "OK" for each; no ImportError, no RuntimeError.
```

---

## Success Criteria

Observable truths after this plan lands:

1. `os.environ["LLM_TIMEOUT"] = "300"; import lightrag.lightrag` (freshly) shows
   `LightRAG.default_llm_timeout` field default == 300 (PRD success criterion 1).
2. `lib.llm_deepseek._client.timeout` is observably `120.0` (or `httpx.Timeout(120.0)`) — PRD
   success criterion 2. A patched-200s-sleep DeepSeek transport raises within ~120s.
3. `_compute_article_budget_s("x" * 240_000) == 1620`; `_compute_article_budget_s("") == 900` —
   PRD success criterion 3 (budget formula verified in isolation; full rollback proof lives in
   Plan 09-01).
4. All 22 Phase 8 regression tests still pass.
5. 10 new Plan 09-00 unit tests pass.

---

## Out of Scope

- LightRAG internal changes (we only consume its env-respecting contract; we don't patch its
  source).
- Rollback behavior on `wait_for` timeout — lives in Plan 09-01 (STATE-02).
- Pre-batch buffer flush — Plan 09-01 (STATE-01).
- `get_rag()` signature change — Plan 09-01 (STATE-04).
- Finer-grained `chunk_count` derivation (exact token count vs char/4800 approximation) —
  deferred to Phase 11 benchmark feedback.
- Moving `wait_for` from outer orchestration to inner `rag.ainsert`-only wrap — Phase 10
  scrape/ingest decoupling work.

---

## Rollback

**Standard:** `git revert <commit-hash>` reverses all three changes atomically.

**Rollback ordering note:** Plan 09-00 MUST land BEFORE Plan 09-01 if 09-01 starts consuming
`_compute_article_budget_s` (it does not in the current plan, but keep ordering in mind). If
09-01 references the helper, revert 09-01 first, then 09-00. `git revert --no-commit <09-01>
<09-00>` handles both.

**Risk surface:** adding `os.environ.setdefault("LLM_TIMEOUT", "600")` at module top is
additive — it only sets the var if not already set, so shell/`~/.hermes/.env` overrides still
win. No behavioral change for environments that already set the var.

---

## Parallelism note

Plan 09-00 and Plan 09-01 touch overlapping files (`batch_ingest_from_spider.py`,
`ingest_wechat.py`). Sequence them: **09-00 → 09-01** to avoid merge conflicts. 09-01 will
layer the rollback handler on top of this plan's `wait_for` rewrite.
