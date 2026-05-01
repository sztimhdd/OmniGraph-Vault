# Phase 10 — Context (locked decisions derived from 10-PRD.md)

**Mode:** PRD express path — discuss-phase skipped per user request.
**Derived from:** `10-PRD.md` (single source of truth for acceptance criteria).
**Date:** 2026-04-29.

This document codifies the 8 PRD requirements as **locked decisions** (D-10.XX) that plans MUST
reference. Each requirement in the PRD maps 1:1 to a decision below — no interpretation, no
judgment, just a direct restatement for traceability, plus two architectural discretion-resolving
decisions (D-10.09, D-10.10) that the planner pre-decides to prevent downstream drift.

---

## Canonical Refs (MANDATORY)

All plans MUST cross-reference these files when implementing decisions:

| Ref                                                                    | Purpose                                                                    |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `.planning/phases/10-classification-and-ingest-decoupling/10-PRD.md`   | Primary source — acceptance criteria                                       |
| `.planning/REQUIREMENTS.md` (CLASS-01..04, ARCH-01..04)                | Milestone v3.1 traceability matrix                                         |
| `.planning/ROADMAP.md` (Phase 10 success criteria)                     | Phase-level observable truths                                              |
| `.planning/phases/09-timeout-state-management/09-CONTEXT.md`           | Dependency — D-09.05 doc_id registry + D-09.07 `get_rag(flush)` contract   |
| `.planning/phases/09-timeout-state-management/09-01-SUMMARY.md`        | Post-Phase-9 state: rollback, ids=[doc_id] at ainsert, 12 tests guarding   |
| `ingest_wechat.py` (lines 580–810: `ingest_article`; 168–187: registry)| ARCH-01 split target; D-09.05 registry already in place                    |
| `batch_ingest_from_spider.py` (lines 109–169: `ingest_article` wrapper)| CLASS-01 integration point; rollback handler already wired                 |
| `batch_classify_kol.py` (lines 168–216: prompt builder + `_call_deepseek`) | CLASS-02 prompt reuse — extend to accept full body not digest/title   |
| `spiders/wechat_spider.py` (lines 22–50: rate limit constants)         | CLASS-03 anti-abuse params — reuse, do NOT invent new                      |
| `image_pipeline.py` (lines 371+: `describe_images`; 83: `emit_batch_complete`) | ARCH-02 Vision worker target; provider cascade unchanged              |
| `data/kol_scan.db` — `articles` + `classifications` tables             | CLASS-04 persistence target (existing schema)                              |
| `tests/unit/test_rollback_on_timeout.py` (Phase 9 pattern)             | Async test pattern template — MagicMock + AsyncMock for rag mock           |

---

## Locked Decisions

### D-10.01 — Scrape before classify (CLASS-01)

- **Decision:** `batch_ingest_from_spider.py --from-db` (and `run` batch path) MUST scrape the
  full article body BEFORE classification. The WeChat `digest` field is NO LONGER consulted as
  classifier input.
- **Rationale:** Empirically `digest=N/A` for the v3.1 gate fixture (gpt55_article) and truncated/
  ad-laden in random samples. Classifier decisions based on digest produce depth=3 false positives.
- **Implementation constraint:** When the `articles.body` column is empty for a pending article,
  scrape on-demand via `spiders.wechat_spider` (NOT via `ingest_wechat.scrape_wechat_ua` — that
  path couples to LightRAG init). The scraped body is written back to `articles.body` (adding
  the column if absent — idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS body TEXT` at init_db)
  OR held in-memory for the current run.
- **Plan:** 10-00.
- **Verification:** unit test passes a fake DB row with `digest=""` + stubbed scraper returning
  full body → classifier receives body, not digest → returns depth≠3 for news fixture.

### D-10.02 — DeepSeek classifies on full body (CLASS-02)

- **Decision:** DeepSeek is called with the FULL article text (not digest, not title-only) and
  MUST return `{depth: 1-3, topics: [...], rationale: str}`. The prompt shape reuses
  `batch_classify_kol._build_prompt` pattern but feeds full body in place of the `[digest: ...]`
  suffix.
- **Prompt adjustment:** drop the `[digest: <200 chars>]` annotation; instead send the body text
  truncated to a reasonable LLM budget (planner picks truncation — suggest 8000 chars per
  article as the upper bound to avoid DeepSeek context blowup across a batch). Single-article
  calls SHOULD NOT truncate below 8000 chars.
- **JSON schema change:** prompt now requires `topics: [string, ...]` array (not boolean
  `relevant`). This is additive — existing `relevant`-using callers (`batch_classify_kol.run`
  for batch-scan) stay unchanged; the scrape-first path uses the new topics-array shape and
  writes `topics` as JSON-serialized to the SQLite column.
- **Plan:** 10-00.
- **Verification:** unit test passes fixture GPT-5.5 news article full body to a stubbed
  DeepSeek → asserts prompt includes body substring (not digest) AND parsed result has `depth`,
  `topics` (list), `rationale` keys. Live test against real DeepSeek deferred to Phase 11.

### D-10.03 — Reuse existing WeChat anti-abuse params (CLASS-03)

- **Decision:** Scrape phase MUST reuse existing constants from `spiders/wechat_spider.py`:
  - `SESSION_REQUEST_LIMIT = 50` (aka "54" in PRD — treat existing 50 as canonical; PRD allows
    batch path to drift to 54 but local-fixture gate does not exercise)
  - `RATE_LIMIT_SLEEP_ACCOUNTS = 5.0`
  - `RATE_LIMIT_COOLDOWN = 60.0`
  - Existing rotating `_UA_POOL` + `_ua_cooldown()` in `ingest_wechat.py` — treat as ALREADY
    spec-compliant (Phase 5-00c established the UA rotation pattern)
- **Implementation constraint:** Do NOT invent new rate-limit parameters. Do NOT add per-article
  delay constants beyond what `wechat_spider` already exposes. If scrape-on-demand needs
  additional per-article throttling, REUSE `_ua_cooldown()` which is already 3–8s random + 40-req
  session cap.
- **v3.1 gate scope:** Local fixture path does NOT exercise WeChat rate limits. This REQ is
  spec-correctness only — the BATCH path (Phase 5 RSS/KOL automation) will invoke it and is
  where the regression risk lies.
- **Plan:** 10-00.
- **Verification:** source-grep test asserts `batch_ingest_from_spider` imports
  `RATE_LIMIT_SLEEP_ACCOUNTS`, `RATE_LIMIT_COOLDOWN`, `SESSION_REQUEST_LIMIT` from
  `spiders.wechat_spider` (or that scrape-on-demand reuses `_ua_cooldown` from ingest_wechat)
  AND that no new rate-limit constants are introduced.

### D-10.04 — Persist classifier output to SQLite (CLASS-04)

- **Decision:** The `classifications` table MUST receive a row with `article_id`, `depth`,
  `topics` (JSON-serialized list), `rationale`, `classified_at` BEFORE the ingest decision is
  made. Existing schema is close but uses `depth_score` + `topic` (single) + `reason` —
  planner MUST decide: either (a) add NEW columns `depth INTEGER`, `topics TEXT`, `rationale
  TEXT` alongside the old `depth_score`/`topic`/`reason` (backward-compatible), OR (b)
  `ALTER TABLE` to rename (breaking — requires migration).
- **Plan picks (a) — additive columns.** Rationale: existing `batch_classify_kol.run` still
  writes to the old columns for batch-scan use case; breaking them ripples to Phase 5 plans.
  New columns `depth`, `topics`, `rationale`, `classified_at` (already present as
  `classified_at`) are added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` guards.
- **Classification persistence ordering (STRICT):** scrape → classify → INSERT INTO
  classifications → THEN ingest decision. If classification write fails, SKIP ingest (do NOT
  silently pass-through). The one exception — if DeepSeek API call fails, fail the article
  (log + skip). No fail-open behavior on classify errors for the scrape-first path
  (distinguishes from existing `batch_classify_articles` fail-open which is fine for batch-scan).
- **Plan:** 10-00.
- **Verification:** unit test simulates full flow with mocked scraper + mocked DeepSeek, asserts
  `classifications` row exists with all 4 fields populated, and that an exception in the
  classify call prevents the `ingestions` row from being written.

### D-10.05 — Text ingest synchronous-fast (ARCH-01)

- **Decision:** `ingest_wechat.ingest_article(url, rag)` MUST return successfully AFTER
  `rag.ainsert(full_content, ids=[doc_id])` completes — with NO Vision API call blocking this
  return path. The image pipeline (`download_images`, `filter_small_images`, `describe_images`)
  is RE-ORDERED so that:
  1. `download_images` runs synchronously (fast — HTTP I/O only, no LLM)
  2. `filter_small_images` runs synchronously (fast — PIL local reads)
  3. Markdown body (with localized image URLs but WITHOUT descriptions) is `ainsert`-ed
  4. `ingest_article` schedules the Vision worker (D-10.06) via `asyncio.create_task()` and
     RETURNS the task handle (for test awaiting) but does NOT await it in production
- **Content shape change:** the synchronously-ainserted `full_content` no longer contains
  `[Image N Description]: <desc>` lines. It contains only `[Image N Reference]: <local_url>`
  lines (the image local URLs, no descriptions). Descriptions arrive via the sub-doc (D-10.07).
- **Return type change:** `ingest_article` currently returns `None`; under Phase 10 it MUST
  return `asyncio.Task | None` (Task when Vision worker was spawned; None when zero images or
  error-before-spawn). The batch orchestrator in `batch_ingest_from_spider.ingest_article` does
  NOT await the returned task — it lets it fire-and-forget. Tests MAY await the returned task
  to deterministically observe sub-doc insertion.
- **Plan:** 10-01.
- **Verification:** unit test times `await ingest_article(url, rag=mock_rag)` end-to-end while
  `describe_images` is a mock that sleeps 60 seconds — assertion: `ingest_article` returns in
  under 5 seconds (no await on the Vision worker). Returned value is an `asyncio.Task` if
  images were present.

### D-10.06 — Async Vision worker (ARCH-02)

- **Decision:** After `rag.ainsert` returns (text ingest), a background async worker is spawned
  via `asyncio.create_task(_vision_worker(...))`. The worker:
  1. Calls `describe_images(paths)` (existing image_pipeline function — unchanged signature)
  2. Builds the sub-doc markdown per D-10.07
  3. Calls `rag.ainsert(sub_doc_content, ids=[f"wechat_{article_hash}_images"])`
  4. Emits the existing `emit_batch_complete` aggregate log
  5. Returns; task completion is observable but not required for the parent to succeed
- **Worker location:** NEW function `_vision_worker_impl` MUST live in `ingest_wechat.py`
  (co-located with `ingest_article`). Do NOT put it in `image_pipeline.py` — that module is
  pipeline-stage-scoped and rag-agnostic. The worker closes over `rag`, `article_hash`,
  `url_to_path`, `title` — passed explicitly as kwargs (not via closure capture from the outer
  function to keep the worker testable in isolation).
- **Task handle:** `ingest_article` returns the `asyncio.Task` object so orchestrators/tests
  can optionally `await task`. Production `batch_ingest_from_spider.ingest_article` does NOT
  await. Process-exit leak prevention: the batch orchestrator's `finally` block MAY gather
  pending tasks via `asyncio.all_tasks(asyncio.get_running_loop())` and await them with a
  short timeout (planner decides — suggested 60s aggregate deadline across all pending Vision
  tasks at batch end) before calling `rag.finalize_storages()`.
- **Plan:** 10-02.
- **Verification:** unit test 1 — asserts `ingest_article` returns an `asyncio.Task` when
  images are present. Unit test 2 — awaits the task, asserts `rag.ainsert` was called twice
  (once for main body, once for sub-doc). Unit test 3 — asserts the main-body ainsert call
  completes BEFORE the sub-doc ainsert call (ordering).

### D-10.07 — Append sub-doc, NOT re-embed (ARCH-03) — LOCKED by PRD

- **Decision:** LOCKED by PRD § ARCH-03 — planner MUST NOT revisit this architectural choice.
  Vision-generated image descriptions are linked to the graph by **appending an image sub-doc
  via `ainsert`** (one sub-doc per article, NOT per image). Planner is NOT permitted to
  propose re-embed, edge-update, or node-patch alternatives.
- **Sub-doc `doc_id`:** `f"wechat_{article_hash}_images"` (PRD-specified — do NOT drift to
  alternatives like `_img` or `_vision` suffixes).
- **Parent `doc_id`:** `f"wechat_{article_hash}"` (established Phase 9 — D-09.05 / STATE-02,
  already in place in `ingest_wechat.py:626, 751`).
- **Sub-doc content shape (PRD-specified, copy verbatim):**
  ```
  # Images for <title>

  - [image 0]: <description>
  - [image 1]: <description>
  ...
  ```
  where `<title>` is the article title (D-09.05 `article_hash` already provides identity) and
  `[image N]: <description>` is a markdown list item per successfully-described image.
- **Failed images in sub-doc:** images where `describe_images` returned empty string or raised
  (captured as empty in the returned dict) are OMITTED from the sub-doc entirely — do NOT
  emit `[image N]: <error: ...>` lines. Rationale: sub-doc exists to ADD retrieval signal;
  empty/error descriptions degrade retrieval.
- **Empty sub-doc handling:** if zero images described successfully (all failed OR no images
  to begin with), the worker MUST NOT call `rag.ainsert` for the sub-doc. Log an info line
  `vision_subdoc_skipped article_hash=... reason=<no_images|all_failed>` and return. The
  parent doc is queryable regardless per ARCH-04.
- **Plan:** 10-02.
- **Verification:** unit test mocks `describe_images` to return `{Path("a.jpg"): "desc A",
  Path("b.jpg"): ""}` (one success, one empty) → asserts sub-doc ainsert called once, content
  contains `[image 0]: desc A` and does NOT contain `[image 1]`. Second test: all empty →
  asserts sub-doc ainsert NOT called.

### D-10.08 — Vision failure does not invalidate text ingest (ARCH-04)

- **Decision:** `_vision_worker_impl` MUST wrap its entire body in `try/except Exception`.
  Exceptions do NOT propagate to the caller. The worker logs structured failure via
  `emit_batch_complete(describe_stats={"provider_mix": {"vision_error": N}, ...})` and
  returns normally.
- **Scope of swallowing:** ALL exceptions from `describe_images`, `rag.ainsert` (of the
  sub-doc), and any intermediate I/O are swallowed. This is deliberately broader than
  Phase 9's rollback behavior — Phase 9 rolls back parent doc on timeout; Phase 10's Vision
  worker failure NEVER rolls back the parent (parent ainsert already returned successfully
  by the time the worker runs).
- **Rollback asymmetry:** the sub-doc has its OWN `doc_id` separate from the parent. If
  sub-doc ainsert partially fails (unlikely — sub-doc is single markdown string, small), the
  worker MAY call `rag.adelete_by_doc_id(f"wechat_{article_hash}_images")` to clean up, but
  this is optional given sub-doc scope. Planner SHOULD implement this as belt-and-suspenders
  but it is NOT a gating criterion.
- **Plan:** 10-02.
- **Verification:** unit test mocks `describe_images` to raise `RuntimeError("all providers
  down")` → awaits the worker → asserts the worker returns None (no exception propagates) AND
  asserts the parent doc's ainsert succeeded before the worker ran. Second test: mock
  `rag.ainsert` to raise on sub-doc call (second call) → worker still returns None.

### D-10.09 — Async task return + orchestrator awaiting (architectural discretion)

- **Decision (pre-resolved by planner):** `ingest_article` returns the Vision worker task
  handle (`asyncio.Task | None`). Tests await the task explicitly to observe sub-doc
  insertion. Production orchestrator (`batch_ingest_from_spider.ingest_article`) does NOT
  await — lets Vision work run in the background.
- **Batch-end hygiene:** before `rag.finalize_storages()` in `batch_ingest_from_spider.run` /
  `.ingest_from_db`, the orchestrator MUST gather any still-pending Vision tasks on the event
  loop and await them with an aggregate deadline (suggested 120s total). Rationale: if
  `finalize_storages` runs while a Vision worker is mid-`ainsert` for a sub-doc, the sub-doc
  insertion may be lost or corrupt.
- **Implementation sketch:**
  ```python
  # In batch_ingest_from_spider, after the for-loop, before finalize_storages:
  pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
  if pending:
      try:
          await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=120)
      except asyncio.TimeoutError:
          logger.warning("Vision worker drain timeout — %d tasks still pending", len(pending))
  ```
- **Test implications:** tests using a module-level mocked `rag` MUST await the returned task
  from `ingest_article` before asserting on `rag.ainsert.call_args_list`. Pattern goes in each
  test — no global fixture needed.
- **Plan:** 10-01 establishes the return type; 10-02 wires the orchestrator drain.

### D-10.10 — Scrape-on-demand integration with existing `ingest_article` flow (architectural discretion)

- **Decision (pre-resolved by planner):** The scrape-first classifier pre-flight in
  `batch_ingest_from_spider.ingest_from_db` runs BEFORE the existing
  `await asyncio.wait_for(ingest_wechat.ingest_article(url, rag=rag), timeout=...)` call. The
  pre-flight:
  1. Checks `articles.body` column for existing scraped content
  2. If empty, invokes scrape (reusing `ingest_wechat.scrape_wechat_ua` directly — NOT a
     duplicate scraper), writes body to `articles.body` column
  3. Calls classifier with full body
  4. Persists classification (D-10.04)
  5. ONLY IF depth ≥ min_depth AND topics passes filter → proceeds to `ingest_wechat.ingest_article`
  6. `ingest_wechat.ingest_article` itself uses its EXISTING cache path (`final_content.md`) —
     the pre-flight scrape does NOT pollute that cache. Planner MAY opportunistically share
     the scrape result by writing it to the ingest_wechat cache, but it is NOT required.
- **Rationale:** Keeps `ingest_wechat.ingest_article` unchanged for single-URL CLI callers
  (e.g., `python ingest_wechat.py <url>` which has no pre-scrape step — goes straight through
  its existing scrape+ingest flow). The pre-flight lives in the batch orchestrator.
- **Trade-off:** an article scraped twice in one batch invocation (once for classify, once
  inside ingest) wastes one HTTP round-trip per article. Acceptable for Phase 10 — single-
  article v3.1 gate is the priority. Planner MAY resolve this in Phase 11 by hooking the
  cache write into the pre-flight.
- **Plan:** 10-00.

---

## Out of Scope (defer to later phases)

Per PRD § "Out of Scope":

- Checkpoint/resume of Vision worker across crashes (v3.2)
- Vision provider circuit breaker (v3.2 — current cascade form retained)
- Removing Gemini Vision entirely (keep as last-resort fallback)
- Multimodal embedding changes (Gemini embedding-2 stays)
- Phase 5-00b full re-run on Hermes (Phase 5 owns that)
- Vertex AI migration (v3.3)
- End-to-end benchmark with real LightRAG + real NanoVectorDB (Phase 11)

---

## Deferred Ideas (for future phases — DO NOT implement in Phase 10 plans)

- Smarter topic extraction (hierarchical, multi-label with confidence) — v3.2 if retrieval
  shows flat-list topics are insufficient for routing
- Scrape-cache sharing between pre-flight classifier and `ingest_article` proper — Phase 11
  opportunity; not load-bearing for v3.1 gate
- Vision worker priority queue (describe-most-important-image-first) — v3.2 if worker
  latency becomes user-visible
- Sub-doc embedding optimization (separate embed func for image descriptions vs text) —
  never; Gemini embedding-2 multimodal is load-bearing

---

## Claude's Discretion

Decisions intentionally left to the planner/implementer:

1. **DeepSeek full-body prompt length:** truncation budget (suggested 8000 chars; planner may
   raise/lower based on DeepSeek token budget in requirements.txt).
2. **`classifications` table schema migration:** add columns additively via
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` vs creating a new `classifications_v2` table.
   D-10.04 picks additive; planner confirms ALTER TABLE works (LightRAG/sqlite3 standard).
3. **Vision worker closure vs kwargs:** D-10.06 specifies kwargs-passed; planner confirms no
   hidden closure capture from `ingest_article` scope (testability).
4. **Batch-end drain timeout:** D-10.09 suggests 120s aggregate; planner picks and documents.
5. **Sub-doc rollback on partial failure:** D-10.08 makes optional; planner picks and documents.
6. **Test file organization:** extend existing `test_rollback_on_timeout.py` for async task
   patterns, or create `test_classification_flow.py` + `test_vision_worker.py` — planner picks
   per single-responsibility.

---

## Success Criteria Reference

All 7 success criteria from `10-PRD.md` § "Success Criteria for Phase 10" are inherited
verbatim. Plans validate against them:

1. Classifier reads full body (D-10.01, D-10.02 → Plan 10-00)
2. `classifications` row persisted (D-10.04 → Plan 10-00)
3. Text ingest <20s on local fixture (D-10.05 → Plan 10-01)
4. Image sub-doc queryable via `aquery` (D-10.06, D-10.07 → Plan 10-02)
5. Vision failure → text ingest still succeeds + failure logged (D-10.08 → Plan 10-02)
6. No leaked tasks at process exit (D-10.09 → Plan 10-02 orchestrator drain)
7. Phase 8 + Phase 9 regression green (both plans — verification gate)

---

*Generated: 2026-04-29 — PRD express path, autonomous overnight execution.*
