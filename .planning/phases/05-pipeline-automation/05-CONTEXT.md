# Phase 5: pipeline-automation - Context

**Gathered:** 2026-04-28
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
