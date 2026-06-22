# Phase arx-2-finish: Deep Research usable in KB UI (Aliyun + Databricks) — Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Source:** Command PRD brief (`/gsd:plan-phase` args) + 2026-06-12 4-dimension audit (workflow `w1ppw59o1`)
**Milestone:** Agentic-RAG-v1.1 (suffix-named track — `*-Agentic-RAG-v1.1.md`)

> **Note for orchestrator/agents:** This is a suffix-named milestone track. The
> canonical planning files are `.planning/{PROJECT,ROADMAP,STATE,REQUIREMENTS}-Agentic-RAG-v1.1.md`,
> NOT the bare `.planning/ROADMAP.md`. `gsd-tools init` cannot resolve this phase
> (ISSUE #54, memory `feedback_parallel_track_gates_manual_run`). Orchestration is manual.

<domain>
## Phase Boundary

**What this phase delivers:** Turn the *shipped-but-unusable* `/api/research` SSE
endpoint (commit 38a7286, 2026-05-25) into a REAL user-facing Deep Research
feature on BOTH the Aliyun-hosted KB and the Databricks-hosted KB.

**Phase goal (success criterion):** A KB user on BOTH environments can: open a
Deep Research page → submit a query → watch the 5-stage pipeline progress live →
receive a REAL LLM-synthesized, cited, image-embedded markdown report. Proven by
a real end-to-end run on EACH environment (NOT mocked tests) per CLAUDE.md
Principle #6.

**Relationship to ROADMAP arx-2-http:** ROADMAP's `arx-2-http` shipped the SSE
endpoint + 5-stage orchestrator (the transport layer). This `arx-2-finish` phase
closes the gaps between "endpoint responds" and "user has a usable feature":
real LLM synthesis (not a template stub), a frontend UI, and real E2E proof on
both serving targets.

### ALREADY DONE — DO NOT REBUILD (verified 2026-06-12)

- POST /api/research SSE endpoint + wire protocol (5 named stage frames +
  terminal done/error) — `kb/api_routers/research.py`, committed 38a7286.
- Orchestrator + all 5 stages run — `lib/research/orchestrator.py` + `lib/research/stages/*`.
- LLM wiring (`cfg.llm_complete`) + standalone CLI (`python -m lib.research`) — built.
- Retriever uses the SAME `omnigraph_search.query.search(mode=hybrid)` as the
  working /api/synthesize — so wherever /api/synthesize retrieves, research retrieves.
- Image embedding (caption-anchored, capped 5) + sources aggregation in
  synthesizer output — real (the path exists; it's the LLM prose that's stubbed).
- Router committed (38a7286) + Databricks inherits it via `from kb.api import app`
  in app_entry.py. Both envs expose the endpoint at the app level.
- ~179 stubbed tests green (transport/event-shaping only — they do NOT prove
  real LLM+KG).

### NON-ISSUE — explicitly OUT of scope (do NOT chase)

- **Dim-mismatch / reindex:** runtime app embeds 3072 unconditionally on both
  envs; the 1024 provider is offline-reindex-job-only, never imported by the
  running app. NO REINDEX in scope. The `.scratch/arx-2-curl-sse-260525.log` 1024
  failure was a LOCAL `.dev-runtime` store — ignore it. (This was "GAP C" in the
  audit; it is a confirmed non-issue.)
- **LLM language-detection:** the CJK-ratio heuristic in `synthesizer._detect_language`
  works; do NOT replace with an LLM call (deferred).
- **Inline-citation feature beyond [n] threading:** the milestone dropped a
  separate inline-citation feature; this phase threads `[n]` source indices into
  prose as part of synthesis, which is in scope.

</domain>

<decisions>
## Implementation Decisions (LOCKED — from command brief)

### GAP A — Real LLM synthesis (BACKEND, ~40-80 LoC, single file)

`lib/research/stages/synthesizer.py` `run()` receives `cfg` (holds
`cfg.llm_complete`) but IGNORES it for synthesis — line 108 returns
`state.retrieved.chunks[0].snippet` verbatim under a hardcoded heading (line 99
comment "real LLM synthesis lands in ar-2"). Must:

1. Build a synthesis prompt from: query + ALL chunks (not just chunks[0]) +
   reasoner findings + verifier citations.
2. Await the **PLAIN-TEXT** provider, NOT the json-adapter-wrapped `cfg.llm_complete`.
   - **CONFIRMED RISK SHAPE** (see `config.py:50-59`): `cfg.llm_complete` =
     `make_json_decision_adapter(underlying_llm)` — a `(prompt, tools) -> _DecisionPayload`
     JSON-mode adapter for the Reasoner/Verifier tool-calling loops. The plain
     `(prompt) -> str` provider is `lib.llm_complete.get_llm_func()`'s return
     (`underlying_llm`), which `ResearchConfig` does NOT currently store.
   - **The planner MUST resolve how the synthesizer reaches the plain-text provider.**
     Options the researcher should evaluate: (a) add a `plain_llm` field to
     `ResearchConfig` populated from `underlying_llm` in `from_env()`; (b) have
     the synthesizer call `get_llm_func()` directly (lazy import, mirrors config);
     (c) unwrap the adapter. Pick the one that respects the frozen-types contract
     (`types.py` ResearchConfig is `@dataclass`) and Axis-3 single-env-read rule.
3. Inline `[n]` citations threading source indices into prose.
4. Weave image captions into the narrative (preserve the existing
   `/static/img/{parent}/{name}` URL pattern from arx-1 — already correct).
5. DEFER LLM language-detection (CJK-ratio heuristic stays).

Synthesizer is the TERMINAL stage (Axis 8 — NO status field) and MUST NOT raise.
Real LLM synthesis must preserve best-effort: if the LLM call fails, degrade
gracefully (fall back to current template behavior + a note_line), never raise.

### GAP B — KB frontend UI (FRONTEND, DOMINANT cost)

Zero research UI exists in `kb/templates|static|output`. Mirror the `/ask/` Q&A
pattern with critical divergences:

- **NEW** `kb/templates/research.html` (~100 lines) + a `max_iterations` 1-10 control.
- **NEW** `kb/templates/_research_result.html` (~80 lines) — a **5-STAGE STEPPER**,
  NOT the Q&A 8-state matrix.
- **NEW** `kb/static/research.js` (~150-250 lines):
  - ⚠️ **CANNOT reuse qa.js submit/poll loop**: `/api/research` is an SSE
    **single-shot POST + JSON body**, so `EventSource` won't work (GET-only).
    MUST use `fetch()` + `ReadableStream` reader + manual SSE frame parse
    (split on `\n\n`, parse `event:` / `data:` lines).
  - **REUSE ONLY** the qa.js render half: `renderAnswerMarkdown` /
    `rewriteAnswerHtml` / `renderSources`.
- **SSG registration:** add a `research.html` render block in
  `export_knowledge_base.py:render_index_pages` (~6 lines, analogous to the
  `ask_html` block) — pages are NOT auto-discovered.
- **nav:** 2 edits in `base.html` (nav + footer).
- **locale:** ~15-20 keys × 2 langs (`zh-CN.json` + `en.json`), `research.*` namespace.
- **CSS:** stage-stepper in `style.css` — lean on existing `.qa-*` / `.chip` /
  `.prose`; mind the CSS budget ceiling (ISSUE #6 — `style.css` already 2172 lines
  vs 2150 budget; `test_css_budget_within_2100` already failing pre-this-phase).

### GAP D — Aliyun deploy parity (OPS, SMALL — likely already live)

Research router IS committed (38a7286, verified locally). Wave 0 (run FIRST,
ops gate) must SSH Aliyun, confirm git HEAD includes 38a7286 AND `/api/research`
answers (not 404). If Aliyun is behind: pull + kb-api restart. Probably a 5-min confirm.

### GAP E — E2E proof each env (OPS, Principle #6, SMALL each)

No real `/api/research` run has EVER succeeded. Need one real cited report on each env.

- **Aliyun fastest path** = CLI `python -m lib.research "<corpus-resident query>" --dump-state`
  against the 3072-healthy `/root/.hermes/omonigraph-vault`. Env MUST be sourced:
  `set -a; source /root/.hermes/.env; set +a` else silent 401 (memory
  `aliyun_ssh_manual_trigger_env`). Then browser UI UAT against the Aliyun KB.
- **Databricks** = FULL Makefile deploy (touches `kb/static` + `kb/templates` →
  Principle #9 FORBIDS sync-only; MUST run the full pipeline including Pass 0 SSG
  bake) + browser UAT against the deployed URL.
- **Query choice:** use a corpus-resident RAG/Agent-topic query that returned
  8-10 cites on `/api/synthesize` (NOT "LightRAG" — arx-3 found that brand absent
  from corpus). ⚠️ **See OPEN RISK below re: ISSUE #44** — the planner/researcher
  MUST pick a query that actually returns sources on the CURRENT Aliyun KG state.

### Recommended decomposition (5 waves — researcher may refine)

- **Wave 0** (ops GATE, run first): SSH Aliyun resolve GAP D — confirm router
  live or pull. Resolves the one real deploy unknown.
- **Wave 1** (backend, independent): GAP A real LLM synthesis + unit test pinning
  observable behavior (non-empty prose, all-chunk usage, inline [n], NOT
  chunks[0] verbatim) + CLI verify shows real prose.
- **Wave 2** (frontend, DOMINANT): GAP B full UI. Structurally independent, but
  its UAT value depends on Wave 1 real prose — sequence Wave 1 before Wave 2 UAT.
- **Wave 3** (ops): Aliyun e2e proof — CLI real report + browser UI UAT against
  Aliyun KB. Depends Wave 0 + 1 + 2.
- **Wave 4** (ops): Databricks e2e — FULL Makefile deploy (Principle #9) + browser
  UAT against Databricks URL + cite evidence in VERIFICATION.md. Depends Wave 1 + 2;
  parallel to Wave 3.
- **NO wave gate on a dim reindex** (GAP C is a non-issue).

### Claude's Discretion

- Exact synthesis prompt wording and structure (must satisfy the observable
  acceptance criteria: all-chunk usage, inline [n], image captions woven in).
- Exact stepper visual treatment (within CSS budget + brand conventions).
- Internal structure of `research.js` SSE frame parser.
- Whether GAP A resolves the plain-LLM-access via a new `ResearchConfig` field vs
  lazy `get_llm_func()` import — researcher to recommend, planner to lock.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone planning (suffix track)
- `.planning/PROJECT-Agentic-RAG-v1.1.md` — milestone scope, locked architectural choices
- `.planning/ROADMAP-Agentic-RAG-v1.1.md` — arx-1/arx-2 decomposition, REQ mapping
- `.planning/STATE-Agentic-RAG-v1.1.md` — phase status, decisions locked
- `.planning/REQUIREMENTS-Agentic-RAG-v1.1.md` — REQ-1.1-B-1..B-5 acceptance criteria

### Backend (GAP A)
- `lib/research/stages/synthesizer.py` — the stub to replace (line 99/108)
- `lib/research/config.py` — `from_env()`; confirms `llm_complete` = JSON adapter, `get_llm_func()` = plain provider
- `lib/research/types.py` — frozen `ResearchConfig` / `ResearchState` / `SynthesizerOutput` contracts
- `lib/research/orchestrator.py` — how stages are sequenced; `research()` / `research_stream()`
- `lib/research/llm_adapter.py` — `make_json_decision_adapter` (what NOT to use for synthesis)
- `lib/llm_complete.py` — `get_llm_func()` plain-text provider

### Frontend (GAP B) — reuse sources
- `kb/templates/ask.html` — Q&A page to mirror (structure, i18n keys, form)
- `kb/templates/_qa_result.html` — Q&A result partial (do NOT copy 8-state matrix; build 5-stage stepper)
- `kb/static/qa.js` — REUSE render half only (`renderAnswerMarkdown` / `rewriteAnswerHtml` / `renderSources`); do NOT reuse submit/poll loop
- `kb/api_routers/research.py` — the SSE wire protocol the JS must parse (event names + frame shape)
- `kb/templates/base.html` — nav + footer edit sites
- `kb/static/style.css` — `.qa-*` / `.chip` / `.prose` to lean on; CSS budget ceiling (ISSUE #6)
- `export_knowledge_base.py` — `render_index_pages` (`ask_html` block to mirror for SSG registration)
- `kb/locale/zh-CN.json` + `kb/locale/en.json` — i18n key files (research.* namespace)

### Ops (GAP D/E) — deploy + UAT
- `CLAUDE.md` Principles #5 (run SSH yourself), #6 (KB local UAT mandatory), #7 (Claude owns Databricks deploy), #9 (kb/static+templates → FULL Makefile deploy, sync-only forbidden)
- `Makefile` — full deploy pipeline (Pass 0a SSG bake → 0b lang → 0c dep → 0d brand → 1 → 2 → 3)
- Memory `aliyun_ssh_manual_trigger_env` — `set -a; source /root/.hermes/.env; set +a` before manual CLI
- Memory `aliyun_vitaclaw_ssh` — SSH alias `aliyun-vitaclaw`, kb-api/Caddy/systemd ops
- Memory `aliyun_kb_serve_dir_gap` — Caddy serves `/var/www/kb/` (RESOLVED via daily_rebuild Phase 5 + KB_BASE_PATH=/kb)
- Memory `claude_databricks_deployment_autonomous` + `databricks_apps_logs_websocket` + `databricks_apps_stop_start_wipes_deployment`
- `databricks-deploy/app_entry.py` — `from kb.api import app` (how Databricks inherits the router)

### Issue tracker (PRINCIPLE #10 — read before starting)
- `.planning/ISSUES.md` row #6 (CSS budget overrun — relevant to GAP B CSS)
- `.planning/ISSUES.md` row #44 (graphml↔Qdrant divergence → long_form 0 sources — **CRITICAL for GAP E**)

</canonical_refs>

<specifics>
## Specific Ideas / Constraints

- **Bilingual parity** (zh-CN + en) for ALL UI per KB convention — both locale files, both langs in stepper labels.
- **Aliyun read-only** except deliberate deploy ops (GAP D pull + restart, GAP E browser UAT). Zero Hermes (RO until 2026-06-22).
- **Plan artifacts** go in `.planning/phases/arx-2-finish/`.
- **STATE update** on close: `STATE-Agentic-RAG-v1.1.md` (suffix track), NOT bare STATE.md.
- **Forward-only commits**, explicit `git add <files>` (no `-A`), per memory `feedback_git_add_explicit_in_parallel_quicks`.
- **Databricks deploy is Claude-owned + autonomous** (Principle #7) — but this is the
  v1.1 endpoint's deploy; the FIRST-deploy human-in-the-loop checkpoint from
  PROJECT-Agentic-RAG-v1.1.md "Deploy Gate" applies IF this is genuinely the first
  deploy of the research endpoint to Databricks. The planner should include a
  preflight-then-go checkpoint for the Databricks deploy unless Wave 0/research
  confirms the endpoint already deployed there.

## OPEN RISKS the researcher MUST resolve

1. **(PRIMARY) GAP D liveness** — confirm via SSH that Aliyun git HEAD includes
   38a7286 AND `/api/research` answers (not 404). Local git confirms it's
   committed; just verify Aliyun pulled it. Read-only probe.

2. **(SECONDARY) GAP A plain-LLM access** — `config.py:50-59` confirms
   `cfg.llm_complete` is the JSON adapter and `get_llm_func()` returns the plain
   provider, but `ResearchConfig` stores ONLY the adapter. Researcher must
   recommend HOW the synthesizer reaches a plain `(prompt)->str` provider without
   breaking the frozen-types contract or the Axis-3 single-env-read rule.

3. **(CRITICAL — newly surfaced, NOT in original command brief) ISSUE #44 vs GAP E** —
   Research shares the EXACT retriever (`search(mode=hybrid)`) with `/api/synthesize`
   `long_form`. ISSUE #44 (P0, open) documents that on Aliyun, `long_form`
   synthesize returns `sources=0 markdown=empty` because the 5/24 graphml baseline
   (27654 ent / 39604 rel) is ~26.5k entities SMALLER than the Qdrant store
   (54225 ent / 75441 rel) — hybrid retrieval finds chunks in Qdrant but the
   entity/relationship nodes don't exist in graphml, so the KG join yields 0
   sources. **If this is still true, GAP E's Aliyun E2E proof CANNOT produce a
   cited report** — the retriever returns nothing to synthesize. The researcher
   MUST: (a) determine whether #44 is still reproducing on current Aliyun state
   (it was "likely RESOLVED-by-atomic-write-patch" but the 14-day historical gap
   "still requires user-decided rebuild" per the issue row); (b) identify a query
   that DOES return sources on the current Aliyun KG (the command says "a query
   that returned 8-10 cites on /api/synthesize" — confirm that's still true in
   hybrid mode, or find one that is); (c) if NO query returns sources on Aliyun,
   surface this as a phase blocker (Aliyun E2E proof depends on a working KG join)
   — the fix is the #44 graphml-rebuild, which is OUT of this phase's scope.

</specifics>

<deferred>
## Deferred Ideas

- LLM-driven language detection (CJK heuristic stays — GAP A item 5).
- Dim reindex / 1024-provider path (GAP C non-issue).
- v1.1-C native function-calling, v1.1-D per-tool-call telemetry, v1.1-E LightRAG
  cache write-perms (all deferred to v1.2 per PROJECT-Agentic-RAG-v1.1.md).
- ISSUE #44 graphml rebuild (Path X cron / Path Y Hermes batch) — out of phase
  scope; only its IMPACT on GAP E query selection is in scope.

</deferred>

---

*Phase: arx-2-finish*
*Context gathered: 2026-06-12 from command PRD brief + audit w1ppw59o1*
