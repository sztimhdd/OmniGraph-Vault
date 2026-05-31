# Phase v1.1.P2-3-perf-fix-B: Aliyun Vertex Gemini Rerank Parity — Context

**Gathered:** 2026-05-31
**Status:** Ready for planning
**Source:** PRD Express Path (inherited from `v1.1.P2-3-perf-fix-A` PLAN.md `Out of scope` + ISSUES.md #22 — no separate discuss-phase needed; B is the parity follow-up A explicitly queued)

<domain>
## Phase Boundary

Add **Vertex Gemini batch JSON output** route to the LLM-as-reranker dispatcher shipped in `v1.1.P2-3-perf-fix-A`, and deploy + verify on **Aliyun ECS** so the Aliyun kb-api uses the same LLM-as-reranker pipeline as Databricks.

**Asymmetry today (post-A, pre-B):**

- Databricks Apps `kb-api`: `OMNIGRAPH_LLM_RERANK_PROVIDER=databricks_serving` → Haiku batch JSON rerank, mode='mix' default. SHIPPED in A.
- Aliyun ECS `kb-api`: `OMNIGRAPH_LLM_PROVIDER=deepseek`, `OMNIGRAPH_LLM_RERANK_PROVIDER` UNSET → dispatcher default `databricks_serving` → Databricks SDK init fails (no Databricks PAT on Aliyun) → graceful degrade to `app.state.rerank_disabled=True` → mode='hybrid' fallback (P5 baseline).

**B fixes the asymmetry.** After B ships:

- Aliyun ECS `kb-api`: `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini` → Vertex Gemini 2.5 Flash-Lite (or equivalent) batch JSON rerank, mode='mix' default. Same observable behavior + graceful-degrade contract as A.

**Files in scope:**

| File | Status | LoC est | Why |
|---|---|---|---|
| `lib/vertex_gemini_rerank.py` | NEW | +60 | Vertex batch JSON rerank helper (mirrors `databricks-deploy/lightrag_databricks_rerank.py` + reuses `lib/vertex_gemini_complete.py` client pattern). |
| `lib/llm_rerank.py` | MODIFY | +15 / -1 = +14 | Add `vertex_gemini` to `_VALID`; new `if provider == "vertex_gemini"` branch importing `lib.vertex_gemini_rerank.make_rerank_func`. |
| `kb/deploy/kb-api.service` | MODIFY | +3 | Add `Environment="OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini"`, `Environment="OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite"`, `Environment="OMNIGRAPH_LLM_RERANK_TOP_K=30"`, `Environment="OMNIGRAPH_LLM_RERANK_TIMEOUT=20"`. |
| `tests/unit/test_vertex_gemini_rerank_parse_scores.py` | NEW | +40 | Mirror of `tests/unit/test_llm_rerank_parse_scores.py` but for `lib/vertex_gemini_rerank._parse_scores` (or, if `_parse_scores` is shared/extracted, this collapses into one parametric test file). Pure-function tests, no Vertex creds needed. |
| `tests/integration/kb/test_p2_p3_llm_reranker.py` | EXTEND | +20 | Add `test_lifespan_vertex_rerank_loaded` (env-skip when Vertex SA absent) + `test_dispatcher_unknown_provider_raises`. |

**Total LoC est: +137 added / −1 removed = +136 net.** Larger than the +65 cited in ISSUES #22 (test split + dispatcher unit-test parity raised the floor); still well under arx-3-style scopes. plan-phase tier (multi-subsystem: lib/ helper + lib/ dispatcher + Aliyun deploy artifact + 2 test layers).

**OUT OF SCOPE for B (explicitly):**

- Re-running A's evaluation harness (`tests/eval/test_p2_p3_perf_quality.py`) on Aliyun. Aliyun has no Databricks creds and Vertex rerank quality should equal A's (LLM-as-judge property is provider-agnostic). Cite A's evaluation evidence in B's VERIFICATION.md.
- Touching kb/static or kb/templates (PRINCIPLE #9 sync-only deploy permissible — none of these files change).
- Trimming `sentence-transformers` + `torch` from requirements (filed as ISSUES #23, post-B cleanup).
- Hermes parity. Hermes is RO-frozen until 2026-06-22 (HC-7); Hermes uses cron not kb-api FastAPI service so the rerank wiring is not active there anyway.
- Adding new providers beyond `vertex_gemini` (e.g. OpenAI, Cohere). One provider per phase.

</domain>

<decisions>
## Implementation Decisions (LOCKED)

All decisions below are LOCKED — do NOT re-litigate during planning. They flow from A's PLAN.md "Out of scope" block + ROADMAP HC-1..HC-9 + ISSUES.md #22 + the existing dispatcher pattern in `lib/llm_complete.py`.

### Architecture & Pattern (mirrors A + lib/llm_complete.py)

- **Vertex helper module path:** `lib/vertex_gemini_rerank.py` (NOT under `databricks-deploy/`; lives alongside `lib/vertex_gemini_complete.py` since Aliyun is the consumer, not Databricks).
- **Helper public API:** `def make_rerank_func() -> Callable` returning the same async closure contract as A's `_haiku_batch_rerank`: `async def (query: str, documents: list[str], top_n: int | None = None) -> list[dict]` returning `[{"index": int, "relevance_score": float}, ...]`.
- **Dispatcher route:** `lib/llm_rerank.py` adds `_VALID = ("databricks_serving", "vertex_gemini", "disabled")` and a `if provider == "vertex_gemini":` branch that imports `from lib.vertex_gemini_rerank import make_rerank_func` and returns `(make_rerank_func(), True)`. Lazy-import inside the branch (mirrors `lib/llm_complete.py:50-51`). On import or factory exception → `(None, False)` graceful degrade (matches A's `databricks_serving` branch behavior).
- **Vertex client construction:** REUSE the same idiom as `lib/vertex_gemini_complete.py:_make_client` — `genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION)`. Do NOT introduce a new client construction path.
- **Vertex JSON output mechanism:** use `types.GenerateContentConfig(response_mime_type="application/json", response_schema=<schema>)` — Vertex Gemini's native JSON mode (analogous to Databricks' `temperature=0.0` + prompt-discipline approach in A). Schema:
  ```python
  {"type": "object", "properties": {"scores": {"type": "array", "items": {
      "type": "object", "properties": {"i": {"type": "integer"}, "s": {"type": "number"}},
      "required": ["i", "s"]}}}, "required": ["scores"]}
  ```
- **Parse function reuse:** `_parse_scores(raw, n_docs)` semantics MUST be byte-equivalent to A's `databricks-deploy/lightrag_databricks_rerank._parse_scores`. Two implementation options (PLANNER picks):
  - **Option a — Duplicate** the function in `lib/vertex_gemini_rerank.py` (~25 LoC). Trade: code duplication; isolation from A.
  - **Option b — Extract** `_parse_scores` into a shared module (`lib/_rerank_json_parse.py` or similar) and import from both A's helper and B's helper. Trade: touches A's file (+1 import + 0 logic change), eliminates duplication.
  - **PLANNER DEFAULT: option a** (Surgical Changes principle #3 — don't touch A's file; +25 LoC duplication is cheaper than the cross-file refactor + risk of touching shipped A code). Document this choice in PLAN.md SC table.

### Async-Safety (NO new lock — inherits P5 lock)

- Same as A: rerank closure runs inside `LightRAG.aquery()` → `apply_rerank_if_enabled` (utils.py:2701-2737), which is already wrapped in `app.state.lightrag_lock` (kg_synthesize.py:221-226). NO new lock introduced.
- `genai.Client.aio.models.generate_content(...)` is a native async method (no `loop.run_in_executor` bridge needed, unlike Databricks SDK). Avoid the `run_in_executor` pattern from A — use `await client.aio.models.generate_content(...)` directly.

### Timeout & Retry (mirrors A's behavior, adapts to Vertex SDK)

- Per-request timeout: `OMNIGRAPH_LLM_RERANK_TIMEOUT` (default 20s, same env var as A) wrapped via `asyncio.wait_for(...)`.
- On timeout / endpoint failure / parse failure: identical behavior to A — return `[{"index": i, "relevance_score": 0.0} for i in range(len(documents))]` (identity / no-op). Apply 1× retry with stricter prompt on parse failure.
- **NO 503 retry loop here.** The `_RETRY_BACKOFFS_SEC = (2, 4, 8)` pattern in `lib/vertex_gemini_complete.py` is for LLM completion (long, expensive, idempotent). Rerank is short + replaceable — graceful degrade beats retry. Keep parity with A: 1 retry on JSON parse, then identity. Vertex 503 → return identity (do NOT retry-loop; rerank-fail must NOT cascade-block the synthesize timeout budget).

### Aliyun Deploy (operator: agent SSHes Aliyun directly per `feedback_aim1_agent_is_operator`)

- Edit `kb/deploy/kb-api.service` reference template (committed to repo) — adds 4 `Environment=` lines.
- Aliyun apply: agent SSHes `aliyun-vitaclaw`, runs `git pull --ff-only`, `cp kb/deploy/kb-api.service /etc/systemd/system/`, `systemctl daemon-reload`, `systemctl restart kb-api.service`. Captures `journalctl -u kb-api.service -n 50 --no-pager` showing `llm_rerank_init_ok provider=vertex_gemini` exactly once per process.
- **Pre-flight check:** confirm `GOOGLE_APPLICATION_CREDENTIALS` (or `KB_KG_GCP_SA_KEY_PATH`) + `GOOGLE_CLOUD_PROJECT` already set on Aliyun (they are — Vertex embedding already runs there). If missing, B aborts and queues a separate ops phase.
- **Aliyun smoke test:** curl `/api/synthesize` with a known Chinese query; assert wall ≤ 65s, mode='mix' in response, source chips populated. Capture into `<phase>-VERIFICATION.md` per HC-8.
- **Aliyun OAuth pin:** `[[aliyun_oauth_pin]]` already in place — `oauth2.googleapis.com` + `us-central1-aiplatform` pinned in `/etc/hosts`. Vertex Gemini global endpoint requires the same OAuth refresh path; verify it works (do NOT modify /etc/hosts).

### Compat & Rollback

- Existing Aliyun behavior (`OMNIGRAPH_LLM_RERANK_PROVIDER` UNSET → graceful degrade) MUST remain functional. Adding `vertex_gemini` to `_VALID` does NOT change the default.
- Rollback path: comment out the 4 new `Environment=` lines in the systemd unit, daemon-reload, restart. kb-api boots with `OMNIGRAPH_LLM_RERANK_PROVIDER` unset → dispatcher default `databricks_serving` → Databricks SDK fails on Aliyun (no PAT) → graceful degrade to mode='hybrid' (current pre-B baseline). Verified by smoke.
- **Force-fail env still honored:** `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` short-circuits `_build_llm_rerank` regardless of provider (this is in `kb/api.py:59-62`, unchanged by B). Useful for SC#4 testing.

### Testing

- **Unit tests** (NEW `tests/unit/test_vertex_gemini_rerank_parse_scores.py` OR extend `tests/unit/test_llm_rerank_parse_scores.py` if `_parse_scores` is option-b extracted): six tests mirroring A — garbage, empty object, partial below threshold (None/retry), partial above threshold (sort), full descending, markdown-fence stripping. Pure-function, no Vertex creds.
- **Integration tests** (EXTEND `tests/integration/kb/test_p2_p3_llm_reranker.py`):
  1. `test_lifespan_vertex_rerank_loaded` — set env `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini`. CI without Vertex SA gracefully accepts either branch (mirrors A's CI graceful pattern). Skip with `pytest.importorskip("google.genai")` if SDK absent.
  2. `test_dispatcher_unknown_provider_raises` — set `OMNIGRAPH_LLM_RERANK_PROVIDER=cohere` (unknown). Assert `ValueError` listing `_VALID`.
- **Eval harness** SKIP — A's `tests/eval/test_p2_p3_perf_quality.py` evidence is sufficient (provider-agnostic LLM-as-judge property).

### Logging

- Lifespan log: `kb/api.py:71-74` already logs `llm_rerank_init_ok provider=%s wall_s=%.2f` reading `OMNIGRAPH_LLM_RERANK_PROVIDER` env. NO changes needed in `kb/api.py` — B's only repo touch is `lib/`, `tests/`, and `kb/deploy/kb-api.service`.

### Claude's Discretion (NOT pre-decided; PLANNER chooses)

- Exact Vertex Gemini model ID: `gemini-2.5-flash-lite` is the sane default (cost-effective + 1M context + JSON mode), but PLANNER may pick `gemini-2.5-flash` if cost vs. quality dictates. Document choice in PLAN.md.
- `_parse_scores` option a (duplicate) vs option b (extract). DEFAULT a; PLANNER may choose b with justification.
- Retry behavior on Vertex `ServerError code=503`: PLANNER may add a 1-retry-with-2s-backoff (mirrors `vertex_gemini_complete.py` shorter version), OR drop straight to identity-degrade. DEFAULT: identity-degrade (rerank is short and skippable; do not introduce wall-time variance into mode='mix' path).
- Test file naming: `test_vertex_gemini_rerank_parse_scores.py` separate vs. extending `test_llm_rerank_parse_scores.py`. PLANNER picks based on `_parse_scores` location decision.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### A's Phase Artifacts (reuse pattern)

- `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/PLAN.md` — defines `_parse_scores` semantics, dispatcher pattern, lifespan wiring, SC contract, force-fail compat. B mirrors these exactly.
- `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/RESEARCH.md` — N=131 chunk distribution evidence, 6 Pitfalls (Pitfall 4 — sync SDK in async; Pitfall 6 — JSON parse fragility). Vertex Gemini's native JSON mode is the answer to Pitfall 6.
- `databricks-deploy/lightrag_databricks_rerank.py` (committed in commit `6feb210`) — A's helper, full reference impl B mirrors.
- `lib/llm_rerank.py` (committed in commit `6feb210`) — A's dispatcher, B extends.
- `kb/api.py:50-95` (committed in commit `c257c64`) — A's lifespan wiring, UNCHANGED by B.

### Existing Vertex Gemini Code (reuse client pattern)

- `lib/vertex_gemini_complete.py` — canonical Vertex client construction (`_make_client`, `_require_project`), `genai.Client(vertexai=True, project=..., location=...)`. B's helper imports + reuses these helpers OR replicates them.
- `lib/lightrag_embedding.py` — also uses `genai.Client(vertexai=True, ...)`; cross-reference.
- `lib/llm_complete.py:50-51` — canonical lazy-import pattern for the dispatcher branch.

### Hard Constraints (from ROADMAP HC-1..HC-9)

- **HC-1** Never bypass LightRAG core asset. Rerank flows through LightRAG's `rerank_model_func` ctor kwarg + `apply_rerank_if_enabled` — DO NOT add a side-channel rerank path.
- **HC-3** `omonigraph` typo is canonical (path strings).
- **HC-4** LightRAG 1.4.15 stays (project memory `[[lightrag_pin_drift_115_vs_116]]` corrects ROADMAP HC-4 from 1.4.16). B does NOT upgrade LightRAG.
- **HC-6** Aliyun + Databricks deploy parity required. B closes the parity gap from A.
- **HC-7** Hermes RO until 2026-06-22 — B does NOT touch Hermes.
- **HC-8** KB Local UAT mandatory. B's PLAN.md MUST include a final task `checkpoint:human-verify` that runs `local_serve.py` + browser smoke + cites VERIFICATION.md (Principle #6).
- **HC-9** Right-Size — B is plan-phase tier (~+136 LoC, multi-subsystem); ceremony justified.

### Project-Specific Disciplines (from CLAUDE.md)

- **Principle #5** Don't outsource SSH to user — agent runs `ssh aliyun-vitaclaw "..."` directly.
- **Principle #6** Local UAT mandatory before phase complete.
- **Principle #7** Claude owns Databricks deployments — DOES NOT APPLY here (B is Aliyun-only). Aliyun ownership: agent SSHes directly per `[[feedback_aim1_agent_is_operator]]`.
- **Principle #8** Right-Size — applied above; plan-phase tier validated.
- **Principle #9** Touching `kb/static/` or `kb/templates/` requires full Makefile deploy — B does NOT touch these; sync-only deploy on Aliyun (it's a `git pull` + `systemctl restart` flow, no Makefile / SSG bake on Aliyun anyway).

### Project Memory (load-bearing for B)

- `[[vertex_ai_smoke_validated]]` — SA JSON + Vertex AI embedding validated 2026-04-30; non-obvious model name suffix finding. Cite when picking the model ID.
- `[[aliyun_oauth_pin]]` — `/etc/hosts` pin for Vertex token refresh on Aliyun. Pre-existing — verify still in place during deploy task.
- `[[aliyun_vitaclaw_ssh]]` — SSH alias `aliyun-vitaclaw` direct kb-api ops.
- `[[feedback_aim1_agent_is_operator]]` — for Aliyun-Ingest-Migration phases, agent SSHes Aliyun directly via Bash; "operator-channel" overridden.
- `[[lightrag_pin_drift_115_vs_116]]` — actual prod LightRAG = 1.4.15 (NOT 1.4.16 as ROADMAP HC-4 claims). B does not upgrade. P2-3 API verified compatible on 1.4.15.
- `[[claude_databricks_deployment_autonomous]]` — does NOT apply here (Aliyun, not Databricks). Cited only to clarify that A's deploy was autonomous; B's deploy is also autonomous but via SSH not databricks CLI.

</canonical_refs>

<specifics>
## Specific Ideas

### Vertex Gemini batch JSON output — concrete pattern

```python
from google.genai import types

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

config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=_RESPONSE_SCHEMA,
    temperature=0.0,
    max_output_tokens=2048,
    http_options=types.HttpOptions(timeout=int(_TIMEOUT * 1000)),
)
response = await asyncio.wait_for(
    client.aio.models.generate_content(
        model=_RERANK_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
        config=config,
    ),
    timeout=_TIMEOUT,
)
raw = response.text  # already valid JSON when schema is enforced
```

### Aliyun deploy task — concrete commands

```bash
# Agent runs from local Windows shell
ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && git fetch --quiet origin && git pull --ff-only origin main"
ssh aliyun-vitaclaw "diff /etc/systemd/system/kb-api.service /root/OmniGraph-Vault/kb/deploy/kb-api.service || true"
ssh aliyun-vitaclaw "cp /root/OmniGraph-Vault/kb/deploy/kb-api.service /etc/systemd/system/kb-api.service && systemctl daemon-reload && systemctl restart kb-api.service"
ssh aliyun-vitaclaw "journalctl -u kb-api.service -n 80 --no-pager | grep -E 'llm_rerank_init|lightrag_singleton'"
# Smoke: curl /api/synthesize through nginx → expect mode='mix', wall ≤ 65s
ssh aliyun-vitaclaw "curl -sS -X POST http://127.0.0.1:8766/api/synthesize -H 'Content-Type: application/json' -d '{\"query\":\"<known-zh-query>\",\"format\":\"long_form\"}' | head -200"
```

(Note: actual Aliyun WorkingDirectory is `/root/OmniGraph-Vault` per live `systemctl cat`; the `kb/deploy/kb-api.service` reference template uses `/home/kb/...` for portability. PLANNER must verify which is canonical and not introduce drift — the live unit is the source of truth.)

### Verification evidence required (HC-8)

- `journalctl` excerpt showing `llm_rerank_init_ok provider=vertex_gemini` exactly ONCE on start.
- curl `/api/synthesize` smoke result with `mode='mix'` in response + wall_s ≤ 65.
- pytest `tests/unit/test_vertex_gemini_rerank_parse_scores.py -v` 6/6 pass output.
- pytest `tests/integration/kb/test_p2_p3_llm_reranker.py -v` showing `test_lifespan_vertex_rerank_loaded` pass + new `test_dispatcher_unknown_provider_raises` pass.
- Local UAT (Principle #6): `local_serve.py` running with `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini` env, browser session showing /api/synthesize works, screenshot saved.

</specifics>

<deferred>
## Deferred Ideas

- **Trim `sentence-transformers` + `torch` from requirements** — ISSUES.md #23. Post-B cleanup; saves ~1.2 GB. Surgical Changes principle delays this until rollback option no longer needed (i.e. B verified stable for ≥1 week on Aliyun).
- **Cohere / OpenAI rerank providers** — out of v1.1 scope. New provider = new phase.
- **Vertex 503 retry loop** — PLANNER may consider but DEFAULT is identity-degrade. Add only if Aliyun smoke shows >5% Vertex 503 rate during smoke window (unlikely; embedding doesn't see this rate).
- **Cross-provider rerank A/B test** — switching between Haiku and Vertex on the SAME query set to compare quality. Not v1.1; future analytical work.
- **Hermes parity** — Hermes uses cron not kb-api so the rerank wiring is inactive there. Defer to post-2026-06-22 (Hermes RO unfreeze).

</deferred>

---

*Phase: P2-3-perf-fix-B*
*Context gathered: 2026-05-31 via PRD Express Path (inherited from A's PLAN.md Out-of-scope + ISSUES #22)*
