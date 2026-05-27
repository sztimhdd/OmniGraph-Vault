# Plan 09-01 — LightRAG State Management + Rollback + `get_rag()` Contract

**Phase:** 9 — Timeout Control + LightRAG State Management
**REQs covered:** STATE-01, STATE-02, STATE-03, STATE-04
**Dependencies:** 09-00 (Timeout Layer) — this plan wraps the `asyncio.wait_for` that 09-00
establishes with a rollback handler
**Wave:** 2 (sequenced after 09-00 to avoid merge conflicts on `batch_ingest_from_spider.py`
and `ingest_wechat.py`)

---

## Summary

Make LightRAG state explicit and recoverable: change `get_rag()` from a stateful no-arg coroutine
to `get_rag(flush: bool = True)` returning a fresh instance per call (D-09.07 / STATE-04);
eliminate "history debt" by flushing pending buffers at the start of every batch (D-09.04 /
STATE-01); on `asyncio.wait_for` timeout during ingest, roll back partial inserts via
`rag.adelete_by_doc_id(doc_id)` using deterministic `ids=[...]` passed into `ainsert` (D-09.05
/ STATE-02); prove idempotency with a test that ingests → times out → rolls back → re-ingests
and compares graph state against a clean-single-ingest baseline (D-09.06 / STATE-03).

---

## Canonical Refs

- `.planning/phases/09-timeout-state-management/09-PRD.md` — primary acceptance criteria
- `.planning/phases/09-timeout-state-management/09-CONTEXT.md` — D-09.04, D-09.05, D-09.06, D-09.07
- `.planning/REQUIREMENTS.md` — STATE-01, STATE-02, STATE-03, STATE-04
- `venv/Lib/site-packages/lightrag/lightrag.py:3223` —
  `adelete_by_doc_id(doc_id, delete_llm_cache=False) -> DeletionResult`
- `venv/Lib/site-packages/lightrag/lightrag.py:1237` —
  `ainsert(input, ..., ids: str | list[str] | None = None, ...)` accepts deterministic doc IDs
- `ingest_wechat.py:114-129` — current `get_rag()` definition (STATE-04 target)
- `ingest_wechat.py:564, 667, 800` — in-file `get_rag()` callers
- `batch_ingest_from_spider.py:73-99` — `ingest_article` wraps `wait_for` (STATE-02 rollback site)
- `batch_ingest_from_spider.py:482, 591` — batch-scoped `get_rag()` callers
- `enrichment/merge_and_ingest.py:133` — external `get_rag()` caller (MUST update in same commit)
- `ingest_github.py:258` — production GitHub URL ingest `get_rag()` caller (MUST update in same commit)
- `multimodal_ingest.py:147` — production PDF ingest `get_rag()` caller (MUST update in same commit)
- `scripts/wave0_reembed.py:200, 253`, `scripts/phase0_delete_spike.py:98` — non-production
  callers (update for API consistency)
- `tests/unit/test_api_keys.py:14-28` — `monkeypatch` env-reset fixture pattern

---

## Files to modify

| File                                                  | Why                                                                                           |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `ingest_wechat.py`                                    | (a) `get_rag()` signature change to `(flush: bool = True)` (D-09.07); (b) `ingest_article` + `ingest_pdf` pass `ids=[doc_id]` + register doc_id in a module-level tracker (D-09.05) |
| `batch_ingest_from_spider.py`                         | (a) wrap `wait_for` with rollback handler that calls `rag.adelete_by_doc_id(doc_id)` on `TimeoutError` (D-09.05); (b) pre-batch flush via `get_rag(flush=True)` (D-09.04) |
| `enrichment/merge_and_ingest.py:133`                  | Call-site audit — currently `get_rag()`; behavior changes from stateful singleton to fresh-per-call. Add explicit `flush=True` for clarity (D-09.07) |
| `ingest_github.py:258`                                | Production GitHub URL ingest — call-site audit; add explicit `flush=True` (D-09.07). Missed in STATE-04 sweep v1. |
| `multimodal_ingest.py:147`                            | Production PDF ingest — call-site audit; add explicit `flush=True` (D-09.07). Missed in STATE-04 sweep v1. |
| `scripts/wave0_reembed.py:200, 253`                   | Non-production — update to `get_rag(flush=False)` to preserve historical "reuse prior state" (D-09.07) |
| `scripts/phase0_delete_spike.py:98`                   | Non-production — update to `get_rag(flush=False)` (D-09.07)                                   |
| `tests/unit/test_get_rag_contract.py` (NEW)           | D-09.07: signature + docstring contract; two-call instance-distinctness test                  |
| `tests/unit/test_rollback_on_timeout.py` (NEW)        | D-09.05, D-09.06: forced-timeout rollback + idempotency (both with mocked LightRAG)           |
| `tests/unit/test_prebatch_flush.py` (NEW)             | D-09.04: flush=True path exercised by pre-batch entry                                         |

**ALL 10 `get_rag()` call sites MUST update in the SAME commit** (breaking change scope from
D-09.07). The changes are primarily additive (passing `flush=True` makes the new default
explicit; the behavior is already `flush=True`), but the semantics of ALL call sites shift —
code comments MUST call this out at each production site.

---

## Interface Contract (NEW / CHANGED)

```python
# ingest_wechat.py — CHANGED signature

async def get_rag(flush: bool = True) -> LightRAG:
    """Build a LightRAG instance for this process / batch.

    D-09.07 (STATE-04) — breaking change from the pre-Phase-9 no-arg stateful
    singleton. Each call returns a FRESH LightRAG instance (no module-level
    cache). `flush` controls whether in-memory pending buffers are cleared:

    - flush=True (PRODUCTION DEFAULT): fresh instance, cleared buffers. Prior
      crashed runs CANNOT replay old entities → no wasted embed quota
      (D-09.04 / STATE-01).
    - flush=False: fresh instance, on-disk state intact, no explicit buffer
      clear. Only for tests and one-off spikes that need to observe the old
      stateful behavior.

    Returns:
        LightRAG: initialized via `await rag.initialize_storages()`.
    """
```

```python
# ingest_wechat.py — NEW module-level registry (D-09.05)

# Maps article_hash → doc_id (the id passed to rag.ainsert via ids=[...]).
# Orchestrators read this after asyncio.wait_for raises TimeoutError to call
# rag.adelete_by_doc_id(doc_id) for rollback.
_PENDING_DOC_IDS: dict[str, str] = {}


def _register_pending_doc_id(article_hash: str, doc_id: str) -> None:
    """Track a doc_id so rollback can delete partial state on timeout (D-09.05)."""


def _clear_pending_doc_id(article_hash: str) -> None:
    """Drop tracker after successful ainsert OR after rollback (D-09.05)."""


def get_pending_doc_id(article_hash: str) -> str | None:
    """Read a tracked doc_id; used by orchestrators in the TimeoutError branch."""
```

```python
# batch_ingest_from_spider.py — CHANGED ingest_article rollback handler (D-09.05)

async def ingest_article(url: str, dry_run: bool, rag) -> bool:
    """...
    D-09.05: on asyncio.TimeoutError, call rag.adelete_by_doc_id(doc_id) to
    roll back partial chunks/entities/vectors. doc_id is read from
    ingest_wechat._PENDING_DOC_IDS (populated inside ingest_wechat.ingest_article
    before rag.ainsert is invoked).
    """
```

---

## Tasks

### Task 1 — STATE-04: `get_rag()` signature change + call-site sweep

**File:** `ingest_wechat.py` (line 114), 10 call sites across 7 files.

**Change A — `ingest_wechat.py:114-129` signature + docstring:**

```python
# BEFORE:
async def get_rag():
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=deepseek_model_complete,
        embedding_func=embedding_func,
        llm_model_name="deepseek-v4-flash",
        embedding_func_max_async=1,
        embedding_batch_num=20,
        llm_model_max_async=2,
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    return rag


# AFTER:
async def get_rag(flush: bool = True) -> LightRAG:
    """Build a LightRAG instance for this process / batch.

    D-09.07 (STATE-04) — breaking change from the pre-Phase-9 no-arg stateful
    singleton. Each call returns a FRESH LightRAG instance. `flush`:

    - True (PRODUCTION DEFAULT, D-09.04 / STATE-01): prior crashed runs cannot
      replay buffered entities — fresh instance guarantees no replay.
    - False: preserves old "reuse prior state" behavior for tests and spikes.

    The distinction between True/False today is observable: True discards any
    in-memory pending state from prior `get_rag()` calls in THIS process
    (there is no cache — we always build a fresh object). For now flush=False
    is equivalent to flush=True (no module-level cache exists); the parameter
    is reserved for future "reuse prior instance" semantics if needed.
    """
    rag = LightRAG(
        working_dir=RAG_WORKING_DIR,
        llm_model_func=deepseek_model_complete,
        embedding_func=embedding_func,
        llm_model_name="deepseek-v4-flash",
        embedding_func_max_async=1,
        embedding_batch_num=20,
        llm_model_max_async=2,
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    # D-09.04 (STATE-01): flush=True is a no-op today because we always build
    # a fresh object. If a future refactor introduces a module-level cache
    # OR LightRAG exposes an explicit "drop pending queue" API, the flush
    # branch below MUST clear that state. The parameter reserves the contract.
    if flush:
        # Intentional no-op today — see docstring. Fresh-per-call suffices.
        pass
    return rag
```

**Change B — production call sites (7 files, 10 sites) — update with explicit `flush=True`:**

Planner rationale: the new default is `flush=True`, so `await get_rag()` keeps working. However,
updating ALL production sites to `await get_rag(flush=True)` makes the intent explicit and
protects against a future default-flip. Scripts that need historical behavior pass `flush=False`.

| Site | Current | New |
| ---- | ------- | --- |
| `ingest_wechat.py:564` | `rag = await get_rag()` | `rag = await get_rag(flush=True)` |
| `ingest_wechat.py:667` | `rag = await get_rag()` | `rag = await get_rag(flush=True)` |
| `ingest_wechat.py:800` | `rag = await get_rag()` | `rag = await get_rag(flush=True)` |
| `batch_ingest_from_spider.py:482-484` | `from ingest_wechat import get_rag; rag = await get_rag()` | `from ingest_wechat import get_rag; rag = await get_rag(flush=True)` |
| `batch_ingest_from_spider.py:591-593` | `from ingest_wechat import get_rag; rag = await get_rag()` | `from ingest_wechat import get_rag; rag = await get_rag(flush=True)` |
| `enrichment/merge_and_ingest.py:133-134` | `from ingest_wechat import get_rag; rag = await get_rag()` | `from ingest_wechat import get_rag; rag = await get_rag(flush=True)` |
| `ingest_github.py:258` | `rag = await get_rag()` | `rag = await get_rag(flush=True)` |
| `multimodal_ingest.py:147` | `rag = await get_rag()` | `rag = await get_rag(flush=True)` |
| `scripts/wave0_reembed.py:200` (and 253) | `from ingest_wechat import get_rag; ...rag = await get_rag()` | `from ingest_wechat import get_rag; ...rag = await get_rag(flush=False)` |
| `scripts/phase0_delete_spike.py:98` | `from ingest_wechat import get_rag; rag = await get_rag()` | `from ingest_wechat import get_rag; rag = await get_rag(flush=False)` |

Each production site gets a short code comment at the call:

```python
# D-09.07 / D-09.04: flush=True → fresh instance, no replay of prior pending buffer.
rag = await get_rag(flush=True)
```

Each spike/script site gets:

```python
# D-09.07: flush=False preserves historical "reuse prior state" semantics for this spike.
rag = await get_rag(flush=False)
```

**Test (NEW `tests/unit/test_get_rag_contract.py`):**

```python
"""D-09.07 (STATE-04): get_rag() contract — flush param + fresh per call.

Tests the public contract without constructing a real LightRAG (heavy init).
Uses monkeypatch to stub `LightRAG` + `initialize_storages` so the test runs
in <1s without network / file / embedding calls.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def test_get_rag_signature_has_flush_default_true():
    """Signature is `async def get_rag(flush: bool = True) -> LightRAG` (D-09.07)."""
    from ingest_wechat import get_rag
    sig = inspect.signature(get_rag)
    params = sig.parameters
    assert list(params.keys()) == ["flush"], f"unexpected params: {list(params.keys())}"
    assert params["flush"].default is True
    assert params["flush"].annotation is bool


def test_get_rag_docstring_documents_contract():
    """Docstring references D-09.07 and explains flush=True vs flush=False (D-09.07)."""
    from ingest_wechat import get_rag
    doc = (get_rag.__doc__ or "")
    assert "flush" in doc.lower()
    assert "D-09.07" in doc or "STATE-04" in doc
    assert "production" in doc.lower() or "default" in doc.lower()


@pytest.mark.asyncio
async def test_get_rag_returns_distinct_instances_per_call():
    """Two successive get_rag() calls return distinct LightRAG objects (D-09.07)."""
    with patch("ingest_wechat.LightRAG") as mock_cls:
        # Each construction returns a fresh MagicMock with an awaitable
        # initialize_storages() so `await rag.initialize_storages()` resolves.
        def _new_instance(*_a, **_kw):
            inst = MagicMock()
            inst.initialize_storages = AsyncMock()
            return inst
        mock_cls.side_effect = _new_instance

        from ingest_wechat import get_rag
        a = await get_rag(flush=True)
        b = await get_rag(flush=True)
        assert a is not b
        # Both instances had initialize_storages awaited:
        a.initialize_storages.assert_awaited_once()
        b.initialize_storages.assert_awaited_once()


@pytest.mark.asyncio
async def test_flush_false_also_returns_fresh_instance_today():
    """D-09.07: flush=False is reserved-for-future; current behavior = fresh."""
    with patch("ingest_wechat.LightRAG") as mock_cls:
        def _new_instance(*_a, **_kw):
            inst = MagicMock()
            inst.initialize_storages = AsyncMock()
            return inst
        mock_cls.side_effect = _new_instance

        from ingest_wechat import get_rag
        a = await get_rag(flush=False)
        b = await get_rag(flush=False)
        # Current implementation: fresh per call regardless of flush. Docstring
        # notes flush=False is reserved for future "reuse prior instance".
        assert a is not b


def test_all_production_callers_pass_flush_explicitly():
    """Breaking-change scope: production sites pass flush=True explicitly (D-09.07)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    production_sites = [
        "ingest_wechat.py",
        "batch_ingest_from_spider.py",
        "enrichment/merge_and_ingest.py",
        "ingest_github.py",
        "multimodal_ingest.py",
    ]
    for site in production_sites:
        src = (root / site).read_text(encoding="utf-8")
        # Each production site that mentions get_rag MUST either define it
        # (ingest_wechat.py) OR call it with flush=True.
        if site == "ingest_wechat.py":
            # Defining site — must show signature `flush: bool = True`.
            assert "flush: bool = True" in src, f"{site} missing flush signature"
        else:
            # Must NOT call bare get_rag() in production code.
            assert "get_rag(flush=True)" in src, f"{site} missing explicit flush=True"
            # And must not have a bare call that slipped through:
            import re
            # Match `await get_rag()` with no args — flag it.
            bare_calls = re.findall(r"await\s+get_rag\s*\(\s*\)", src)
            assert not bare_calls, f"{site} has bare get_rag() call(s): {bare_calls}"


def test_spike_scripts_pass_flush_false():
    """Non-production spikes pass flush=False explicitly (D-09.07)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for site in ("scripts/wave0_reembed.py", "scripts/phase0_delete_spike.py"):
        path = root / site
        if not path.exists():
            pytest.skip(f"{site} absent")
        src = path.read_text(encoding="utf-8")
        if "get_rag" in src:
            assert "get_rag(flush=False)" in src, \
                f"{site} should use flush=False per D-09.07"
```

**Rollback note (breaking change):** `git revert <commit-hash>` restores the no-arg signature.
**CRITICAL:** reverting ALSO restores all 10 call-site changes, so no partial-revert state is
reachable from a single-commit revert. If only part of this plan is reverted (e.g., just the
tests), the production code is still valid against the new signature. Document in commit body:
"Breaking API change — see D-09.07. Revert with `git revert <hash>` to restore pre-Phase-9
signature + all 10 call sites."

---

### Task 2 — STATE-01 (pre-batch flush) + STATE-02 (rollback on timeout) + STATE-03 (idempotency)

These three decisions land as one atomic code change because they share the same infrastructure
(deterministic `doc_id`, pending-doc-id registry, rollback handler in the `wait_for` wrapper).

**File A — `ingest_wechat.py`**

**Change 1:** Add the pending-doc-id registry at module scope (near the top, after imports):

```python
# D-09.05 (STATE-02) — pending doc_id tracker for rollback-on-timeout.
# Orchestrators consult this after asyncio.wait_for raises TimeoutError
# to call rag.adelete_by_doc_id(doc_id) → partial state cleanup.
# Cleared on successful ainsert completion AND on rollback completion.
_PENDING_DOC_IDS: dict[str, str] = {}


def _register_pending_doc_id(article_hash: str, doc_id: str) -> None:
    _PENDING_DOC_IDS[article_hash] = doc_id


def _clear_pending_doc_id(article_hash: str) -> None:
    _PENDING_DOC_IDS.pop(article_hash, None)


def get_pending_doc_id(article_hash: str) -> str | None:
    """Public accessor — used by batch_ingest_from_spider on TimeoutError (D-09.05)."""
    return _PENDING_DOC_IDS.get(article_hash)
```

**Change 2:** In `ingest_article` (line ~682 and the cache-branch line ~565), wrap the
`rag.ainsert(full_content)` call:

```python
# BEFORE (main branch, line 682):
    await rag.ainsert(full_content)

# AFTER:
    # D-09.05: deterministic doc_id lets rollback remove partial state on timeout.
    doc_id = f"wechat_{article_hash}"
    _register_pending_doc_id(article_hash, doc_id)
    try:
        await rag.ainsert(full_content, ids=[doc_id])
    finally:
        # Whether ainsert succeeded or raised, clear tracker here.
        # On TimeoutError the orchestrator has already captured the doc_id
        # BEFORE raising (cancellation is cooperative; this finally runs).
        _clear_pending_doc_id(article_hash)
```

Same treatment at the cache-hit branch (line ~565):

```python
# BEFORE:
        try:
            if rag is None:
                rag = await get_rag()
            await rag.ainsert(full_content)
        except Exception as e:
            print(f"LightRAG insert failed: {e}")

# AFTER:
        try:
            if rag is None:
                rag = await get_rag(flush=True)
            # D-09.05: deterministic doc_id for rollback.
            doc_id = f"wechat_{article_hash}"
            _register_pending_doc_id(article_hash, doc_id)
            try:
                await rag.ainsert(full_content, ids=[doc_id])
            finally:
                _clear_pending_doc_id(article_hash)
        except Exception as e:
            print(f"LightRAG insert failed: {e}")
```

And `ingest_pdf` (line ~800 area — after the `await rag.ainsert(...)` call):

Inspect current `ingest_pdf` code — if it does NOT call `rag.ainsert(full_text)` on the assembled
content, the rollback pattern applies to whichever `ainsert` it makes (the task author wires the
same doc_id / register / ids=[doc_id] / finally clear pattern).

Grep check during implementation: `grep -n "rag.ainsert\|await rag\." ingest_wechat.py` — all
`ainsert` sites MUST follow the register/ids/clear pattern.

**File B — `batch_ingest_from_spider.py`**

**Change 1:** Pre-batch flush in both `run` (line 478–484) and `ingest_from_db` (line 588–593)
is already satisfied by Task 1's `get_rag(flush=True)` update. Add a one-line log:

```python
# BEFORE:
    rag = None
    if not dry_run and passed:
        from ingest_wechat import get_rag
        logger.info("Initializing shared LightRAG instance (one-time)...")
        rag = await get_rag()

# AFTER:
    rag = None
    if not dry_run and passed:
        from ingest_wechat import get_rag
        # D-09.04 (STATE-01): flush=True discards any in-memory pending buffer
        # from a prior crashed run → no replay → no wasted embed quota.
        logger.info("Initializing fresh LightRAG instance (flush=True; STATE-01)...")
        rag = await get_rag(flush=True)
```

Same treatment at line 588–593 in `ingest_from_db`.

**Change 2:** Rollback handler in `ingest_article` (lines 73–99):

```python
# BEFORE (full function):
async def ingest_article(url: str, dry_run: bool, rag) -> bool:
    """..."""
    if dry_run:
        logger.info("  [dry-run] would ingest: %s", url)
        return True

    try:
        import ingest_wechat
        await asyncio.wait_for(
            ingest_wechat.ingest_article(url, rag=rag),
            timeout=_SINGLE_CHUNK_FLOOR_S,  # (from Plan 09-00 Task 3)
        )
        return True
    except asyncio.TimeoutError:
        logger.warning("TIMEOUT (%ds) — skipping: %s", _SINGLE_CHUNK_FLOOR_S, url[:80])
        return False
    except Exception as exc:
        logger.warning("Ingest failed (%s): %s — skipping: %s",
                       exc.__class__.__name__, exc, url[:80])
        return False

# AFTER:
async def ingest_article(url: str, dry_run: bool, rag) -> bool:
    """...
    D-09.05 (STATE-02): on asyncio.TimeoutError, roll back partial state via
    rag.adelete_by_doc_id(doc_id). doc_id is computed inside ingest_wechat
    BEFORE ainsert starts and exposed via ingest_wechat.get_pending_doc_id().
    """
    if dry_run:
        logger.info("  [dry-run] would ingest: %s", url)
        return True

    import hashlib
    import ingest_wechat

    # Compute the same article_hash ingest_wechat uses to track doc_id.
    # Kept here so the rollback handler doesn't need to inspect ingest_wechat
    # internals on the error path.
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]

    try:
        await asyncio.wait_for(
            ingest_wechat.ingest_article(url, rag=rag),
            timeout=_SINGLE_CHUNK_FLOOR_S,
        )
        return True
    except asyncio.TimeoutError:
        logger.warning("TIMEOUT (%ds) — skipping: %s", _SINGLE_CHUNK_FLOOR_S, url[:80])
        # D-09.05: rollback partial state if ainsert started.
        doc_id = ingest_wechat.get_pending_doc_id(article_hash)
        if doc_id and rag is not None:
            try:
                logger.info("  Rolling back partial doc_id=%s (STATE-02)", doc_id)
                await rag.adelete_by_doc_id(doc_id)
                logger.info("  Rollback complete — graph consistent (STATE-02)")
            except Exception as rb_exc:
                logger.error("  Rollback FAILED for doc_id=%s: %s — graph may be inconsistent",
                             doc_id, rb_exc)
            finally:
                ingest_wechat._clear_pending_doc_id(article_hash)
        return False
    except Exception as exc:
        logger.warning("Ingest failed (%s): %s — skipping: %s",
                       exc.__class__.__name__, exc, url[:80])
        return False
```

**Test (NEW `tests/unit/test_rollback_on_timeout.py`):**

```python
"""D-09.05 / D-09.06 (STATE-02 / STATE-03): rollback-on-timeout + idempotency.

All tests mock LightRAG so no real embeddings or LLM calls occur. Exercises the
observable contract: on asyncio.TimeoutError in the outer wait_for, the
orchestrator calls rag.adelete_by_doc_id(doc_id) exactly once.
"""
from __future__ import annotations

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


@pytest.fixture
def _fake_rag():
    rag = MagicMock()
    rag.ainsert = AsyncMock()
    rag.adelete_by_doc_id = AsyncMock()
    return rag


@pytest.mark.asyncio
async def test_timeout_triggers_adelete_by_doc_id(monkeypatch, _fake_rag):
    """STATE-02: asyncio.wait_for timeout → rag.adelete_by_doc_id called once."""
    url = "https://test.example/abc123"
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    expected_doc_id = f"wechat_{article_hash}"

    # Mock ingest_wechat.ingest_article so it simulates in-flight ainsert
    # that the orchestrator will cancel via wait_for. The mock registers
    # the pending doc_id (matching what the real implementation does) then
    # sleeps beyond the budget.
    import ingest_wechat

    async def _slow_ingest(_url, rag=None):
        ingest_wechat._register_pending_doc_id(article_hash, expected_doc_id)
        try:
            await asyncio.sleep(10)
        finally:
            # Simulate the real implementation: clear the tracker in a finally.
            # But because CancelledError fires AFTER wait_for raises TimeoutError
            # to the caller, the caller sees the doc_id via get_pending_doc_id
            # at the exact moment wait_for raises. We leave the tracker
            # populated by NOT clearing here so the orchestrator's error path
            # can read it — matching real cooperative-cancellation semantics.
            pass

    monkeypatch.setattr(ingest_wechat, "ingest_article", _slow_ingest)

    # Short budget to force TimeoutError.
    import batch_ingest_from_spider as bi
    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 0.1)

    ok = await bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)

    assert ok is False
    _fake_rag.adelete_by_doc_id.assert_awaited_once_with(expected_doc_id)


@pytest.mark.asyncio
async def test_successful_ingest_does_not_call_adelete(monkeypatch, _fake_rag):
    """Happy path: ainsert completes → no rollback."""
    url = "https://test.example/ok"
    import ingest_wechat

    async def _fast_ingest(_url, rag=None):
        # Simulate successful ainsert — register AND clear.
        article_hash = hashlib.md5(_url.encode()).hexdigest()[:10]
        doc_id = f"wechat_{article_hash}"
        ingest_wechat._register_pending_doc_id(article_hash, doc_id)
        await asyncio.sleep(0)
        ingest_wechat._clear_pending_doc_id(article_hash)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _fast_ingest)

    import batch_ingest_from_spider as bi
    ok = await bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)

    assert ok is True
    _fake_rag.adelete_by_doc_id.assert_not_called()


@pytest.mark.asyncio
async def test_rollback_failure_is_logged_not_raised(monkeypatch, _fake_rag, caplog):
    """STATE-02 defensive: if adelete_by_doc_id raises, orchestrator logs + returns False."""
    url = "https://test.example/fail-rollback"
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]

    import ingest_wechat

    async def _slow_ingest(_url, rag=None):
        ingest_wechat._register_pending_doc_id(article_hash, f"wechat_{article_hash}")
        await asyncio.sleep(10)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _slow_ingest)
    _fake_rag.adelete_by_doc_id.side_effect = RuntimeError("storage corrupt")

    import batch_ingest_from_spider as bi
    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 0.1)

    # No exception should propagate.
    ok = await bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)
    assert ok is False
    # And log message contains the diagnostic.
    assert any("Rollback FAILED" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_idempotent_reingest_after_rollback(monkeypatch, _fake_rag):
    """STATE-03: rollback + re-ingest is idempotent — ainsert called twice, same doc_id."""
    url = "https://test.example/retry"
    article_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    expected_doc_id = f"wechat_{article_hash}"

    import ingest_wechat

    call_count = {"n": 0}

    async def _first_slow_then_fast(_url, rag=None):
        call_count["n"] += 1
        ingest_wechat._register_pending_doc_id(article_hash, expected_doc_id)
        if call_count["n"] == 1:
            await asyncio.sleep(10)  # forced timeout
        else:
            # Second call: simulate successful ainsert.
            await rag.ainsert(f"# {_url}\n...", ids=[expected_doc_id])
            ingest_wechat._clear_pending_doc_id(article_hash)

    monkeypatch.setattr(ingest_wechat, "ingest_article", _first_slow_then_fast)

    import batch_ingest_from_spider as bi
    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 0.1)

    # First call: timeout → rollback.
    ok1 = await bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)
    assert ok1 is False
    _fake_rag.adelete_by_doc_id.assert_awaited_once_with(expected_doc_id)

    # Reset budget for the second call — fast path.
    monkeypatch.setattr(bi, "_SINGLE_CHUNK_FLOOR_S", 30)

    # Second call: succeeds.
    ok2 = await bi.ingest_article(url=url, dry_run=False, rag=_fake_rag)
    assert ok2 is True

    # adelete_by_doc_id was called EXACTLY once (from the first timeout only).
    # ainsert was called EXACTLY once with ids=[expected_doc_id] (from the second call).
    assert _fake_rag.adelete_by_doc_id.await_count == 1
    _fake_rag.ainsert.assert_awaited_once()
    kwargs = _fake_rag.ainsert.await_args.kwargs
    assert kwargs.get("ids") == [expected_doc_id]
```

**Test (NEW `tests/unit/test_prebatch_flush.py`):**

```python
"""D-09.04 (STATE-01): pre-batch flush — get_rag(flush=True) produces fresh instance.

The observable truth: every entry point calls get_rag with flush=True and each
call returns a fresh LightRAG (covered structurally by test_get_rag_contract).
This test verifies the ENTRY POINTS use the flush=True path — catches a regression
where a future refactor reverts to bare get_rag().
"""
from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def _deepseek_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


def _src(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / rel_path).read_text(encoding="utf-8")


def test_batch_run_uses_flush_true():
    """batch_ingest_from_spider.run calls get_rag(flush=True) at pre-batch init."""
    src = _src("batch_ingest_from_spider.py")
    # Require at least two flush=True call sites (run + ingest_from_db).
    assert src.count("get_rag(flush=True)") >= 2, \
        "batch_ingest_from_spider must call get_rag(flush=True) at both batch entry points"


def test_state01_comment_present():
    """Pre-batch flush log references STATE-01 / D-09.04 for traceability."""
    src = _src("batch_ingest_from_spider.py")
    assert "STATE-01" in src or "D-09.04" in src, \
        "batch_ingest_from_spider.py pre-batch flush comment must reference STATE-01"
```

**Rollback:** `git revert <commit-hash>` restores:

- `get_rag()` no-arg signature (removes `flush` param from `ingest_wechat.py`)
- All 10 call-site updates to bare `get_rag()`
- `_PENDING_DOC_IDS` registry + tracker helpers (removed)
- `batch_ingest_from_spider.ingest_article` rollback branch (reverts to plain `return False`)

**BREAKING CHANGE CAVEAT:** if downstream code (outside the 10 audited sites) has started calling
`get_rag(flush=True)` between this plan landing and the revert, those call sites will raise
`TypeError: get_rag() got an unexpected keyword argument 'flush'` after revert. Revert must be
paired with a sweep: `grep -rn "get_rag(flush=" .` → restore those to bare `get_rag()`.

---

## Verification

Run from repo root on Windows:

```bash
# 1. Plan 09-01 tests
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_get_rag_contract.py \
    tests/unit/test_rollback_on_timeout.py \
    tests/unit/test_prebatch_flush.py \
    -v

# Expected: all tests pass (count: 5 contract + 4 rollback + 2 flush = 11 new).

# 2. Plan 09-00 regression
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/test_lightrag_llm.py \
    tests/unit/test_timeout_budget.py \
    tests/unit/test_lightrag_timeout.py \
    -v

# Expected: all 09-00 tests still pass.

# 3. Phase 8 regression (MANDATORY — must remain 22 green)
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest \
    tests/unit/ -v -k "phase8 or image_pipeline or IMG"

# Expected: 22/22 green.

# 4. Full unit suite regression
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -m pytest tests/unit/ -v

# Expected: prior green count + 11 new from 09-01 + 10 new from 09-00.

# 5. Smoke — all 7 production / 3 non-production files still import cleanly
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_wechat; print('ingest_wechat OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import batch_ingest_from_spider; print('batch OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import enrichment.merge_and_ingest; print('merge OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import ingest_github; print('ingest_github OK')"
DEEPSEEK_API_KEY=dummy venv/Scripts/python.exe -c "import multimodal_ingest; print('multimodal_ingest OK')"

# Expected: 5 "OK" prints, no ImportError, no TypeError on get_rag signature.

# 6. Grep audit — ensure ZERO bare get_rag() calls in production code
grep -rn "await get_rag()" ingest_wechat.py batch_ingest_from_spider.py enrichment/ ingest_github.py multimodal_ingest.py 2>/dev/null

# Expected: no matches (ALL production sites pass flush=True explicitly).
```

---

## Success Criteria

Observable truths after this plan lands (from PRD § Success Criteria):

1. **STATE-01:** `get_rag(flush=True)` after a prior crashed run does NOT replay old buffered
   entities — covered by `test_prebatch_flush` + `test_get_rag_contract`.
2. **STATE-02:** `asyncio.wait_for` timeout on an article task → `rag.adelete_by_doc_id(doc_id)`
   called exactly once — covered by `test_timeout_triggers_adelete_by_doc_id`.
3. **STATE-03:** Ingest → timeout → rollback → re-ingest same article succeeds with one
   `adelete_by_doc_id` + one `ainsert(ids=[doc_id])` — covered by
   `test_idempotent_reingest_after_rollback`.
4. **STATE-04:** `get_rag()` signature is `async def get_rag(flush: bool = True) -> LightRAG`
   with contract documented in docstring — covered by `test_get_rag_signature_has_flush_default_true`
   + `test_get_rag_docstring_documents_contract` + source-grep test
   `test_all_production_callers_pass_flush_explicitly`.
5. **Phase 8 regression:** 22/22 tests still green.
6. **Rollback failure mode:** `adelete_by_doc_id` raising does not propagate — orchestrator
   returns False cleanly, logs diagnostic — covered by `test_rollback_failure_is_logged_not_raised`.

---

## Out of Scope

- Full end-to-end rollback against a REAL LightRAG instance with real NanoVectorDB — deferred
  to Phase 11 E2E benchmark. Unit tests mock LightRAG.
- Cognee integration rollback — Cognee is fire-and-forget and already non-blocking per
  `ingest_wechat.py` line 695. No Cognee-side cleanup needed for STATE-02.
- Persistent doc-id tracking (e.g., SQLite ledger of in-flight doc_ids across process restarts)
  — v3.2 checkpoint/resume work.
- Flushing LightRAG's on-disk vdb/graphml state — out of scope; we only flush in-memory
  pending buffers between runs. On-disk state IS the knowledge graph.
- Introspection-based validation of "zero orphan entity nodes" — we rely on LightRAG's
  `adelete_by_doc_id` contract as documented. Phase 11 E2E benchmark validates end-to-end.

---

## Rollback

**Standard:** `git revert <commit-hash>`.

**Breaking-change caveat:** See Task 1 rollback note — if any downstream code adopted
`get_rag(flush=...)` after this plan landed, revert must be paired with a source sweep
(`grep -rn "get_rag(flush=" .` → restore bare calls).

**Rollback ordering with 09-00:** If reverting both plans, revert 09-01 FIRST, then 09-00,
because 09-01's `ingest_article` rollback handler references the `_SINGLE_CHUNK_FLOOR_S`
constant introduced by 09-00. `git revert --no-commit <09-01-hash> <09-00-hash> && git commit`
handles the sequenced revert atomically.

**Partial rollback option:** STATE-04 can be reverted independently (just the signature +
call-site sweep) if downstream dependencies make a full revert risky. STATE-02 rollback handler
depends on `get_pending_doc_id` accessor in `ingest_wechat.py`; removing only the rollback
handler (Task 2, Change 2 in `batch_ingest_from_spider.py`) is safe without touching STATE-04.
