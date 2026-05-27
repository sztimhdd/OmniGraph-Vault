# T3 — batch_ingest_from_spider.py Deep Review

**Generated:** 2026-05-11 ADT
**File:** `batch_ingest_from_spider.py` — 2035 LOC, last touch `a66622c` (260510-uai source-aware dispatch)
**Audit budget:** 3-5h target, completed under budget (read-only single-pass).
**Auditor scope:** read-only / no business code edits / no Hermes SSH.

---

## TL;DR

| Severity | Count | Notes |
|----------|-------|-------|
| HIGH | **0** | No release blocker. No silent-fail or status-mislabel found. Already-audited regions (W2/W3/p1n/h09/rl2/b3y) verified intact. |
| MEDIUM | **3** | Dead-in-production code (~570 LOC, 28% of file), legacy `run()` path divergence, lib→app `config` import inversion (small, isolated). |
| LOW | **4** | Marker hygiene, late-import locality, `nonlocal` capture in nested coroutine, log-format restoration coupling. |
| Cross-cutting | 1 | F-2 (lib→app inversion) extends beyond batch_ingest into 4 lib modules — finding listed once here, evidence in §4. |

**Estimated cleanup:** **2-4 h across 2 quicks** (one ~1-2h dead-code purge, one ~1h `config` import flatten — both low-risk).

**Release verdict:** **CLEAR** ✅
- HIGH = 0
- MEDIUM = 3 — none are release blockers; all are hygiene / pollution-debt issues. Production cron path (`ingest_from_db` via `--from-db`) is healthy.
- Recommendation: **ship release now**, file MEDIUMs as backlog quicks for post-release hygiene.

---

## 1. File sectional map

26 functions / 2035 LOC. ⚠ marks **god functions** (>100 LOC); ✓ marks already-audited.

| Lines | LOC | Function | Purpose |
|------:|----:|----------|---------|
| 125 | 27 | `_drain_pending_vision_tasks` ✓ | Delegates to `lib.vision_tracking.drain_vision_tasks` (260509-p1n).  |
| 152 | 27 | `_compute_article_budget_s` | `max(120 + 30·chunks, 900)` — per-article budget. |
| 179 | 8 | `_bucket_article_time` | Histogram bucket lookup. |
| 187 | 18 | `_resolve_batch_timeout` | CLI vs `OMNIGRAPH_BATCH_TIMEOUT_SEC` resolution. |
| 205 | 32 | `_build_batch_timeout_metrics` | Builds the metrics JSON. |
| 237 | 99 | `ingest_article` | Single-article wrapper around `ingest_wechat.ingest_article` with `asyncio.wait_for` + STATE-02 rollback. |
| 336 | 28 | `_ensure_fullbody_columns` | Schema-additive migration for `articles.body`. |
| 364 | 27 | `_load_hermes_env` | Lazy `~/.hermes/.env` loader. |
| 391 | 30 | `get_deepseek_api_key` | 3-tier fallback (env → .env → config.yaml). |
| 421 | 68 | `_build_filter_prompt` | (legacy `run()` path) DeepSeek title-classify prompt. |
| 489 | 45 | `_call_deepseek` | (legacy `run()` path) HTTP POST to DeepSeek. |
| 534 | 18 | `_call_gemini` | (legacy `run()` path) `generate_sync` wrapper. |
| 552 | **102** ⚠ | `batch_classify_articles` | (legacy `run()` path) Title-only classifier — superseded by Layer 1/2 in `lib.article_filter`. |
| 654 | 35 | `print_filter_summary` | (legacy `run()` path) summary stdout table. |
| 689 | **232** ⚠ | `run` | (legacy) account-scan → classify → ingest path; **NOT** invoked by production cron. |
| 921 | 25 | `_needs_scrape` | KOL: scrape iff body empty; RSS: scrape iff body short (<100). |
| 946 | 50 | `_persist_scraped_body` | BODY-01 atomic body write, source-dispatched. |
| 996 | **104** ⚠ | `_classify_full_body` | (orphaned) Per-article scrape+classify; superseded by `lib.article_filter.layer2_full_body_score` in `_drain_layer2_queue`. Only exercised by tests. |
| 1100 | 65 | `_graded_probe_prompts` | (graded MVP, default OFF) prompt builder. |
| 1165 | 12 | `_parse_probe_json` | (graded MVP) parse helper. |
| 1177 | 50 | `_graded_probe_deepseek` | (graded MVP) DeepSeek path. |
| 1227 | 69 | `_graded_probe_vertex` | (graded MVP) Vertex path. |
| 1296 | 50 | `_graded_probe` | (graded MVP) dispatcher. |
| 1346 | **97** ✓ | `_build_topic_filter_query` | Candidate SELECT — already audited W2 (`42a1b79`); 22+ unit tests. |
| 1443 | **531** ⚠⚠ | `ingest_from_db` | **Production main loop.** Layer 1 batch → per-article scrape → Layer 2 batch drain → ainsert. Contains nested `_drain_layer2_queue` coroutine (87 LOC) declared inside the function. |
| 1974 | 62 | `main` | argparse + dispatcher to `run` or `ingest_from_db`. |

**Production-active path** (cron via `enrichment/orchestrate_daily.py:197` → `--from-db`): only `ingest_from_db` (and the helpers it calls) is live in cron. Everything in the legacy `run()` chain (`run`, `batch_classify_articles`, `_call_deepseek`, `_call_gemini`, `_build_filter_prompt`, `print_filter_summary`) is dead-on-default-config.

---

## 2. CLAUDE.md "Lessons Learned" cross-reference

| Lesson | Status | Evidence (file:line) | Notes |
|--------|--------|----------------------|-------|
| 2026-05-04 #3 — schema CHECK vs INSERT value drift | **fixed** | `batch_ingest_from_spider.py:1486-1494` whitelist `('ok', 'failed', 'skipped', 'skipped_ingested', 'dry_run', 'skipped_graded')` matches all 7 INSERT sites (1576/1701/1752/1798/1810/1828/1852). | Verified: every status literal that appears in INSERT statements is in the CHECK whitelist. |
| 2026-05-05 #2 — scrape-first classify has irreducible Apify waste on filter-rejected | **partial** | Graded probe at `:1840-1856` is the v3.5 MVP fix. Default `OMNIGRAPH_GRADED_CLASSIFY=0` (line 1840) means production cron still pays scrape-then-reject cost. | v3.5 backlog — intentional gating per design. |
| 2026-05-05 #3 — verify ingest progress from DB, not in-process counter | **applicable / not violated** | All status writes go to `ingestions` table (7 INSERT sites). In-process counters (`processed`, `completed_times`) feed metrics but are write-only. | DB is authoritative across the file. |
| 2026-05-05 #4 — half-fix pattern: producer↔consumer data shape changes need joint grep | **fixed** | `:1041-1053` reads BOTH `scraped.markdown` and `scraped.content_html` (the 2026-05-05 SCR-06 fix); same dual-key handling at `_persist_scraped_body:978`. | Verified consumer side honors both keys. |
| 2026-05-05 #5 — body atomic persist at scrape moment, before downstream gate | **fixed** | `_persist_scraped_body:946-993` writes body **before** Layer 2 verdict; called at `:1883` during the per-article loop, not after Layer 2. SQL guard `body IS NULL OR length(body) < 500` (`:983`) is race-safe. | Correct ordering preserved. |
| 2026-05-05 #6 — DB candidate SELECT didn't exclude `status='skipped'` | **fixed (W2)** | `_build_topic_filter_query:1406-1408` and `:1426-1428` exclude rows whose `skip_reason_version = SKIP_REASON_VERSION_CURRENT (=1)`. | Cite quick `260509-s29 W2` (`42a1b79`). |
| 2026-05-07 #1 — schema/SQL changes need production-shape simulation | **applicable / not violated** | `classifications` UPSERT at `:1077-1086` uses `ON CONFLICT(article_id, topic)` — the post-2026-05-07 reverted form. The companion `idx_classifications_article_id` single-col UNIQUE was dropped by migration 005. | Regression discipline preserved. NOTE: this code lives in `_classify_full_body` which is dead in production — the test-only path still exercises it. |
| 2026-05-07 #2 — migration reverse must come with INSERT call site reverse | **fixed (commit `428b16f`)** | Same `ON CONFLICT(article_id, topic)` form at `:1081`. | No drift. |

**No regressions** found in any of the 8 lessons against the current `batch_ingest_from_spider.py`.

---

## 3. Findings by severity

### HIGH (release blocker / bound to break)

**No findings.** No silent-fail, no status-mislabel, no schema-INSERT drift, no producer↔consumer mismatch, no async task escape, no SQL injection. Production cron path is intact.

### MEDIUM (real but not urgent)

#### M-1 — Dead-in-production code (~570 LOC, ~28% of file)

**Evidence:**
- `enrichment/orchestrate_daily.py:195-205` invokes `batch_ingest_from_spider.py --from-db ...` → routes to `ingest_from_db()` (`:1443`).
- `main()` at `:1974-2031` only branches into `run()` (`:689`, legacy account-scan) when `--from-db` is **not** set. No production caller passes `--from-db=False`.
- The following are reachable only via the legacy `run()` branch (or tests):
  - `run` (`:689-920`, 232 LOC) — legacy entrypoint
  - `batch_classify_articles` (`:552-651`, 102 LOC) — title-only classifier, superseded by `lib.article_filter` Layer 1/2
  - `_build_filter_prompt` (`:421-488`, 68 LOC) — used only by `batch_classify_articles`
  - `_call_deepseek` (`:489-533`, 45 LOC) — used only by `batch_classify_articles`
  - `_call_gemini` (`:534-551`, 18 LOC) — used only by `batch_classify_articles`
  - `print_filter_summary` (`:654-688`, 35 LOC) — used only by `run()`
  - `_classify_full_body` (`:996-1099`, 104 LOC) — orphaned; ir-4 PLAN explicitly stated `LF-5.1: Delete _classify_full_body` (`.planning/phases/ir-4-rss-integration-and-cleanup/ir-4-PLAN.md:31`) but the LOC is still in the file. Now only exercised by tests `test_scrape_first_classify.py`, `test_classify_full_body_topic_hint.py`, `test_batch_ingest_hash.py`, `test_scrape_on_demand_apify_markdown.py` — they are essentially testing a dead function.

**Why MEDIUM, not HIGH:** code is reachable (CLI flag exists), so it's not strictly garbage; it just isn't invoked by any cron / orchestrator / runbook. Present `_classify_full_body` is referenced by 5 test files — deletion needs coordinated test removal.

**Why not LOW:** at 28% of file, it inflates every grep, every line-count, every cognitive read, and (per the 2026-05-08 #1 cascade-divergence lesson) any future edit to `lib.scraper.scrape_url` shape MUST also touch the dead `_classify_full_body:1041` site, costing real audit time forever.

**Fix scope:** ~570 LOC delete + 4 test file cleanups + 1 ir-4 PLAN docs amendment. Quick type: `dead-code-purge`. Risk: low (run codebase-wide grep for each function name pre-delete; production cron does not invoke them; W2 test suite covers `--from-db` regression). Estimated effort: 1-2 h.

**Maps to:** prior-existing **F-3 / ir-4 LF-5.1** (already on backlog).

#### M-2 — `run()` legacy path diverges from `ingest_from_db()` invariants

**Evidence:**
- `run()` at `:689-920` and `ingest_from_db()` at `:1443-1973` both contain duplicated state-setup blocks for the batch-budget interlock:
  - `:771-779` (run) ≈ `:1614-1622` (ingest_from_db) — `total_batch_budget`, `batch_start`, `completed_times`, `timeout_histogram`, `timed_out_count`, `clamped_count`, `safety_margin_triggered`.
  - `:863-868` (run) ≈ `:1945-1950` (ingest_from_db) — `finally: rag.finalize_storages()` + drain.
  - `:870-888` (run) ≈ `:1952-1970` (ingest_from_db) — metrics emit + JSON write.
  - `:828-841` (run) ≈ `:1736-1749` (ingest_from_db inside `_drain_layer2_queue`) — `success/doc_confirmed → status` mapping.
- `run()` does NOT use `skip_reason_version` because it doesn't write to `ingestions` (it writes to a JSON summary file, `coldstart_run_*.json`). `ingest_from_db()` writes to `ingestions` with W2 `skip_reason_version`.
- `run()` uses `_SINGLE_CHUNK_FLOOR_S` (900s flat), `ingest_from_db()` uses `_compute_article_budget_s(body)` (1620s for 50-chunk articles, per the 2026-05-08 fix). If `run()` were ever resurrected for a long article, it would timeout.

**Why MEDIUM:** divergent invariants in two paths means any new lesson learned (like the 2026-05-08 budget-scaling) only gets applied to `ingest_from_db()`. Future operator who runs `run()` interactively gets the unfixed path. Latent footgun.

**Fix scope:** depends on whether `run()` is ever needed again. If M-1 ships (delete legacy paths), this collapses. If `run()` stays, factor budget/finalize/metrics into a shared helper. Quick type: depends on M-1 outcome. Estimated effort: subsumed by M-1 (0 h additional) OR ~1 h refactor if M-1 deferred.

**Maps to:** **F-1 (cascade/duplicate logic)** — proposed in user's framing; this is the in-file duplicate.

#### M-3 — `lib/*` modules import from root-level `config.py` (lib→app inversion)

**Evidence:** `from config import ...` appears in 4 `lib/` modules:
- `lib/checkpoint.py:23` — `from config import BASE_DIR as _CONFIG_BASE_DIR`
- `lib/cli_bootstrap.py:23` — `from config import load_env`
- `lib/llm_deepseek.py:47` — `from config import load_env` (with comment "Defect C (quick 260510-l14): use the canonical loader from config.py")
- `lib/vision_cascade.py:129` — `from config import BASE_DIR` (lazy, inside function)

**Why MEDIUM, not HIGH:** `config.py` is a root-level shared-config module, not an app-stage module. Real F-2 violation (e.g., `from batch_ingest_from_spider import ...` inside `lib/`) does **not** exist — verified by `grep -rln "^from batch_ingest_from_spider\|^import batch_ingest_from_spider\|from ingest_wechat" lib/` — 0 hits. So lib does NOT inverse-import any pipeline driver. The `config.py` dependency is the only concession.

**Why not LOW:** still violates the user's stated F-2 rubric ("lib should NOT import root-level modules"). Easy fix: relocate `BASE_DIR` and `load_env` into `lib/config.py` (or `lib/__init__.py`) and re-export from `config.py` for backward compat. 4 lib import sites + 1 root re-export = ~10 LOC.

**Fix scope:** ~10 LOC refactor + grep all callers of `config.BASE_DIR` / `config.load_env` to verify backward-compat. Quick type: `refactor-flatten`. Risk: very low (pure import-locality change). Estimated effort: 0.5-1 h.

**Maps to:** **F-2 (lib↔app inversion)** — partial evidence; the full F-2 hypothesis (lib pulls business logic) is **NOT** confirmed.

### LOW (nice-to-have)

#### L-1 — Marker hygiene: 22 `# Phase X` / `# Plan Y` / `# Wave Z` markers reflecting old plans

Mostly load-bearing context comments (D-09.03, BTIMEOUT-02, ir-4 LF-4.4, 260509-s29 W2, etc.). All 22 occurrences (lines 112, 290, 314, 321, 702, 742, 760, 761, 771, 800, 814, 855, 870, 1501, 1597, 1614, 1715, 1805, 1865, 1870, 1918, 1952, 2024) are still applicable. **No action needed.** Listed for completeness per audit angle A1.

#### L-2 — `from ingest_wechat import get_rag` is duplicated (lazy-imported twice)

**Evidence:** `:765` (inside `run()`) and `:1600` (inside `ingest_from_db()`).

Both are lazy imports inside async functions to avoid circular-import init cost (rag = LightRAG instance with embedding-model init). Functionally equivalent and intentional. If M-1 deletes `run()`, the `:765` site goes with it. Otherwise harmless.

#### L-3 — Nested coroutine `_drain_layer2_queue` uses `nonlocal` for 5 counters

**Evidence:** `:1639` — `nonlocal layer2_chunk_idx, processed, timed_out_count, clamped_count, safety_margin_triggered`.

This is fine for a single-batch single-loop coroutine — but the function is 87 LOC declared inside `ingest_from_db` (1635-1764), making the parent function visually 531 LOC. Extracting `_drain_layer2_queue` to module level + passing a small dataclass-state object would simplify both reading and testing, and reduce `ingest_from_db` from 531 → ~440 LOC.

**Why LOW:** behavior is correct; this is purely a readability / future-maintainability hint. No release impact.

#### L-4 — `logging.basicConfig(force=True)` race with LightRAG

**Evidence:** `:104-109` (module top) and `:1607-1612` (re-applied after `get_rag()`).

Comment at `:107` and `:1605-1606` notes "v3.5 ir-2 hotfix: prevent LightRAG `get_rag()` from swallowing `[layer2]` output". The fix works (verified by 14-ok production run), but it leaks LightRAG-specific knowledge into `batch_ingest_from_spider.py`. A cleaner fix lives upstream in LightRAG (don't reconfigure root logger), but that's out of OmniGraph-Vault scope. **Document, don't fix.**

---

## 4. Cross-cutting issues

### CC-1 — `lib/*` modules importing `config` root module (4 sites)

Same as M-3. Listed here because it spans **4 lib files**, not just `batch_ingest_from_spider.py`. The single-quick fix flattens all four sites + a re-export shim. Doing it once is preferable to chasing it during 4 future feature quicks.

**No other** cross-cutting issues identified within scope.

---

## 5. Async + error-handling observations (A5+A6)

### A5 — `try/except` audit (45 hits across 25 sites)

| Site | Pattern | Verdict |
|------|---------|---------|
| `:42-55, :95-99` | `try: import; except ImportError: x=None` | Correct — optional dependency guards. |
| `:288-329` (`ingest_article`) | `try: wait_for; except TimeoutError: rollback + flush; except Exception: log+return False` | **Correct.** TimeoutError properly rolls back via `rag.adelete_by_doc_id`; rollback failure logged but doesn't re-raise (`:306-311`). Returns `(False, wall, False)` so `doc_confirmed=False` propagates up — caller marks `status='failed'`, NOT `'ok'`. ✅ No silent FAILED→ok mislabel. |
| `:317-323` | `try: flush_partial_checkpoint; except ImportError: pass; except Exception: log` | Correct — Phase 12 not-yet-shipped soft fallback. |
| `:377-417` (env loaders) | log-and-skip on env-file read failures | Correct — fall-through to next tier. |
| `:494-532, :539-547` | DeepSeek / Gemini API call try-except | Correct — returns `None`; caller (`batch_classify_articles`) checks for None and falls open (`:604-606`). NOTE: this is dead code per M-1; correctness is moot. |
| `:568-572` | `try: from lib import current_key; except: warn + pass-through` | Dead path (M-1). |
| `:725-732` | WeChat list rate-limit catch | Correct — sleeps `RATE_LIMIT_COOLDOWN`, continues to next account. |
| `:781-862` (`run` outer) | outer try / `finally: drain + finalize + metrics` | Correct — finalization always runs, even on exception. |
| `:977-993` (`_persist_scraped_body`) | log+return None on DB failure | Correct — explicit "swallow, never raise into main loop" (line 988 noqa). |
| `:1167-1175, :1201-1226, :1240-1295` (graded probe) | per-call exception handling | Correct — fail-open (returns None on any error), feature is OFF by default. |
| `:1624-1971` (`ingest_from_db` outer) | outer try / `finally: drain + finalize + metrics` | Correct — symmetric with `run()`. |
| `:1879-1893` (per-article scrape) | `try: scrape; except: warn` → `body` stays None → caller skips Layer 2 enqueue at `:1898` | **Correct.** Silent-skip is intentional ("will retry next tick" comment at `:1903`). The article row stays `body=NULL`, so the next ingest tick re-attempts. ✅ No status drift. |
| `:2027-2031` (`main`) | KeyboardInterrupt → exit 130 | Correct — coroutine `finally` block flushes storage. |

**Conclusion A5: no silent-fail-labeled-ok patterns.** All `status='ok'` writes are gated on `success AND doc_confirmed` (lines 833-836 in `run()` and 1741-1744 in `_drain_layer2_queue`).

### A6 — Async engineering audit

| Pattern | Sites | Verdict |
|---------|-------|---------|
| `async def` | 9 functions (`:125, :237, :689, :996, :1177, :1227, :1296, :1443, :1635`) | All awaited at call site. |
| `asyncio.create_task` | 0 hits | The only task-spawning code lives in the LightRAG vision worker pool (already audited 260509-p1n). |
| `asyncio.gather` | 0 hits | No fan-out within batch_ingest. |
| `asyncio.wait_for` | 1 site (`:291`) inside `ingest_article` | Correct — has matching `except asyncio.TimeoutError` with rollback. |
| `nest_asyncio` | 0 hits | Not used at this layer (correct — pipeline runs under `asyncio.run` only). |
| `asyncio.run` | 1 site (`:2028`) | `main()` entrypoint only. |
| `await` | ~20 sites | All are awaited inside coroutines; no orphaned awaitables. |

**No task-escape risks.** The vision-drain task escape that 260509-p1n fixed (delegated `_drain_pending_vision_tasks` to `lib/vision_tracking.drain_vision_tasks`) is the only async risk vector this file introduces, and it is already closed.

---

## 6. Test coverage gap (A7)

### Test files referencing `batch_ingest_from_spider`

24 files / **5980 LOC of test code**:

| Test file | LOC | Targets |
|-----------|----:|---------|
| `tests/unit/test_text_first_ingest.py` | 665 | Whole-file scrape-first orchestration |
| `tests/unit/test_vision_worker.py` | 566 | (cross-file but mocks batch_ingest internals) |
| `tests/unit/test_article_filter.py` | 550 | (cross-file, but uses persist_layer1/2 wired to ingest_from_db) |
| `tests/unit/test_batch_ingest_topic_filter.py` | 498 | `_build_topic_filter_query` (W2) |
| `tests/unit/test_scrape_first_classify.py` | 403 | `_classify_full_body` (dead-in-prod) |
| `tests/unit/test_dual_source_dispatch.py` | 353 | ir-4 RSS dispatch in `ingest_from_db` |
| `tests/unit/test_skip_reason_version.py` | 338 | `skip_reason_version` cohort gate (W2) |
| `tests/unit/test_orchestrate_daily.py` | 318 | (cross-file, asserts batch_ingest CLI shape) |
| `tests/unit/test_graded_classify_prompt_quality.py` | 283 | `_graded_probe_*` (default-OFF feature) |
| `tests/integration/test_checkpoint_resume_e2e.py` | 223 | `ingest_from_db` resume semantics |
| `tests/unit/test_ingest_article_processed_gate.py` | 205 | `ingest_article` PROCESSED-gate (h09) |
| `tests/unit/test_classify_full_body_topic_hint.py` | 194 | `_classify_full_body` (dead-in-prod) |
| `tests/unit/test_rollback_on_timeout.py` | 178 | `ingest_article` STATE-02 rollback |
| `tests/unit/test_classifications_upsert.py` | 176 | `_classify_full_body` UPSERT |
| `tests/unit/test_batch_timeout_instrumentation.py` | 146 | `_build_batch_timeout_metrics` |
| `tests/unit/test_persist_body_pre_classify.py` | 124 | `_persist_scraped_body` (BODY-01) |
| `tests/unit/test_get_rag_contract.py` | 122 | `get_rag` (cross-file) |
| `tests/unit/test_kol_scan_db_path_override.py` | 118 | `KOL_SCAN_DB_PATH` env override |
| `tests/unit/test_scrape_on_demand_apify_markdown.py` | 118 | `_classify_full_body` markdown handling (dead-in-prod) |
| `tests/unit/test_batch_ingest_hash.py` | 113 | `_classify_full_body` cascade routing (dead-in-prod) |
| `tests/unit/test_timeout_budget.py` | 97 | `_compute_article_budget_s` |
| `tests/unit/test_cron_daily_ingest.py` | 86 | (cross-file, cron CLI shape) |
| `tests/unit/test_lightrag_timeout.py` | 69 | LLM_TIMEOUT env (D-09.01) |
| `tests/unit/test_prebatch_flush.py` | 37 | LightRAG `flush=True` (STATE-01) |

### Coverage gap analysis

**Well-covered functions:**
- `_build_topic_filter_query` — 22+ tests in `test_batch_ingest_topic_filter.py`, `test_skip_reason_version.py`, `test_dual_source_dispatch.py`
- `ingest_article` — `test_ingest_article_processed_gate.py`, `test_rollback_on_timeout.py`
- `_compute_article_budget_s` — `test_timeout_budget.py`
- `_persist_scraped_body` — `test_persist_body_pre_classify.py`

**Under-covered functions** (no dedicated tests; relied on via integration only):
- `run` (232 LOC, dead in production) — no direct tests; deletion would orphan zero coverage
- `batch_classify_articles` (102 LOC, dead in production) — no direct tests
- `_call_deepseek` / `_call_gemini` / `_build_filter_prompt` — no direct tests
- `_resolve_batch_timeout` (18 LOC) — implicit only
- `_load_hermes_env` — no direct test (manually exercised in `test_kol_scan_db_path_override.py`)
- `_drain_layer2_queue` (nested 87 LOC) — exercised only via `ingest_from_db` integration tests; no isolated unit test
- `print_filter_summary` (35 LOC, dead) — no direct test

**Tests targeting dead code** (would deletion-orphan):
- `test_scrape_first_classify.py` (403 LOC) — entirely about `_classify_full_body`
- `test_classify_full_body_topic_hint.py` (194 LOC) — same
- `test_classifications_upsert.py` (176 LOC) — exercises `_classify_full_body`'s UPSERT
- `test_scrape_on_demand_apify_markdown.py` (118 LOC) — same
- `test_batch_ingest_hash.py` (113 LOC) — `_classify_full_body` scrape routing

**Total test LOC tied to dead production code: ~1004 LOC** (~17% of all test LOC for this module). Deleting `_classify_full_body` would orphan all of this. M-1 cleanup must include test-file deletion.

---

## 7. Recommended fix quick sequence

| # | Quick | Effort | Depends on | Notes |
|---|-------|-------:|------------|-------|
| 1 | **Q-DEAD** — Delete legacy paths (`run()`, `batch_classify_articles`, `_call_deepseek`, `_call_gemini`, `_build_filter_prompt`, `print_filter_summary`, `_classify_full_body`) + 5 dead-code test files (~1004 LOC tests) + amend ir-4 PLAN closure note | 1-2 h | none | Solves M-1 + M-2 simultaneously. Risk: low. Pre-flight: `grep -rn 'batch_classify_articles\|_classify_full_body' --include='*.py' --include='*.sh' --include='*.md'` to confirm no production caller. |
| 2 | **Q-CONFIG** — Move `BASE_DIR`/`load_env` to `lib/config.py`, re-export from `config.py` for back-compat, update 4 `lib/*.py` import sites | 0.5-1 h | Q-DEAD (or independent — no shared lines) | Solves M-3 + CC-1. Risk: very low. |
| 3 | (deferred) Extract `_drain_layer2_queue` from nested closure into a module-level coroutine + state dataclass | 1-2 h | Q-DEAD | L-3. Cosmetic — defer until next refactor wave. |

**Total release-prep effort: 0 hours.** All 3 quicks are post-release backlog.

**Total post-release hygiene cleanup: 2-4 h**.

### Dependency graph

```
Q-DEAD (M-1 + M-2)  — release-independent
   │
   └─→ (enables) extract _drain_layer2_queue (L-3, deferred)

Q-CONFIG (M-3 + CC-1) — release-independent, parallel
```

---

## 8. Module verdict

### Pollution score: **MEDIUM**

Reasoning:
- **2035 LOC, 26 functions** — by absolute size, this is a god module.
- **~28% (~570 LOC) is dead in production cron** — but actively maintained and tested. Genuine technical debt, not active rot.
- **Zero correctness HIGHs.** All 8 CLAUDE.md "Lessons Learned" entries are properly defended. All 7 INSERT sites use the W2 cohort gate. Production cron has been healthy 24h since `260511-b3y` (14 ok / 0 failed per user briefing).
- **All previously-audited regions remain intact:** W2 (skip_reason_version), W3 (LLM dispatcher), p1n (vision drain), h09 (PROCESSED retry), rl2 F-4 (trivial cleanups), b3y (Vertex location).
- **One identified F-2 violation (4 lib→config imports) is small and isolated** — not the systemic lib↔app inversion the F-2 hypothesis feared.
- **One identified F-1 candidate (run/ingest_from_db duplication) is bounded** — both halves are self-contained; the duplication doesn't extend to lib.

### Release readiness: **CLEAR** ✅

- HIGH = 0 (decision threshold: HIGH = 0 + MEDIUM ≤ 3 → release directly)
- MEDIUM = 3 (dead-code purge / legacy duplication / config import inversion — all hygiene, none block release)
- LOW = 4 (markers / late imports / nonlocal capture / log-format restoration — all cosmetic)
- Production path (`ingest_from_db` via `--from-db`) verified intact against all 8 lessons.

### Recommendation: **ship release now**

File the 2 backlog quicks (Q-DEAD, Q-CONFIG) for post-release hygiene. **Do NOT** block the release on either. The dead code is dormant; deleting it post-release reduces audit cost forever but does not fix any user-facing bug.

---

## 9. Open questions for user

1. **Confirm `run()` is truly retired**: is there any operator workflow (manual smoke, ad-hoc account scan, debugging session) that still invokes `python batch_ingest_from_spider.py` **without** `--from-db`? If yes, M-1 deletion needs a pre-flight check on those operator scripts. If no, Q-DEAD ships clean.
   - Auditor inference: `enrichment/orchestrate_daily.py:197-203` is the only caller in production tree, and it always passes `--from-db`. `scripts/local_e2e.sh` `kol` mode (per CLAUDE.md "Local E2E testing" section) was not inspected — recommend grep before Q-DEAD.

2. **Confirm test deletion plan for Q-DEAD**: deleting `_classify_full_body` orphans ~1004 LOC of tests. Acceptable to delete those tests outright (they exercise dead code), or do you want to preserve any as regression-protection in case the function ever returns?
   - Auditor recommendation: delete outright. The function name `_classify_full_body` is in 4 ir-4 PLAN docs flagged for removal (LF-5.1) — it is permanent dead code. Tests exercising it have no production analog.

3. **`config.py` flatten priority**: M-3 / CC-1 (lib→config inversion) is genuinely tiny — 4 import sites + 1 re-export shim — but it isn't a release blocker. Is it worth a 30-min quick now, or batch with the next "lib hygiene" wave?
   - Auditor recommendation: batch. 4 sites is too small to standalone — let it ride with the next intentional `lib/` work.

4. **`OMNIGRAPH_GRADED_CLASSIFY` enable plan**: is the graded-probe MVP (currently dormant at default OFF) on a trajectory toward enabled? If yes, the `_graded_probe_*` family (234 LOC) gains active production coverage and the 2026-05-05 #2 lesson moves from `partial` → `fixed`. If no, those 234 LOC become candidates for purge along with M-1.
   - Auditor recommendation: out of scope for this audit; defer to v3.5 backlog review.

---

**End of REVIEW.md.** Auditor: read-only / no business code modified / no Hermes SSH. All findings cite raw evidence (file:line / commit SHA / lesson date).
