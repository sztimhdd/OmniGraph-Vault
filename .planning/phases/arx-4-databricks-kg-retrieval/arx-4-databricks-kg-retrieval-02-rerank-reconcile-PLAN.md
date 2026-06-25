---
phase: arx-4-databricks-kg-retrieval
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - kb/api.py
autonomous: true
requirements: [ARX4-65]
user_setup: []

must_haves:
  truths:
    - "The init-vs-query disagreement is RESOLVED: either rerank actually applies at query time (the rerank_model_func reaches LightRAG's global_config and a successful-rerank log appears), OR enable_rerank is explicitly False and the misleading WARNING is gone by design."
    - "The deployed Databricks backend log no longer emits 'Rerank is enabled but no rerank model is configured' on every query."
    - "The decision (wire-it vs disable-it) is grounded in an actual code trace recorded in the SUMMARY, not a guess."
  artifacts:
    - path: "kb/api.py"
      provides: "Reconciled rerank wiring — a diagnostic-grounded fix in lifespan() that either (a) confirms+enforces rerank_model_func reaching the query path with enable_rerank left default, or (b) sets enable_rerank=False (via RERANK_BY_DEFAULT/QueryParam) so the warning is dropped"
      contains: "rerank"
  key_links:
    - from: "kb/api.py:_build_llm_rerank"
      to: "LightRAG global_config['rerank_model_func']"
      via: "rag = LightRAG(rerank_model_func=rerank_func) → asdict(self) at query time"
      pattern: "rerank_model_func"
    - from: "kb/api_routers/search.py + synthesize.py query paths"
      to: "rerank application"
      via: "app.state.rerank_disabled → mode='mix' (rerank) vs 'hybrid' (no rerank)"
      pattern: "rerank_disabled"
---

<objective>
Reconcile ISSUES #65: on deployed Databricks, startup logs `llm_rerank_init_ok provider=databricks_serving` (so `kb/api.py:_build_llm_rerank` succeeds and `LightRAG(rerank_model_func=rerank_func)` is constructed at `:100`), BUT every query then logs `WARNING: Rerank is enabled but no rerank model is configured`. The two states disagree — rerank is configured at init but reported absent at query time, meaning rerank is likely NOT actually applied to retrieval despite the deliberate P2-3-perf-fix-A wiring.

This plan is INDEPENDENT of #41/#64 — it is pure code in `kb/api.py` + a trace, touching different files, so it runs in parallel (its own Wave 1).

Purpose: make the deployed retrieval either actually rerank (restoring the quality mechanism) or honestly report it disabled (dropping the misleading warning) — decided by tracing where LightRAG reads `rerank_model_func` vs what survives into the query path.

Output: a diagnostic-grounded ~10-40 LoC change in `kb/api.py`, verified on the deployed Databricks log.

ZERO new features — this fixes an existing wiring disagreement.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md

<interfaces>
<!-- THE ROOT-CAUSE TRACE (already done by the planner — give the executor the anchors, not a scavenger hunt). -->

The exact WARNING source is LightRAG's `apply_rerank_if_enabled` in `venv/Lib/site-packages/lightrag/utils.py`:
```python
# utils.py:2637-2645
async def apply_rerank_if_enabled(query, retrieved_docs, global_config, enable_rerank=True, top_n=None):
    if not enable_rerank or not retrieved_docs:
        return retrieved_docs
    rerank_func = global_config.get("rerank_model_func")        # :2640
    if not rerank_func:                                          # :2641
        logger.warning(
            "Rerank is enabled but no rerank model is configured. ...")   # :2642-2644  <-- THE WARNING
        return retrieved_docs
    ...  # else: calls rerank_func, logs "Successfully reranked: N chunks ..." (:2684)
```
Gated by (utils.py:2729) `if query_param.enable_rerank and query and unique_chunks:`.
`enable_rerank` default (base.py:160): `os.getenv("RERANK_BY_DEFAULT","true").lower()=="true"` → True by default. Docstring (base.py:161): "If True but no rerank model is configured, a warning will be issued."

How `rerank_model_func` is SUPPOSED to reach `global_config` (lightrag.py):
- `rerank_model_func: Callable | None = field(default=None)` (:438) — a plain dataclass field.
- Query path builds `global_config = asdict(self)` (:2788, :2906) — so a non-None `rerank_model_func` on the instance SHOULD land in `global_config["rerank_model_func"]`.

∴ The warning firing despite `init_ok` means ONE of:
  (A) the deployed runtime's `get_rerank_func()` actually returns `(None, False)` at query time but a stale/earlier log line showed ok — i.e. `app.state.reranker is None` / `rerank_disabled is True` on the live instance; OR
  (B) `rerank_func` is truthy at init but `asdict(self)` drops/nulls it, so `global_config["rerank_model_func"]` is falsy at query time; OR
  (C) the deployed `RERANK_BY_DEFAULT`/`enable_rerank` is True while the provider genuinely no-ops on Databricks.

The dispatcher: `databricks-deploy/lib/llm_rerank.py:get_rerank_func()` → on `databricks_serving` imports `lightrag_databricks_rerank.make_rerank_func()` inside a `try/except: return None,False` (graceful degrade) — so an import/runtime failure there silently yields `(None, False)` while a PRIOR successful path could have logged ok. This is the prime suspect for (A).
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add a query-time rerank diagnostic to lifespan() and capture it on the deployed Databricks log to settle (A) vs (B) vs (C)</name>
  <files>kb/api.py</files>
  <read_first>
    - kb/api.py (:50-120 — _build_llm_rerank + lifespan; esp. :86-88 app.state.reranker/rerank_disabled, :95-102 the LightRAG ctor with rerank_model_func=rerank_func)
    - venv/Lib/site-packages/lightrag/utils.py (:2617-2645 apply_rerank_if_enabled — the WARNING; :2729-2737 the enable_rerank gate)
    - venv/Lib/site-packages/lightrag/base.py (:160-162 enable_rerank default / RERANK_BY_DEFAULT)
    - venv/Lib/site-packages/lightrag/lightrag.py (:438 rerank_model_func field; :2788 + :2906 `global_config = asdict(self)`)
    - databricks-deploy/lib/llm_rerank.py (the get_rerank_func dispatcher with the silent try/except graceful-degrade)
    - databricks-deploy/lightrag_databricks_rerank.py (make_rerank_func — what may fail to import on the deployed env)
    - .planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-CONTEXT.md (#65 section — wire-it-or-disable decision criteria)
    - MEMORY: databricks-kg-weight-fallback-residue (the exact deployed symptom)
  </read_first>
  <action>
    Add a single diagnostic log line in `kb/api.py:lifespan()` immediately AFTER the `rag = LightRAG(...)` ctor (after :102) that records the ground truth needed to pick the branch:
    ```python
    from dataclasses import asdict as _asdict
    _gc_rerank = _asdict(rag).get("rerank_model_func")
    _log.warning(
        "rerank_diag init_reranker_set=%s rerank_disabled=%s global_config_has_func=%s enable_rerank_default=%s",
        app.state.reranker is not None,
        app.state.rerank_disabled,
        _gc_rerank is not None,
        os.getenv("RERANK_BY_DEFAULT", "true"),
    )
    ```
    (Keep it ≤6 LoC. This is a pure diagnostic — it tells us, on the LIVE deployed instance, whether the reranker survived init AND whether `asdict()` carries it into the query-path global_config. That is the exact A/B/C discriminator from the interfaces trace.)

    Then deploy + read the log (CHANNEL: Databricks CLI — executor runs directly per Principle #7, PowerShell to avoid Git Bash path breakage; redeploy reuses the current workspace artifact, no full SSG bake since this is a `kb/` python-source change only — CLAUDE.md Principle #9 sync-only-OK for kb/services|api):
    - Sync the changed kb/api.py to the workspace: `databricks sync . /Workspace/Users/hhu@edc.ca/omnigraph-kb --profile dev` (PowerShell; or the project's deploy.sh kb-sync step).
    - Redeploy: `databricks apps deploy omnigraph-kb --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy --profile dev`.
    - Fetch logs (use the project's `make logs` / tail_app_logs.py per MEMORY databricks_apps_logs_websocket — `databricks apps logs` does NOT exist in this CLI version). Grep the deploy/startup log for `rerank_diag` AND for `llm_rerank_init_ok` / `llm_rerank_init_disabled`.

    Record the `rerank_diag` line verbatim in SUMMARY — it decides Task 2's branch.
  </action>
  <verify>
    <automated>grep -n "rerank_diag" kb/api.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "rerank_diag" kb/api.py` shows the new diagnostic line.
    - The deployed startup log (captured via make logs / tail_app_logs.py) contains a `rerank_diag init_reranker_set=... rerank_disabled=... global_config_has_func=... enable_rerank_default=...` line, recorded verbatim in SUMMARY.
    - From that line the executor states in SUMMARY which root cause holds: (A) `init_reranker_set=False`/`rerank_disabled=True` (provider no-ops on Databricks) → disable-it branch; (B) `init_reranker_set=True` but `global_config_has_func=False` (asdict drops it) → wire-it branch; (C) both True but query still warns → deeper wire-it branch.
  </acceptance_criteria>
  <done>The deployed Databricks instance has emitted the rerank_diag line, the SUMMARY records it verbatim, and the A/B/C root cause is identified empirically (not guessed) — selecting Task 2's branch.</done>
</task>

<task type="auto">
  <name>Task 2: Apply the trace-selected reconcile — wire rerank through OR set enable_rerank=False — then redeploy and confirm the WARNING is gone</name>
  <files>kb/api.py (and, if Branch A requires it, kb/api_routers/search.py + kb/api_routers/synthesize.py QueryParam build sites)</files>
  <read_first>
    - kb/api.py (the lifespan() rerank section + the diagnostic from Task 1)
    - The Task 1 SUMMARY rerank_diag finding (which branch)
    - venv/Lib/site-packages/lightrag/utils.py (:2637-2645 + :2729) and base.py (:160) — to know exactly which knob silences the warning
    - kb/api_routers/search.py (:59,73 — `rerank_disabled` → `mode="mix" if not rerank_disabled else "hybrid"`); kb/api_routers/synthesize.py (:68 — passes rerank_disabled into kb_synthesize) — so the executor knows the downstream effect of flipping rerank_disabled
    - databricks-deploy/lib/llm_rerank.py + databricks-deploy/lightrag_databricks_rerank.py (if branch B/C requires fixing the provider import)
  </read_first>
  <action>
    Implement EXACTLY the branch the Task 1 trace proved — do NOT do both:

    **Branch A (provider no-ops on Databricks: `init_reranker_set=False`/`rerank_disabled=True`):** The reranker genuinely isn't available at runtime → the warning is misleading because rerank can't apply. Set `enable_rerank=False` so LightRAG stops warning. Concretely: in `kb/api.py:lifespan()`, when `rerank_ok` is False, set the LightRAG query default off. The cleanest knob is the env `RERANK_BY_DEFAULT` (base.py:160 reads it for the `QueryParam.enable_rerank` default) — but env must be set BEFORE LightRAG/QueryParam import-time evaluation, so prefer threading `enable_rerank=False` through the query-path QueryParam construction in the kb routers when `rerank_disabled` is True (the routers already select `mode="hybrid"` when disabled — verify whether `hybrid` mode still calls `apply_rerank_if_enabled` with `enable_rerank=True`; if so, also pass `enable_rerank=False` into those QueryParam builds). Keep it surgical (~10-30 LoC across kb/api.py + the 1-2 router QueryParam sites that build with enable_rerank). Add an inline comment citing #65 + the rerank_diag finding.

    **Branch B (asdict drops the func: `init_reranker_set=True` but `global_config_has_func=False`):** `rerank_model_func` is set on the instance but `asdict()` strips it. Fix: pass the rerank func via a path that survives into `global_config`. Verify against lightrag.py whether there is a setter / whether `asdict` truly drops callables (dataclasses.asdict should keep non-recursable values). If it genuinely drops it, the wire is to ensure the func is a module-level callable (not a closure that asdict deepcopy chokes on) — re-bind `make_rerank_func()`'s return to a top-level function reference. (~20-40 LoC.) Confirm via a re-run of the rerank_diag (Task 1 line) showing `global_config_has_func=True`.

    **Branch C (both True, still warns):** The func reaches global_config but a per-query QueryParam re-build (lightrag.py:2790 data_param) doesn't carry it — but global_config is rebuilt fresh, so this is unlikely; if it occurs, treat as Branch B wire. If truly unresolvable as a small fix, fall back to Branch A (disable) to drop the warning — document that rerank stays off pending a larger fix.

    Then redeploy (CHANNEL: Databricks CLI direct, PowerShell, sync-only OK — kb/ python source) and confirm: trigger ONE query (the simplest deployed endpoint that exercises kg retrieval — e.g. `/api/search?mode=kg` poll, or the Plan-04 research UAT will also cover it) and grep the backend log.
  </action>
  <verify>
    <automated>grep -nE "enable_rerank|#65" kb/api.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -nE "enable_rerank|#65|rerank" kb/api.py` shows the reconcile change with a comment referencing #65 and the trace branch.
    - The change is ONE branch only (not both): if Branch A, `grep -rn "enable_rerank=False" kb/ | wc -l` ≥ 1; if Branch B, the redeployed rerank_diag line shows `global_config_has_func=True`.
    - After redeploy + one query, the deployed backend log does NOT contain `Rerank is enabled but no rerank model is configured` (Branch A: gone because enable_rerank=False; Branch B: gone because rerank now applies → instead a `Successfully reranked: N chunks` INFO appears).
    - Branch B only: the log contains `Successfully reranked` on a query (proving rerank actually applied).
    - The diff is ≤40 LoC total (Principle #8 right-sizing) — recorded in SUMMARY.
  </acceptance_criteria>
  <done>The init-vs-query disagreement is reconciled per the empirical trace: the deployed log no longer emits the misleading "no rerank model is configured" WARNING — either because rerank now genuinely applies (Branch B: "Successfully reranked" appears) or because enable_rerank is honestly False (Branch A). #65 closed.</done>
</task>

</tasks>

<verification>
- `grep -n "rerank_diag" kb/api.py` (diagnostic present) and the reconcile change present with a #65 comment.
- Deployed backend log (via make logs / tail_app_logs.py): the rerank_diag line is captured; after the fix, `Rerank is enabled but no rerank model is configured` is ABSENT on queries.
- Branch B path additionally: `Successfully reranked: N chunks` present.
</verification>

<success_criteria>
- Root cause identified by trace (rerank_diag line), recorded in SUMMARY.
- Exactly one reconcile branch applied, ≤40 LoC.
- Deployed log: misleading rerank WARNING gone.
</success_criteria>

<output>
After completion, create `.planning/phases/arx-4-databricks-kg-retrieval/arx-4-databricks-kg-retrieval-02-SUMMARY.md` citing: the rerank_diag log line verbatim, the chosen branch + why, the kb/api.py diff (LoC count), and the before/after deployed-log WARNING excerpt.
</output>
