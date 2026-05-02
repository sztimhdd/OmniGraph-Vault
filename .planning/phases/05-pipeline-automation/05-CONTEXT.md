# Phase 5: pipeline-automation - Context

**Gathered:** 2026-04-28
**Updated:** 2026-05-01 (post v3.1 close @ `2b38e98` + v3.2 close @ `40cba44` — infrastructure composition section added; existing D-01..D-18 decisions unchanged)
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 delivers an **unattended daily pipeline**: scan 56 WeChat KOL + 92 Karpathy RSS feeds → classify articles for depth → enrich deep ones via Zhihu 好问 (reusing Phase 4) → ingest into LightRAG → generate Telegram digest. **Wave 0 first migrates LightRAG embeddings from `gemini-embedding-001` to `gemini-embedding-2` (multimodal)** — a mandatory prerequisite because the free-tier 100-RPM quota on `-001` is what blocked Phase 4 criteria 11/12 and would block the catch-up too.

**In scope:**

- Wave 0: Embedding migration spike + consolidation of 6 duplicated `embedding_func` copies + 18-doc re-embed benchmark
- Wave 0b: Keyword+quality-filtered catch-up of KOL historical articles (re-runnable as keyword scope grows)
- Wave 1: RSS infrastructure (`rss_fetch.py`, `rss_classify.py`, `rss_ingest.py`) + SQLite schema
- Wave 2: `orchestrate_daily.py` state-machine + `daily_digest.py` Telegram delivery
- Wave 3: Cron deployment + 3-day observation

**Out of scope (belongs elsewhere):**

- `kg_synthesize.py` refactor — deferred to future Agentic RAG phase
- Web UI / dashboard for digest
- Streaming/realtime ingest
- Sources beyond Karpathy 92 RSS + existing WeChat KOLs
- Image-as-query cross-modal (only text-query → image chunks is in scope)
- Image-to-image similarity
- Additional knowledge sources beyond Zhihu (X/Twitter, HN, blogs) — Phase 4 boundary carries forward

</domain>

<decisions>
## Implementation Decisions

### Embedding migration landing zone

- **D-01:** A **new shared module** owns `embedding_func` as single source of truth. Planner picks the exact path (likely `config/embedding.py` or `lightrag_embedding.py` — deliberately not specified here to leave room for the Wave 0 spike to influence). All 6 files that currently duplicate the wrapper import from this module.
- **D-02:** Model name is configured via env var **`EMBEDDING_MODEL`** in `~/.hermes/.env` (matches the existing pattern for LLM model + API keys in Phase 4 D-12). Rollback = one-line env change + restart, zero code.
- **D-03:** **Consolidation is in-scope for Wave 0.** Migration and dedup happen together — shipping `gemini-embedding-2` to some files while others stay on `-001` would create two incompatible embedding spaces simultaneously.

### Multimodal integration

- **D-04:** **In-band multimodal**. The new `embedding_func` receives text chunks from LightRAG; when a chunk contains an image reference (e.g., `http://localhost:8765/<hash>/<i>.jpg`), the function fetches the bytes and sends text + `inline_data` as one Gemini `embed_content` call → one aggregated vector. LightRAG's contract remains `(texts: list[str]) -> np.ndarray` — the image dance is transparent to LightRAG. This is the minimum-viable multimodal path with zero LightRAG fork.
- **D-05:** **Gemini-2 task prefix formatting lives inside the `embedding_func` wrapper.** Per Gemini docs (accessed 2026-04-28), `-2` drops the `task_type` parameter entirely and requires task instructions in the prompt: documents get `title: none | text: {chunk}` prefix, queries get `task: search result | query: {content}` prefix. The wrapper must distinguish query vs document paths — either via a runtime flag (`is_query=True`) or two wrapper variants (e.g., `embed_documents` + `embed_query`). LightRAG code stays unchanged.
- **D-06:** **Catch-up uses Gemini Batch API** (50% cheaper, ~24hr max turnaround). Wave 0b submits a single batch overnight. Sync API is used for the 18-doc re-embed (Wave 0 gate) for fast feedback and for live RSS ingestion in Wave 1+.

### RSS enrichment policy

- **D-07:** **Uniform contract with WeChat** (inherits Phase 4 D-07 "mandatory for all depth≥2"). All RSS articles classified `depth_score ≥ 2` go through Zhihu 好问 enrichment, regardless of source language. Agent/LLM/RAG/transformer concepts are language-neutral; 好问's Chinese corpus often has deeper coverage than English sources.
- **D-08:** **EN→CN translation happens inside the `extract_questions` prompt** — one-step LLM call. `enrichment/extract_questions.py` receives English body + instruction "output questions in Chinese." No separate translation step. Matches Phase 4's one-LLM-call pattern (D-12).
- **D-09:** **English RSS body is fully translated to Chinese before LightRAG ingest.** The final ingested doc is single-language Chinese (translated body + inline Chinese 好问 summaries + Chinese Zhihu answer docs as per Phase 4 D-08/D-09). Costs an extra LLM call per English article, in exchange for graph-wide language consistency. **Reconsiderable** if post-Wave-0 benchmarks show `gemini-embedding-2`'s cross-language retrieval is strong enough to eliminate the translation step.

### 302-article catch-up (Wave 0b)

- **D-10:** **Ingestion filter = keyword match AND `depth_score ≥ 2`**. Current keyword scope: `{openclaw, hermes, agent, harness}` (case-insensitive, matched over title + content). Wave 0b ingests only the subset that passes both filters — NOT all 302 articles. Keywords will expand over time; this is a first-class operational pattern, not a hack.
- **D-11:** **Catch-up is re-runnable as keyword scope grows.** `batch_ingest_from_spider.py` already has `--from-db --topic-filter <keyword>` (see `batch_ingest_from_spider.py:598-614`); planner extends to accept multiple keywords (multi-flag or comma-separated). Already-ingested articles are skipped via existing dedup.
- **D-12:** **Classification runs first, over all 302 articles**, to populate the currently-empty `classifications` table (known gap per 05-PRD §9 and STATE.md). Depth score is produced by LLM classification (DeepSeek or Gemini free-tier, rate-limited). Ingestion filter (D-10) applies on the classified subset.
- **D-13:** **Timing: Wave 0b fires immediately after 18-doc re-embed passes Wave 0 success criteria**, before Wave 1 RSS work starts. Ensures the daily digest from Wave 1+ has a non-empty, depth-filtered graph floor from day 1.
- **D-14:** **Execution: single Gemini Batch API submission** for the filtered subset. 24hr max turnaround, cost-optimized. Failure recovery: re-run with `--from-db` — already-ingested articles skip via dedup.

### Carried from Phase 4 (unchanged)

- **D-15** (= Phase 4 D-04/05/06): All Phase 5 code executes on the **remote WSL host**. Dev box is edit-only.
- **D-16** (= Phase 4 D-01): Cron orchestration follows **"Hermes drives"** — cron jobs invoke Hermes skills which shell to Python helpers; Python does not call Hermes directly.
- **D-17** (= Phase 4 D-14): LightRAG **delete-by-id + re-ainsert** path was proven in Phase 4. Reused verbatim for Wave 0 re-embedding of the 18 existing docs.
- **D-18** (= Phase 4 D-13): Telegram delivery path is proven. Daily digest + cron failure alerts reuse it.

### Claude's Discretion

The following are left for researcher/planner to decide:

- Exact path and name of the shared embedding module (`config/embedding.py` vs `lightrag_embedding.py` vs `embedding.py`) — depends on existing import patterns and Wave 0 spike findings.
- Whether query-side embedding uses a separate function (`embed_query`) or the same function with an `is_query=True` kwarg.
- Exact CLI shape for multi-keyword filtering in `batch_ingest_from_spider.py` (`--topic-filter` multi-flag vs comma-separated string vs config-file scope).
- Daily digest empty-state behavior on light days (skip Telegram delivery vs send "light day" note).
- OPML source strategy (bundle the Karpathy 92 in-repo with a versioned snapshot vs fetch from the gist on first run with a local cache; freshness cadence).
- Cron failure alerting threshold — which steps page the user via Telegram vs silent-log.
- Embedding benchmark golden-query set design (count, topics, scoring method — NDCG / top-5 overlap / exact match).
- Sync fallback path if a Gemini Batch API submission is rejected or a result retrieval fails.
- Chunked vs single-batch fallback if a single batch request exceeds an API limit.

### Folded Todos

None — `gsd-tools todo match-phase 5` returned zero matches.

</decisions>

<infra_composition>
## v3.1 / v3.2 Infrastructure Composition (added 2026-05-01)

Between Phase 5 planning (2026-04-28) and Phase 5 execution, milestones **v3.1** (single-article ingest stability) and **v3.2** (batch reliability + infra) landed. Phase 5 plans MUST compose with the delivered libraries rather than reimplement equivalent logic. This section lists what exists on `main` at commit `40cba44` and how each Phase 5 plan should use it. **Original 18 decisions (D-01..D-18) are unchanged** — this section only adds composition guidance, not new locked decisions.

### Delivered libraries (all importable, unit-tested, in production code path)

| Module | Contract | Phase 5 composition point |
|---|---|---|
| `lib/checkpoint.py` | 6-stage per-article state machine: `scrape → classify → image_download → vision → text_ingest → sub_doc_ingest`. Markers `0[1-6]_<stage>.done` under `checkpoints/{ckpt_hash}/`. `ckpt_hash = sha256(url)[:16]` (parallel to legacy md5[:10]; does NOT replace). APIs: `has_stage(hash, stage)`, `mark_stage(hash, stage)`, `list_vision_markers(hash)`. | **05-03b** (RSS ingest) MUST wrap per-article ingest in checkpoint guards — same as v3.2 Phase 12 did for `ingest_wechat.py`. **05-04** step_7 inherits this automatically via `batch_ingest_from_spider.py`. |
| `lib/vision_cascade.py` | SiliconFlow Qwen3-VL-32B → OpenRouter GLM-4.5V → Gemini Vision, with per-provider circuit breaker (consecutive-N failures → auto-skip for cooldown window). `image_pipeline.describe_images()` already delegates here. | **05-03b** images inherit automatically via `image_pipeline.describe_images()`. No new Vision code. |
| `lib/batch_timeout.py` | `clamp_article_timeout(budget_total, articles_remaining, per_article_floor, per_article_ceiling)` — splits a total batch budget across remaining articles. Default `OMNIGRAPH_BATCH_TIMEOUT_SEC=28800` (8h, sized for 56 articles × 441s Hermes prod baseline). | **05-04** step_7 should wrap `batch_ingest_from_spider.py` invocation within this total budget (default 28800s). **05-06** cron `daily-ingest` inherits via `batch_ingest_from_spider.py` instrumentation. |
| `lib/siliconflow_balance.py` | Module-load reads `~/.hermes/.env` (fixes v3.1 Finding 2 env-read bug). `check_siliconflow_balance() → Decimal`. Reads `data.totalBalance` (not gift `balance`). With `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1`, pre-batch balance gating is disabled — cascade always tries SiliconFlow first and falls back only on actual errors. | **05-06** cron `daily-ingest` may call it at the top as pre-check (non-fatal warning if balance low); OPERATOR_RUNBOOK.md documents how to top up. No new balance code in Phase 5. |
| `lib/lightrag_embedding.py` | Vertex AI opt-in (env-triggered: `GOOGLE_APPLICATION_CREDENTIALS` + `GOOGLE_CLOUD_PROJECT` set → Vertex; else Gemini Developer API). Model `gemini-embedding-2` (stable; `-preview` suffix removed 2026-05-02 — deprecated by Vertex AI). | Already adopted by Wave 0 (05-00). RSS ingest (**05-03b**) uses the same embedding function via LightRAG — zero change needed. |

### v3.1 contracts Phase 5 relies on

| Contract | Where | Phase 5 usage |
|---|---|---|
| `get_rag(flush=True/False)` API + LLM_TIMEOUT=600 + per-article timeout `max(120+30×chunks, 900)` | Phase 9 | **05-03b** + **05-04** `batch_ingest_from_spider.py` invocation: no extra timeout wrapping needed on top of this. |
| Scrape-first full-body classification writing to `classifications` SQLite table | Phase 10 (CLASS-04) | **05-03** writes to the parallel `rss_classifications` table per PRD §3.1.4 schema — same column pattern (`article_id`, `depth_score`, `topic`, `rationale`, `classified_at`). **Keep them as separate tables** (different `article_id` FK targets: `articles` vs `rss_articles`) but **mirror the column design** for operational consistency. |
| Text-first `ainsert` decoupled from async Vision sub-doc worker | Phase 10 (ARCH-01..04) | **05-03b** gets this automatically by calling into the same `ingest_article()` entry point `ingest_wechat.py` uses. |

### v3.2 operator surfaces referenced by Phase 5

| Document | Owner | Phase 5 referrer |
|---|---|---|
| `docs/OPERATOR_RUNBOOK.md` (Phase 15) | Hermes ops | **05-06** Task 6.3 Phase 5 Exit State MUST point to this; 3-day observation anomalies reference its recovery procedures. |
| `docs/Deploy.md` (Phase 15 updates) | Hermes ops | **05-06** env var list + SA rotation guidance lives here; Phase 5-specific env additions (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, OPML cache path) append here. |
| `docs/VERTEX_AI_MIGRATION_SPEC.md` (Phase 16) | Design only | Referenced by **05-00** Wave 0 SUMMARY retroactively if embedding behavior matches. No Phase 5 code change. |
| `lib/checkpoint.py` CLI tools (`scripts/checkpoint_status.py`, `scripts/checkpoint_resume.py`) | Phase 12 | **05-06** 3-day observation uses these to report resume-vs-fresh counts. |

### What does NOT change in Phase 5

- All 18 existing decisions (D-01..D-18) stand as-is.
- PRD §3.1.4 `rss_classifications` schema stays separate from Phase 10 `classifications` (different source tables).
- PRD §3.2 9-step orchestrator contract unchanged — composition with `lib/checkpoint.py` happens **inside** `batch_ingest_from_spider.py` (already wired in v3.2 Phase 12-03), not at the orchestrator layer.
- OPML curation (**05-01**), RSS fetch (**05-02**), daily digest (**05-05**) are largely independent of v3.1/v3.2 infra — light touches only, documented per plan.

### Pre-execution checklist for Phase 5

Before `/gsd:execute-phase 5`:
1. `lib/checkpoint.py`, `lib/vision_cascade.py`, `lib/batch_timeout.py`, `lib/siliconflow_balance.py` importable — `python -c "from lib import checkpoint, vision_cascade, batch_timeout, siliconflow_balance"` exits 0.
2. `docs/OPERATOR_RUNBOOK.md` exists on main.
3. **v3.2 E2E regression complete** — P0 fixture scrape + P1 Gate 3 + P2 cascade smoke + P3 unit tests all shipped (commits `2a8bde2` through `3c338f8`). 4-probe UAT harness at `scripts/probe_e2e_v3_2.py` validates checkpoint/resume + cascade + full 6-stage E2E.
4. **UAT smoke gate**: before any Phase 5 batch ingest, run `python scripts/probe_e2e_v3_2.py --probe A,B --fixture text_only_article` (~7 min) to verify checkpoint/resume works in the target environment.
5. **Zombie doc cleanup**: before each batch ingest command, run `python scripts/clean_lightrag_zombies.py` to purge PROCESSING/FAILED entries from `kv_store_doc_status.json`. Integrated into cron health-check (`e7afccd9931b`).
6. Hermes top-up on SiliconFlow is operational housekeeping — Phase 5 does not gate on it. With `OMNIGRAPH_VISION_SKIP_BALANCE_CHECK=1`, cascade always tries SiliconFlow first.

### UAT Smoke Gates (v3.2 regression probe integration)

The 4-probe UAT harness (`scripts/probe_e2e_v3_2.py`) validates v3.2 infrastructure
that Phase 5 depends on. Inject at these points:

| Phase 5 step | UAT command | Time | Validates |
|-------------|------------|------|-----------|
| Pre-Wave 0 (embedding migration) | `--probe A,C --fixture gpt55_article` | ~2 min | Checkpoint file structure + vision cascade before changing embedding model |
| Pre-Wave 0b (batch catch-up) | `--probe B --fixture text_only_article` | ~7 min | Resume mechanism survives environment drift |
| Pre-05-06 (cron deploy) | `--probe A,B --fixture text_only_article` | ~7 min | Final smoke before unattended cron goes live |
| 05-06 observation (daily) | `--probe D --fixture sparse_image_article` | ~15 min | Full 6-stage regression on schedule |

Probe A (2s, no API) can run before every Phase 5 task as a cheap structural check.
Probe B should run at least once per day during 3-day observation to catch
checkpoint drift. See `docs/UAT_v3_2.md` for full documentation.

</infra_composition>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product spec

- `.planning/phases/05-pipeline-automation/05-PRD.md` v1.0 (extended 2026-04-28 with §2.4 Embedding migration) — source of truth for Phase 5 scope.
  - **Supersessions:** §8 `ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"` is superseded by Phase 4 D-12 (Gemini 2.5 Flash Lite + grounding).
  - **PRD edit deferred:** §2.4 Wave 0 currently refers to model name "embedding-002" — the actual name per Gemini docs is `gemini-embedding-2`. Planner or executor should fix this in the PRD.

### External API (authoritative)

- `https://ai.google.dev/gemini-api/docs/embeddings` — accessed 2026-04-28. Confirms:
  - Model name is `gemini-embedding-2` (not `-002`).
  - Multimodal input via `parts: [{inline_data: {mime_type, data}}]` — up to 6 images/request, 8192 input tokens.
  - `task_type` param is gone; use prompt prefixes instead (`title: X | text: Y`, `task: search result | query: {content}`).
  - Batch API exists at 50% default price.
  - Embedding spaces between `-001` and `-2` are **incompatible** — re-embed all data.
  - Output dims 128-3072 supported; `-2` auto-normalizes truncated dims (vs `-001` requiring manual norm).

### Prior phase context (load first)

- `.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md` — 16 locked decisions (D-01 through D-16). Especially D-01 (Hermes drives), D-04/05/06 (remote WSL host only), D-13 (Telegram recovery), D-14 (LightRAG delete-by-id spike, now reused).
- `.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md` — technical research (if needed for deeper context).
- `docs/testing/04-07-validation-results.md` — Phase 4 exit state showing which criteria were embedding-quota-blocked.

### Project context

- `CLAUDE.md` — project rules, typo'd data dir `~/.hermes/omonigraph-vault/` (preserve), highest-priority principles.
- `.planning/PROJECT.md` — pipeline overview, tech stack, constraints.
- `.planning/STATE.md` — current state (Phase 4 closed 2026-04-28).
- `docs/enrichment-prd.md` — full Phase 4 PRD; enrichment contract that Wave 0b catch-up and RSS enrichment reuse.

### Code touch points

Embedding duplication sites (all get consolidated in D-03):

- `ingest_wechat.py:128-164` — current `embedding_func`, `wrap_embedding_func_with_attrs` decorator, LightRAG construction, 100-RPM throttle.
- `ingest_github.py:51-67` — duplicate.
- `kg_synthesize.py:53-58` — duplicate (read path).
- `multimodal_ingest.py:60-76` — duplicate.
- `query_lightrag.py:30-34` — duplicate (read path).
- `cognee_wrapper.py:27` — `os.environ["EMBEDDING_MODEL"] = "gemini-embedding-001"` (sets env for Cognee's LLM stack; update in lockstep).

Existing pipeline:

- `batch_ingest_from_spider.py:598-614` — existing `--topic-filter` + `--from-db` CLI; extend for multi-keyword (D-11).
- `batch_classify_kol.py` — runs first in Wave 0b (D-12).
- `enrichment/extract_questions.py` — extend prompt for EN→CN translation (D-08).
- `enrichment/merge_and_ingest.py` — may need RSS variant or language-agnostic refactor for D-09.

### Hermes docs (read during planning)

- `https://hermes-agent.nousresearch.com/docs/guides/automate-with-cron` — "script stdout becomes agent context" pattern for cron-triggered flows (Phase 4 D-03).
- `https://hermes-agent.nousresearch.com/docs/user-guide/features/skills` — `skills.external_dirs`; remote already points at the repo's `skills/` dir.

### Deferred docs to locate during research

- **LightRAG internal embedding call sites** — confirm how LightRAG distinguishes query vs document embedding calls, so D-05 task-prefix routing can be correct. Inspect `venv/Lib/site-packages/lightrag/` on the remote.
- **Gemini Batch API Python SDK reference** — confirm submission, polling, and result retrieval API shape for Wave 0b implementation.
- **Karpathy HN 2025 OPML source** at `https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b` — verify accessibility + content when Wave 1 kicks off.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`wrap_embedding_func_with_attrs`** from LightRAG — current decorator that supplies `embedding_dim`, `send_dimensions`, `max_token_size`, `model_name`. Must continue to work post-migration; `embedding_dim` changes from 768 to the chosen `-2` dimension (planner picks from 768/1536/3072).
- **`gemini_embed.func`** from `lightrag.llm.gemini` — current embedding call. **Needs replacement**: `-2` uses `parts` / `inline_data` instead of a simple `texts` list, drops `task_type`, and aggregates multi-input calls. The new wrapper calls Gemini's SDK directly rather than reusing LightRAG's helper.
- **`batch_ingest_from_spider.py --from-db --topic-filter`** — already present; extend for multi-keyword (D-11).
- **`batch_classify_kol.py`** — already present, multi-`--topic` supported. Drives Wave 0b classification pass (D-12).
- **`cognee_wrapper.remember_article`** fire-and-forget pattern — applies to every new ingest path (KOL catch-up, RSS daily).
- **Atomic write patterns** (`.tmp` → rename for `canonical_map.json`, per CLAUDE.md) — apply to any new state files (cron run logs, digest archives).

### Established Patterns

- **SQLite dual-write + file fallback** (Phase 2) — applies to RSS schema additions (D-11 new tables).
- **"Hermes drives"** (Phase 4 D-01) — cron jobs invoke Hermes skills which shell to Python helpers. Phase 5 cron jobs follow this.
- **Remote-only execution** (Phase 4 D-04/05/06) — no local testability; everything runs on WSL.
- **Gemini free-tier RPM throttle** — the `-001` 100-RPM ceiling is what blocked Phase 4 criteria 11/12. Need to research `-2`'s free-tier limits during Wave 0 spike; presumed more generous per Google's "built for production scale" positioning, but not yet verified.

### Integration Points

- **`~/.hermes/omonigraph-vault/lightrag_storage/`** — target for delete-by-id + re-ainsert during Wave 0 re-embed (18 docs).
- **`data/kol_scan.db`** — `classifications` table (currently empty) is populated by Wave 0b pre-classification; `rss_feeds` + `rss_articles` + `rss_classifications` tables are added by Wave 1 (per PRD §3.1.4 schema).
- **`~/.hermes/.env`** — new `EMBEDDING_MODEL=gemini-embedding-2` env var lands here.
- **`config.py`** — consolidated embedding module imports live here or an adjacent module that `config.py` references.
- **Image server on port 8765** — continues to serve WeChat + Zhihu images; new RSS pipeline ingests images via the same URL scheme if they get localized (Phase 4 D-15 `image_pipeline.describe_images` batch form).

</code_context>

<specifics>
## Specific Ideas

- **Keyword scope is expandable over time** — `{openclaw, hermes, agent, harness}` today; tomorrow might add `claude-code`, `openai-agent-sdk`, `lightrag`, etc. The pipeline treats "re-run with new keyword" as normal usage, not a hack. Dedup is already in `batch_ingest_from_spider.py`.
- **English RSS → Chinese body translation** is an explicit cost + design commitment (D-09). It happens at the merge step (`enrichment/merge_and_ingest.py` or a new helper), before LightRAG `ainsert`. Original English body may be preserved as a debug artifact but is NOT the doc in the graph.
- **Batch API is overnight** — Wave 0b is async by design. Submitted at end of Wave 0, results polled next day. Wave 1 development can start before Batch completes (D-13 says Wave 1 starts after catch-up finishes; adjust if parallel development is acceptable).
- **Embedding benchmark is a Wave 0 deliverable**, not post-hoc. The 18-doc re-embed must validate on a golden-query set (planner designs it) — Chinese retrieval quality must not regress before Wave 0b is greenlit.
- **"Research-first for feasibility"** — the user's original fallback for multimodal was to check the Gemini docs. That check happened in this discuss-phase (canonical ref #2). Outcome: multimodal IS feasible; the spike's question shifts from "can we?" to "what integration shape is cleanest?"

</specifics>

<deferred>
## Deferred Ideas

### Not this phase

- **Image-as-query** (paste image → get text chunks) — requires query API changes in `omnigraph_query` skill. Phase 5 supports text-query → image chunks only (one-way multimodal).
- **Image-to-image similarity** — same reason.
- **Cross-language retrieval benchmark elimination of D-09** — if `gemini-embedding-2` proves strong at CN↔EN retrieval in Wave 0 benchmarks, D-09's translation-to-Chinese step becomes redundant. Reconsider in a follow-up phase, don't block Phase 5 on this.
- **`kg_synthesize` refactor for Agentic RAG** — Phase 5 touches `kg_synthesize.py` only for the embedding import (D-01). Synthesis logic stays unchanged.
- **Additional RSS sources beyond Karpathy's 92** — out of scope per PRD §2.3.
- **Per-question retry state for RSS enrichment** — inherits Phase 4 D-11 (article-level `enriched=-2` marker, no per-question retry table).
- **Vertex AI `multimodalembedding@001`** — a different model, not needed; `gemini-embedding-2` via Gemini API is sufficient.
- **Streaming/realtime RSS ingest** — out of scope per PRD §2.3.
- **Web digest UI** — out of scope per PRD §2.3.
- **Sources beyond Zhihu for enrichment** (X threads, HN, blogs) — inherits Phase 4 boundary.

### Secondary gray areas (Claude's discretion during planning)

These came up but didn't need user decision:

- Daily digest empty-state message on light days (skip delivery vs "light day" note).
- OPML bundle strategy (versioned snapshot in-repo vs fetch-from-gist with local cache).
- Cron failure alerting granularity (which steps are page-worthy vs silent-log).
- Embedding benchmark golden-query set size + scoring method.
- Sync fallback if Batch API fails.
- CLI shape for multi-keyword (`--topic-filter` multi-flag vs comma-separated).

### Reviewed Todos

None — no Phase 5-relevant todos in the backlog.

### PRD inconsistencies surfaced during discussion

- **Model name typo** — PRD §2.4 (added this session) calls the new model "embedding-002"; actual Gemini model is `gemini-embedding-2` (no `0`, single digit). Fix during planning.
- **PRD §8** `ENRICHMENT_LLM_MODEL = "deepseek-v4-flash"` — superseded by Phase 4 D-12 (Gemini 2.5 Flash Lite + grounding).
- **PRD §3.1.5** hints "英文 RSS 可能不需要增厚" — superseded by D-07 (mandatory for all depth≥2 regardless of language).
- **PRD §8 Wave 0b description** implies "all 302 articles" catch-up — superseded by D-10 (keyword + depth filter; NOT all 302).

</deferred>

---

*Phase: 05-pipeline-automation*
*Context gathered: 2026-04-28*
