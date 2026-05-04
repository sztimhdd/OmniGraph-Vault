# Milestone v3.4 Requirements — RSS-KOL Alignment

**Status:** ACTIVE (started 2026-05-03).

**Milestone goal:** Close the RSS-vs-KOL architectural gap. RSS articles run through the full pipeline (scrape → full-body classify → multimodal ingest) except Zhihu enrichment — identical quality tier as KOL articles. Generic scraper defaults to full cascade (Apify → CDP → MCP → UA → fallback); failed-ingest stuck docs have a CLI cleanup tool and do not contaminate subsequent batches.

**Gate:** All 6 success criteria in PROJECT.md Current Milestone pass + post-rollout Day-1/2/3 observation window clean.

**Locked D-level decisions (from `.planning/research/SUMMARY.md`):**

- **D-RSS-SCRAPER-SCOPE = Option A (Unified)** — `lib/scraper.py::scrape_url()` serves both KOL and RSS arms; patches `batch_ingest_from_spider.py:940` UA-only bug (2:1 researcher consensus + user preference)
- **D-STUCK-DOC-IDEMPOTENCY = CLI tool** (not cron pre-hook) — `scripts/cleanup_stuck_docs.py`; Wave 3 first task is a 30-min NanoVectorDB cleanup spike to resolve confidence gap between Architecture (HIGH) and Pitfalls (MEDIUM) before implementing full CLI

**Prior milestones archived:**

- v3.1 (Single-Article Ingest Stability, 26 reqs) — `docs/MILESTONE_v3.1_CLOSURE.md` + `.planning/MILESTONE_v3.1_MORNING_SUMMARY.md`
- v3.2 (Batch Reliability + Infra) — `.planning/MILESTONE_v3.2_REQUIREMENTS.md` + `docs/MILESTONE_v3.2_EXECUTION_REPORT.md`
- v3.3 (Pipeline Automation: RSS Fetch + Daily Digest + Cron) — `.planning/MILESTONE_v3.3_REQUIREMENTS.md`

---

## v3.4 Requirements

34 REQs across 9 categories, grouped by wave. Categories use new namespaces (SCR / SCH / RCL / RIN / COG / STK / BKF / E2R / CUT) to avoid colliding with v3.1 namespaces (IMG / CLASS / STATE / ARCH / TIMEOUT / E2E).

**2026-05-03 pre-v3.4 emergency hotfix context:** Day-1 preview round 2 exposed a Cognee LiteLLM routing bug (`EMBEDDING_PROVIDER=gemini` → AI Studio, but `EMBEDDING_MODEL=gemini-embedding-2` is Vertex-exclusive → 422 NOT_FOUND retry loop blocks ingest fast-path). A hotfix `/gsd:quick` on 2026-05-03 gates `ingest_wechat.py:1099-1108` via `OMNIGRAPH_COGNEE_INLINE=0` (default disabled) to unblock 2026-05-04 06:00 ADT Day-1 cron. The root cause is now tracked as COG-01..03 in Wave 2 below, to be properly fixed before cron cutover (CUT-01).

---

### Wave 1 — Generic Scraper + Schema + KOL Hotfix

#### Scraper (SCR)

- [ ] **SCR-01**: `lib/scraper.py` is a new module exposing public API `scrape_url(url: str, site_hint: str) -> ScrapeResult`. Extracted from `ingest_wechat.py::process_content` + related cascade logic. ScrapeResult is a dataclass with `{markdown: str, images: list[ImageRef], metadata: dict, method: str, summary_only: bool, content_html: Optional[str]}`.
  - *Amendment 2026-05-03 (Phase 19 planning):* Added 6th field `content_html: Optional[str] = None` — required by the `batch_ingest_from_spider.py:940` WeChat consumer (`_classify_full_body` passes it to `ingest_wechat.process_content`). Field is Optional / defaults to None for non-WeChat callers; filled only on WeChat cascade path.
- [ ] **SCR-02**: 4-layer cascade — trafilatura UA fetch (PRIMARY for non-WeChat) → requests UA-spoofed + trafilatura extract (SECONDARY) → CDP / MCP browser render (TERTIARY — Medium / gated content skip layers 1-2) → RSS summary fallback (LAST RESORT — flags result as `summary_only=True`, not `enriched=2`).
- [ ] **SCR-03**: URL router dispatches by site type using stdlib `urllib.parse.urlparse` (no `tldextract` dep). Routing table: `mp.weixin.qq.com/*` → WeChat cascade (existing path); `arxiv.org/abs/*` → trafilatura (abstract only); `arxiv.org/pdf/*` → existing PyMuPDF path; everything else → generic cascade.
- [ ] **SCR-04**: Content-quality gate before accepting a layer's output: `len(text) >= 500` AND no login-wall keywords (`"Sign in"`, `"Log in to continue"`, `"Subscribe to read"`, `"登录查看"`, etc.). If gate fails, cascade to next layer.
- [ ] **SCR-05**: HTTP 429 triggers **exponential backoff** (30s / 60s / 120s) on the same layer; does NOT immediately cascade (prevents burning through layers unnecessarily on transient rate limits). Cascade-after-429 only after 3 backoff attempts.
- [ ] **SCR-06**: `batch_ingest_from_spider.py:940` UA-only path is replaced by `scrape_url(url, site_hint="wechat")`. Locks **D-RSS-SCRAPER-SCOPE = Option A**. Closes Day-1 pre-flight article 1 KOL regression bug (Phase 10 D-10.01 residue).
- [x] **SCR-07**: `trafilatura>=2.0.0,<3.0` + `lxml>=4.9,<6` pinned in `requirements.txt`. Note: `lxml>=6` has open trafilatura incompatibility issues — pin `<6` until resolved.

#### Schema (SCH)

- [ ] **SCH-01**: `rss_articles` table ALTER adds 5 columns (all nullable, SQLite metadata-only change — safe against 1020-row backlog without rewrite): `body TEXT`, `body_scraped_at TEXT` (ISO-8601), `depth INTEGER` (1-3), `topics TEXT` (JSON array), `classify_rationale TEXT`.
- [ ] **SCH-02**: Hash function unified to **SHA-256 first 16 hex** at `batch_ingest_from_spider.py:275` (currently inline MD5 first 10 hex — collides namespace with `lib/checkpoint.py` which uses SHA-256 first 16). **Prerequisite for the 1020-article backlog run** — without unification, `checkpoint_reset.py` will be blind to half the checkpoints (MP-08 pitfall).

---

### Wave 2 — RSS Full-Body Classify + Multimodal Ingest

#### RSS Classify (RCL)

- [ ] **RCL-01**: `rss_classify.py` ports `_build_fullbody_prompt` from `batch_classify_kol.py:226-256` verbatim (multi-topic single-call pattern, Phase 10 D-10.02 — returns single JSON object `{depth, topics, rationale}`). Truncation budget `FULLBODY_TRUNCATION_CHARS=8000` preserved.
- [ ] **RCL-02**: `FULLBODY_THROTTLE_SECONDS=4.5` replaces the current `THROTTLE_SECONDS=0.3` (which was sized for 200-char summaries and breaks DeepSeek 15 RPM within 30 calls under 8000-char full-body prompts). 429 exponential backoff preserved (same pattern as existing KOL classifier). **Fixes pitfall CP-02**.
- [ ] **RCL-03**: Classify writes `rss_articles.body + body_scraped_at + depth + topics + classify_rationale` BEFORE any ingest decision (D-10.02 scrape-first pattern mirrored from KOL side).

#### RSS Ingest (RIN)

- [ ] **RIN-01**: `enrichment/rss_ingest.py` rewritten (replacing current summary-only ingest) to follow the 5-stage KOL path: `01_scrape` → `02_classify` → `03_image_download` → `04_text_ingest` (localhost-rewrite + multimodal `ainsert`) → `05_vision_worker` (fire-and-forget `asyncio.create_task`).
- [ ] **RIN-02**: `image_pipeline.localize_markdown` is called on the RSS body before LightRAG `ainsert` — replaces CDN URLs with `http://localhost:8765/<hash>/<n>.jpg` (matches `lib/lightrag_embedding._build_contents` regex for in-band `types.Part` multimodal assembly).
- [ ] **RIN-03**: `download_images` sends `Referer` header matching source domain (Substack/Medium/HuggingFace CDN hot-link blocking). Header value = scheme + host of the article URL.
- [ ] **RIN-04**: `download_images` filters SVG (`content-type: image/svg+xml`) BEFORE enqueueing to Vision Cascade. Prevents SiliconFlow circuit-breaker from opening on Arxiv batches that contain many inline diagrams.
- [ ] **RIN-05**: `rss_ingest.run()` wraps per-article work in `asyncio.wait_for` with drain + rollback on timeout. On timeout: call `_drain_pending_vision_tasks()` with 120s cap, then `adelete_by_doc_id(article_id)` for partial state cleanup. **Fixes pitfall CP-04**.
- [ ] **RIN-06**: `aget_docs_by_ids` PROCESSED gate preserved from current `rss_ingest.py:184-207` — `enriched=2` is set only after LightRAG confirms the doc reached PROCESSED status (D-19 pattern). Must be retained identically in the rewrite.

#### Cognee (COG) — Day-1 preview round 2 discovery (2026-05-03)

Emergency hotfix 2026-05-03 gates `ingest_wechat.py:1099-1108` inline Cognee call via `OMNIGRAPH_COGNEE_INLINE=0` (default disabled) to unblock Day-1 cron. That hotfix is a **band-aid**; these three REQs restore the dual-store design intent (LightRAG semantic + Cognee episodic) by fixing the LiteLLM routing root cause and hardening the async boundary.

- [ ] **COG-01**: `cognee_wrapper.py:46-50` LiteLLM routing corrected. Current config uses `EMBEDDING_PROVIDER=gemini` (routes to Google AI Studio, `generativelanguage.googleapis.com`) with `EMBEDDING_MODEL=gemini-embedding-2` (Vertex-exclusive GA model). AI Studio returns **422 NOT_FOUND** because `gemini-embedding-2` doesn't exist there — it's only on Vertex global endpoint. Two fix paths; research spike in Phase 20 plan selects one:
  - **(a) Vertex provider** — `EMBEDDING_PROVIDER=vertex_ai` + model path `vertex_ai/gemini-embedding-2` (LiteLLM Vertex provider prefix); requires validating LiteLLM's Vertex auth pathway is compatible with the existing SA JSON + `GOOGLE_APPLICATION_CREDENTIALS` env setup; preserves 3072 dim.
  - **(b) AI Studio fallback** — `EMBEDDING_PROVIDER=gemini` + `EMBEDDING_MODEL=text-embedding-004` (AI Studio-available, 768 dim); simpler but downgrades Cognee embedding dimension and ties Cognee back to free-tier quota.
  
  Recommendation precedence: try (a) first; fall back to (b) only if LiteLLM Vertex auth proves intractable. Dimension implication: if (b), document retrieval-quality delta and consider v3.5 alignment.

- [ ] **COG-02**: Cognee `run_in_background=True` regression mitigation. Observed 2026-05-03 round 2: `cognee.remember(..., run_in_background=True)` does **NOT actually detach** in Cognee 1.0 — the outer `await` blocked the ingest fast-path for articles 5-8 while article 4's 422 retry loop churned. CLAUDE.md design contract says "Cognee is async — never block the ingestion fast-path" — current behavior violates it. Fix: wrap the call in `asyncio.create_task` inside `cognee_wrapper.remember_article` to force detachment at the Python asyncio level, regardless of Cognee's internal behavior. Test: mock `cognee.remember` as a coroutine that sleeps 10s; assert `remember_article` returns within 100ms (true fire-and-forget).

- [ ] **COG-03**: Retire `OMNIGRAPH_COGNEE_INLINE` hotfix env gate. After COG-01 + COG-02 land AND Hermes spot-check confirms dual-store works without blocking ingest (verify via `/tmp/<preview>.log` — articles 5-N continue processing while Cognee tasks run in background), remove the env gate in `ingest_wechat.py:1099-1108` (restore the original unconditional call). Update `CLAUDE.md` env variables table to remove the entry. Document the retirement in a plan SUMMARY + `vertex_ai_smoke_validated.md` memory note. Must complete before CUT-01 cron cutover to avoid shipping the band-aid into production permanently.

---

### Wave 3 — E2E + Stuck-Doc + Backlog + Cutover

#### Stuck-Doc Ops (STK)

- [ ] **STK-01**: **30-minute diagnostic spike** confirms `adelete_by_doc_id` cleanup behavior against **the live LightRAG version installed in the venv**. Spike writes a probe doc, force-transitions it to FAILED/PROCESSING, calls `adelete_by_doc_id`, then inspects all 4 storage layers (`kv_store_doc_status.json`, `kv_store_full_docs.json`, NanoVectorDB `*.json`, Kuzu graph) to verify zero residue. **Resolves Delta 2 confidence gap** (Architecture HIGH vs Pitfalls MEDIUM) BEFORE full CLI implementation.
- [ ] **STK-02**: `scripts/cleanup_stuck_docs.py` CLI removes FAILED/PROCESSING docs via `adelete_by_doc_id`. Includes active-process guard: advisory warning emitted if LightRAG pipeline lock detected busy, but does NOT hard-fail (safe per Architecture's `adelete_by_doc_id` blocks-not-corrupts finding).
- [ ] **STK-03**: CLI outputs structured cleanup report: `{docs_identified: int, docs_deleted: int, docs_skipped: int, skipped_reasons: [...], elapsed_ms: int}` as JSON to stdout. Non-zero exit if any unexpected error; 0 exit on normal "nothing to clean" and on "all cleaned".

#### Backlog Re-Ingest (BKF)

- [ ] **BKF-01**: `python enrichment/rss_ingest.py --backlog --max-articles N` supports **100-article chunks** for the 1020-article backlog. Chunks are serialized (not parallel) per SiliconFlow balance management convention (SVG filter + rate limiting already in place per RIN-04 + RCL-02).
- [ ] **BKF-02**: `--backlog` mode enables **delete-before-reinsert**: for each article where a legacy summary-only doc ID exists in LightRAG, call `adelete_by_doc_id(doc_id)` THEN `ainsert(full_body)`. **Fixes pitfall CP-03** (LightRAG `ainsert` silently skips existing doc IDs → legacy summary-only docs block full-body re-ingest).
- [ ] **BKF-03**: Backlog run is checkpoint-aware — resumes from last completed stage per article using the existing `checkpoints/<hash>/` flat namespace (same 5-stage markers as KOL path, reused per Architecture recommendation).

#### E2E Regression (E2R)

- [ ] **E2R-01**: `test/fixtures/rss_sample_article/` fixture created — a Substack-style RSS article with 2+ images. Mirrors `test/fixtures/gpt55_article/` directory structure: `article.html`, `article.md` (expected extraction), `images/{1,2}.jpg`, `metadata.json` (url, title, expected depth/topics).
- [ ] **E2R-02**: `scripts/bench_rss_ingest.py` mirrors `scripts/bench_ingest_fixture.py` structure. Emits `benchmark_result.json` with the same 9-key schema (`article_hash`, `stage_timings_ms.*`, `counters.*`, `gate_pass: bool`, `errors: []`). Gate: text ingest phase completes in <600s on dev hardware (same threshold as v3.1 E2E-02).
- [ ] **E2R-03**: **Stuck-doc isolation test** — test harness deliberately fails one ingest (mid-Vision crash simulated), runs `cleanup_stuck_docs.py`, then runs the next batch; assert next-batch `benchmark_result.json.gate_pass == true` with zero stuck-doc residue in `kv_store_doc_status.json`. **Validates SC-6**.
- [ ] **E2R-04**: **Cross-arm smoke test** — `orchestrate_daily.step_7_ingest_all` is invoked with `--kol-max 5 --rss-max 5` (or equivalent); both arms succeed; LightRAG graph grows by `≥8 docs` across the two arms (allowing ~20% extraction failure). **Validates SC-2**.

#### Cron Cutover (CUT)

- [ ] **CUT-01**: `scripts/register_phase5_cron.sh` updated — `daily-ingest` cron body switches from OLD `batch_ingest_from_spider.py` (KOL-only) to `orchestrate_daily.step_7_ingest_all` (includes both KOL + RSS arms). Idempotent re-run preserved per existing register-script convention.
- [ ] **CUT-02**: **Kill-switch file** `~/.hermes/.rss-cutover-disabled` — if present (operator creates with `touch`), the cron body skips the RSS arm and falls back to KOL-only. Provides fast rollback without editing crontab. Default: file absent, RSS arm runs.
- [ ] **CUT-03**: Post-rollout observation window **Day-1/2/3 after cutover** documented as milestone close criteria. Cron must fire on all 3 days; RSS digest entries must demonstrate content depth ≥ KOL digest entries (sample retrieval query `"最新 Agent 框架技术动态"` returns RSS content at comparable top-k rank as KOL content). **Validates SC-5**.

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| SCR-01 | Phase 19 | Pending |
| SCR-02 | Phase 19 | Pending |
| SCR-03 | Phase 19 | Pending |
| SCR-04 | Phase 19 | Pending |
| SCR-05 | Phase 19 | Pending |
| SCR-06 | Phase 19 | Pending |
| SCR-07 | Phase 19 | Complete |
| SCH-01 | Phase 19 | Pending |
| SCH-02 | Phase 19 | Pending |
| RCL-01 | Phase 20 | Pending |
| RCL-02 | Phase 20 | Pending |
| RCL-03 | Phase 20 | Pending |
| RIN-01 | Phase 20 | Pending |
| RIN-02 | Phase 20 | Pending |
| RIN-03 | Phase 20 | Pending |
| RIN-04 | Phase 20 | Pending |
| RIN-05 | Phase 20 | Pending |
| RIN-06 | Phase 20 | Pending |
| COG-01 | Phase 20 | Pending |
| COG-02 | Phase 20 | Pending |
| COG-03 | Phase 20 | Pending (depends on COG-01 + COG-02) |
| STK-01 | Phase 21 | Pending |
| STK-02 | Phase 21 | Pending |
| STK-03 | Phase 21 | Pending |
| E2R-01 | Phase 21 | Pending |
| E2R-02 | Phase 21 | Pending |
| BKF-01 | Phase 22 | Pending |
| BKF-02 | Phase 22 | Pending |
| BKF-03 | Phase 22 | Pending |
| E2R-03 | Phase 22 | Pending |
| E2R-04 | Phase 22 | Pending |
| CUT-01 | Phase 22 | Pending |
| CUT-02 | Phase 22 | Pending |
| CUT-03 | Phase 22 | Pending |
---

## Out of Scope (explicit exclusions)

Permanently excluded from v3.4 — do NOT add these during execute without a new milestone / GSD quick:

- **Zhihu 好问 enrichment for RSS** — D-07 REVISED permanent exclusion; KOL-only feature
- **Option D RSS classifier batch refactor** (classify 50 articles / topic in a single LLM call) — deferred; `OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP=500` env cap is the short-term band-aid
- **LLM-based body extraction** (feed full HTML to a model, ask for clean body) — tokens per article + hallucination risk on code blocks; trafilatura is the right tool
- **Site-specific CSS selectors** per RSS source — maintenance hell; selectors break on site redesigns
- **EN→CN translation** in RSS ingest — doubles LLM cost; loses nuance; KOL arm does not translate; skip entirely
- **Duplicate detection beyond URL hash** — URL UNIQUE + LightRAG `filter_keys` is sufficient
- **Cron pre-hook for stuck-doc cleanup** — LightRAG self-heals FAILED docs on next `ainsert` (`lightrag.py:1687-1735`); cron pre-hook would delete retryable docs unnecessarily
- **Parallel / concurrent RSS article ingest** — correctness first; serial batch respects SiliconFlow quota, same pattern as KOL
- **DeepSeek merge phase 600s timeout** — Day-1 E2E leftover, Phase 17 residue; separate follow-up quick
- **WeChat CDP cron-env robustness** — Phase 5 Wave 1 KOL-side issue; not RSS-alignment scope
- **Day-1/2/3 KOL baseline active intervention** — observe only, no fixes until window closes
- **Ingest `ORDER BY` priority change** (FIFO vs today's new-scan first) — `batch_ingest_from_spider.py:1043` currently uses `ORDER BY a.id ASC` + `--max-articles 20` (success-cap), which means **today's fresh KOL scans are starved** whenever the backlog is larger than the daily cap. Legitimate architectural + product decision (is digest a "news of today" or "backfill old reading"?); scope outside v3.4's RSS-KOL alignment. Deferred to v3.5 candidate.
- **Topic-filter keyword plumbing through `_classify_full_body`** — Phase 10 D-10.02's `_build_fullbody_prompt` supports a `topic_filter: list[str]` parameter that injects keyword hints into the classifier prompt, but `batch_ingest_from_spider._classify_full_body:955` calls it with `(title, body)` only — the keyword list is never wired through. Means the current cron's `--topic-filter openclaw,hermes,agent,harness` doesn't reach the classifier (it only filters the post-classify SELECT). Legitimate but separate architecture decision; v3.5 candidate.

---

## Future Requirements (deferred to later milestones)

### v3.5 (candidate — post-cutover stabilization)

- Parallel RSS article ingest (2-3 concurrent) with SiliconFlow balance-aware concurrency control
- Option D full-body RSS classifier batch refactor (50 articles / topic single LLM call)
- Site-specific extractor overrides for high-value sources (e.g., Substack API for known Substacks)
- Retrieval-quality monitoring dashboard (track RSS vs KOL `aquery` rank distribution over time)
- **Ingest ORDER BY priority inversion** — prioritize today's fresh KOL scans over backlog during daily ingest (prevents starvation of today's content in digest when backlog is large; current `ORDER BY a.id ASC` is oldest-first)
- **Topic-filter wiring through `_classify_full_body`** — pass cron's `--topic-filter` keyword list into `_build_fullbody_prompt(topic_filter=...)` so the classifier prompt actually biases toward user-specified keywords
- **Cognee embedding dimension harmonization** — if COG-01 landed path (b) `text-embedding-004` (768 dim), consider whether LightRAG embedding should match or whether mixed-dim dual-store is acceptable (retrieval quality impact study)

### Carry-over follow-ups (independent GSD quicks)

- DeepSeek merge phase 600s timeout resolution (Phase 17 residue)
- WeChat CDP cron-env robustness hardening (Phase 5 Wave 1 residue)

---

*Last updated: 2026-05-03 (Milestone v3.4 requirements defined)*
