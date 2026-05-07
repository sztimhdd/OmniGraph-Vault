# Phase 20: RSS Full-Body Classify + Multimodal Ingest Rewrite + Cognee Routing Fix - Context

**Gathered:** 2026-05-06
**Mode:** YOLO (user delegated discuss + plan to autonomous defaults under principles "simple, easy to maintain, no overengineering")
**Status:** Ready for planning

<domain>
## Phase Boundary

Rewrite the RSS arm to **architectural parity with the KOL arm** (no new capabilities). Three deliverables, locked at REQ level:

1. **RCL-01..03** — `enrichment/rss_classify.py` upgraded from summary-string classify (200-char) to full-body classify (≤8000-char). Reuses Phase 10's `_build_fullbody_prompt` + `_call_fullbody_llm` from `batch_classify_kol.py`. Throttle bumped 0.3s → 4.5s. Writes `rss_articles.{body, body_scraped_at, depth, topics, classify_rationale}` BEFORE any ingest decision (mirrors KOL scrape-first pattern).
2. **RIN-01..06** — `enrichment/rss_ingest.py` rewritten as a 5-stage path identical to KOL: `01_scrape → 02_classify → 03_image_download → 04_text_ingest → 05_vision_worker`. Multimodal `ainsert` via `image_pipeline.localize_markdown` → `lib/lightrag_embedding._build_contents` URL regex. `asyncio.wait_for` ceiling + `_drain_pending_vision_tasks` + `adelete_by_doc_id` rollback on timeout. PROCESSED gate (D-19) preserved verbatim.
3. **COG-02..03** — Validate `cognee.remember(..., run_in_background=True)` actually detaches post-`74f7503` LiteLLM routing fix. If yes: retire `OMNIGRAPH_COGNEE_INLINE` env gate. If no: wrap `cognee_wrapper.remember_article` in `asyncio.create_task` first, then retire.

**Carve-outs (explicitly out of scope, per PROJECT.md and REQUIREMENTS.md "Out of Scope"):**

- Zhihu 好问 enrichment for RSS (D-07 REVISED permanent exclusion)
- Option D RSS classifier batch refactor (`OMNIGRAPH_RSS_CLASSIFY_DAILY_CAP=500` band-aid retained until v3.5)
- Async-drain D-10.09 hang — known architectural issue; Phase 20 must work *around* it, not fix it
- 60s embed vs 1800s LLM timeout asymmetry — v3.5 candidate
- Hermes cron systemd migration — v3.5 candidate
- Stuck-doc CLI (`scripts/cleanup_stuck_docs.py`) — Phase 21
- 1020-article backlog re-ingest — Phase 22
- Cron cutover — Phase 22
- BKF-class scope reduction (e.g., 1020 → 200) — surgical change to REQUIREMENTS at Phase 22 plan time, not now
- Vertex AI for LLM/Vision — Vertex stays embedding-only

</domain>

<decisions>
## Implementation Decisions

### D-RCL-PROMPT-PORT — Import, don't copy

- **D-20.01:** `enrichment/rss_classify.py` **imports** `_build_fullbody_prompt`, `_call_fullbody_llm`, and `FULLBODY_TRUNCATION_CHARS` directly from `batch_classify_kol`. **No literal copy-paste.** Single source of truth; future tweaks to the KOL prompt automatically propagate to RSS.
  - **Why:** The 2026-05-06 quick task `260506-en4` already added `topic_filter: list[str] | None` parameter support to `_build_fullbody_prompt`. Importing inherits that wiring for free; copy-paste would diverge on the next prompt iteration.
  - **How to apply:** `from batch_classify_kol import _build_fullbody_prompt, _call_fullbody_llm, FULLBODY_TRUNCATION_CHARS`. Treat the underscore prefix as a soft signal — these are inter-module helpers within the OmniGraph-Vault project, not public library surface.
- **D-20.02:** RSS classify call shape: `prompt = _build_fullbody_prompt(title, body, topic_filter=topics)` where `topics` comes from existing `--topics` CLI flag normalization in `enrichment/rss_classify.py:_eligible_articles`. Mirrors `batch_ingest_from_spider:1503` caller pattern. **No RSS-specific prompt tweaks** (URL field, source field, EN/CN translation hint) — the prompt is already language-agnostic; D-09 handles CN body translation in `enrichment/rss_ingest.py` BEFORE classify is called.
- **D-20.03:** Throttle constant: `FULLBODY_THROTTLE_SECONDS = 4.5` defined at module level in `enrichment/rss_classify.py` (NOT imported from `batch_classify_kol` — KOL uses its own pacing in a different orchestration loop). DeepSeek 15 RPM ceiling is the binding constraint; `60s / 15 = 4.0s`, `4.5s` adds 12.5% safety margin per RCL-02 spec. `THROTTLE_SECONDS=0.3` line is **deleted** (not kept dual-flag) — single setting per "Simplicity First".
- **D-20.04:** 429 backoff: reuse the existing `lib/scraper.py::_BACKOFF_SCHEDULE_S = (30.0, 60.0, 120.0)` schedule **inline in `_call_fullbody_llm`** (already has DeepSeek error handling); RCL throttle changes do NOT introduce a new backoff function. Cascade after 3 backoff attempts → mark article `enriched=-1` and skip. Mirrors SCR-05 pattern.

### D-RIN-DOC-ID — Keep arms split, don't merge at query layer

- **D-20.05:** RSS doc_id stays `f"rss-{article_id}"` (already in `enrichment/rss_ingest.py:164`). Sub-doc id is `f"rss-{article_id}_images"` (mirrors KOL `wechat_{hash}_images` per Phase 10 ARCH-03). **No query-layer merge** with KOL `wechat_{hash}` — LightRAG's `aquery` already retrieves across all docs regardless of doc_id format; split namespaces are debug-friendly (operator can grep "rss-" vs "wechat_" in logs to attribute regressions).
  - **Why:** Merging would require either renaming all 18 existing wechat_ docs (rolling re-embed, expensive, regression risk) or a translation layer in `kg_synthesize`. Phase 20 stays surgical.
  - **How to apply:** Phase 22 BKF-02 delete-before-reinsert: legacy summary-only doc_id from old code path was also `f"rss-{article_id}"` (verified at `rss_ingest.py:164`) — same key, so `adelete_by_doc_id(f"rss-{id}")` followed by `ainsert(full_body, ids=[f"rss-{id}"])` overwrites cleanly. **Do NOT change the doc_id format**, or BKF-02 becomes a migration job.
- **D-20.06:** Article identity in RSS uses **`article_id` (SQLite primary key)** — NOT a SHA-256 of URL like KOL's `get_article_hash(url)`. Reason: RSS items have a stable monotonic `article_id`; URL hashing would add a layer for zero benefit (RSS dedup is already URL-UNIQUE at the SQL level). KOL uses URL hash because the WeChat path occasionally has stable `article_id` across re-scrapes.

### D-IMAGE-PIPELINE-REUSE — Direct reuse, shared cascade

- **D-20.07:** `enrichment/rss_ingest.py` calls `image_pipeline.localize_markdown(...)`, `image_pipeline.download_images(...)`, `image_pipeline.describe_images(...)` **directly** — same module imports as `ingest_wechat.py`. **No RSS-flavor fork.**
  - **Why:** Vision Cascade circuit-breaker state (`lib/vision_cascade.py`) is module-global per provider — when SiliconFlow returns 503 three times, both arms should pause attempts to that provider, not just one. Forking would silo state and double the breaker storms during real outages.
  - **How to apply:** `from image_pipeline import describe_images, download_images, localize_markdown`. Vision worker code in RSS uses identical pattern to `ingest_wechat._vision_worker_impl` — append sub-doc via `ainsert` with `ids=[f"rss-{id}_images"]`. Per ARCH-03 LOCKED: append-sub-doc, NOT re-embed parent.
- **D-20.08:** RIN-03 Referer header (Substack/Medium/HuggingFace hot-link blocking): **add to `image_pipeline.download_images` itself** (not RSS-specific wrapper) via optional `referer: str | None = None` parameter. KOL callers omit it (default None → no header), RSS callers pass `urlparse(article_url).scheme + "://" + urlparse(article_url).netloc`. One code path, opt-in semantics.
- **D-20.09:** RIN-04 SVG filter: **add to `image_pipeline.download_images`** as a content-type guard (`if response.headers.get("Content-Type", "").startswith("image/svg")`: skip download). Same module-global benefit as D-20.07 — Arxiv batches with inline SVG diagrams won't tank SiliconFlow circuit breaker for either arm.

### D-RIN-05-TIMEOUT-DRAIN — Mirror KOL formula, per-arm tracker

- **D-20.10:** RSS per-article timeout formula: **identical to KOL's Phase 9 formula** `max(120 + 30 * chunk_count, 900)`. Reuse `_compute_article_budget_s` if it's exposed at module scope in `ingest_wechat.py` (per Phase 9 D-09.01 it should be); else inline the formula in `enrichment/rss_ingest.py` with a comment citing this decision.
  - **Why:** Single behavior across arms simplifies operator reasoning ("why did this timeout?"); RSS articles can have wildly varying chunk counts (Arxiv abstract = 1 chunk, Substack longform = 30+) — fixed 1800s ceiling either over- or under-budgets. Formula scales correctly. Phase 9 already battle-tested it on KOL.
- **D-20.11:** `_pending_doc_ids` tracker is **per-module**, NOT shared. KOL's tracker lives in `ingest_wechat` (currently); RSS gets its own tracker dict in `enrichment/rss_ingest`. Reason: tracker keyed by `doc_id` namespace, and the namespaces are split (D-20.05); cross-module shared state would create a debugging nightmare for zero observable benefit. Each arm cleans up its own partial state on rollback.
- **D-20.12:** On `asyncio.TimeoutError`: 1) call `_drain_pending_vision_tasks(article_id, cap_seconds=120)` — best-effort drain so vision sub-doc tasks don't write to a deleted parent; 2) `await rag.adelete_by_doc_id(f"rss-{article_id}")`; 3) leave `enriched` at prior value (NOT `enriched=-1`) so next batch retries. RIN-06 PROCESSED gate already guards against premature `enriched=2` write.

### D-COG-02-VALIDATION — Two-gate validation

- **D-20.13:** **COG-02 merge gate (mock test):** `tests/unit/test_cognee_remember_detaches.py` — mock `cognee.remember` to `await asyncio.sleep(10)` and assert `cognee_wrapper.remember_article(...)` returns within 100ms. **This gate determines whether COG-02 needs an `asyncio.create_task` wrap or whether `run_in_background=True` already suffices post-`74f7503`.**
- **D-20.14:** **COG-03 retirement gate (live Hermes 3-article smoke):** before deleting the `OMNIGRAPH_COGNEE_INLINE=0` env gate from `ingest_wechat.py:1163-1172`, operator runs `OMNIGRAPH_COGNEE_INLINE=1 venv/bin/python batch_ingest_from_spider.py --from-db --topic-filter agent --min-depth 2 --max-articles 3` on Hermes and confirms (a) all 3 articles complete in <30 min total (no 422 retry-loop regression); (b) Cognee episodic store actually grew (`cognee_status` query); (c) ingest fast-path latency unchanged vs gate=0 baseline. **Both gates required** — mock alone is insufficient because LiteLLM retry behavior can differ between mocked sleep and real network 422.
- **D-20.15:** If COG-02 mock test fails (still blocks > 100ms): wrap call site inside `cognee_wrapper.remember_article` in `asyncio.create_task(_inner_remember(...))` and immediately return; let the task fire-and-forget. **Do NOT** add `asyncio.wait_for` around `cognee.remember` — fire-and-forget is the design intent, no caller is waiting on the result.

### D-RIN-CHECKPOINT — Reuse lib/checkpoint.py for RSS

- **D-20.16:** RSS 5-stage checkpoint markers reuse `lib/checkpoint.py` (Phase 12). Stage names mirror KOL: `01_scrape, 02_classify, 03_image_download, 04_text_ingest, 05_vision_worker`. Hash key uses `get_article_hash(url)` (SHA-256[:16] per SCH-02 unification). Single checkpoint namespace covers both arms — `scripts/checkpoint_status.py` lists all without filtering.
  - **Why:** v3.2 Phase 12 explicitly designed `lib/checkpoint.py` to be source-agnostic. Forking would require a parallel CLI tool. Per "Simplicity First."

### Claude's Discretion

The following are left for the planner to decide based on existing code patterns (no user input needed):

- Exact split between `_classify_one_article(...)` helper and the run loop in `enrichment/rss_classify.py` — match whatever pattern the existing module already uses.
- Whether `_build_fullbody_prompt` import goes at module top or inside `_classify_one_article` — module top unless there's a circular-import smell.
- Test file naming: `tests/unit/test_rss_classify_fullbody.py` + `tests/unit/test_rss_ingest_5stage.py` + `tests/unit/test_cognee_remember_detaches.py` (3 new test files); planner picks granularity inside each.
- Logging: stick with module-level `logger = logging.getLogger("rss_ingest")` / `"rss_classify"` per existing pattern; no structured-event format change in this phase.
- Whether RIN-05 timeout wraps the entire `_ingest_one_rss(article)` async function or just the `ainsert + drain` portion — planner picks based on what `ingest_wechat` actually does.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 20 requirements + roadmap context
- `.planning/PROJECT.md` — v3.4 milestone goal + 6 success criteria + carve-outs
- `.planning/REQUIREMENTS.md` §"Wave 2 — RSS Full-Body Classify + Multimodal Ingest" (RCL-01..03 / RIN-01..06 / COG-02..03 + the COG-01 superseded-fix history)
- `.planning/ROADMAP.md` Phase 20 section — 6 success criteria + dependency on Phase 19
- `.planning/STATE.md` — Phase 19 closeout state + execute gate lift rationale (user override 2026-05-06 evening)

### Patterns to port verbatim (KOL arm)
- `batch_classify_kol.py:223-263` — `FULLBODY_TRUNCATION_CHARS` constant + `_build_fullbody_prompt(title, body, topic_filter)` (D-20.01 imports this directly)
- `batch_classify_kol.py:266-368` — `_call_fullbody_llm` provider dispatch (D-20.01 imports this)
- `batch_ingest_from_spider.py:950-1010` — `_classify_full_body` (caller-side reference for how to wire `topic_filter` through; D-20.02 mirrors)
- `batch_ingest_from_spider.py:1115-1145` — KOL parent `ainsert` + `_pending_doc_ids` tracker write + `_vision_worker_impl` `asyncio.create_task` spawn (D-20.10 + D-20.11 mirror this shape)
- `ingest_wechat.py:264-290` — `_pending_doc_ids` tracker contract (D-20.11 forks this pattern per-module)
- `ingest_wechat.py:300-380` — `_vision_worker_impl` reference impl (D-20.07 mirrors with `rss-{id}_images` doc_id)
- `ingest_wechat.py:797-810, 1163-1172` — `OMNIGRAPH_COGNEE_INLINE` env gate (D-20.14 retires this)

### Existing RSS code to rewrite
- `enrichment/rss_ingest.py` — current 324-line summary-only impl; D-20.05/D-20.10/D-20.11/D-20.12 rewrite preserves doc_id `f"rss-{id}"` + PROCESSED gate (lines 184-207)
- `enrichment/rss_classify.py` — current 236-line summary-string classify; D-20.01..04 replace with full-body
- `enrichment/rss_schema.py` — Phase 19 added `body, body_scraped_at, depth, topics, classify_rationale` columns (RCL-03 writes them)

### Multimodal + LightRAG infra (already shipped, reuse only)
- `image_pipeline.py:149-200, 271-289, 388` — `download_images` / `localize_markdown` / `describe_images` (D-20.07/08/09 reuse + minor RIN-03/04 additions)
- `lib/vision_cascade.py` — provider cascade with circuit breaker; reused implicitly via `image_pipeline.describe_images` (D-20.07)
- `lib/lightrag_embedding.py::_build_contents` — multimodal regex `http://localhost:8765/<hash>/<n>.jpg` (D-20.07 explanation: localize_markdown output must match this regex)
- `lib/checkpoint.py` — 5-stage checkpoint markers (D-20.16 reuses)

### Cognee fix (already landed; reference only)
- `cognee_wrapper.py:109-150` — `remember_article` current shape with `run_in_background=True` (D-20.13 mock-tests this, D-20.15 wraps if needed)
- Commit `74f7503` — LiteLLM `gemini/gemini-embedding-2` routing fix (already in main)
- Commit `e2d16e4` — `OMNIGRAPH_COGNEE_INLINE` hotfix env gate (Phase 20 retires)

### Project guidance (always-on)
- `CLAUDE.md` — typo'd data dir `~/.hermes/omonigraph-vault/`, Vision Cascade, checkpoint, Lessons Learned (especially 2026-05-05 entries on cascade + body persistence)
- `CLAUDE.md` "Vertex AI Migration Path" — explains why LLM/Vision stays DeepSeek/SiliconFlow in Phase 20 (only embedding migrated)

### Hermes operator handoff
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md` — SSH details for COG-03 live smoke (D-20.14)
- `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_agent_cron_timeout.md` — `HERMES_CRON_TIMEOUT=28800` workaround context

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (drop-in imports)

- `batch_classify_kol._build_fullbody_prompt` / `_call_fullbody_llm` / `FULLBODY_TRUNCATION_CHARS` — D-20.01 (single source of truth)
- `image_pipeline.{download_images, localize_markdown, describe_images}` — D-20.07 (same shared cascade)
- `lib/checkpoint.{has_stage, mark_stage, get_article_hash}` — D-20.16 (reuse)
- `lib.scraper.scrape_url(url, site_hint=...)` — Phase 19 SCR-06 already wired for KOL; RSS uses `site_hint="generic"` for non-WeChat URLs (Substack/Medium/Arxiv)
- `cognee_wrapper.remember_article` — D-20.13/15 either passes mock test as-is OR gets `asyncio.create_task` wrap

### Established Patterns (preserve)

- **Module-level logger** (`logger = logging.getLogger("module_name")`) — keep
- **Atomic writes** (`.tmp` then `os.replace`) — `enrichment/rss_ingest.py:_atomic_write` already correct; do not change
- **Async fast-path returns BEFORE Vision worker completes** (Phase 10 ARCH-01) — same in RSS
- **PROCESSED gate before `enriched=2` write** (Phase 5 D-19) — preserve verbatim per RIN-06
- **Topic-filter normalization at SQL caller layer** (quick `260506-en4` pattern) — RSS classify mirrors

### Integration Points

- `enrichment/orchestrate_daily.step_7_ingest_all` — Phase 22 cutover target. Phase 20 leaves orchestrator untouched; rewritten `rss_ingest.run(...)` keeps same CLI signature so step_7 wiring doesn't break.
- `data/kol_scan.db` — `rss_articles` already has the 5 new columns from Phase 19 SCH-01. Phase 20 RCL-03 writes them; no schema change in this phase.
- `~/.hermes/omonigraph-vault/lightrag_storage/` — LightRAG store; same instance for both arms (D-20.07 corollary).
- `~/.hermes/omonigraph-vault/checkpoints/<hash>/` — flat namespace per D-20.16; KOL + RSS share.

</code_context>

<specifics>
## Specific Ideas

User-stated principles for Phase 20 (delegated discuss + plan to YOLO):

- **Simple, easy to understand, easy to maintain** — drives "import don't copy" (D-20.01), single-cascade-instance reuse (D-20.07), formula reuse (D-20.10), per-module trackers (D-20.11), checkpoint reuse (D-20.16).
- **Avoid overdesign and overengineering** — drives no new abstractions, no RSS-flavor pipeline forks, no shared cross-module state, no "configurability we don't need." Phase 20 = port + glue, not new architecture.

Concrete commitments captured in decisions:

- "Apples-to-apples Phase 22 cross-arm smoke" — drives prompt-import (D-20.01), formula-share (D-20.10), single-cascade (D-20.07).
- "Phase 22 BKF-02 must not turn into a migration" — drives doc_id format preservation (D-20.05).
- "Operator can grep logs to attribute regressions" — drives split namespaces (D-20.05).
- "Two-gate validation, mock then live" — drives COG-02 / COG-03 separation (D-20.13/14).

</specifics>

<deferred>
## Deferred Ideas

Surfaced during scout/analysis but explicitly NOT in Phase 20 scope:

### To Phase 21
- `scripts/cleanup_stuck_docs.py` CLI (STK-02/03) — Phase 20 leaves stuck docs to LightRAG self-healing on next `ainsert` (per Phase 19 architecture finding); CLI is operational tooling, not Phase 20 correctness.
- 30-min NanoVectorDB cleanup spike (STK-01) — first task of Phase 21.
- RSS E2E fixture `test/fixtures/rss_sample_article/` (E2R-01) + `scripts/bench_rss_ingest.py` (E2R-02) — needs working Phase 20 RSS ingest to capture meaningful fixture; sequencing constraint per ROADMAP.

### To Phase 22
- 1020-article backlog re-ingest with delete-before-reinsert (BKF-01..03)
- `orchestrate_daily.step_7_ingest_all` cutover (CUT-01..03)
- Cross-arm smoke + stuck-doc isolation tests (E2R-03/04)

### To v3.5 (post-cutover)
- Async-drain D-10.09 hang root-cause fix — Phase 20 works around it via `_drain_pending_vision_tasks(cap_seconds=120)`; not architectural fix.
- 60s embed worker timeout vs 1800s LLM timeout asymmetry — image-heavy RSS articles (e.g., Arxiv with 30+ figures) may surface this; Phase 20 acknowledges, does not fix.
- Hermes cron systemd migration — Phase 20 inherits `HERMES_CRON_TIMEOUT=28800` env-var workaround.
- Graded classification (cheap title+excerpt LLM probe pre-scrape) — Phase 20 keeps RSS scrape-first; v3.5 candidate.
- Reject-reason versioning — re-class permanent-fail rows on every cron iteration; deferred.

### Out of milestone v3.4 entirely
- Vertex AI for LLM/Vision (only embedding stays on Vertex) — design frozen in Phase 16 spec, code migration post-v3.4.
- Vertex AI Cognee path (Cognee uses LiteLLM AI Studio routing; Phase 20 verifies this works post-`74f7503` for RSS, no migration to Vertex SDK).

### Reviewed Todos (not folded)
None — `todo match-phase 20` returned 0 matches.

</deferred>

---

*Phase: 20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix*
*Context gathered: 2026-05-06 (YOLO mode under user-stated principles)*
