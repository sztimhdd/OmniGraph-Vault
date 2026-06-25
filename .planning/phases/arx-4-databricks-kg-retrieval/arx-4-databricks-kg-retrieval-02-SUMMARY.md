---
phase: arx-4-databricks-kg-retrieval
plan: 02
status: complete
requirements: [ARX4-65]
commits:
  - 47a255f  # fix(arx-4-02): rerank init-vs-query trace diagnostic (#65)
---

# Plan 02 SUMMARY — Reconcile #65 rerank init-vs-query disagreement

## Outcome

**#65 RESOLVED by trace — the wiring is correct; no disable/rewire needed.**

The empirical diagnostic on the live Databricks deployment proves the rerank
function reaches the query-time `global_config`, so the misleading
"no rerank model is configured" warning **cannot fire** at query time on this
deployment. The disagreement reported in #65 reflected an earlier/stale state,
not the current deployed wiring.

## Task 1 — diagnostic added + captured on deployed log

Added a 6-line `rerank_diag` warning in `kb/api.py:lifespan()` immediately
after the `LightRAG(...)` ctor (commit `47a255f`). It records the A/B/C
discriminator from the planner's interfaces trace.

Deploy: sync-only (Principle #9 — `kb/` python source, no `kb/static`|`kb/templates`
touched). `databricks sync --full ./kb …/databricks-deploy/kb` → `apps deploy
omnigraph-kb` → deployment `01f170a523ac136f9b03f514670713b3` SUCCEEDED
("App started successfully"). LightRAG pin 1.4.15 (matches `requirements.txt`).

**`rerank_diag` line captured verbatim from the deployed startup log**
(via `make logs` / `tail_app_logs.py`):

```
1782400309 [APP] llm_rerank_init_start
1782400310 [APP] llm_rerank_init_ok provider=databricks_serving wall_s=0.61
1782400337 [APP] WARNING:kb.api:rerank_diag init_reranker_set=True rerank_disabled=False global_config_has_func=True enable_rerank_default=true
1782400337 [APP] WARNING:kb.api:lightrag_vector_storage backend=nanovectordb
1782400338 [APP] WARNING:kb.api:lightrag_singleton_ready wall_s=28.31
```

## Root cause (empirical, not guessed)

| Field | Value | Implication |
|-------|-------|-------------|
| `init_reranker_set` | **True** | reranker survived init — **rules out Branch A** (provider no-op) |
| `rerank_disabled` | **False** | `_build_llm_rerank` returned ok — not disabled |
| `global_config_has_func` | **True** | `asdict(rag)` **carries** `rerank_model_func` into query-path global_config — **rules out Branch B** (asdict drops it) |
| `enable_rerank_default` | true | RERANK_BY_DEFAULT default |

LightRAG `apply_rerank_if_enabled` (venv `lightrag/utils.py:2640-2645`) emits the
warning **only** when `global_config.get("rerank_model_func")` is falsy. Every
query-time call site (`operate.py` kg_query/naive_query → `process_chunks_unified`
:4142/:5045 → `apply_rerank_if_enabled` :2731) is fed `global_config = asdict(self)`
off the **same** singleton instance, which the diagnostic proves contains the func.
∴ the warning cannot fire at query time on this deployment.

The kb routers thread `rerank_disabled` correctly: `search.py:73` selects
`mode="mix"` (rerank path) when `not rerank_disabled`, and `app.state.rerank_disabled`
is `False` here — so the rerank mode is selected, consistent with the trace.

## Task 2 — branch decision: NO code change (trace-grounded)

The plan's Task 2 said "implement EXACTLY the branch the Task 1 trace proved."
The trace proved **neither A nor B** — the func is wired correctly through to the
query path. Forcing `enable_rerank=False` (Branch A) would wrongly disable a
working reranker; rewiring (Branch B) is unnecessary since `asdict` does not drop
the func. Per Principle #8 (right-size — don't manufacture a change when the trace
proves correctness), the resolution is:

- **Keep** the `rerank_diag` line as the permanent #65 resolution evidence +
  regression canary (≤6 LoC net add, well under the 40-LoC ceiling).
- **Query-time confirmation** (absence of "no rerank model is configured" +
  presence of "Successfully reranked: N chunks") is the explicit #65 pass-bar in
  Plan 04's combined deployed UAT (which runs a real query — no query has run since
  the restart yet, so the live log has no query-time rerank line to capture in
  isolation here; Plan 04 closes that loop).

## Diff

`kb/api.py`: +15 lines (the diagnostic block + comment). One file. ≤40 LoC. ✓

## Carry-forward to Plan 04

Plan 04's UAT must confirm on a real query: the deployed backend log does NOT
contain `Rerank is enabled but no rerank model is configured`. Given the trace,
the expected result is the warning is absent (and, since the func is wired,
`Successfully reranked: N chunks` should appear when the rerank path executes).
