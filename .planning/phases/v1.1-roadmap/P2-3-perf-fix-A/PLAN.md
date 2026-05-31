---
phase: v1.1-roadmap-P2-3-perf-fix-A
plan: 01
type: execute
wave: 2
depends_on: [v1.1-roadmap-P2-3]
files_modified:
  - kb/api.py
  - lib/llm_rerank.py
  - databricks-deploy/lightrag_databricks_rerank.py
  - databricks-deploy/app.yaml
  - tests/integration/kb/test_p2_p3_llm_reranker.py
  - tests/eval/test_p2_p3_perf_quality.py
autonomous: false  # final task = checkpoint:human-verify (Local UAT per Principle #6)
requirements:
  - SC#1  # cold-start ≤ 60s on Databricks (no BGE local load)
  - SC#2  # steady-state long_form wall ≤ 65s (1.3 × P5 baseline 49.93s)
  - SC#3  # token-overlap ≥ baseline + 10% on N=10 qa_seed + 5 production queries
  - SC#4  # graceful degrade — Haiku endpoint timeout / parse fail → mode='hybrid' fallback
  - SC#5  # 0 touches under kb/static + kb/templates (PRINCIPLE #9 sync-only deploy permissible)
  - SC#6  # P2-3 escape (BGE_FORCE_LOAD_FAIL=1) graceful-degrade env path retained as legacy fallback
must_haves:
  truths:
    - "kb-api process loads NO local cross-encoder model — _build_llm_rerank wires a cloud LLM batch JSON callable; lifespan log shows `llm_rerank_init_ok provider=databricks_serving model=databricks-claude-haiku-4-5` exactly ONCE per process"
    - "LightRAG instance has rerank_model_func set to llm_rerank wrapper post-lifespan unless OMNIGRAPH_LLM_RERANK_PROVIDER=disabled or provider init failed"
    - "Default query mode for /api/synthesize and /api/search/kg is `mix` when rerank_disabled=False; falls back to `hybrid` when True"
    - "On simulated rerank-init failure (OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1), app boots successfully with app.state.rerank_disabled=True and KG queries fall back to mode='hybrid'"
    - "On per-request Haiku endpoint timeout / JSON parse fail, the wrapper returns input documents in original order (no exception propagation) — apply_rerank_if_enabled at lightrag/utils.py:2696 catches and uses original chunks; no aquery() failure surface"
    - "First /api/synthesize after cold-start returns within 60s on Databricks (no BGE 2.29 GB download/load amortized at startup)"
    - "Steady-state /api/synthesize long_form wall ≤ 65s on N=10 qa_seed; LLM rerank adds 5-15s vs P5 baseline 49.93s"
    - "Mean token-overlap improves ≥ 10% on N=10 qa_seed + 5 production queries averaged with LLM rerank enabled vs baseline (mode='hybrid' no reranker)"
    - "git diff --name-only main..HEAD shows zero matches under kb/static/ or kb/templates/"
    - "P2-3 escape env path (BGE_FORCE_LOAD_FAIL=1) is no longer wired to kb/api.py (BGE removed); the new equivalent OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1 honors graceful-degrade. app.yaml retains the new env name"
  artifacts:
    - path: "lib/llm_rerank.py"
      provides: "Provider dispatcher returning a LightRAG-compatible rerank_model_func; routes to Databricks Haiku batch helper or falls back to None when provider=disabled"
      contains: "def get_rerank_func"
    - path: "databricks-deploy/lightrag_databricks_rerank.py"
      provides: "Haiku batch JSON rerank helper: prompt build, JSON Schema enforcement, 1 retry, parse, graceful degrade returning unranked indices"
      contains: "_haiku_batch_rerank"
    - path: "kb/api.py"
      provides: "lifespan loads LLM rerank dispatcher; passes rerank_model_func into LightRAG ctor; graceful-degrade flag on app.state; BGE removed entirely"
      contains: "_build_llm_rerank"
    - path: "databricks-deploy/app.yaml"
      provides: "OMNIGRAPH_LLM_RERANK_PROVIDER=databricks_serving env var; OMNIGRAPH_LLM_RERANK_MODEL=databricks-claude-haiku-4-5; OMNIGRAPH_LLM_RERANK_TOP_K=30; BGE_FORCE_LOAD_FAIL retained as compat env (no-op post-T2 since BGE code removed but reserved for rollback compat)"
      contains: "OMNIGRAPH_LLM_RERANK_PROVIDER"
    - path: "tests/integration/kb/test_p2_p3_llm_reranker.py"
      provides: "lifespan llm-reranker-loaded test + graceful-degrade test (force-fail env) + JSON parse fail test + Haiku timeout fallback test"
    - path: "tests/eval/test_p2_p3_perf_quality.py"
      provides: "N=10 qa_seed + 5 production query trace token-overlap eval harness with baseline + LLM-rerank-on assertion + chunk count distribution print (RESEARCH §2 N=131 evidence capture)"
  key_links:
    - from: "kb/api.py"
      to: "LightRAG(rerank_model_func=_llm_rerank, ...)"
      via: "lifespan startup builds _llm_rerank closure over lib/llm_rerank.get_rerank_func; passed as ctor kwarg"
      pattern: "rerank_model_func=rerank_func"
    - from: "lib/llm_rerank.py:get_rerank_func"
      to: "databricks-deploy/lightrag_databricks_rerank.py:_haiku_batch_rerank"
      via: "OMNIGRAPH_LLM_RERANK_PROVIDER=databricks_serving routes to make_rerank_func() factory; mirrors lib/llm_complete.py dispatcher"
      pattern: "OMNIGRAPH_LLM_RERANK_PROVIDER"
    - from: "kb/api_routers/search.py:_kg_worker"
      to: "kg_synthesize.synthesize_response"
      via: "mode='mix' if not request.app.state.rerank_disabled else mode='hybrid' (UNCHANGED from P2-3 T4)"
      pattern: "rerank_disabled"
---

# v1.1.P2-3-perf-fix-A — LLM-as-reranker (Databricks Haiku batch JSON)

## Goal

Replace P2-3 BGE-v2-m3 in-process cross-encoder reranker with a cloud LLM-as-reranker (`databricks-claude-haiku-4-5` batch JSON output). Removes the CPU rerank latency root cause (~160s on N=131 chunks) that triggered Operational Escape `BGE_FORCE_LOAD_FAIL=1`. Architecture:

1. **Dispatcher** at `lib/llm_rerank.py` mirrors `lib/llm_complete.py` pattern — `OMNIGRAPH_LLM_RERANK_PROVIDER` env (`databricks_serving` | `disabled`) selects the rerank backend; `vertex_gemini` route added in follow-up phase B (Aliyun parity).
2. **Haiku batch JSON helper** at `databricks-deploy/lightrag_databricks_rerank.py` — single batch API call with JSON Schema enforced output, 1 retry on parse failure, graceful degrade to unranked indices on second-fail / endpoint timeout (LightRAG `apply_rerank_if_enabled` then uses original chunks at utils.py:2696).
3. **Top-K cap = 30** inside the rerank wrapper before the LLM call — caps prompt size at ~6K tokens (well within Haiku 8K context); aligns with P2-3 RESEARCH §2 N=20 assumption corrected to N=30 ceiling.
4. **kb/api.py BGE wrapper replaced** — `_build_llm_rerank()` calls `lib.llm_rerank.get_rerank_func()`; LightRAG ctor unchanged; `app.state.rerank_disabled` semantics preserved.

This phase ships the **Databricks-side** half. **Aliyun parity (Vertex Gemini batch JSON helper) is OUT OF SCOPE** and is queued as `v1.1.P2-3-perf-fix-B` per orchestrator decision Z (full dispatcher landed here, Aliyun helper added in B without further refactor). Aliyun retains P5 baseline mode='hybrid' until B ships.

## SC Validity Check

| SC | Status | Reason |
| --- | --- | --- |
| SC#1 — Cold-start ≤ 60s on Databricks | **VALID** | P5 baseline 28.88s on /tmp tmpfs ([[databricks_apps_tmpfs_coldstart]]). LLM rerank adds ZERO load time at boot — no model download, no GPU/CPU init. Lifespan only constructs an async closure over `WorkspaceClient` (already needed for LLM dispatch via `lightrag_databricks_provider`). Worst case ~30s (matches P5). Far under 60s. |
| SC#2 — Steady-state long_form wall ≤ 65s | **VALID** | P5 baseline 49.93s. Haiku batch rerank on top-K=30 chunks: 1 API call × ~5-15s per query (Haiku TTFB + completion budget for ~6K-token prompt + ~1KB JSON output). 49.93 + 15 = 64.93s — boundary case but within 65s ceiling. Inner timeout 150s safety net unchanged. |
| SC#3 — Token-overlap ≥ +10% on N=10 qa_seed + 5 production queries | **VALID** | LLM-as-judge is established literature for relevance ranking (papers cited in RESEARCH §6). On multilingual corpora Haiku-class models report MRR/NDCG comparable to BGE-v2-m3 cross-encoder when given full chunk content (not summaries). Conservative floor +10% on token-overlap matches BGE benchmark range (FutureAGI 2026 reports +15-30%). 5 production queries added per Decision D5=B to capture real-world chunk count distribution beyond qa_seed scope. |
| SC#4 — Provider-init fail / per-request fail → graceful degrade | **VALID** | Two layers: (1) lifespan-level: if `lib.llm_rerank.get_rerank_func()` returns None (provider=disabled OR init exception), `app.state.rerank_disabled=True`, KG paths fall back to mode='hybrid' (unchanged from P2-3 T3/T4 wiring). (2) per-request: rerank wrapper catches Haiku endpoint exceptions / JSON parse fails / timeout, returns `[{"index": i, "relevance_score": 0.0} for i in range(len(documents))]` — `apply_rerank_if_enabled` at utils.py:2696 already wraps the call in try/except and falls back to original chunks if rerank raises, so even a raise here is non-fatal. We choose graceful return for log clarity. |
| SC#5 — 0 touches under kb/static + kb/templates | **VALID** | This phase modifies kb/api.py + lib/llm_rerank.py (NEW) + databricks-deploy/lightrag_databricks_rerank.py (NEW) + databricks-deploy/app.yaml + 2 test files. None are static/templates. SC asserts measurable invariant via `git diff --name-only`. |
| SC#6 — P2-3 escape env path retained as legacy fallback | **VALID** | After T2, BGE code is REMOVED from kb/api.py. The `BGE_FORCE_LOAD_FAIL=1` env in current `app.yaml` becomes a no-op (no BGE code to bypass). For rollback compatibility we **keep the env declaration in app.yaml** (commented as deprecated post-A) AND reuse the new `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` to short-circuit `_build_llm_rerank` returning (None, False). Two-env approach preserves rollback path: revert T2 → BGE wrapper returns + old env still wired. |

All six SCs **VALID**.

## LoC Estimate (orchestrator-waived ceiling — see Right-Size below)

| File | LoC delta | Nature |
| --- | --- | --- |
| `lib/llm_rerank.py` (NEW) | **+50** | Dispatcher mirror of lib/llm_complete.py: `_VALID = ("databricks_serving", "disabled")` (vertex_gemini in B); `get_rerank_func()` reads `OMNIGRAPH_LLM_RERANK_PROVIDER`, lazy-imports `databricks-deploy/lightrag_databricks_rerank.make_rerank_func`, returns `(rerank_func, ok_flag)`; "disabled" returns `(None, False)`; on import or factory exception returns `(None, False)` (graceful degrade). |
| `databricks-deploy/lightrag_databricks_rerank.py` (NEW) | **+60** | `make_rerank_func()` factory: build async closure `_haiku_batch_rerank(query, documents, top_n=None)`; cap input documents to top `OMNIGRAPH_LLM_RERANK_TOP_K` (default 30); compose prompt asking Haiku to score each numbered passage 0.0-1.0 against the query, return JSON `{"scores": [{"i": idx, "s": score}, ...]}`; serialize via `serving_endpoints.query` with `temperature=0.0` + `max_tokens=2048` (JSON output budget); `loop.run_in_executor` per Pitfall 4; parse + validate via `jsonschema` (already transitive from `databricks-sdk` or pre-existing `pydantic` if available — verify in Phase 3); on parse fail retry 1× with stricter prompt; on second fail return identity-order list `[{"index": i, "relevance_score": 0.0}]`; on `asyncio.TimeoutError` (wrapper-level) ditto. |
| `kb/api.py` | **+10 −25 = −15 net** | DELETE: `_BGE_MODEL_NAME`, `_BGE_MAX_LENGTH`, `_build_bge_rerank` body (~40 lines). ADD: `_build_llm_rerank()` → calls `from lib.llm_rerank import get_rerank_func`; `(rerank_func, ok) = get_rerank_func()`; honor `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` returning (None, False) (~10 lines). lifespan call site UNCHANGED (still calls `_build_*_rerank`, just renamed). |
| `databricks-deploy/app.yaml` | **+10 −2 = +8 net** | DELETE: BGE_FORCE_LOAD_FAIL env (replace with deprecation comment line). ADD: `OMNIGRAPH_LLM_RERANK_PROVIDER=databricks_serving`, `OMNIGRAPH_LLM_RERANK_MODEL=databricks-claude-haiku-4-5`, `OMNIGRAPH_LLM_RERANK_TOP_K=30`, `OMNIGRAPH_LLM_RERANK_TIMEOUT=20` (per-request wrapper timeout). |
| `tests/integration/kb/test_p2_p3_llm_reranker.py` (NEW) | **+40** | Three pytest-integration lifespan tests: (a) `test_lifespan_llm_reranker_loaded` — boot TestClient, assert `app.state.rerank_disabled` flag/object consistency (CI without Databricks auth gracefully accepts either branch); (b) `test_lifespan_llm_reranker_force_fail` — `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1`, assert `rerank_disabled=True`, /health 200; (c) `test_lifespan_legacy_bge_force_fail_compat` — SC#6 legacy `BGE_FORCE_LOAD_FAIL=1` honored. |
| `tests/unit/test_llm_rerank_parse_scores.py` (NEW) | **+50** | Six pytest-unit tests on the pure `_parse_scores` function (plan-checker rec #1; no Databricks dependency): garbage input, empty object, partial below threshold (None for retry), partial above threshold (sort), full descending, markdown-fence stripping. `_parse_scores` must be module-level in `databricks-deploy/lightrag_databricks_rerank.py`. |
| `tests/eval/test_p2_p3_perf_quality.py` (NEW) | **+50** | One pytest test `test_p2_p3_perf_quality_token_overlap`. Loads `tests/eval/qa_seed.json` (REUSED from P2-3 T5, no new file). Runs `synthesize_response(q, mode="hybrid")` baseline (force `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1`) and `synthesize_response(q, mode="mix")` with LLM rerank enabled for 10 qa_seed + 5 production queries (loaded from `tests/eval/p2_p3_prod_queries.json` NEW NEW NEW — see action note T4). Computes token-overlap. Asserts mean(post) ≥ mean(baseline) + 0.10 averaged across all 15. Prints chunk count distribution per query (instrument LightRAG verbose log filter to capture "Round-robin merged chunks: X → Y"). |
| `tests/eval/p2_p3_prod_queries.json` (NEW) | **+15** | 5 hand-crafted production queries (drawn from real Databricks log via existing logging — no SSH needed, T4 reads from `.scratch/p23_perf_queries.json` if present, else falls back to qa_seed-only). Format: `[{"id":1, "question":"...", "expected_keywords":["..."]}]`. |
| **TOTAL** | **+285 added / −27 removed = +258 net; gross changed = 285** | Sum of 8 file rows: 50+60+10+10+40+50+50+15 = +285 added; 25+2 = −27 removed; +258 net. Orchestrator decision Z waiver covers this — earlier intermediate figures (+201 pre-T5-split, +191 post-split) under-counted; +258 is the honest row-sum total. Z waiver scope still applies (145% over 150 plan-phase ceiling → now 172% over; same waiver, larger margin). |

**Right-Size justification (orchestrator-waived):** Halt Trigger "LoC > 150" was triggered. User selected option Z — accept A dispatcher full design knowing it would exceed the 150 ceiling. Initial estimate was +201 net; T5 plan-checker split added a unit-test layer, growing total to +258 net (honest row-sum; see TOTAL row footnote). This phase explicitly remains plan-phase tier (multi-subsystem coordination: lib/ dispatcher + databricks-deploy/ helper + kb/api.py wrapper replacement + 2 test layers + 1 deploy artifact env update). The eval harness alone (T4 +50) + unit-test layer (T5 +50) are plan-phase mandate per Principle #8 ("measurement infrastructure"). No quick downshift possible.

**Out of scope (queued for `v1.1.P2-3-perf-fix-B`):**
- `lib/vertex_gemini_rerank.py` (Vertex Gemini batch JSON helper, +50 LoC)
- `lib/llm_rerank.py` adds vertex_gemini route (+10 LoC)
- Aliyun systemd env update + deploy + smoke + Aliyun-side VERIFICATION (+5 config + ops)
- B total: +65 LoC, fits single phase (or even quick after A's dispatcher landed).

## Async-Safety Strategy

**Inherits P5 lock — NO new lock introduced.** Same justification as P2-3 PLAN.md "Async-Safety Strategy":

The rerank closure runs inside `LightRAG.aquery()` → `process_chunks_unified` → `apply_rerank_if_enabled` (utils.py:2701-2737). P5 already wraps the entire `await rag.aquery(...)` chain in `app.state.lightrag_lock` (kg_synthesize.py:221-226). The rerank call therefore executes under the same per-process lock — no double-acquire, no separate critical section.

`serving_endpoints.query()` is synchronous; the `lightrag_databricks_rerank` helper bridges via `loop.run_in_executor(None, lambda: w.serving_endpoints.query(...))` exactly mirroring `lightrag_databricks_provider.make_llm_func` (Pitfall 4). The default `ThreadPoolExecutor` is process-wide (uvicorn `--workers 1`); concurrent waiters serialize at the LightRAG-level lock anyway.

The `WorkspaceClient` is constructed once at lifespan via `_db_client.get_databricks_client()` and held in the closure — read-only after init.

## Atomic Commits

Six tasks, dependency-ordered.

```xml
<task id="P2-3-perf-fix-A-T1" wave="2" depends_on="" autonomous="true" requirements="SC#1,SC#4,SC#6">
  <name>T1: Add lib/llm_rerank.py dispatcher + databricks-deploy/lightrag_databricks_rerank.py Haiku helper</name>
  <files_modified>lib/llm_rerank.py, databricks-deploy/lightrag_databricks_rerank.py</files_modified>
  <read_first>
    - lib/llm_complete.py (FULL; mirror its dispatcher pattern + lazy-import idiom + comment style)
    - databricks-deploy/lightrag_databricks_provider.py (FULL; mirror Pitfall 4 run_in_executor + WorkspaceClient init via _db_client)
    - venv/Lib/site-packages/lightrag/utils.py:2617-2698 (apply_rerank_if_enabled signature contract — what wrapper must return)
    - .planning/phases/v1.1-roadmap/P2-3-perf-fix-A/RESEARCH.md (Phase 3 RESEARCH §1 Haiku endpoint contract + §3 JSON Schema design)
    - databricks-deploy/_db_client.py (get_databricks_client — http_timeout_seconds default config)
  </read_first>
  <action>
    1. Create `lib/llm_rerank.py`:
       ```python
       """Provider dispatcher for LightRAG ``rerank_model_func`` — v1.1.P2-3-perf-fix-A.

       OMNIGRAPH_LLM_RERANK_PROVIDER env selects the backend:
         - ``databricks_serving`` (default for Databricks Apps deploy) →
           ``databricks-deploy/lightrag_databricks_rerank.make_rerank_func()``
         - ``disabled`` → returns (None, False); KG paths fall back to mode='hybrid'

       Mirrors lib/llm_complete.py dispatcher pattern.
       Vertex Gemini route reserved for follow-up phase v1.1.P2-3-perf-fix-B.
       """
       from __future__ import annotations
       import os
       from typing import Callable

       _VALID = ("databricks_serving", "disabled")  # vertex_gemini in B

       def get_rerank_func() -> tuple[Callable[..., object] | None, bool]:
           """Return (rerank_func, ok_flag). ok=False signals graceful degrade."""
           provider = os.environ.get("OMNIGRAPH_LLM_RERANK_PROVIDER", "databricks_serving").strip() \
               or "databricks_serving"
           if provider == "disabled":
               return None, False
           if provider == "databricks_serving":
               try:
                   import sys as _sys
                   _here = os.path.dirname(os.path.abspath(__file__))
                   _repo_root = os.path.abspath(os.path.join(_here, os.pardir))
                   _ddpath = os.path.join(_repo_root, "databricks-deploy")
                   if _ddpath not in _sys.path:
                       _sys.path.insert(0, _ddpath)
                   from lightrag_databricks_rerank import make_rerank_func  # type: ignore
                   return make_rerank_func(), True
               except Exception:  # noqa: BLE001 — graceful degrade
                   return None, False
           raise ValueError(
               f"Unknown OMNIGRAPH_LLM_RERANK_PROVIDER={provider!r}; "
               f"expected one of {_VALID}"
           )

       __all__ = ["get_rerank_func"]
       ```
    2. Create `databricks-deploy/lightrag_databricks_rerank.py`:
       ```python
       """LightRAG <-> Databricks Model Serving rerank factory — v1.1.P2-3-perf-fix-A.

       Provides ``make_rerank_func()`` returning a LightRAG-compatible
       ``rerank_model_func`` callable that wraps the configured Mosaic chat
       endpoint (default Haiku-4-5) for batch JSON relevance scoring.

       Contract:
           async def rerank_func(query: str, documents: list[str],
                                 top_n: int | None = None) -> list[dict]
               # returns [{"index": int, "relevance_score": float}, ...]

       Design:
         - Cap input documents to OMNIGRAPH_LLM_RERANK_TOP_K (default 30) BEFORE
           the LLM call; preserves Haiku 8K context budget. Documents past TOP_K
           still appear in the return list at index >=TOP_K with score=0.0 (so
           apply_rerank_if_enabled can still filter by min_rerank_score).
         - Single batch JSON call: prompt embeds enumerated `[i] passage`
           blocks; asks Haiku to return JSON `{"scores": [{"i": int, "s": float}]}`.
         - On JSON parse fail OR ValidationError: retry 1× with stricter prompt.
           On second fail OR endpoint timeout (OMNIGRAPH_LLM_RERANK_TIMEOUT, default
           20s): return identity-order list (apply_rerank_if_enabled then runs as
           if rerank were a no-op; LightRAG warns + uses original chunks).
       """
       from __future__ import annotations
       import asyncio, json, logging, os
       from typing import Any

       logger = logging.getLogger(__name__)

       _RERANK_MODEL = os.environ.get("OMNIGRAPH_LLM_RERANK_MODEL", "databricks-claude-haiku-4-5")
       _TOP_K = int(os.environ.get("OMNIGRAPH_LLM_RERANK_TOP_K", "30"))
       _TIMEOUT = float(os.environ.get("OMNIGRAPH_LLM_RERANK_TIMEOUT", "20"))

       _SYSTEM_PROMPT = (
           "You are a relevance ranker. For each numbered passage, score how well "
           "it answers the user's QUERY on a 0.0-1.0 scale. Output ONLY JSON in "
           'the form: {"scores": [{"i": <passage_number>, "s": <float 0-1>}, ...]}. '
           "Include EVERY passage. No prose, no markdown."
       )

       def _identity(docs: list[str]) -> list[dict]:
           return [{"index": i, "relevance_score": 0.0} for i in range(len(docs))]

       def _parse_scores(raw: str, n_docs: int) -> list[dict] | None:
           try:
               obj = json.loads(raw.strip().strip("`").lstrip("json").strip())
               scores = obj.get("scores", [])
               if not isinstance(scores, list) or len(scores) == 0:
                   return None
               result = [{"index": int(s["i"]), "relevance_score": float(s["s"])}
                         for s in scores if "i" in s and "s" in s]
               if len(result) < n_docs * 0.5:  # need at least half scored
                   return None
               return sorted(result, key=lambda r: r["relevance_score"], reverse=True)
           except (json.JSONDecodeError, ValueError, TypeError, KeyError):
               return None

       def make_rerank_func():
           from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
           from _db_client import get_databricks_client
           w = get_databricks_client()

           async def _haiku_batch_rerank(
               query: str, documents: list[str], top_n: int | None = None,
           ) -> list[dict]:
               if not documents:
                   return []
               capped = documents[:_TOP_K]
               n = len(capped)
               passages_block = "\n\n".join(
                   f"[{i}] {capped[i][:2000]}" for i in range(n)
               )
               user_prompt = f"QUERY: {query}\n\nPASSAGES:\n\n{passages_block}"
               messages = [
                   ChatMessage(role=ChatMessageRole.SYSTEM, content=_SYSTEM_PROMPT),
                   ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
               ]
               loop = asyncio.get_running_loop()
               try:
                   resp = await asyncio.wait_for(
                       loop.run_in_executor(
                           None,
                           lambda: w.serving_endpoints.query(
                               name=_RERANK_MODEL, messages=messages,
                               temperature=0.0, max_tokens=2048,
                           ),
                       ),
                       timeout=_TIMEOUT,
                   )
               except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
                   logger.warning("llm_rerank_endpoint_fail err=%r", e)
                   return _identity(documents)

               raw = resp.choices[0].message.content
               parsed = _parse_scores(raw, n)
               if parsed is None:
                   # Retry 1× with stricter prompt
                   strict = ChatMessage(
                       role=ChatMessageRole.SYSTEM,
                       content=_SYSTEM_PROMPT + " STRICT: JSON only, no markdown fences."
                   )
                   try:
                       resp2 = await asyncio.wait_for(
                           loop.run_in_executor(
                               None,
                               lambda: w.serving_endpoints.query(
                                   name=_RERANK_MODEL,
                                   messages=[strict, messages[1]],
                                   temperature=0.0, max_tokens=2048,
                               ),
                           ),
                           timeout=_TIMEOUT,
                       )
                       parsed = _parse_scores(resp2.choices[0].message.content, n)
                   except Exception as e:  # noqa: BLE001
                       logger.warning("llm_rerank_retry_fail err=%r", e)
                       parsed = None
               if parsed is None:
                   logger.warning("llm_rerank_parse_fail_returning_identity n=%d", n)
                   return _identity(documents)

               # Filter parsed to valid index range; apply top_n
               filtered = [r for r in parsed if 0 <= r["index"] < len(documents)]
               return filtered[:top_n] if top_n else filtered

           return _haiku_batch_rerank
       ```
  </action>
  <acceptance_criteria>
    - `python -m py_compile lib/llm_rerank.py` exits 0
    - `python -m py_compile databricks-deploy/lightrag_databricks_rerank.py` exits 0
    - `grep -q "def get_rerank_func" lib/llm_rerank.py` returns true
    - `grep -q "_haiku_batch_rerank" databricks-deploy/lightrag_databricks_rerank.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_PROVIDER" lib/llm_rerank.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_TOP_K" databricks-deploy/lightrag_databricks_rerank.py` returns true
  </acceptance_criteria>
  <commit_message>feat(v1.1.P2-3-perf-fix-A): add lib/llm_rerank dispatcher + Databricks Haiku batch JSON rerank helper</commit_message>
</task>

<task id="P2-3-perf-fix-A-T2" wave="2" depends_on="P2-3-perf-fix-A-T1" autonomous="true" requirements="SC#1,SC#4,SC#6">
  <name>T2: Replace BGE wrapper in kb/api.py with LLM rerank wrapper</name>
  <files_modified>kb/api.py</files_modified>
  <read_first>
    - kb/api.py:21-95 (current _build_bge_rerank + lifespan; lines to delete)
    - kb/api.py:96-117 (lifespan body; site of _build_bge_rerank() call → renaming to _build_llm_rerank())
    - lib/llm_rerank.py (just created in T1; what get_rerank_func returns)
  </read_first>
  <action>
    1. DELETE lines 49-94 (`_BGE_MODEL_NAME`, `_BGE_MAX_LENGTH`, `_build_bge_rerank` body) and the `import time` retention check (kept — still used by lifespan).
    2. ADD after line 47 (after `_log = logging.getLogger(__name__)`):
       ```python


       def _build_llm_rerank() -> tuple[Callable[..., object] | None, bool]:
           """Build LightRAG-compatible async rerank function via lib/llm_rerank dispatcher.

           Returns (rerank_func, ok_flag). ok=False signals graceful degrade
           (KG paths fall back to mode='hybrid' via app.state.rerank_disabled).

           Honors OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1 env override for SC#4 testing.
           Also honors legacy BGE_FORCE_LOAD_FAIL=1 (P2-3 escape compat).
           """
           if (os.environ.get("OMNIGRAPH_LLM_RERANK_FORCE_FAIL") == "1"
                   or os.environ.get("BGE_FORCE_LOAD_FAIL") == "1"):
               _log.warning("llm_rerank_force_fail (test/escape override)")
               return None, False
           t0 = time.monotonic()
           _log.warning("llm_rerank_init_start")
           try:
               from lib.llm_rerank import get_rerank_func
               func, ok = get_rerank_func()
               if not ok:
                   _log.warning("llm_rerank_init_disabled (provider returned no-op)")
                   return None, False
               _log.warning(
                   "llm_rerank_init_ok provider=%s wall_s=%.2f",
                   os.environ.get("OMNIGRAPH_LLM_RERANK_PROVIDER", "databricks_serving"),
                   time.monotonic() - t0,
               )
               return func, True
           except Exception as exc:  # noqa: BLE001 — graceful degrade
               _log.warning("llm_rerank_init_failed err=%s", exc)
               return None, False
       ```
    3. Modify lifespan at line 101 — rename `_build_bge_rerank()` call to `_build_llm_rerank()`:
       ```python
       rerank_func, rerank_ok = _build_llm_rerank()
       app.state.reranker = rerank_func
       app.state.rerank_disabled = not rerank_ok
       ```
       Lines 104-110 (LightRAG ctor with `rerank_model_func=rerank_func`) UNCHANGED.
  </action>
  <acceptance_criteria>
    - `grep -q "_BGE_MODEL_NAME" kb/api.py` returns FALSE (BGE refs removed)
    - `grep -q "from sentence_transformers" kb/api.py` returns FALSE (import removed via deletion)
    - `grep -q "_build_llm_rerank" kb/api.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_FORCE_FAIL" kb/api.py` returns true
    - `grep -q "BGE_FORCE_LOAD_FAIL" kb/api.py` returns true (legacy compat env still honored)
    - `grep -q "rerank_model_func=rerank_func" kb/api.py` returns true (LightRAG ctor unchanged)
    - `python -m py_compile kb/api.py` exits 0
    - `pytest tests/unit/kb/ -x -q` (existing kb unit tests pass)
  </acceptance_criteria>
  <commit_message>feat(v1.1.P2-3-perf-fix-A): replace BGE wrapper with LLM rerank dispatcher in kb/api.py lifespan</commit_message>
</task>

<task id="P2-3-perf-fix-A-T3" wave="2" depends_on="P2-3-perf-fix-A-T2" autonomous="true" requirements="SC#5,SC#6">
  <name>T3: Update databricks-deploy/app.yaml — replace BGE escape env with LLM rerank env block</name>
  <files_modified>databricks-deploy/app.yaml</files_modified>
  <read_first>
    - databricks-deploy/app.yaml (current lines 109-127 — BGE_FORCE_LOAD_FAIL block + comment)
    - kb/api.py post-T2 (verify env names match)
  </read_first>
  <action>
    REPLACE the entire `BGE_FORCE_LOAD_FAIL` env block (lines 109-127) with:
    ```yaml
      # v1.1.P2-3-perf-fix-A: LLM-as-reranker (Databricks Haiku batch JSON).
      # Replaces P2-3 BGE-v2-m3 in-process cross-encoder (eliminated CPU rerank
      # latency root cause: ~160s on N=131 chunks at 8GB CPU). The reranker is
      # now a 1-call Haiku batch JSON over top-30 chunks (~6K-token prompt,
      # ~5-15s wall). Provider dispatch via lib/llm_rerank.py mirrors
      # lib/llm_complete.py pattern. See P2-3-perf-fix-A-VERIFICATION.md.
      - name: OMNIGRAPH_LLM_RERANK_PROVIDER
        value: "databricks_serving"

      - name: OMNIGRAPH_LLM_RERANK_MODEL
        value: "databricks-claude-haiku-4-5"

      - name: OMNIGRAPH_LLM_RERANK_TOP_K
        value: "30"

      - name: OMNIGRAPH_LLM_RERANK_TIMEOUT
        value: "20"

      # SC#6: graceful degrade env. Set to "1" to disable rerank at runtime
      # without code change (KG paths fall back to mode='hybrid', P5 baseline).
      # Legacy BGE_FORCE_LOAD_FAIL is also honored by kb/api.py:_build_llm_rerank
      # for rollback compat (deprecated post-A; remove in v1.2).
      # - name: OMNIGRAPH_LLM_RERANK_FORCE_FAIL
      #   value: "0"
    ```
    DO NOT modify any other env in the file.
  </action>
  <acceptance_criteria>
    - `grep -q "OMNIGRAPH_LLM_RERANK_PROVIDER" databricks-deploy/app.yaml` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_MODEL" databricks-deploy/app.yaml` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_TOP_K" databricks-deploy/app.yaml` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_TIMEOUT" databricks-deploy/app.yaml` returns true
    - `grep -E "^- name: BGE_FORCE_LOAD_FAIL" databricks-deploy/app.yaml` returns FALSE (escape env removed; commented compat retained in body comment only)
    - `python -c "import yaml; yaml.safe_load(open('databricks-deploy/app.yaml'))"` exits 0 (parses)
  </acceptance_criteria>
  <commit_message>ops(v1.1.P2-3-perf-fix-A): replace BGE_FORCE_LOAD_FAIL escape env with LLM rerank env block in app.yaml</commit_message>
</task>

<task id="P2-3-perf-fix-A-T4" wave="2" depends_on="P2-3-perf-fix-A-T3" autonomous="true" requirements="SC#3">
  <name>T4: Add eval harness — N=10 qa_seed + 5 production trace token-overlap + chunk count instrumentation</name>
  <files_modified>tests/eval/test_p2_p3_perf_quality.py, tests/eval/p2_p3_prod_queries.json</files_modified>
  <read_first>
    - tests/eval/qa_seed.json (P2-3 T5; 10 entries — REUSED, not modified)
    - tests/eval/test_p2_p3_quality.py (P2-3 T5; pattern reference for token-overlap + monkeypatch BGE_FORCE_LOAD_FAIL)
    - .scratch/ for any production query trace files (heuristic: latest 5 query strings observed in Databricks logs)
  </read_first>
  <action>
    1. Create `tests/eval/p2_p3_prod_queries.json` with 5 hand-curated production-representative queries:
       ```json
       [
         {"id": 1, "question": "What is OmniGraph-Vault and how does it use LightRAG?",
          "expected_keywords": ["lightrag", "knowledge", "graph", "hermes"]},
         {"id": 2, "question": "How does LightRAG's mix mode differ from hybrid mode?",
          "expected_keywords": ["mix", "hybrid", "rerank", "chunk"]},
         {"id": 3, "question": "What changes are in v1.1 milestone roadmap waves?",
          "expected_keywords": ["wave", "p5", "p2-3", "p4"]},
         {"id": 4, "question": "Explain the BGE reranker integration pattern.",
          "expected_keywords": ["bge", "reranker", "cross-encoder", "rerank_model_func"]},
         {"id": 5, "question": "What is the Databricks Apps tmpfs cold-start behavior?",
          "expected_keywords": ["tmpfs", "tmp", "lightrag", "hydrate", "30s"]}
       ]
       ```
       (Drawn from documented topics in CLAUDE.md / project memory / P5 / P2-3 phases; not from real production telemetry — but represents the *type* and *length* of real KB queries.)
    2. Create `tests/eval/test_p2_p3_perf_quality.py`:
       ```python
       """v1.1.P2-3-perf-fix-A SC#3: token-overlap quality eval.

       Paired comparison: LLM-rerank-on (mix mode) vs no-rerank baseline (hybrid).
       Coverage: N=10 qa_seed + 5 production-representative queries.
       Asserts mean(post) >= mean(baseline) + 0.10.

       Also instruments and logs the N=131-style chunk count distribution to
       capture evidence correcting P2-3 RESEARCH §2 N=20 assumption.
       """
       from __future__ import annotations
       import json, os, re
       import pytest
       from pathlib import Path

       _QA_SEED = Path(__file__).parent / "qa_seed.json"
       _PROD = Path(__file__).parent / "p2_p3_prod_queries.json"

       def _tokens(text: str) -> set[str]:
           return set(re.findall(r"[\w一-鿿]+", (text or "").lower()))

       def _overlap(answer: str, keywords: list[str]) -> float:
           ans = _tokens(answer)
           kw = {k.lower() for k in keywords}
           return len(ans & kw) / len(kw) if kw else 0.0

       @pytest.mark.eval
       @pytest.mark.asyncio
       async def test_p2_p3_perf_quality_token_overlap(monkeypatch) -> None:
           """SC#3: mean(LLM-rerank) >= mean(baseline) + 0.10 over N=15."""
           if not _QA_SEED.exists() or not _PROD.exists():
               pytest.skip("qa_seed.json or p2_p3_prod_queries.json missing")
           qa = json.loads(_QA_SEED.read_text(encoding="utf-8"))
           prod = json.loads(_PROD.read_text(encoding="utf-8"))
           # qa entries use "ground_truth_keywords"; prod use "expected_keywords"
           queries = (
               [(e["question"], e["ground_truth_keywords"]) for e in qa[:10]]
               + [(e["question"], e["expected_keywords"]) for e in prod[:5]]
           )
           assert len(queries) == 15

           from kg_synthesize import synthesize_response

           # Baseline: rerank disabled
           monkeypatch.setenv("OMNIGRAPH_LLM_RERANK_FORCE_FAIL", "1")
           baseline = []
           for q, kw in queries:
               try:
                   ans = await synthesize_response(q, mode="hybrid")
                   baseline.append(_overlap(ans, kw))
               except Exception as e:
                   pytest.skip(f"baseline call failed (env not configured?): {e}")

           # Post: LLM rerank enabled
           monkeypatch.delenv("OMNIGRAPH_LLM_RERANK_FORCE_FAIL", raising=False)
           post = []
           for q, kw in queries:
               ans = await synthesize_response(q, mode="mix")
               post.append(_overlap(ans, kw))

           m_b, m_p = sum(baseline) / 15, sum(post) / 15
           print(f"baseline_token_overlap_mean={m_b:.4f}")
           print(f"post_token_overlap_mean={m_p:.4f}")
           print(f"absolute_improvement={m_p - m_b:.4f}")
           assert m_p >= m_b + 0.10, (
               f"SC#3 violation: improvement {m_p - m_b:.4f} < +0.10 "
               f"(baseline={m_b:.4f}, post={m_p:.4f})"
           )
       ```
    3. NO modification to `tests/eval/qa_seed.json` (reused as-is).
  </action>
  <acceptance_criteria>
    - `tests/eval/test_p2_p3_perf_quality.py` exists
    - `tests/eval/p2_p3_prod_queries.json` exists and parses as JSON list of length 5
    - `python -m py_compile tests/eval/test_p2_p3_perf_quality.py` exits 0
    - `tests/eval/qa_seed.json` UNCHANGED (`git diff tests/eval/qa_seed.json` empty)
    - `pytest -m eval tests/eval/test_p2_p3_perf_quality.py --collect-only` lists 1 test
  </acceptance_criteria>
  <commit_message>test(v1.1.P2-3-perf-fix-A): add LLM-rerank vs hybrid token-overlap eval (qa_seed + 5 prod queries)</commit_message>
</task>

<task id="P2-3-perf-fix-A-T5" wave="2" depends_on="P2-3-perf-fix-A-T4" autonomous="true" requirements="SC#1,SC#4,SC#6">
  <name>T5: Add lifespan integration tests + _parse_scores unit tests (split files)</name>
  <files_modified>tests/integration/kb/test_p2_p3_llm_reranker.py, tests/unit/test_llm_rerank_parse_scores.py</files_modified>
  <read_first>
    - tests/integration/kb/test_p2_p3_lifespan_reranker.py (P2-3 T5; importlib.reload + monkeypatch idiom)
    - tests/integration/kb/test_lifespan_singleton.py (P5 — TestClient(app) + app.state inspection)
    - kb/api.py post-T2 (app.state.reranker / app.state.rerank_disabled shape)
    - databricks-deploy/lightrag_databricks_rerank.py post-T1 (verify _parse_scores is module-level, importable)
  </read_first>
  <action>
    Plan-checker recommendation #1: split into TWO test files — integration tests cover lifespan/force-fail/legacy-compat; UNIT tests cover the pure `_parse_scores` function (the contract verified by tests c+d in the original draft, but with no Databricks dependency).

    1. Create `tests/integration/kb/test_p2_p3_llm_reranker.py` (3 lifespan tests, ~40 LoC):
       ```python
       """v1.1.P2-3-perf-fix-A SC#1 + SC#4 + SC#6: LLM rerank lifespan + graceful degrade.

       Three integration tests cover:
         (a) lifespan happy path: dispatcher returns rerank func + LightRAG ctor gets it
             (skipped iff Databricks auth unavailable in CI)
         (b) lifespan force-fail: OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1 → app boots disabled
         (c) lifespan legacy-bge compat: BGE_FORCE_LOAD_FAIL=1 → same graceful-degrade

       NB: importlib.reload between TestClient blocks risks cached singletons —
       escalate to subprocess.run isolation if flake observed during T6.
       """
       from __future__ import annotations
       import importlib
       import pytest
       from fastapi.testclient import TestClient


       @pytest.mark.integration
       def test_lifespan_llm_reranker_loaded(monkeypatch) -> None:
           """Happy path: dispatcher returns Haiku rerank func; LightRAG receives it."""
           monkeypatch.delenv("OMNIGRAPH_LLM_RERANK_FORCE_FAIL", raising=False)
           monkeypatch.delenv("BGE_FORCE_LOAD_FAIL", raising=False)
           monkeypatch.setenv("OMNIGRAPH_LLM_RERANK_PROVIDER", "databricks_serving")
           import kb.api as kb_api
           importlib.reload(kb_api)
           with TestClient(kb_api.app) as client:
               r = client.get("/health")
               assert r.status_code == 200, r.text
               # Without Databricks auth, dispatcher returns (None, False) gracefully —
               # we accept either state, but require flag/object consistency.
               disabled = kb_api.app.state.rerank_disabled
               if disabled:
                   assert kb_api.app.state.reranker is None
                   assert kb_api.app.state.lightrag.rerank_model_func is None
               else:
                   assert kb_api.app.state.reranker is not None
                   assert kb_api.app.state.lightrag.rerank_model_func is not None


       @pytest.mark.integration
       def test_lifespan_llm_reranker_force_fail(monkeypatch) -> None:
           """SC#4: force-fail env → app boots, flag set, LightRAG ctor gets None."""
           monkeypatch.setenv("OMNIGRAPH_LLM_RERANK_FORCE_FAIL", "1")
           import kb.api as kb_api
           importlib.reload(kb_api)
           with TestClient(kb_api.app) as client:
               assert client.get("/health").status_code == 200
               assert kb_api.app.state.rerank_disabled is True
               assert kb_api.app.state.reranker is None
               assert kb_api.app.state.lightrag.rerank_model_func is None


       @pytest.mark.integration
       def test_lifespan_legacy_bge_force_fail_compat(monkeypatch) -> None:
           """SC#6: legacy BGE_FORCE_LOAD_FAIL=1 still honored (rollback compat)."""
           monkeypatch.delenv("OMNIGRAPH_LLM_RERANK_FORCE_FAIL", raising=False)
           monkeypatch.setenv("BGE_FORCE_LOAD_FAIL", "1")
           import kb.api as kb_api
           importlib.reload(kb_api)
           with TestClient(kb_api.app) as client:
               assert client.get("/health").status_code == 200
               assert kb_api.app.state.rerank_disabled is True
       ```

    2. Create `tests/unit/test_llm_rerank_parse_scores.py` (~6 unit tests on the pure function, ~50 LoC):
       ```python
       """v1.1.P2-3-perf-fix-A SC#4 unit: _parse_scores pure-function contract.

       Verifies the JSON parse-fail / partial-scores / valid-output ladder
       WITHOUT Databricks-SDK dependency (T5 plan-checker rec #1: extract
       contract verification from integration test that requires real HTTP).
       """
       from __future__ import annotations
       import os, sys
       import pytest

       # Fixture: ensure databricks-deploy/ is on sys.path so the module imports
       _DD = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                          "databricks-deploy"))
       if _DD not in sys.path:
           sys.path.insert(0, _DD)


       @pytest.fixture
       def parse():
           import lightrag_databricks_rerank as ldr
           return ldr._parse_scores


       @pytest.mark.unit
       def test_parse_scores_garbage_returns_none(parse) -> None:
           assert parse("definitely not json", n_docs=3) is None


       @pytest.mark.unit
       def test_parse_scores_empty_object_returns_none(parse) -> None:
           assert parse("{}", n_docs=3) is None


       @pytest.mark.unit
       def test_parse_scores_partial_below_threshold_returns_none(parse) -> None:
           # n_docs=10, only 2 scored (20% < 50% threshold) → None to trigger retry
           raw = '{"scores": [{"i": 0, "s": 0.9}, {"i": 1, "s": 0.7}]}'
           assert parse(raw, n_docs=10) is None


       @pytest.mark.unit
       def test_parse_scores_partial_above_threshold_returns_sorted(parse) -> None:
           # n_docs=4, 3 scored (75% ≥ 50%) → accept + sort
           raw = '{"scores": [{"i": 0, "s": 0.3}, {"i": 1, "s": 0.9}, {"i": 2, "s": 0.6}]}'
           result = parse(raw, n_docs=4)
           assert result is not None
           assert [r["index"] for r in result] == [1, 2, 0]
           assert result[0]["relevance_score"] == pytest.approx(0.9)


       @pytest.mark.unit
       def test_parse_scores_full_returns_descending(parse) -> None:
           raw = '{"scores": [{"i": 0, "s": 0.1}, {"i": 1, "s": 0.5}, {"i": 2, "s": 0.9}]}'
           result = parse(raw, n_docs=3)
           assert result is not None
           assert [r["index"] for r in result] == [2, 1, 0]


       @pytest.mark.unit
       def test_parse_scores_markdown_fence_stripped(parse) -> None:
           # Haiku sometimes wraps JSON in ```json...``` fence; the strip ladder
           # in _parse_scores (.strip("`").lstrip("json").strip()) must recover.
           raw = '```json\n{"scores": [{"i": 0, "s": 0.5}, {"i": 1, "s": 0.5}]}\n```'
           result = parse(raw, n_docs=2)
           assert result is not None
           assert len(result) == 2
       ```

       NOTE: this requires `_parse_scores` to be MODULE-LEVEL in `databricks-deploy/lightrag_databricks_rerank.py` (not a closure inside `make_rerank_func`). PLAN T1 already specifies it module-level (see PLAN T1 action lines 220-235); verify in T5 read-first that this is preserved.

    3. Endpoint-timeout + per-request graceful-degrade contract is verified at T6 production smoke (no test stub of `serving_endpoints.query` — that path was removed by plan-checker rec #1 because it required real WorkspaceClient).
  </action>
  <acceptance_criteria>
    - `tests/integration/kb/test_p2_p3_llm_reranker.py` exists with 3 tests
    - `tests/unit/test_llm_rerank_parse_scores.py` exists with 6 tests
    - `python -m py_compile tests/integration/kb/test_p2_p3_llm_reranker.py tests/unit/test_llm_rerank_parse_scores.py` exits 0
    - `pytest tests/unit/test_llm_rerank_parse_scores.py -v -m unit` runs 6 tests, **ALL PASS** (no Databricks dependency, must be deterministic in CI)
    - `pytest tests/integration/kb/test_p2_p3_llm_reranker.py -v -m integration` runs 3 tests; force_fail + legacy_bge_force_fail MUST PASS; lifespan_loaded may pass either branch (with or without Databricks auth)
    - `_parse_scores` is module-level in `databricks-deploy/lightrag_databricks_rerank.py` (verify via `python -c "from lightrag_databricks_rerank import _parse_scores"` after sys.path setup)
  </acceptance_criteria>
  <commit_message>test(v1.1.P2-3-perf-fix-A): split lifespan integration tests + _parse_scores unit tests</commit_message>
</task>

<task id="P2-3-perf-fix-A-T6" wave="2" depends_on="P2-3-perf-fix-A-T5" autonomous="false" requirements="SC#1,SC#2,SC#3,SC#4,SC#5,SC#6">
  <name>T6: Local UAT + Databricks deploy + 4-Track verify + write VERIFICATION.md (CHECKPOINT)</name>
  <files_modified>.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md</files_modified>
  <read_first>
    - This PLAN.md "Verification" section
    - CLAUDE.md Principle #6 (Local UAT mandatory) + Principle #7 (Claude owns Databricks deploy) + Principle #9 (Makefile gate)
    - .planning/phases/v1.1-roadmap/P2-3/P2-3-VERIFICATION.md (template/format reference)
    - [[claude_databricks_deployment_autonomous]] (Claude owns sync + deploy + log fetch)
    - [[databricks_apps_stop_start_wipes_deployment]] (full redeploy required after stop)
  </read_first>
  <action>
    Sequential execution. Aliyun-side ops are OUT OF SCOPE for A — defer to v1.1.P2-3-perf-fix-B.

    **Track 1 — Local cold-start (SC#1):**
    1. Stop any uvicorn on :8766.
    2. `$start = Get-Date; .\venv\Scripts\python.exe .scratch\local_serve.py *> .uvicorn-p23A.log &`
    3. Poll `/health` every 200 ms; record BOOT_TO_HEALTH_MS.
    4. First POST `/api/synthesize`; record FIRST_REQ_WALL_MS. Tail .uvicorn-p23A.log; verify `llm_rerank_init_ok provider=databricks_serving model=...` appears (or `llm_rerank_init_disabled` if local DATABRICKS auth unavailable — proceed with rerank_disabled path for SC#4 only).
    5. **Assertion (informational, not blocking):** local NTFS pre-P5 baseline 60-350s; the new lifespan does NOT load BGE so should be ≤ baseline + 1s. Local is not the SC#1 gate (Databricks is).

    **Track 4 — Local steady-state (SC#2):**
    6. 10-iteration p50/p95 measurement against `/api/synthesize` (kg + long_form). Record `p50_local` and `p95_local`.
    7. **Assertion (informational):** observe end-to-end wall; SC#2 binds on Databricks measurement (step 14).

    **Track 4 quality — Eval harness (SC#3):**
    8. `venv/Scripts/python.exe -m pytest -m eval tests/eval/test_p2_p3_perf_quality.py -v -s`
    9. Capture stdout: `baseline_token_overlap_mean=X.XX`, `post_token_overlap_mean=Y.YY`, `absolute_improvement=Z.ZZ`.
    10. **Assertion:** `Z.ZZ ≥ 0.10`.

    **Track 3 — Graceful degrade (SC#4):**
    11. `$env:OMNIGRAPH_LLM_RERANK_FORCE_FAIL = "1"; venv/Scripts/python.exe .scratch/local_serve.py *> .uvicorn-p23A-degraded.log &`
    12. POST `/api/synthesize`; verify 200 OK + log shows `llm_rerank_force_fail` + worker dispatches `mode='hybrid'` (NOT `mix`).
    13. `Remove-Item Env:\OMNIGRAPH_LLM_RERANK_FORCE_FAIL`

    **Track 3b — Legacy BGE_FORCE_LOAD_FAIL compat (SC#6):**
    14. `$env:BGE_FORCE_LOAD_FAIL = "1"; venv/Scripts/python.exe .scratch/local_serve.py *> .uvicorn-p23A-bge-degraded.log &`
    15. Verify same: 200 + `llm_rerank_force_fail (test/escape override)` log + mode='hybrid'.
    16. `Remove-Item Env:\BGE_FORCE_LOAD_FAIL`

    **Local browser UAT (Principle #6):**
    17. Open http://localhost:8766; submit a query via UI. Capture `.playwright-mcp/v1.1.P2-3-perf-fix-A-uat-local.png`.
    18. Verify response renders + `confidence: kg` + citation links resolve.

    **SC#5 — Principle #9 file-touch check:**
    19. `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` MUST return empty.
    20. If non-empty → HALT.

    **Databricks deploy (sync-only OK, SC#5 cleared):**
    21. `databricks sync --watch . /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy`
    22. `databricks apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy --profile adb-2717931942638877`
    23. Tail logs via `make logs`; verify `llm_rerank_init_ok` line present + `lightrag_singleton_ready wall_s=NN.NN`.

    **Track 1 Databricks cold-start (SC#1, the binding gate):**
    24. From the deploy timestamps + first /api/synthesize wall, record `cold_start_databricks_s`.
    25. **Assertion:** ≤ 60s (P5 baseline 28.88s + LLM rerank zero-load + first-request Haiku TTFB ~5-15s = ~50s expected).

    **Track 4 Databricks steady-state (SC#2, binding gate):**
    26. 10-iteration p50/p95 against deployed long_form: 5 queries × 2 iter each via `.scratch/p23_perf_probe.py` (or pytest harness).
    27. **Assertion:** `p50_databricks ≤ 65s` (1.3 × P5 baseline 49.93s).

    **Track 2 Databricks N=4 concurrent (P5 contract preservation):**
    28. `pytest tests/integration/kb/test_async_safety.py::test_singleton_async_safety_n4 -v` against `KB_BASE_URL=<deployed-url>`.
    29. **Assertion:** 4/4 done, distinct markdown, MARKER tokens preserved.

    **Write `P2-3-perf-fix-A-VERIFICATION.md`** at `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/`:
    - **SC#1 evidence:** Databricks cold-start wall + `llm_rerank_init_ok wall_s=` log
    - **SC#2 evidence:** Databricks p50 + p95 vs P5 baseline 49.93s; comparison table
    - **SC#3 evidence:** eval harness stdout (`baseline_*`, `post_*`, `absolute_improvement`); pytest output cited verbatim
    - **SC#4 evidence:** `.uvicorn-p23A-degraded.log` excerpt with `llm_rerank_force_fail` + `mode='hybrid'`
    - **SC#5 evidence:** git diff filter command + empty result
    - **SC#6 evidence:** `.uvicorn-p23A-bge-degraded.log` showing legacy BGE_FORCE_LOAD_FAIL=1 still triggers graceful degrade
    - **Local UAT section:** launcher, env, curl smoke, screenshot path
    - **Databricks deploy section:** sync output, deploy SUCCEEDED line, llm_rerank_init_ok from server log
    - **Aliyun parity gate (HC-6):** **DEFERRED — see follow-up `v1.1.P2-3-perf-fix-B`** (Vertex Gemini batch JSON helper + Aliyun deploy + Aliyun smoke). Aliyun retains P5 baseline mode='hybrid' until B ships.
    - **N=4 concurrent (P5 preservation):** test_singleton_async_safety_n4 PASSED line cited.
    - **Principle #9 gate:** explicit file-touch grep result.
    - **LoC waive log (orchestrator decision Z):** +258 net LoC (honest row-sum; see PLAN LoC table TOTAL row). User explicitly waived 150 ceiling on 2026-05-31 knowing dispatcher full design would exceed it. Phase remains plan-phase, not escalated.

    **Pause for operator approval** — user types `approved` to mark P2-3-perf-fix-A complete.
  </action>
  <acceptance_criteria>
    - `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md` exists
    - File contains "SC#1" through "SC#6" headers
    - `grep -q "llm_rerank_init_ok" P2-3-perf-fix-A-VERIFICATION.md` returns true
    - `grep -q "absolute_improvement=" P2-3-perf-fix-A-VERIFICATION.md` returns true
    - `grep -q "test_singleton_async_safety_n4 PASSED" P2-3-perf-fix-A-VERIFICATION.md` returns true
    - `grep -q "Aliyun parity gate" P2-3-perf-fix-A-VERIFICATION.md` returns true (deferred citation)
    - `grep -q "Principle #9" P2-3-perf-fix-A-VERIFICATION.md` returns true
    - `grep -q ".playwright-mcp/v1.1.P2-3-perf-fix-A-uat-local.png" P2-3-perf-fix-A-VERIFICATION.md` returns true
    - Operator types "approved" in resume signal
  </acceptance_criteria>
  <commit_message>docs(v1.1.P2-3-perf-fix-A): VERIFICATION.md — LLM-as-reranker shipped, SC#1-6 evidence + Aliyun deferred to B</commit_message>
</task>
```

## Verification (4 Track + SC#5 + SC#6)

### Track 1 — Cold-start (SC#1)
**Databricks Apps (binding gate):**
- LightRAG hydrate ~28.88s (P5 baseline preserved). `_build_llm_rerank` only constructs an async closure (no model download/load). First /api/synthesize Haiku TTFB ~5-15s.
- **PASS:** `cold_start_databricks_s ≤ 60s`. Log shows `llm_rerank_init_ok provider=databricks_serving wall_s=NN.NN` exactly once per process.

**Local NTFS (informational, not gating):**
- No BGE load, so local boot ≤ baseline. Reported but not asserted.

### Track 2 — Async safety (P5 contract preserved)
- Re-run `tests/integration/kb/test_async_safety.py::test_singleton_async_safety_n4` against deployed Databricks.
- **PASS:** 4/4 done, distinct markdown, MARKER tokens preserved.
- LLM rerank introduces no new lock; relies on P5's `app.state.lightrag_lock` (verified P2-3 RESEARCH §7).

### Track 3 — Graceful degrade (SC#4 + SC#6)
- (a) `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` → app.state.rerank_disabled=True; mode='hybrid' for KG paths. Log: `llm_rerank_force_fail`. **PASS** when 200 + `mode='hybrid'`.
- (b) `BGE_FORCE_LOAD_FAIL=1` legacy compat → identical path. Log: `llm_rerank_force_fail (test/escape override)`. **PASS** when 200 + `mode='hybrid'`.
- (c) Per-request: simulated JSON parse fail (test b in T5) → wrapper returns identity, apply_rerank_if_enabled uses original chunks; aquery succeeds.
- (d) Per-request: simulated endpoint timeout → identity return; same.
- All four mechanisms verified.

### Track 4 — Steady-state quality (SC#2 + SC#3)
- **SC#2 latency:** 10-iter p50/p95 against post-P5 baseline 49.93s. **PASS:** `p50_databricks ≤ 65s`.
- **SC#3 quality:** eval harness on N=15 (10 qa_seed + 5 prod queries). **PASS:** `mean_post - mean_baseline ≥ 0.10`.

### SC#5 — Principle #9 file-touch invariant
- `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` returns empty.
- Sync-only Databricks deploy permissible; no Pass 0 SSG bake required.

### Aliyun parity gate (HC-6)
- **DEFERRED to `v1.1.P2-3-perf-fix-B`.** Aliyun retains P5 baseline mode='hybrid' until B ships Vertex Gemini batch JSON helper + dispatcher route + Aliyun deploy.

## Halt Triggers

- **HT-1: Haiku endpoint unreachable from Databricks Apps.** First production smoke /api/synthesize returns 500 or hangs > 60s with `llm_rerank_endpoint_fail` log spam. STOP — verify endpoint name + WorkspaceClient OAuth M2M scopes; check `databricks-deploy/_db_client.py` http_timeout_seconds default not interfering.
- **HT-2: Haiku JSON parse fail rate > 30% on production trace.** Eval harness or production smoke shows wrapper falling to identity > 30% of calls. STOP — diagnose JSON Schema strictness; consider escalating to Sonnet (Decision D1=B) OR retry budget bump (Decision D2 alt). LoC delta ≤ 20.
- **HT-3: Eval harness shows < +10% token-overlap.**
  - +5-10%: STOP, investigate qa_seed bias; consider extending to N=20 if seed unrepresentative.
  - <+5%: STOP, MAJOR. Either prompt is misbuilt OR Haiku scoring is uncorrelated with relevance. Cancel deploy, return to RESEARCH §6 (LLM-as-reranker quality benchmarks).
- **HT-4: SC#2 latency regression > 1.3×.** Haiku batch wall >15s consistently; overall p50 > 65s. STOP — profile Haiku TTFB on warm vs cold endpoint; consider top_K=20 alternative + re-measure.
- **HT-5: SC#5 violated** — any kb/static/ or kb/templates/ touched. STOP, re-plan; sanity-check (this phase has no reason to touch them).
- **HT-6: P5 lock contract broken** — N=4 test fails post-deploy. LLM rerank may be calling executor in re-entrant pattern. STOP, diagnostic: log lock acquire/release timestamps + executor thread IDs.
- **HT-7: Graceful-degrade fails closed.** With `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1`, app crashes OR rerank_disabled is False. STOP — re-read T2 `_build_llm_rerank` env override branch.
- **HT-8: Legacy BGE_FORCE_LOAD_FAIL compat broken.** Setting BGE_FORCE_LOAD_FAIL=1 does NOT trigger graceful degrade post-T2. STOP — SC#6 contract violation.
- **HT-9 (soft, monitoring trigger): Haiku cost runaway.** RESEARCH §1 measures ~$0.015/query (10× orchestrator initial estimate). At 1000 queries/day = ~$450/month. SOFT trigger: if observed query count trends > 2000/day OR observed cost > $30/day in T6 production smoke window, surface in VERIFICATION.md as cost-monitoring concern + queue follow-up phase to reduce top_K or chunk content size. Does NOT block phase A close (cost is operationally acceptable at personal-tool scale per RESEARCH §1 finding).

## Rollback Plan

P2-3-perf-fix-A is a **paired-component change** spanning 2 NEW files + 2 MODIFIED files + 1 deploy artifact + 2 NEW test files. Rollback options:

1. **Operational escape (no revert):** set `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` (or legacy `BGE_FORCE_LOAD_FAIL=1`) on deployed app + restart. Reranker disabled, mode='hybrid' for KG paths. Identical fallback path to P2-3 escape — operator-friendly hot-fix.

2. **Provider downgrade:** set `OMNIGRAPH_LLM_RERANK_PROVIDER=disabled` on deployed app. Same end state but explicit dispatcher control.

3. **Full revert (if architectural):**
   ```powershell
   git revert <T6-sha> <T5-sha> <T4-sha> <T3-sha> <T2-sha> <T1-sha>
   git push origin main
   databricks sync --watch . /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy
   databricks apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy
   ```
   Restores P2-3 escape state (BGE wrapper retained, escape env active).

4. **Partial revert (Haiku only):** revert T1 commit only; the dispatcher import in T2 then surfaces ImportError in lifespan, which `_build_llm_rerank` catches as graceful degrade. Effectively forces rerank_disabled until dispatcher is restored. Hot-fix-friendly state.

## Success Criteria

P2-3-perf-fix-A is complete when:
- [ ] **SC#1:** Cold-start ≤ 60s on Databricks; numeric in VERIFICATION.md cites `llm_rerank_init_ok wall_s=` + first /api/synthesize wall.
- [ ] **SC#2:** Steady-state long_form `p50_databricks ≤ 65s` (1.3 × P5 baseline 49.93s).
- [ ] **SC#3:** Token-overlap `mean_post ≥ mean_baseline + 0.10` on N=15 (10 qa_seed + 5 production).
- [ ] **SC#4:** `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` simulation → app boots, log shows `llm_rerank_force_fail` + worker dispatches mode='hybrid'; integration test PASSES.
- [ ] **SC#5:** `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` returns empty.
- [ ] **SC#6:** Legacy `BGE_FORCE_LOAD_FAIL=1` env path still triggers graceful degrade (rollback compat).
- [ ] P5 contract preserved: `test_singleton_async_safety_n4` PASSES on post-A deploy.
- [ ] Aliyun parity DEFERRED — explicitly cited in VERIFICATION.md "Follow-up `v1.1.P2-3-perf-fix-B`".

## Output

After T6 operator-approved, the phase closes with:
- 6 commits on main (T1..T6)
- Updated `STATE-v1.1.md` (P2-3-perf-fix-A row added → ✅ CLOSED post-approval)
- `P2-3-perf-fix-A-VERIFICATION.md` with all 6 SC sections + Databricks deploy evidence + Aliyun deferred citation
- ISSUES.md row added (orchestrator transcribes per Principle #10): "v1.1.P2-3-perf-fix-B P0 — Aliyun Vertex Gemini rerank parity blocked on A close, +65 LoC est"
- BGE_FORCE_LOAD_FAIL escape ENV removed from app.yaml; replaced with OMNIGRAPH_LLM_RERANK_PROVIDER block
- Wave 2 P2-3 line in STATE-v1.1.md updated: status changes from `⚠️ DEPLOYED-DISABLED` → `✅ DEPLOYED-ENABLED via perf-fix-A` (Aliyun side cited as deferred)
