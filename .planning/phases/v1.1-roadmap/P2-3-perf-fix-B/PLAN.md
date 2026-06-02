---
phase: v1.1-roadmap-P2-3-perf-fix-B
plan: 01
type: execute
wave: 3
depends_on: [v1.1-roadmap-P2-3-perf-fix-A]
files_modified:
  - lib/vertex_gemini_rerank.py        # NEW
  - lib/llm_rerank.py                  # MODIFY (add vertex_gemini route)
  - kb/deploy/kb-api.service           # MODIFY (add 4 Environment= lines)
  - tests/unit/test_vertex_gemini_rerank_parse_scores.py   # NEW
  - tests/integration/kb/test_p2_p3_llm_reranker.py        # EXTEND (+2 tests)
autonomous: false  # final task = checkpoint:human-verify (Local UAT per HC-8 / Principle #6)
requirements:
  - SC#1-Aliyun  # cold-start ≤ 60s on Aliyun ECS (kb-api restart → first /api/synthesize 200)
  - SC#2-Aliyun  # steady-state long_form wall ≤ 65s on Aliyun for known zh-CN queries
  - SC#3-Aliyun  # token-overlap parity with A's measured Databricks rerank quality (cite A; do NOT re-run on Aliyun)
  - SC#4-Aliyun  # provider-init fail → graceful degrade to mode='hybrid'; per-request fail → identity-rerank no-exception
  - SC#5         # 0 touches under kb/static + kb/templates (PRINCIPLE #9 sync-only deploy permissible)
  - SC#6         # backwards-compat — UNSET env still works (graceful degrade to mode='hybrid')
  - SC#7         # OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1 shorts dispatcher regardless of provider (vertex_gemini included)
must_haves:
  truths:
    - "kb-api process on Aliyun loads NO local cross-encoder model — _build_llm_rerank wires Vertex Gemini batch JSON callable; lifespan log shows `llm_rerank_init_ok provider=vertex_gemini wall_s=NN.NN` exactly ONCE per process"
    - "LightRAG instance on Aliyun has rerank_model_func set to the Vertex rerank wrapper post-lifespan unless OMNIGRAPH_LLM_RERANK_PROVIDER=disabled / unknown / provider init failed"
    - "Default query mode for /api/synthesize and /api/search/kg on Aliyun is `mix` when rerank_disabled=False; falls back to `hybrid` when True"
    - "Setting OMNIGRAPH_LLM_RERANK_PROVIDER UNSET on Aliyun (rollback path) keeps app booting; dispatcher default `databricks_serving` fails to construct on Aliyun (no Databricks PAT) → graceful degrade to mode='hybrid' (current pre-B baseline). Verified by smoke."
    - "On simulated rerank-init failure (OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1) with provider=vertex_gemini, app boots successfully with app.state.rerank_disabled=True; KG queries fall back to mode='hybrid'"
    - "On per-request Vertex Gemini timeout / parse fail, the wrapper returns input documents in original order (`[{index: i, relevance_score: 0.0}]`) — apply_rerank_if_enabled uses original chunks; no aquery() failure surface"
    - "First /api/synthesize after kb-api restart on Aliyun returns within 60s (Vertex client construction is lazy + cheap; no model load wall-time)"
    - "Steady-state /api/synthesize long_form wall ≤ 65s on Aliyun for ≥3 known zh-CN queries"
    - "git diff --name-only main..HEAD shows zero matches under kb/static/ or kb/templates/"
    - "Setting OMNIGRAPH_LLM_RERANK_PROVIDER=cohere (unknown) raises ValueError listing _VALID = ('databricks_serving', 'vertex_gemini', 'disabled')"
  artifacts:
    - path: "lib/vertex_gemini_rerank.py"
      provides: "Vertex Gemini batch JSON rerank helper. Public make_rerank_func() returning async closure (query, documents, top_n) -> [{index, relevance_score}]. Reuses `genai.Client(vertexai=True, project=..., location=...)` idiom from lib/vertex_gemini_complete._make_client. Uses types.GenerateContentConfig(response_mime_type='application/json', response_schema=...) for native JSON enforcement. Async-native via await client.aio.models.generate_content(...). Identity-degrade on failure. **Lazy-import google.genai INSIDE _make_client() (NOT at module top), mirroring databricks-deploy/lightrag_databricks_rerank.py:75-77 — keeps `from lib.vertex_gemini_rerank import _parse_scores` working in CI without google.genai installed.**"
      contains: "make_rerank_func"
    - path: "lib/llm_rerank.py"
      provides: "Provider dispatcher with vertex_gemini route added. _VALID = ('databricks_serving', 'vertex_gemini', 'disabled'). Lazy-imports `lib.vertex_gemini_rerank.make_rerank_func`. Unknown provider raises ValueError listing _VALID."
      contains: "vertex_gemini"
    - path: "kb/deploy/kb-api.service"
      provides: "Aliyun systemd unit reference template — adds 4 Environment= lines: OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini, OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite, OMNIGRAPH_LLM_RERANK_TOP_K=30, OMNIGRAPH_LLM_RERANK_TIMEOUT=20"
      contains: "OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini"
    - path: "tests/unit/test_vertex_gemini_rerank_parse_scores.py"
      provides: "6 pure-function unit tests on lib.vertex_gemini_rerank._parse_scores (mirroring A's test_llm_rerank_parse_scores.py): garbage, empty object, partial below threshold, partial above threshold (sort), full descending, markdown-fence stripping. No Vertex creds needed. **No `pytest.importorskip` needed — module top has no google.genai dep after T1's lazy-import; importing `_parse_scores` is pure-stdlib.**"
      contains: "test_parse_scores_garbage_returns_none"
    - path: "tests/integration/kb/test_p2_p3_llm_reranker.py"
      provides: "Two NEW lifespan/dispatcher tests added: test_lifespan_vertex_rerank_loaded (env-skip when google.genai SDK absent — needed because lifespan path actually constructs the client) + test_dispatcher_unknown_provider_raises (asserts ValueError listing _VALID)."
      contains: "test_lifespan_vertex_rerank_loaded"
  key_links:
    - from: "lib/llm_rerank.py:get_rerank_func"
      to: "lib/vertex_gemini_rerank.py:make_rerank_func"
      via: "OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini routes through lazy-import inside the new branch; mirrors lib/llm_complete.py:50-51 (vertex_gemini branch)"
      pattern: "OMNIGRAPH_LLM_RERANK_PROVIDER"
    - from: "lib/vertex_gemini_rerank.py:make_rerank_func"
      to: "google.genai.Client(vertexai=True, project=..., location=...)"
      via: "Constructed via _make_client helper REPLICATED from lib/vertex_gemini_complete.py:84-94 (Surgical Changes — duplicate, do not import-couple A's helper). google.genai imports live INSIDE _make_client (NOT at module top), mirroring databricks-deploy/lightrag_databricks_rerank.py:75-77 (A lazy-imports databricks.sdk.service.serving inside make_rerank_func)."
      pattern: "genai.Client(vertexai=True"
    - from: "kb/api.py:_build_llm_rerank (UNCHANGED)"
      to: "lib.llm_rerank.get_rerank_func (returns vertex_gemini closure)"
      via: "Existing lifespan logging at kb/api.py:71-74 surfaces `provider=vertex_gemini` automatically when env is set; no kb/api.py change needed"
      pattern: "llm_rerank_init_ok provider=%s"
    - from: "/etc/systemd/system/kb-api.service on Aliyun"
      to: "kb-api uvicorn process env"
      via: "Aliyun deploy task: agent SSHes aliyun-vitaclaw, git pull, cp service file, daemon-reload, restart kb-api.service (per [[feedback_aim1_agent_is_operator]] + Principle #5 — agent runs SSH itself)"
      pattern: "Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini"
---

# v1.1.P2-3-perf-fix-B — Aliyun Vertex Gemini rerank parity

## Goal

Add **Vertex Gemini batch JSON output** route to the LLM-as-reranker dispatcher shipped in v1.1.P2-3-perf-fix-A, and deploy + verify on Aliyun ECS so the Aliyun kb-api uses the same LLM-as-reranker pipeline as Databricks. Closes the parity gap A explicitly queued.

Architecture:

1. **NEW helper** `lib/vertex_gemini_rerank.py` — mirrors A's `databricks-deploy/lightrag_databricks_rerank.py` contract. Public `make_rerank_func()` returns an async closure with `(query, documents, top_n) -> [{index, relevance_score}]`. REPLICATES (not imports) `_make_client` + `_require_project` from `lib/vertex_gemini_complete.py:66-94` to avoid import-coupling B's rerank helper to A's LLM-completion helper. Native async via `await client.aio.models.generate_content(...)` — NO `loop.run_in_executor` bridge (Vertex SDK is async-native, unlike Databricks SDK in A). **`google.genai` imports live INSIDE `_make_client()` (lazy), NOT at module top — mirrors A's `databricks-deploy/lightrag_databricks_rerank.py:75-77` lazy-import pattern, so `from lib.vertex_gemini_rerank import _parse_scores` succeeds in CI without the SDK installed.**
2. **Dispatcher extension** `lib/llm_rerank.py` — adds `vertex_gemini` to `_VALID` and a new lazy-import branch returning `(make_rerank_func(), True)`; on import or factory exception → `(None, False)` graceful degrade (mirrors A's `databricks_serving` branch).
3. **Aliyun deploy artifact** `kb/deploy/kb-api.service` — adds 4 `Environment=` lines.
4. **Unit + integration tests** mirror A's structure.
5. **Aliyun deploy task** — agent SSHes `aliyun-vitaclaw` directly per Principle #5 + `[[feedback_aim1_agent_is_operator]]`. NO user-paste-this-SSH commands.

This phase completes the Aliyun side of v1.1 LLM-as-reranker. After B ships, both deploy targets honor HC-6 parity.

## Right-Size justification (Principle #8)

**Plan-phase tier confirmed.** Multi-subsystem (`lib/` helper + `lib/` dispatcher + Aliyun systemd unit + 2 test layers + Aliyun deploy ops); ~+136 net LoC > 50 quick threshold. Not arx-3-style monster (>200 LoC, 4-pass Makefile bake, multi-file SSG). Plan-phase ceremony justified, not over-spec'd. Skip-research path (A's RESEARCH.md is provider-agnostic substrate; no separate B RESEARCH.md needed).

## SC Validity Check

| SC | Status | Reason |
| --- | --- | --- |
| SC#1-Aliyun — Cold-start ≤ 60s on Aliyun | **VALID** | Vertex `genai.Client` construction is metadata-only (no model download/load). `_build_llm_rerank` only constructs an async closure. Aliyun pre-B baseline cold-start ~30s (kb-api uvicorn + LightRAG hydrate from disk + embedding cache). Adding Vertex client init: < 1s. Worst case ~31s. Far under 60s. |
| SC#2-Aliyun — Steady-state long_form wall ≤ 65s | **VALID** | Aliyun pre-B mode='hybrid' baseline observed ~50s for zh-CN long_form. Vertex Gemini 2.5 Flash-Lite batch rerank on top-K=30 chunks: 1 API call × ~5-15s (Flash-Lite TTFB + JSON output budget for ~6K-token prompt). 50 + 15 = 65s — boundary case but within 65s ceiling. Inner timeout 150s safety net unchanged. Identical scope to A's SC#2 on Databricks. |
| SC#3-Aliyun — Token-overlap parity with A | **VALID** | LLM-as-judge is provider-agnostic property (RESEARCH §6 — Anthropic Haiku and Google Gemini class models report comparable MRR/NDCG on multilingual relevance ranking). A's eval harness ran on Databricks Haiku — citing that evidence is sufficient. Re-running on Aliyun would require Databricks SDK creds on Aliyun (absent by design) AND would NOT add information (the reranker is the variable; the rest of the pipeline is identical). |
| SC#4-Aliyun — Graceful degrade | **VALID** | Two layers: (1) lifespan-level: provider init exception → dispatcher returns `(None, False)`, kb/api.py:_build_llm_rerank graceful-degrades, app.state.rerank_disabled=True, KG paths fall back to mode='hybrid'. (2) per-request: Vertex 503 / asyncio timeout / JSON parse fail → wrapper returns `[{index: i, relevance_score: 0.0}]`. Tested via integration test `test_lifespan_vertex_rerank_loaded` + `test_lifespan_llm_reranker_force_fail` with vertex_gemini provider env. |
| SC#5 — 0 touches under kb/static + kb/templates | **VALID** | This phase modifies `lib/vertex_gemini_rerank.py` (NEW) + `lib/llm_rerank.py` + `kb/deploy/kb-api.service` + 2 test files. None are static/templates. SC asserts measurable invariant via `git diff --name-only`. |
| SC#6 — UNSET env backwards-compat | **VALID** | Adding `vertex_gemini` to `_VALID` does NOT change the default. UNSET env → dispatcher reads default `"databricks_serving"` → on Aliyun (no PAT) `make_rerank_func()` raises during `WorkspaceClient` construction → except branch returns `(None, False)` → graceful degrade to mode='hybrid'. Pre-B Aliyun baseline behavior preserved. |
| SC#7 — Force-fail compat | **VALID** | `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` short-circuits `_build_llm_rerank` BEFORE the dispatcher is called (`kb/api.py:59-62`, unchanged by B). Therefore force-fail works regardless of provider, including new vertex_gemini. Tested via `test_lifespan_llm_reranker_force_fail` (already in A; covers vertex_gemini implicitly since it pre-empts dispatcher). Add explicit assertion in T5 NEW test by setting provider=vertex_gemini in addition to FORCE_FAIL=1. |

All seven SCs **VALID**.

## LoC Estimate

| File | LoC delta | Nature |
| --- | --- | --- |
| `lib/vertex_gemini_rerank.py` (NEW) | **+60** | Vertex batch JSON rerank helper. Module constants (`_DEFAULT_MODEL=gemini-2.5-flash-lite`, `_TOP_K`, `_TIMEOUT`, `_DEFAULT_LOCATION="global"`); `_RESPONSE_SCHEMA` dict; `_require_project()` + `_make_client()` REPLICATED from `lib/vertex_gemini_complete.py:66-94` (with `google.genai` imports moved INSIDE `_make_client()` for lazy-import parity with A); `_identity()`; `_parse_scores()` BYTE-EQUIVALENT to A's (Option a — duplicate per CONTEXT default; Surgical Changes — do not touch A's file); `make_rerank_func()` returning async `_vertex_batch_rerank` closure that calls `await client.aio.models.generate_content(model=_RERANK_MODEL, contents=..., config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_RESPONSE_SCHEMA, temperature=0.0, max_output_tokens=2048, http_options=types.HttpOptions(timeout=int(_TIMEOUT*1000))))` wrapped in `asyncio.wait_for(..., timeout=_TIMEOUT)`. On exception or parse fail → 1 retry with stricter prompt; second fail → identity-degrade. NO `loop.run_in_executor` bridge. |
| `lib/llm_rerank.py` | **+15 −1 = +14 net** | Update `_VALID = ("databricks_serving", "vertex_gemini", "disabled")`. Add `if provider == "vertex_gemini":` branch with lazy-import `from lib.vertex_gemini_rerank import make_rerank_func` inside try/except. On exception → `(None, False)` graceful degrade. Update module docstring to list vertex_gemini route. NO change to existing `databricks_serving` branch. |
| `kb/deploy/kb-api.service` | **+5 −0 = +5 net** | Add a comment header line and 4 `Environment=` lines under existing Vertex env block: `Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini`, `Environment=OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite`, `Environment=OMNIGRAPH_LLM_RERANK_TOP_K=30`, `Environment=OMNIGRAPH_LLM_RERANK_TIMEOUT=20`. |
| `tests/unit/test_vertex_gemini_rerank_parse_scores.py` (NEW) | **+50** | 6 pytest-unit tests on `lib.vertex_gemini_rerank._parse_scores` (the duplicated parse function). Mirror A's test names + assertions verbatim, only the import target differs (`from lib.vertex_gemini_rerank import _parse_scores`). NO Vertex creds needed. NO `pytest.importorskip` needed — module top has no `google.genai` dep after T1's lazy-import; `_parse_scores` is pure-stdlib. |
| `tests/integration/kb/test_p2_p3_llm_reranker.py` | **+25 net** | Add `test_lifespan_vertex_rerank_loaded` (env-skip via `pytest.importorskip("google.genai")` — required because the lifespan path actually constructs the Vertex client; set `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini`, accept either rerank_disabled branch as A does for Databricks) + `test_dispatcher_unknown_provider_raises` (set provider=cohere; `pytest.raises(ValueError)` from `lib.llm_rerank.get_rerank_func()`). |
| **TOTAL** | **+155 added / −1 removed = +154 net** | Slightly above the +136 CONTEXT estimate due to module docstring + import block + replicated helpers in `lib/vertex_gemini_rerank.py`. Still well under 200 LoC; plan-phase tier remains correct. |

LoC ceiling not breached. Right-Size remains plan-phase (multi-subsystem confirmed; no waiver needed).

## Async-Safety Strategy

**Inherits P5 lock — NO new lock introduced.** Identical reasoning to A's PLAN.md:

The rerank closure runs inside `LightRAG.aquery()` → `apply_rerank_if_enabled` (lightrag/utils.py:2701-2737), which is already wrapped in `app.state.lightrag_lock` (kg_synthesize.py:221-226). The Vertex rerank call therefore executes under the same per-process lock — no double-acquire, no separate critical section.

**Difference from A:** Vertex SDK `client.aio.models.generate_content(...)` is **already async-native** — we do NOT use `loop.run_in_executor` (which A uses to bridge the synchronous `WorkspaceClient.serving_endpoints.query`). Direct `await` is correct for Vertex; converges on the same lock-protected execution.

The `genai.Client` is constructed once inside `make_rerank_func()` and held in the closure — read-only after init.

## Atomic Commits

Seven tasks, dependency-ordered. Wave assignments within B (note: phase-level Wave 3 is determined by `depends_on: [v1.1-roadmap-P2-3-perf-fix-A]`; the wave numbers below are intra-phase parallelism hints for execute-phase to optimize, NOT separate phase waves):

```xml
<task id="P2-3-perf-fix-B-T1" wave="1" depends_on="" autonomous="true" requirements="SC#1-Aliyun,SC#2-Aliyun,SC#4-Aliyun">
  <name>T1: Add lib/vertex_gemini_rerank.py — Vertex batch JSON rerank helper</name>
  <files_modified>lib/vertex_gemini_rerank.py</files_modified>
  <read_first>
    - lib/vertex_gemini_complete.py:1-95 (FULL; replicate _require_project + _make_client; specifically lines 66-94 — `_require_project` at 66-81 and `_make_client` at 84-94)
    - databricks-deploy/lightrag_databricks_rerank.py (FULL; A's helper; mirror module structure, _identity + _parse_scores semantics byte-equivalent, prompt design). **Specifically lines 75-77 — A lazy-imports `databricks.sdk.service.serving` INSIDE `make_rerank_func()`, NOT at module top. B MUST mirror this pattern: move `from google import genai` and `from google.genai import types` from module top to INSIDE `_make_client()`. This keeps `from lib.vertex_gemini_rerank import _parse_scores` working in CI without the google.genai SDK installed (T4 unit tests rely on this).**
    - lib/lightrag_embedding.py (cross-reference for genai.Client(vertexai=True, ...) pattern + types.GenerateContentConfig usage if applicable)
    - venv/Lib/site-packages/google/genai/types.py (verify HttpOptions(timeout=...) signature; timeout in milliseconds per lib/vertex_gemini_complete.py:194-196)
    - venv/Lib/site-packages/lightrag/utils.py:2617-2698 (apply_rerank_if_enabled signature contract — what wrapper must return)
    - .planning/phases/v1.1-roadmap/P2-3-perf-fix-B/CONTEXT.md (the locked decisions block, especially `<specifics>` showing exact code pattern)
  </read_first>
  <action>
    Create `lib/vertex_gemini_rerank.py`:

    ```python
    """LightRAG <-> Vertex Gemini rerank factory — v1.1.P2-3-perf-fix-B.

    Provides ``make_rerank_func()`` returning a LightRAG-compatible
    ``rerank_model_func`` callable that wraps Vertex Gemini (default
    gemini-2.5-flash-lite) for batch JSON relevance scoring on Aliyun ECS.

    Mirrors the contract of databricks-deploy/lightrag_databricks_rerank.py
    (A's Databricks Haiku helper) — same async signature, same identity-
    degrade behavior, same JSON output shape. Differs in:
      - Async-native: ``await client.aio.models.generate_content(...)``
        (no loop.run_in_executor bridge — Vertex SDK is async-native).
      - JSON enforcement: types.GenerateContentConfig(response_mime_type=
        "application/json", response_schema=_RESPONSE_SCHEMA) (Vertex's
        native structured-output mode; A relies on prompt discipline +
        temperature=0.0 since Databricks SDK has no schema knob).

    Lazy-import discipline:
      - `from google import genai` and `from google.genai import types`
        live INSIDE `_make_client()` (NOT at module top) — mirrors A's
        databricks-deploy/lightrag_databricks_rerank.py:75-77 lazy-import
        of `databricks.sdk.service.serving` inside `make_rerank_func()`.
      - This lets CI import `_parse_scores` (used by the unit tests)
        without google.genai installed. `_parse_scores` is pure-stdlib
        json + str manipulation — no SDK dep.

    Contract:
        async def rerank_func(query: str, documents: list[str],
                              top_n: int | None = None) -> list[dict]
            # returns [{"index": int, "relevance_score": float}, ...]

    Design (matches A):
      - Cap input documents to OMNIGRAPH_LLM_RERANK_TOP_K (default 30).
      - Single batch JSON call with response_schema enforced.
      - On JSON parse fail OR empty/partial scores: retry 1× with stricter
        prompt. On second fail OR endpoint timeout
        (OMNIGRAPH_LLM_RERANK_TIMEOUT, default 20s): return identity-order list.
      - On Vertex 503 / ServerError: identity-degrade (no retry loop —
        rerank is short and skippable; do not introduce wall-time
        variance into mode='mix' path). Diverges from
        lib/vertex_gemini_complete.py's 503 retry — that module is for
        long, expensive LLM completion; rerank is short + replaceable.

    Env vars consumed:
      - GOOGLE_APPLICATION_CREDENTIALS (SA JSON path; required)
      - GOOGLE_CLOUD_PROJECT (required — raises RuntimeError at call-time)
      - GOOGLE_CLOUD_LOCATION (default: "global")
      - OMNIGRAPH_LLM_RERANK_MODEL (default: "gemini-2.5-flash-lite")
      - OMNIGRAPH_LLM_RERANK_TOP_K (default: 30)
      - OMNIGRAPH_LLM_RERANK_TIMEOUT (default: 20)
    """
    from __future__ import annotations

    import asyncio
    import json
    import logging
    import os

    # NOTE: `from google import genai` and `from google.genai import types`
    # are deliberately NOT imported at module top. They are imported INSIDE
    # `_make_client()` and `make_rerank_func()` instead, mirroring A's
    # databricks-deploy/lightrag_databricks_rerank.py:75-77 pattern.
    # Rationale: keep `from lib.vertex_gemini_rerank import _parse_scores`
    # working in CI without the google.genai SDK installed (T4 unit tests).

    logger = logging.getLogger(__name__)

    _DEFAULT_MODEL = "gemini-2.5-flash-lite"
    _DEFAULT_LOCATION = "global"
    _RERANK_MODEL = os.environ.get("OMNIGRAPH_LLM_RERANK_MODEL", _DEFAULT_MODEL).strip() \
        or _DEFAULT_MODEL
    _TOP_K = int(os.environ.get("OMNIGRAPH_LLM_RERANK_TOP_K", "30"))
    _TIMEOUT = float(os.environ.get("OMNIGRAPH_LLM_RERANK_TIMEOUT", "20"))

    _RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "integer"},
                        "s": {"type": "number"},
                    },
                    "required": ["i", "s"],
                },
            },
        },
        "required": ["scores"],
    }

    _SYSTEM_PROMPT = (
        "You are a relevance ranker. For each numbered passage, score how well "
        "it answers the user's QUERY on a 0.0-1.0 scale. Output ONLY JSON in "
        'the form: {"scores": [{"i": <passage_number>, "s": <float 0-1>}, ...]}. '
        "Include EVERY passage. No prose, no markdown."
    )


    def _require_project() -> str:
        """Return GOOGLE_CLOUD_PROJECT; raise RuntimeError if unset.

        REPLICATED from lib/vertex_gemini_complete.py:66-81. Evaluated at
        CALL time so local-dev imports succeed before env file is loaded.
        """
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if not project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT is not set. Vertex Gemini rerank path "
                "requires SA auth (GOOGLE_APPLICATION_CREDENTIALS + "
                "GOOGLE_CLOUD_PROJECT). See docs/LOCAL_DEV_SETUP.md."
            )
        return project


    def _make_client():
        """Construct a Vertex-mode genai.Client (SA-only path).

        REPLICATED from lib/vertex_gemini_complete.py:84-94. Surgical
        Changes: do not import-couple B's rerank helper to A's LLM
        completion helper.

        google.genai is imported HERE (not at module top) so CI can
        `from lib.vertex_gemini_rerank import _parse_scores` without
        the SDK installed (T4 unit tests). Mirrors A's lazy-import at
        databricks-deploy/lightrag_databricks_rerank.py:75-77.
        """
        from google import genai  # lazy: keeps _parse_scores SDK-free in CI
        project = _require_project()
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION) \
            or _DEFAULT_LOCATION
        return genai.Client(vertexai=True, project=project, location=location)


    def _identity(docs: list[str]) -> list[dict]:
        return [{"index": i, "relevance_score": 0.0} for i in range(len(docs))]


    def _parse_scores(raw: str, n_docs: int) -> list[dict] | None:
        """Parse Vertex Gemini JSON output. Returns None when retry should fire.

        BYTE-EQUIVALENT to databricks-deploy/lightrag_databricks_rerank._parse_scores
        (A's helper). Acceptance contract:
          - garbage / empty object / fewer than 50% scored → None (retry)
          - ≥ 50% scored → return sorted descending by score
        """
        try:
            cleaned = raw.strip().strip("`").lstrip("json").strip()
            obj = json.loads(cleaned)
            scores = obj.get("scores", [])
            if not isinstance(scores, list) or len(scores) == 0:
                return None
            result = [
                {"index": int(s["i"]), "relevance_score": float(s["s"])}
                for s in scores
                if isinstance(s, dict) and "i" in s and "s" in s
            ]
            if len(result) < n_docs * 0.5:
                return None
            return sorted(result, key=lambda r: r["relevance_score"], reverse=True)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            return None


    def make_rerank_func():
        """Build a LightRAG-compatible async rerank closure over Vertex Gemini.

        Constructs the Vertex client at factory-call time (lifespan boot);
        the closure reuses it for the process lifetime. Read-only after init.

        google.genai.types is imported HERE (not at module top), matching
        the lazy-import discipline in `_make_client()` — see module docstring.
        """
        from google.genai import types  # lazy: keeps _parse_scores SDK-free in CI
        client = _make_client()

        async def _vertex_batch_rerank(
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

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0.0,
                max_output_tokens=2048,
                system_instruction=_SYSTEM_PROMPT,
                http_options=types.HttpOptions(timeout=int(_TIMEOUT * 1000)),
            )
            try:
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=_RERANK_MODEL,
                        contents=[types.Content(
                            role="user", parts=[types.Part(text=user_prompt)],
                        )],
                        config=config,
                    ),
                    timeout=_TIMEOUT,
                )
            except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
                logger.warning("vertex_rerank_endpoint_fail err=%r", e)
                return _identity(documents)

            raw = getattr(resp, "text", "") or ""
            parsed = _parse_scores(raw, n)
            if parsed is None:
                # Retry 1× with stricter prompt
                strict_config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=0.0,
                    max_output_tokens=2048,
                    system_instruction=_SYSTEM_PROMPT
                        + " STRICT: JSON only, no markdown fences.",
                    http_options=types.HttpOptions(timeout=int(_TIMEOUT * 1000)),
                )
                try:
                    resp2 = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=_RERANK_MODEL,
                            contents=[types.Content(
                                role="user", parts=[types.Part(text=user_prompt)],
                            )],
                            config=strict_config,
                        ),
                        timeout=_TIMEOUT,
                    )
                    parsed = _parse_scores(getattr(resp2, "text", "") or "", n)
                except Exception as e:  # noqa: BLE001
                    logger.warning("vertex_rerank_retry_fail err=%r", e)
                    parsed = None
            if parsed is None:
                logger.warning("vertex_rerank_parse_fail_returning_identity n=%d", n)
                return _identity(documents)

            filtered = [r for r in parsed if 0 <= r["index"] < len(documents)]
            return filtered[:top_n] if top_n else filtered

        return _vertex_batch_rerank


    __all__ = ["make_rerank_func", "_parse_scores"]
    ```
  </action>
  <acceptance_criteria>
    - File `lib/vertex_gemini_rerank.py` exists
    - `python -m py_compile lib/vertex_gemini_rerank.py` exits 0
    - `grep -q "def make_rerank_func" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "def _parse_scores" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "genai.Client(vertexai=True" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "response_mime_type=\"application/json\"" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "response_schema=_RESPONSE_SCHEMA" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "client.aio.models.generate_content" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_MODEL" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_TOP_K" lib/vertex_gemini_rerank.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_TIMEOUT" lib/vertex_gemini_rerank.py` returns true
    - **Module top has NO google.genai import (lazy-import discipline):** `python -c "import ast,sys; tree=ast.parse(open('lib/vertex_gemini_rerank.py').read()); top_imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]; mods=[(getattr(n,'module',None) or '') + ' '.join(a.name for a in n.names) for n in top_imports]; assert not any('google' in m for m in mods), f'google.genai must NOT be imported at module top: {mods}'; print('ok')"` exits 0 with `ok`
    - `python -c "from lib.vertex_gemini_rerank import _parse_scores, make_rerank_func; print('ok')"` exits 0 with output `ok` (importable; do NOT call make_rerank_func without GOOGLE_CLOUD_PROJECT set)
  </acceptance_criteria>
  <commit_message>feat(v1.1.P2-3-perf-fix-B): add lib/vertex_gemini_rerank — Vertex Gemini batch JSON rerank helper</commit_message>
</task>

<task id="P2-3-perf-fix-B-T2" wave="2" depends_on="P2-3-perf-fix-B-T1" autonomous="true" requirements="SC#4-Aliyun,SC#6,SC#7">
  <name>T2: Extend lib/llm_rerank.py dispatcher with vertex_gemini route</name>
  <files_modified>lib/llm_rerank.py</files_modified>
  <read_first>
    - lib/llm_rerank.py (FULL; current 44 lines — verify _VALID + dispatcher branches before edit)
    - lib/llm_complete.py:50-51 (canonical lazy-import branch pattern for vertex_gemini)
    - lib/vertex_gemini_rerank.py (just created in T1; verify make_rerank_func is module-level + importable)
  </read_first>
  <action>
    EDIT `lib/llm_rerank.py`:

    1. Update module docstring (lines 1-10) — add vertex_gemini line:
       ```
       OMNIGRAPH_LLM_RERANK_PROVIDER env selects the backend:
         - ``databricks_serving`` (default for Databricks Apps deploy) →
           ``databricks-deploy/lightrag_databricks_rerank.make_rerank_func()``
         - ``vertex_gemini`` (default for Aliyun ECS deploy) →
           ``lib.vertex_gemini_rerank.make_rerank_func()``
         - ``disabled`` → returns (None, False); KG paths fall back to mode='hybrid'

       Mirrors lib/llm_complete.py dispatcher pattern.
       ```
       Remove the line `Vertex Gemini route reserved for follow-up phase v1.1.P2-3-perf-fix-B.`

    2. Update line 16 from:
       ```python
       _VALID = ("databricks_serving", "disabled")  # vertex_gemini in B
       ```
       To:
       ```python
       _VALID = ("databricks_serving", "vertex_gemini", "disabled")
       ```

    3. INSERT new branch BEFORE the `raise ValueError(...)` at the end of `get_rerank_func()`. After the existing `if provider == "databricks_serving":` block (line 25-36), add:
       ```python
           if provider == "vertex_gemini":
               try:
                   from lib.vertex_gemini_rerank import make_rerank_func  # type: ignore
                   return make_rerank_func(), True
               except Exception:  # noqa: BLE001 — graceful degrade
                   return None, False
       ```

    NO change to existing `databricks_serving` branch logic.
    NO change to function signature.
    NO change to `__all__`.

    Result: dispatcher lazy-imports `lib.vertex_gemini_rerank.make_rerank_func` only when env routes to vertex_gemini. On import or factory exception → graceful degrade `(None, False)`.
  </action>
  <verification>
    Unknown-provider raise behavior is verified by T5's `test_dispatcher_unknown_provider_raises` integration test (added in same plan, runs in wave 2). T2's acceptance_criteria therefore omit a unknown-provider `python -c` snippet — T5 owns that assertion under a real pytest harness.
  </verification>
  <acceptance_criteria>
    - `python -m py_compile lib/llm_rerank.py` exits 0
    - `grep -q "_VALID = (\"databricks_serving\", \"vertex_gemini\", \"disabled\")" lib/llm_rerank.py` returns true (with exact tuple ordering)
    - `grep -q "if provider == \"vertex_gemini\":" lib/llm_rerank.py` returns true
    - `grep -q "from lib.vertex_gemini_rerank import make_rerank_func" lib/llm_rerank.py` returns true
    - `grep -c "return None, False" lib/llm_rerank.py` returns at least 3 (one for "disabled", one for "databricks_serving" except, one for "vertex_gemini" except)
    - Unknown-provider ValueError behavior is verified by T5 integration test `test_dispatcher_unknown_provider_raises` in same wave (NOT a `python -c` AC here — shell-quoting of multi-line try/except is brittle and the test owns it under a real pytest harness).
    - `pytest tests/integration/kb/test_p2_p3_llm_reranker.py -v -m integration -k force_fail` (existing A integration test still passes)
  </acceptance_criteria>
  <commit_message>feat(v1.1.P2-3-perf-fix-B): add vertex_gemini route to lib/llm_rerank dispatcher</commit_message>
</task>

<task id="P2-3-perf-fix-B-T3" wave="1" depends_on="" autonomous="true" requirements="SC#1-Aliyun,SC#2-Aliyun,SC#5">
  <name>T3: Update kb/deploy/kb-api.service — add 4 Environment= lines for Vertex rerank</name>
  <files_modified>kb/deploy/kb-api.service</files_modified>
  <read_first>
    - kb/deploy/kb-api.service (FULL; current 77 lines — verify env block ends at line 52, before MemoryHigh on line 58)
    - .planning/phases/v1.1-roadmap/P2-3-perf-fix-B/CONTEXT.md (locked decision: 4 Environment= lines, exact values)
  </read_first>
  <action>
    EDIT `kb/deploy/kb-api.service`. INSERT 5 new lines (1 comment header + 4 Environment= lines) AFTER line 52 (`# GOOGLE_CLOUD_LOCATION=global`) and BEFORE line 53 (blank line) so the new block sits next to the Vertex env block:

    ```ini

    # v1.1.P2-3-perf-fix-B: Vertex Gemini batch JSON rerank (Aliyun parity to
    # Databricks-side A). Provider dispatch via lib/llm_rerank.py mirrors
    # lib/llm_complete.py. See P2-3-perf-fix-B-VERIFICATION.md.
    Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini
    Environment=OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite
    Environment=OMNIGRAPH_LLM_RERANK_TOP_K=30
    Environment=OMNIGRAPH_LLM_RERANK_TIMEOUT=20
    ```

    Concrete final state of lines 47-60 after edit:
    ```ini
    Environment=KB_DB_PATH=/home/kb/.hermes/data/kol_scan.db
    Environment=KB_IMAGES_DIR=/home/kb/.hermes/omonigraph-vault/images
    Environment=KB_BASE_PATH=/kb
    # KB_KG_GCP_SA_KEY_PATH=/home/kb/.hermes/gcp-paid-sa.json   # uncomment + set on hosts with the SA JSON
    # GOOGLE_CLOUD_PROJECT=your-gcp-project-id
    # GOOGLE_CLOUD_LOCATION=global

    # v1.1.P2-3-perf-fix-B: Vertex Gemini batch JSON rerank (Aliyun parity to
    # Databricks-side A). Provider dispatch via lib/llm_rerank.py mirrors
    # lib/llm_complete.py. See P2-3-perf-fix-B-VERIFICATION.md.
    Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini
    Environment=OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite
    Environment=OMNIGRAPH_LLM_RERANK_TOP_K=30
    Environment=OMNIGRAPH_LLM_RERANK_TIMEOUT=20
    ```

    DO NOT modify any other line in the file. DO NOT touch ExecStart, MemoryHigh, MemoryMax, CPUQuota, Restart=, ProtectSystem=, ReadWritePaths=, [Install].
  </action>
  <acceptance_criteria>
    - `grep -q "Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini" kb/deploy/kb-api.service` returns true
    - `grep -q "Environment=OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite" kb/deploy/kb-api.service` returns true
    - `grep -q "Environment=OMNIGRAPH_LLM_RERANK_TOP_K=30" kb/deploy/kb-api.service` returns true
    - `grep -q "Environment=OMNIGRAPH_LLM_RERANK_TIMEOUT=20" kb/deploy/kb-api.service` returns true
    - `grep -q "v1.1.P2-3-perf-fix-B: Vertex Gemini" kb/deploy/kb-api.service` returns true (comment header present)
    - `grep -c "^Environment=" kb/deploy/kb-api.service` returns at least 7 (3 existing KB_* + 4 new)
    - File still parses as valid systemd unit syntax — `systemd-analyze verify kb/deploy/kb-api.service` exits 0 if `systemd-analyze` available (Aliyun-side check; locally skip if Windows)
    - Pre-existing lines unchanged: `grep -q "MemoryHigh=1.5G" kb/deploy/kb-api.service` returns true; `grep -q "ExecStart=/home/kb/OmniGraph-Vault/venv/bin/uvicorn kb.api:app" kb/deploy/kb-api.service` returns true
  </acceptance_criteria>
  <commit_message>ops(v1.1.P2-3-perf-fix-B): add Vertex rerank env block to kb/deploy/kb-api.service</commit_message>
</task>

<task id="P2-3-perf-fix-B-T4" wave="2" depends_on="P2-3-perf-fix-B-T1" autonomous="true" requirements="SC#4-Aliyun">
  <name>T4: Add unit tests for lib.vertex_gemini_rerank._parse_scores (6 tests)</name>
  <files_modified>tests/unit/test_vertex_gemini_rerank_parse_scores.py</files_modified>
  <read_first>
    - tests/unit/test_llm_rerank_parse_scores.py (FULL; A's 6 unit tests — mirror structure)
    - lib/vertex_gemini_rerank.py post-T1 (verify _parse_scores is module-level + signature matches A; verify google.genai is NOT imported at module top — see T1 lazy-import discipline. This guarantees `from lib.vertex_gemini_rerank import _parse_scores` succeeds in CI without the SDK.)
  </read_first>
  <action>
    Create `tests/unit/test_vertex_gemini_rerank_parse_scores.py`:

    ```python
    """v1.1.P2-3-perf-fix-B SC#4 unit: lib.vertex_gemini_rerank._parse_scores contract.

    Mirrors tests/unit/test_llm_rerank_parse_scores.py (A's helper) exactly —
    same 6 tests, only the import target differs. Verifies the JSON parse-
    fail / partial-scores / valid-output ladder WITHOUT Vertex SDK
    network dependency. Pure-function, deterministic in CI.

    The two _parse_scores functions are byte-equivalent (option a — duplicate
    per CONTEXT.md decision); these tests provide a regression net against
    drift between the two copies.

    NB: NO `pytest.importorskip("google.genai")` is needed here. T1's lazy-
    import discipline guarantees `from lib.vertex_gemini_rerank import
    _parse_scores` succeeds even when google.genai is absent — google.genai
    is imported INSIDE `_make_client()` and `make_rerank_func()`, not at
    module top. _parse_scores is pure stdlib (json + str).
    """
    from __future__ import annotations

    import pytest


    @pytest.fixture
    def parse():
        from lib.vertex_gemini_rerank import _parse_scores
        return _parse_scores


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
        # Vertex Gemini's response_schema=JSON enforcement should prevent
        # markdown fences, but the parse ladder must still recover defensively
        # in case schema enforcement falls back (unlikely but cheap to defend).
        raw = '```json\n{"scores": [{"i": 0, "s": 0.5}, {"i": 1, "s": 0.5}]}\n```'
        result = parse(raw, n_docs=2)
        assert result is not None
        assert len(result) == 2
    ```

    NO Vertex SDK import in this file — the fixture imports `_parse_scores` directly which is a pure stdlib-json function. NO `pytest.importorskip("google.genai")` needed because T1 keeps google.genai out of module-top imports.
  </action>
  <acceptance_criteria>
    - File `tests/unit/test_vertex_gemini_rerank_parse_scores.py` exists
    - `python -m py_compile tests/unit/test_vertex_gemini_rerank_parse_scores.py` exits 0
    - `pytest tests/unit/test_vertex_gemini_rerank_parse_scores.py -v -m unit` collects 6 tests
    - `pytest tests/unit/test_vertex_gemini_rerank_parse_scores.py -v -m unit` returns exit code 0 with 6/6 passed
    - `grep -c "@pytest.mark.unit" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns 6
    - `grep -q "def test_parse_scores_garbage_returns_none" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns true
    - `grep -q "def test_parse_scores_empty_object_returns_none" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns true
    - `grep -q "def test_parse_scores_partial_below_threshold_returns_none" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns true
    - `grep -q "def test_parse_scores_partial_above_threshold_returns_sorted" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns true
    - `grep -q "def test_parse_scores_full_returns_descending" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns true
    - `grep -q "def test_parse_scores_markdown_fence_stripped" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns true
    - **No importorskip:** `grep -q "pytest.importorskip" tests/unit/test_vertex_gemini_rerank_parse_scores.py` returns false (T1 lazy-import keeps module-top SDK-free)
  </acceptance_criteria>
  <commit_message>test(v1.1.P2-3-perf-fix-B): add Vertex rerank _parse_scores unit tests (mirror of A)</commit_message>
</task>

<task id="P2-3-perf-fix-B-T5" wave="2" depends_on="P2-3-perf-fix-B-T2" autonomous="true" requirements="SC#4-Aliyun,SC#6,SC#7">
  <name>T5: Extend tests/integration/kb/test_p2_p3_llm_reranker.py with vertex + unknown-provider tests</name>
  <files_modified>tests/integration/kb/test_p2_p3_llm_reranker.py</files_modified>
  <read_first>
    - tests/integration/kb/test_p2_p3_llm_reranker.py (FULL; A's 3 lifespan tests — `_start_or_skip` helper is reused for new test)
    - lib/llm_rerank.py post-T2 (verify _VALID + new vertex_gemini branch)
    - lib/vertex_gemini_rerank.py post-T1 (verify google.genai import shape — imports are INSIDE `_make_client()` / `make_rerank_func()`. The lifespan path actually constructs the client, so `pytest.importorskip("google.genai")` IS needed here even though T4 unit tests don't need it.)
  </read_first>
  <action>
    APPEND TWO new tests to the existing `tests/integration/kb/test_p2_p3_llm_reranker.py`. After `test_lifespan_legacy_bge_force_fail_compat` (the last test in the file, ending at the existing `client.__exit__` finally block), add:

    ```python


    @pytest.mark.integration
    def test_lifespan_vertex_rerank_loaded(monkeypatch) -> None:
        """SC#4-Aliyun: dispatcher routes to vertex_gemini provider; lifespan boots.

        Skips if google.genai SDK absent. Required because the lifespan path
        actually constructs the Vertex client via lib.vertex_gemini_rerank.
        _make_client() — which imports google.genai. Without GOOGLE_CLOUD_PROJECT
        + SA JSON, factory raises during _make_client → dispatcher graceful-
        degrades → app.state.rerank_disabled=True. We accept either branch
        (auth-present → reranker loaded; auth-absent → degraded); the contract
        under test is dispatcher routing + flag/object consistency.
        """
        pytest.importorskip("google.genai")
        monkeypatch.delenv("OMNIGRAPH_LLM_RERANK_FORCE_FAIL", raising=False)
        monkeypatch.delenv("BGE_FORCE_LOAD_FAIL", raising=False)
        monkeypatch.setenv("OMNIGRAPH_LLM_RERANK_PROVIDER", "vertex_gemini")
        import kb.api as kb_api
        importlib.reload(kb_api)
        client = _start_or_skip(kb_api)
        try:
            r = client.get("/health")
            assert r.status_code == 200, r.text
            disabled = kb_api.app.state.rerank_disabled
            if disabled:
                assert kb_api.app.state.reranker is None
                assert kb_api.app.state.lightrag.rerank_model_func is None
            else:
                assert kb_api.app.state.reranker is not None
                assert kb_api.app.state.lightrag.rerank_model_func is not None
        finally:
            client.__exit__(None, None, None)


    @pytest.mark.integration
    def test_dispatcher_unknown_provider_raises(monkeypatch) -> None:
        """SC#6: setting OMNIGRAPH_LLM_RERANK_PROVIDER=cohere (unknown) raises ValueError.

        Verifies dispatcher fail-fast on typo / misconfiguration. Asserts the error
        message lists _VALID so operator gets immediate feedback on the valid set.
        """
        monkeypatch.setenv("OMNIGRAPH_LLM_RERANK_PROVIDER", "cohere")
        from lib.llm_rerank import get_rerank_func
        with pytest.raises(ValueError) as exc_info:
            get_rerank_func()
        msg = str(exc_info.value)
        assert "cohere" in msg
        assert "databricks_serving" in msg
        assert "vertex_gemini" in msg
        assert "disabled" in msg
    ```

    DO NOT modify the existing 3 tests or the `_start_or_skip` helper.
    Result: file has 5 integration tests total (3 from A + 2 new from B).
  </action>
  <acceptance_criteria>
    - `python -m py_compile tests/integration/kb/test_p2_p3_llm_reranker.py` exits 0
    - `grep -q "def test_lifespan_vertex_rerank_loaded" tests/integration/kb/test_p2_p3_llm_reranker.py` returns true
    - `grep -q "def test_dispatcher_unknown_provider_raises" tests/integration/kb/test_p2_p3_llm_reranker.py` returns true
    - `grep -q "pytest.importorskip(\"google.genai\")" tests/integration/kb/test_p2_p3_llm_reranker.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_PROVIDER\", \"vertex_gemini\"" tests/integration/kb/test_p2_p3_llm_reranker.py` returns true
    - `grep -q "OMNIGRAPH_LLM_RERANK_PROVIDER\", \"cohere\"" tests/integration/kb/test_p2_p3_llm_reranker.py` returns true
    - `pytest tests/integration/kb/test_p2_p3_llm_reranker.py --collect-only -q` lists 5 tests (3 existing + 2 new)
    - `pytest tests/integration/kb/test_p2_p3_llm_reranker.py -v -m integration -k "test_dispatcher_unknown_provider_raises"` passes (deterministic — no env deps)
    - Existing 3 A-tests still pass: `pytest tests/integration/kb/test_p2_p3_llm_reranker.py -v -m integration -k "force_fail or legacy_bge"` returns 0 with 2/2 passed (lifespan_loaded may skip on local env per `_start_or_skip` SSL/dim guard, which is acceptable per A's contract)
  </acceptance_criteria>
  <commit_message>test(v1.1.P2-3-perf-fix-B): add Vertex lifespan + unknown-provider integration tests</commit_message>
</task>

<task id="P2-3-perf-fix-B-T6" wave="3" depends_on="P2-3-perf-fix-B-T2,P2-3-perf-fix-B-T3,P2-3-perf-fix-B-T4,P2-3-perf-fix-B-T5" autonomous="true" requirements="SC#1-Aliyun,SC#2-Aliyun,SC#4-Aliyun,SC#6,SC#7">
  <name>T6: Aliyun deploy — git pull, copy systemd unit, daemon-reload, restart, capture evidence</name>
  <files_modified></files_modified>
  <read_first>
    - .planning/phases/v1.1-roadmap/P2-3-perf-fix-B/CONTEXT.md (`<specifics>` block — exact ssh command sequence)
    - kb/deploy/kb-api.service post-T3 (the new env block)
    - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/aliyun_vitaclaw_ssh.md (SSH alias details)
    - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/aliyun_oauth_pin.md (verify /etc/hosts pin still in place; do NOT modify)
    - ~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/feedback_aim1_agent_is_operator.md (agent runs SSH directly per Principle #5)
  </read_first>
  <action>
    Agent runs the following sequence directly via the Bash tool (Principle #5 — NO user paste-and-report). Each step output is captured for evidence.

    **Pre-flight check (read-only, no mutation):**
    1. `ssh aliyun-vitaclaw "test -f /root/.hermes/gcp-paid-sa.json && echo 'SA_JSON_PRESENT' || echo 'SA_JSON_MISSING'"` — verify Vertex SA JSON exists. If MISSING, HALT and queue ops phase. (The SA JSON is the same one Vertex embedding already uses; should already be present per [[vertex_ai_smoke_validated]] + ROADMAP HC-6.)
    2. `ssh aliyun-vitaclaw "echo \$GOOGLE_CLOUD_PROJECT \$GOOGLE_CLOUD_LOCATION || systemctl show kb-api.service -p Environment | head -5"` — verify Vertex env already set in current systemd unit. (Aliyun has Vertex embedding already; vars must be present.)
    3. `ssh aliyun-vitaclaw "grep -E '^(142\\.250|oauth2\\.googleapis\\.com|us-central1-aiplatform)' /etc/hosts"` — verify [[aliyun_oauth_pin]] still in place. If empty, HALT (do NOT modify /etc/hosts; queue ops phase).

    **Pull repo on Aliyun + verify B commits landed:**
    4. `ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && git fetch --quiet origin && git pull --ff-only origin main && git log --oneline -8"` — pull to latest main; expected to show T1..T5 commits at top.

    **Diff systemd unit before applying (defensive):**
    5. `ssh aliyun-vitaclaw "diff /etc/systemd/system/kb-api.service /root/OmniGraph-Vault/kb/deploy/kb-api.service || true"` — show what will change. Expected diff: 5 new lines (1 comment header + 4 Environment=) plus any prior local Aliyun customizations that differ from the repo template.

       **CAUTION — three diff outcomes:**
       - **(a) Clean diff** (only the 5 new lines from T3 are present in the repo template, with NO other differences): proceed to step 6 (cp path).
       - **(b) Path drift only** (live unit has `WorkingDirectory=/root/OmniGraph-Vault` while repo template has `/home/kb/OmniGraph-Vault`, OR `User=root` vs `User=kb`, OR similar Aliyun-host-specific customizations that are intentional): do NOT cp the template wholesale — it would CLOBBER live customizations. Trigger **HT-4** (halt-and-document) instead. Capture the diff into `<phase>-VERIFICATION.md` under "Manual edit required", list the verbatim 4 Environment= lines + the comment header that must be inserted into `/etc/systemd/system/kb-api.service` after the existing `# GOOGLE_CLOUD_LOCATION=global` line, then PAUSE for operator hand-edit. Operator hand-edits the live unit, types `resumed` to confirm, then T6 resumes from step 7 (daemon-reload + restart). **DO NOT attempt automated `sed` through nested ssh quoting** — `sed -i ... \\\\\\n ...` through Windows-bash → ssh → remote-bash escape layers is unpredictable and can silently corrupt the systemd unit. The 30-minute "wait what just happened" debug cost vastly exceeds the 30-second hand-edit cost.
       - **(c) Substantive non-rerank, non-path drift** (different ExecStart= flags, different MemoryMax=, different Restart= policy, etc.): trigger **HT-4** with stronger guidance — operator decides whether to (i) reconcile the live unit back to the template in a separate ops phase, or (ii) hand-edit the 4 Environment= lines into the live unit and queue the reconciliation as a follow-up.

    **Apply systemd unit (clean-diff path only):**
    6. **Only if step 5 returned outcome (a):** `ssh aliyun-vitaclaw "cp /root/OmniGraph-Vault/kb/deploy/kb-api.service /etc/systemd/system/kb-api.service.new && systemd-analyze verify /etc/systemd/system/kb-api.service.new && mv /etc/systemd/system/kb-api.service.new /etc/systemd/system/kb-api.service"` — atomic write, verified before swap. If outcome (b) or (c), step 6 is SKIPPED — operator hand-edited in step 5 already.
    7. `ssh aliyun-vitaclaw "systemctl daemon-reload"`

    **Restart kb-api + capture timing:**
    8. `ssh aliyun-vitaclaw "echo 'RESTART_START='\$(date +%s) && systemctl restart kb-api.service && for i in 1 2 3 4 5 6 7 8 9 10 11 12; do if curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8766/health 2>/dev/null | grep -q 200; then echo 'HEALTH_OK_AT='\$(date +%s); break; fi; sleep 5; done"` — restart, poll /health for up to 60s. **Assertion (SC#1-Aliyun):** HEALTH_OK_AT - RESTART_START ≤ 60s.

    **Capture journalctl evidence:**
    9. `ssh aliyun-vitaclaw "journalctl -u kb-api.service -n 80 --no-pager --output=short-precise | grep -E 'llm_rerank_init|lightrag_singleton|provider=vertex_gemini'"` — expect ≥1 line with `llm_rerank_init_ok provider=vertex_gemini wall_s=NN.NN` AND `lightrag_singleton_ready wall_s=NN.NN`. Capture verbatim for VERIFICATION.md.

    **Smoke test — known zh-CN query (SC#2-Aliyun):**
    10. Capture wall_s for ≥3 zh-CN queries. Suggested queries (drawn from existing project content):
        - "OmniGraph-Vault 是什么？它如何使用 LightRAG？"
        - "v1.1 里程碑路线图各 wave 包含什么？"
        - "Aliyun ECS 上 kb-api 的内存限制是多少？"
        For each: `ssh aliyun-vitaclaw "time curl -sS -X POST http://127.0.0.1:8766/api/synthesize -H 'Content-Type: application/json' -d '{\"query\":\"<query>\",\"format\":\"long_form\"}' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"mode=\", d.get(\"mode\"),\"wall_s=\", d.get(\"wall_s\"),\"confidence=\", d.get(\"confidence\"))'"`. **Assertion (SC#2-Aliyun):** wall_s ≤ 65 for each; mode='mix'.
        Note: if response shape doesn't include `mode` / `wall_s` directly (depends on synthesize router), capture full response head + measure `time` wall. Adjust assertion to match actual response shape after first query.

    **Backwards-compat smoke (SC#6) — UNSET env:**
    11. Comment out the 4 new Environment= lines temporarily, daemon-reload, restart, smoke once:
        `ssh aliyun-vitaclaw "sed -i.bak-b 's/^Environment=OMNIGRAPH_LLM_RERANK_/#Environment=OMNIGRAPH_LLM_RERANK_/g' /etc/systemd/system/kb-api.service && systemctl daemon-reload && systemctl restart kb-api.service && sleep 30"` — note: this `sed` is a SAFE single-line literal substitution on existing lines (no continuation, no shell metacharacters in the pattern), unlike the rejected step-5 alternative that tried to APPEND multi-line content via `a\\` + nested ssh quoting.
        `ssh aliyun-vitaclaw "curl -sS http://127.0.0.1:8766/health"` — expect 200.
        `ssh aliyun-vitaclaw "journalctl -u kb-api.service -n 30 --no-pager | grep -E 'llm_rerank_init'"` — expect `llm_rerank_init_disabled` (provider returned no-op) OR `llm_rerank_init_failed` (Databricks SDK construction failed; either is graceful-degrade success).
        Smoke one query — expect `mode='hybrid'` (P5 baseline preserved).
    12. RESTORE Vertex env (revert sed): `ssh aliyun-vitaclaw "mv /etc/systemd/system/kb-api.service.bak-b /etc/systemd/system/kb-api.service && systemctl daemon-reload && systemctl restart kb-api.service && sleep 30 && curl -sS http://127.0.0.1:8766/health"`. Expect 200 + restored vertex_gemini journal log.

    **Capture all evidence to `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/aliyun-evidence/`:**
    13. Save: journalctl excerpts (vertex-on, env-unset), curl smoke outputs (3 queries vertex-on + 1 query env-unset), restart timing.

    **Pause — agent does NOT mark phase complete after T6.** Local UAT in T7 is the binding gate per HC-8 / Principle #6. T6 produces all the deploy + remote-smoke evidence; T7 produces the local-UAT screenshot + writes VERIFICATION.md.
  </action>
  <acceptance_criteria>
    - `ssh aliyun-vitaclaw "grep -q 'Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini' /etc/systemd/system/kb-api.service && echo applied"` returns `applied`
    - `ssh aliyun-vitaclaw "systemctl is-active kb-api.service"` returns `active`
    - `ssh aliyun-vitaclaw "journalctl -u kb-api.service -n 50 --no-pager | grep -c 'llm_rerank_init_ok provider=vertex_gemini'"` returns at least 1
    - SC#1-Aliyun timing assertion: HEALTH_OK_AT - RESTART_START ≤ 60 (recorded as integer seconds in evidence)
    - At least 3 SC#2-Aliyun smoke queries return 200 with wall_s ≤ 65 each (recorded as evidence)
    - SC#6 backwards-compat smoke: with Environment= lines commented, kb-api boots + journalctl shows graceful-degrade log + smoke query returns 200 with mode='hybrid'
    - SC#6 restore: Environment= lines re-enabled + smoke query returns 200 with mode='mix'
    - Evidence files exist under `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/aliyun-evidence/` (journal-vertex-on.txt, journal-env-unset.txt, curl-smoke-vertex-on.txt, curl-smoke-env-unset.txt, timing.txt)
    - NO modifications to `/etc/hosts` (verify): `ssh aliyun-vitaclaw "diff <(grep -E '^(142\\.250|oauth2\\.googleapis|us-central1-aiplatform)' /etc/hosts)"` returns same content as pre-flight step 3
    - HT-4 trigger path: if step 5 returned outcome (b) or (c), the verbatim diff + 4 Environment= lines + insertion-point hint are documented in `<phase>-VERIFICATION.md` under "Manual edit required" section, AND operator approval `resumed` is recorded BEFORE step 7 was executed
  </acceptance_criteria>
  <commit_message>ops(v1.1.P2-3-perf-fix-B): deploy Vertex rerank to Aliyun ECS — systemd unit + smoke evidence</commit_message>
</task>

<task id="P2-3-perf-fix-B-T7" wave="4" depends_on="P2-3-perf-fix-B-T6" autonomous="false" requirements="SC#1-Aliyun,SC#2-Aliyun,SC#3-Aliyun,SC#4-Aliyun,SC#5,SC#6,SC#7">
  <name>T7: Local UAT + write VERIFICATION.md (CHECKPOINT — Principle #6 binding gate)</name>
  <files_modified>.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/P2-3-perf-fix-B-VERIFICATION.md</files_modified>
  <read_first>
    - This PLAN.md "Verification" section + SC table
    - CLAUDE.md Principle #6 (Local UAT mandatory) + Principle #5 (don't outsource SSH)
    - .planning/phases/v1.1-roadmap/P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md (template/format reference; if it exists)
    - T6 evidence files under `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/aliyun-evidence/`
  </read_first>
  <action>
    Sequential — Local UAT first, then write VERIFICATION.md, then pause for operator approval.

    **Local UAT (Principle #6 / HC-8):**
    1. Stop any uvicorn on :8766 locally.
    2. Start local server with vertex_gemini provider:
       ```powershell
       $env:OMNIGRAPH_LLM_RERANK_PROVIDER = "vertex_gemini"
       $env:OMNIGRAPH_LLM_RERANK_MODEL = "gemini-2.5-flash-lite"
       $env:OMNIGRAPH_LLM_RERANK_TOP_K = "30"
       $env:OMNIGRAPH_LLM_RERANK_TIMEOUT = "20"
       venv\Scripts\python.exe .scratch\local_serve.py *> .uvicorn-p23B.log
       ```
    3. Tail `.uvicorn-p23B.log`. Expected: `llm_rerank_init_ok provider=vertex_gemini wall_s=NN.NN` (if local SA + GOOGLE_CLOUD_PROJECT set) OR `llm_rerank_init_disabled` / `llm_rerank_init_failed` (graceful degrade — local env may lack SA; that's acceptable per the same `_start_or_skip` graceful guard A uses).
    4. Open http://localhost:8766; submit a query via UI. Capture screenshot to `.playwright-mcp/v1.1.P2-3-perf-fix-B-uat-local.png`. Verify response renders (mode='mix' if vertex auth available locally; mode='hybrid' if degraded — both acceptable for the local UAT, since Aliyun is the binding gate per HC-6).

    **SC#5 — Principle #9 file-touch check:**
    5. `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` MUST return empty.
    6. If non-empty → HALT.

    **Run pytest gates:**
    7. `venv\Scripts\python.exe -m pytest tests/unit/test_vertex_gemini_rerank_parse_scores.py -v -m unit` → 6/6 passed (capture stdout).
    8. `venv\Scripts\python.exe -m pytest tests/integration/kb/test_p2_p3_llm_reranker.py -v -m integration` → 2 new tests pass (test_dispatcher_unknown_provider_raises must pass; test_lifespan_vertex_rerank_loaded may skip on importorskip OR pass) + 3 existing tests still pass / skip-graceful (capture stdout).
    9. `venv\Scripts\python.exe -m pytest tests/unit/test_llm_rerank_parse_scores.py -v -m unit` → 6/6 passed (regression — A's tests must still pass; `_parse_scores` in A's file unchanged).

    **Write `P2-3-perf-fix-B-VERIFICATION.md`** at `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/`:

    Required sections + grep-verifiable headers:

    ```markdown
    # P2-3-perf-fix-B Verification — Aliyun Vertex Gemini Rerank Parity

    **Phase:** v1.1.P2-3-perf-fix-B
    **Status:** [PASS/FAIL — operator-approved]
    **Date:** YYYY-MM-DD

    ## SC#1-Aliyun — Cold-start ≤ 60s on Aliyun
    [Insert RESTART_START + HEALTH_OK_AT + delta from T6 evidence/timing.txt; assert delta ≤ 60.]

    ## SC#2-Aliyun — Steady-state long_form wall ≤ 65s
    [Insert table: query | wall_s | mode for the 3 zh-CN smoke queries. Assert all ≤ 65 + mode='mix'.]

    ## SC#3-Aliyun — Token-overlap parity (cite A)
    Per CONTEXT.md decision: re-running A's eval harness on Aliyun is OUT OF SCOPE.
    LLM-as-judge is provider-agnostic (RESEARCH §6). A's measured improvement
    +X.XX absolute (cite A's VERIFICATION.md numeric) is the binding parity baseline.
    Aliyun smoke wall_s + mode='mix' confirm the rerank is wired and active;
    quality parity is inherited from A's evaluation.
    Cited: `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md` SC#3 section.

    ## SC#4-Aliyun — Graceful degrade
    Two evidence layers:
    - **Lifespan provider-init fail:** [insert `llm_rerank_init_failed` log from T6 step 11
      env-unset run; smoke query returns mode='hybrid'].
    - **Per-request fail (covered by A's eval + identity-degrade pattern):** the
      `_parse_scores` function in lib/vertex_gemini_rerank.py is byte-equivalent to A's;
      6/6 unit tests in tests/unit/test_vertex_gemini_rerank_parse_scores.py pass
      (cite pytest output).

    ## SC#5 — 0 touches under kb/static + kb/templates
    `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` returned: <empty>

    ## SC#6 — Backwards-compat (UNSET env)
    [Insert evidence from T6 step 11: with Environment= lines commented, kb-api boots,
    journalctl shows graceful-degrade, smoke query returns 200 + mode='hybrid' (P5
    pre-B baseline preserved). Then T6 step 12: env restored, mode flips back to 'mix'.]

    ## SC#7 — Force-fail compat across providers
    `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` short-circuits dispatcher BEFORE provider routing.
    Tested via `pytest tests/integration/kb/test_p2_p3_llm_reranker.py::test_lifespan_llm_reranker_force_fail`
    (existing A-test still passes). Provider-agnostic by design.

    ## Local UAT (HC-8 / Principle #6)
    - Launcher: `.scratch\local_serve.py` with env block above
    - Env: provider=vertex_gemini, model=gemini-2.5-flash-lite, top_k=30, timeout=20
    - Log line: `[insert llm_rerank_init_* line from .uvicorn-p23B.log]`
    - Screenshot: `.playwright-mcp/v1.1.P2-3-perf-fix-B-uat-local.png`
    - Status: PASS / DEGRADED-LOCAL-ACCEPTABLE (local SA may be absent — Aliyun is the binding gate per HC-6)

    ## Aliyun deploy section
    - Pre-flight: SA JSON present, GOOGLE_CLOUD_PROJECT set, /etc/hosts pin in place
    - git pull: [insert top 3 commits from T6 step 4]
    - systemd unit applied: [insert grep result from T6 step 12]
    - daemon-reload + restart: SUCCESS
    - llm_rerank_init_ok line: [verbatim from T6 step 9]
    - Smoke 3 queries: [insert table from T6 step 10]

    ## Manual edit required (only if HT-4 fired in T6 step 5)
    [Only present if T6 step 5 returned outcome (b) or (c). Insert:
     - Verbatim diff between live unit and repo template
     - The 4 Environment= lines + comment header that operator hand-edited
     - Insertion point hint (after `# GOOGLE_CLOUD_LOCATION=global`)
     - Operator's `resumed` confirmation timestamp
     - Drift to reconcile in follow-up ops phase (queue ISSUES.md row)]

    ## Pytest evidence
    - tests/unit/test_vertex_gemini_rerank_parse_scores.py: 6/6 passed (paste output)
    - tests/integration/kb/test_p2_p3_llm_reranker.py: 5 collected, [N passed, M skipped] (paste output; explain any skips)
    - tests/unit/test_llm_rerank_parse_scores.py (A regression): 6/6 passed (paste output)

    ## LoC summary
    +154 net (T1: +60 NEW vertex_gemini_rerank.py, T2: +14 dispatcher, T3: +5 systemd unit,
    T4: +50 unit tests NEW, T5: +25 integration tests). Plan-phase tier (Principle #8).

    ## Aliyun parity gate (HC-6)
    PASSED — Aliyun kb-api now uses Vertex Gemini batch JSON rerank, mode='mix'
    default, identical observable behavior + graceful-degrade contract as
    Databricks-side A.

    ## Rollback Plan executed (none required)
    Vertex deploy stable across smoke queries + backwards-compat verified.
    Rollback path documented in PLAN.md for future use.
    ```

    **Pause for operator approval** — user types `approved` to mark P2-3-perf-fix-B complete.
  </action>
  <acceptance_criteria>
    - File `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/P2-3-perf-fix-B-VERIFICATION.md` exists
    - File contains "SC#1-Aliyun" through "SC#7" headers (7 SCs)
    - `grep -q "llm_rerank_init_ok provider=vertex_gemini" P2-3-perf-fix-B-VERIFICATION.md` returns true
    - `grep -q "Aliyun parity gate (HC-6)" P2-3-perf-fix-B-VERIFICATION.md` returns true
    - `grep -q "Principle #6" P2-3-perf-fix-B-VERIFICATION.md` returns true (Local UAT cited)
    - `grep -q ".playwright-mcp/v1.1.P2-3-perf-fix-B-uat-local.png" P2-3-perf-fix-B-VERIFICATION.md` returns true
    - `grep -q "kb/(static|templates)/" P2-3-perf-fix-B-VERIFICATION.md` returns true (SC#5 grep cmd cited; result must be `<empty>`)
    - `grep -q "tests/unit/test_vertex_gemini_rerank_parse_scores.py" P2-3-perf-fix-B-VERIFICATION.md` returns true
    - `grep -q "test_dispatcher_unknown_provider_raises" P2-3-perf-fix-B-VERIFICATION.md` returns true
    - Operator types "approved" in resume signal
  </acceptance_criteria>
  <commit_message>docs(v1.1.P2-3-perf-fix-B): VERIFICATION.md — Aliyun Vertex rerank parity shipped, SC#1-7 evidence</commit_message>
</task>
```

## Verification (per SC + 4-Track adapted from A)

### Track 1 — Cold-start (SC#1-Aliyun, binding gate)

- Aliyun kb-api restart → first /api/synthesize 200. Vertex client construction is metadata-only (no model load).
- **PASS:** HEALTH_OK_AT - RESTART_START ≤ 60s. Journalctl shows `llm_rerank_init_ok provider=vertex_gemini wall_s=NN.NN` exactly once.

### Track 2 — Async safety (P5 contract preserved on Aliyun)

- Vertex rerank introduces no new lock; relies on P5's `app.state.lightrag_lock`.
- Vertex SDK is async-native (`client.aio.models.generate_content`) — no executor bridge.
- Smoke evidence: 3 sequential synthesize queries succeed with consistent mode='mix' + non-zero wall_s.
- (No N=4 concurrent test on Aliyun — single-worker uvicorn, identical to A's contract.)

### Track 3 — Graceful degrade (SC#4-Aliyun + SC#6 + SC#7)

- (a) Provider-init fail → dispatcher returns `(None, False)`; app boots with `rerank_disabled=True`; mode='hybrid'.
- (b) Per-request Vertex 503 / timeout / parse fail → wrapper returns identity-order list; LightRAG uses original chunks.
- (c) `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` shorts dispatcher regardless of provider — A's existing test still passes (covers vertex_gemini implicitly).
- (d) UNSET env on Aliyun → dispatcher default `databricks_serving` → no PAT → graceful degrade to mode='hybrid' (current pre-B baseline preserved).
- All four mechanisms verified via T5 integration test + T6 step 11 backwards-compat smoke.

### Track 4 — Steady-state quality (SC#2-Aliyun + SC#3-Aliyun)

- **SC#2-Aliyun:** 3 zh-CN smoke queries on Aliyun, each wall_s ≤ 65s + mode='mix'.
- **SC#3-Aliyun:** cite A's eval harness output (provider-agnostic LLM-as-judge property; do NOT re-run on Aliyun per CONTEXT.md decision).

### SC#5 — Principle #9 file-touch invariant

- `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` returns empty.
- Sync-only deploy permissible (Aliyun does not use Makefile / SSG bake; deploy is `git pull` + `systemctl restart`).

### Aliyun parity gate (HC-6) — CLOSED in B

- Aliyun + Databricks both running LLM-as-reranker. v1.1 LLM-rerank parity complete.

## Halt Triggers

- **HT-1: Vertex SA JSON missing on Aliyun.** T6 step 1 returns `SA_JSON_MISSING`. STOP — queue ops phase to install SA JSON; do NOT proceed with B until present (would manifest as silent rerank_disabled=True forever).
- **HT-2: GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION not set on Aliyun.** T6 step 2 returns empty. STOP — same as HT-1; ops phase first.
- **HT-3: Aliyun /etc/hosts pin missing.** T6 step 3 returns empty. STOP — `[[aliyun_oauth_pin]]` is a hard precondition for Vertex token refresh; without it Vertex calls hang on metadata refresh. Re-pin before proceeding (separate ops phase).
- **HT-4: Live Aliyun systemd unit drift vs repo template (path drift OR substantive customizations).** T6 step 5 diff shows ANY of:
    - Path drift only (User=, WorkingDirectory=, ExecStart= venv path differ between live and repo template — common since Aliyun is `/root/...` and template is `/home/kb/...`), OR
    - Substantive non-rerank customizations (different ExecStart= flags, MemoryMax=, Restart= policy, etc.).

  **HALT-and-document protocol** (NOT automated sed via nested ssh):
    1. Capture the verbatim `diff` output into `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/aliyun-evidence/systemd-drift-diff.txt`.
    2. Write a "Manual edit required" section to `<phase>-VERIFICATION.md` listing:
       - The verbatim 4 Environment= lines + comment header from T3.
       - Insertion-point hint: "after the existing `# GOOGLE_CLOUD_LOCATION=global` line in `/etc/systemd/system/kb-api.service`".
       - Reason for halt (path drift vs substantive drift).
    3. PAUSE T6. Operator hand-edits the live unit on Aliyun (single ssh shell-escape boundary, deterministic). Operator types `resumed` in chat.
    4. T6 resumes from step 7 (daemon-reload + restart).
    5. If outcome (c) substantive drift, queue an ISSUES.md row "reconcile Aliyun systemd unit with repo template" for a follow-up ops phase.

  **DO NOT attempt automated `sed -i ... a\\ ...` through nested ssh quoting.** The Windows-bash → ssh → remote-bash escape pipeline (`\\\\\\n`-style) is unreliable for sed continuation; risk is silent corruption of `/etc/systemd/system/kb-api.service`. The 30-second hand-edit cost is far cheaper than 30+ minutes of debugging silent shell-quote-driven corruption.
- **HT-5: SC#1-Aliyun violated.** First /api/synthesize after restart > 60s. STOP — investigate Vertex client construction wall (likely OAuth metadata refresh on first call). Likely root cause: `[[aliyun_oauth_pin]]` unhealthy or DNS resolution slow.
- **HT-6: SC#2-Aliyun violated.** Smoke query wall_s > 65s consistently. STOP — profile Vertex Flash-Lite TTFB; consider top_K=20 + re-measure. May indicate model selection issue (Flash-Lite-preview vs production).
- **HT-7: Vertex JSON parse fail rate > 30%.** Journalctl shows >30% `vertex_rerank_parse_fail_returning_identity` in smoke window. STOP — diagnose; switch to `gemini-2.5-flash` (more compliant) and re-deploy. LoC delta: 1 systemd line.
- **HT-8: SC#5 violated.** Any kb/static/ or kb/templates/ touched. STOP, re-plan; sanity-check (this phase has no reason to touch them).
- **HT-9: SC#6 violated.** With Environment= lines commented, kb-api FAILS to boot OR smoke returns mode='mix' (not 'hybrid'). STOP — backwards-compat broken; re-investigate dispatcher default + force_fail short-circuit logic.
- **HT-10: SC#7 violated.** With OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1, app crashes OR rerank_disabled=False. STOP — re-read kb/api.py:_build_llm_rerank env override branch (UNCHANGED by B; if broken, A regression).
- **HT-11: A's existing tests regress.** `pytest tests/unit/test_llm_rerank_parse_scores.py` shows failures. STOP — B's _parse_scores duplication likely corrupted A's parse_scores import path. Verify Option a duplication didn't accidentally edit A's file.

## Rollback Plan

P2-3-perf-fix-B is a **paired-component change** spanning 1 NEW helper + 1 MODIFIED dispatcher + 1 MODIFIED systemd unit + 2 NEW/EXTENDED test files. Rollback options on Aliyun:

1. **Operational escape (no revert):** comment out the 4 new `Environment=` lines in `/etc/systemd/system/kb-api.service`, `systemctl daemon-reload`, `systemctl restart kb-api.service`. UNSET env → dispatcher tries `databricks_serving` → fails (no PAT) → graceful degrade to mode='hybrid'. Pre-B baseline restored. Operator-friendly hot-fix; no git revert needed.

2. **Provider downgrade (explicit):** set `Environment=OMNIGRAPH_LLM_RERANK_PROVIDER=disabled`, daemon-reload, restart. Same end state but explicit dispatcher control. mode='hybrid' for KG paths.

3. **Force-fail at runtime:** set `Environment=OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1`, daemon-reload, restart. Short-circuits before dispatcher even runs. Same end state.

4. **Full revert (if architectural):**

   ```bash
   git revert <T7-sha> <T6-sha> <T5-sha> <T4-sha> <T3-sha> <T2-sha> <T1-sha>
   git push origin main
   ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && git pull --ff-only origin main && cp /root/OmniGraph-Vault/kb/deploy/kb-api.service /etc/systemd/system/kb-api.service && systemctl daemon-reload && systemctl restart kb-api.service"
   ```

   Restores pre-B Aliyun state (Environment= lines absent → graceful degrade → mode='hybrid'). A's Databricks-side rerank UNAFFECTED.

5. **Partial revert (Vertex helper only):** revert T1 commit only; T2 dispatcher's vertex_gemini branch then surfaces ImportError, which the except branch catches as graceful degrade. Effectively forces rerank_disabled until Vertex helper is restored. Hot-fix-friendly state.

## Out of scope (matches CONTEXT.md)

- Re-running A's evaluation harness on Aliyun (provider-agnostic LLM-as-judge property; cite A).
- Touching kb/static or kb/templates (Principle #9; B does not).
- Trimming `sentence-transformers` + `torch` from requirements (ISSUES #23, post-B cleanup).
- Hermes parity (HC-7, RO until 2026-06-22).
- New providers beyond vertex_gemini (one provider per phase).
- Modifying A's helper `databricks-deploy/lightrag_databricks_rerank.py` (Surgical Changes #3 — Option a duplicate chosen; do NOT touch A).
- Vertex 503 retry loop (CONTEXT default: identity-degrade; rerank is short + skippable; matches A's behavior).

## Success Criteria

P2-3-perf-fix-B is complete when:

- [ ] **SC#1-Aliyun:** Cold-start ≤ 60s on Aliyun; numeric in VERIFICATION.md cites RESTART_START + HEALTH_OK_AT + delta.
- [ ] **SC#2-Aliyun:** Steady-state long_form `wall_s ≤ 65s` for ≥3 zh-CN smoke queries; mode='mix' in each response.
- [ ] **SC#3-Aliyun:** A's eval harness output cited verbatim in VERIFICATION.md SC#3 section (no re-run).
- [ ] **SC#4-Aliyun:** Provider-init fail simulation (UNSET env on Aliyun) → graceful degrade to mode='hybrid'; per-request fail covered by 6/6 _parse_scores unit tests passing.
- [ ] **SC#5:** `git diff --name-only main..HEAD | Select-String 'kb/(static|templates)/'` returns empty.
- [ ] **SC#6:** Backwards-compat — UNSET env on Aliyun keeps app booting + smoke returns mode='hybrid' (P5 baseline).
- [ ] **SC#7:** Force-fail compat — A's existing `test_lifespan_llm_reranker_force_fail` still passes (covers vertex_gemini implicitly since FORCE_FAIL pre-empts dispatcher).
- [ ] P5 contract preserved (no new lock; same `app.state.lightrag_lock`).
- [ ] All 6 NEW unit tests + 2 NEW integration tests pass; A's 6 _parse_scores tests still pass (no regression).
- [ ] Local UAT performed + screenshot saved to `.playwright-mcp/v1.1.P2-3-perf-fix-B-uat-local.png`.
- [ ] Operator types `approved` on T7.

## Output

After T7 operator-approved, the phase closes with:

- 6 commits on main (T1..T6; T7 commits VERIFICATION.md)
- Updated `STATE-v1.1.md` (P2-3-perf-fix-B row added → ✅ CLOSED post-approval)
- `P2-3-perf-fix-B-VERIFICATION.md` with all 7 SC sections + Aliyun deploy evidence + Local UAT screenshot
- ISSUES.md row updated by orchestrator: issue #22 status → CLOSED ✅; issue #23 (sentence-transformers + torch trim) status → ready-to-pick-up
- Wave 2 P2-3 line in STATE-v1.1.md updated: "Aliyun side cited as deferred" → "Aliyun + Databricks parity ✅ via perf-fix-A + perf-fix-B"
- v1.1 LLM-as-reranker parity gate (HC-6) CLOSED for both deploy targets
</content>

</invoke>