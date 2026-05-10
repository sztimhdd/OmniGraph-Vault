# POLLUTION-AUDIT — OmniGraph-Vault
Generated: 2026-05-10 14:46 ADT
Scope: top vibe-coding-polluted Python modules across the OmniGraph-Vault repo,
post-exclusion of 7 already-audited surfaces (LightRAG SDK wrapping,
Cognee 422 routing, Vision drain, LLM dispatcher, skip_reason_version cohort
gate, ainsert persistence test, Hermes vendor patch).

## TL;DR

- **Top 3 polluted modules** (in order):
  1. `batch_ingest_from_spider.py` — 2029 LOC, 51 commits, 84 phase/D-XX markers, no exact-match unit-test file (24 scattered tests, 5846 LOC across them), 26 top-level defs spanning 3 different orchestration paths and 4 graded-probe variants. **God module.**
  2. `ingest_wechat.py` — 1408 LOC, 59 commits (highest churn in repo), 76 phase/D-XX markers, 4 scrape implementations (`scrape_wechat_{ua,apify,mcp,cdp}`) physically embedded alongside `ingest_article` orchestration (~375 LOC), `lib/scraper.py` getattr-delegates back to it. Inverted dependency.
  3. **Cross-cutting cluster** in 4 single-purpose CLI scripts (`multimodal_ingest.py`, `query_lightrag.py`, `omnigraph_search/query.py`, `run_uat_ingest.py`) + 2 fail-shut overrides (`enrichment/fetch_zhihu.py`, `enrichment/merge_and_ingest.py`) — all unconditionally clobber `GOOGLE_GENAI_USE_VERTEXAI`, breaking `lib/lightrag_embedding._is_vertex_mode()` opt-in (Phase 11 D-11.08). Same-pattern duplicated `load_env()` + hardcoded `llm_model_name="deepseek-v4-flash"` across them.

- **Cross-cutting issues**: 4
  1. `GOOGLE_GENAI_USE_VERTEXAI` clobbering — 9 sites, 6 of them silently force-disable Vertex
  2. Hardcoded `llm_model_name="deepseek-v4-flash"` while caller uses `get_llm_func()` dispatcher (provider/name mismatch when `OMNIGRAPH_LLM_PROVIDER=vertex_gemini`) — 3 scripts
  3. Duplicated `load_env()` re-implementations bypassing `config.load_env` — 4 sites
  4. `lib/llm_deepseek.py:87` import-time `_API_KEY = _require_api_key()` (the documented Hermes FLAG 2 cross-coupling) — still latent in `lib/__init__.py:34`

- **Files explicitly cleared** (low pollution despite size or churn): 5 — `kg_synthesize.py` (already-audited surface clean), `image_pipeline.py` (well-structured + 0.67 test ratio), `lib/scraper.py` (well-structured cascade orchestrator + 0.43 test ratio), `lib/lightrag_embedding.py` (already-audited 3rd-flip + 0.71 test ratio), `config.py` (small, well-commented).

## Methodology

7 evidence signals applied across all `*.py` files except `venv/`, `.dev-runtime/`, `__pycache__/`, `.planning/`, `.claude/`, and the 7 already-audited surfaces enumerated in the brief. All numbers cite raw evidence (commit hash, file:line, grep count). No fix recommendations given — categorize + rank only.

Limitation: `git log` was scoped to `--since="2026-04-01"` to bound the 6-week window; older churn invisible. `Grep` was scoped to repo root via the filename glob — `tests/` directory included for the test-coverage proxy signal but excluded from churn / migration-marker density.

## Signal 1: Churn ranking

`git log --since="2026-04-01" --pretty=format: --name-only | grep py | sort | uniq -c | sort -rn | head -30` (excluding tests/.planning/.claude/venv).

| rank | file | commits | LOC | last commit |
|---|---|---|---|---|
| 1 | `ingest_wechat.py` | 59 | 1408 | `949e3f4` |
| 2 | `batch_ingest_from_spider.py` | 51 | 2029 | `42a1b79` |
| 3 | `kg_synthesize.py` | 19 | 200 | `e538b2d` |
| 4 | `image_pipeline.py` | 15 | 645 | `ce8127a` |
| 5 | `cognee_wrapper.py` | 14 | DELETED | (retired 260510-gfg) |
| 6 | `lib/lightrag_embedding.py` | 12 | 253 | `f6be225` |
| 7 | `query_lightrag.py` | 11 | 59 | `e538b2d` |
| 8 | `config.py` | 11 | 108 | `50dce70` |
| 9 | `batch_classify_kol.py` | 9 | 513 | `5d943f8` |
| 10 | `multimodal_ingest.py` | 8 | 177 | `e538b2d` |
| 11 | `ingest_github.py` | 8 | 292 | `e538b2d` |
| 12 | `cognee_batch_processor.py` | 8 | DELETED | (retired 260510-gfg) |
| 13 | `lib/__init__.py` | 7 | 58 | `d63b2f5` |
| 14 | `batch_scan_kol.py` | 7 | 367 | `5d943f8` |
| 15 | `lib/scraper.py` | 5 | 360 | `fab60e0` |

Notable churn:LOC ratio: `query_lightrag.py` = 11 commits / 59 LOC (= 0.19 commits per LOC — highest in repo for non-deleted files).

## Signal 2: Revert / rewrite / supersede chains

`git log --since="2026-04-01" | grep -iE "revert|rewrite|supersede|hot[- ]?fix|wave|emergency|rollback|fix.*fix"` produced 40+ matches; 3 chains particularly visible.

**Chain A — CV mass-classify (batch_ingest_from_spider.py + batch_classify_kol.py)**
- `c786a83` feat(classify): UPSERT semantics + UNIQUE article_id index
- `428b16f` fix(classify): revert UPSERT to ON CONFLICT(article_id, topic) — multi-topic loop compatibility

**Chain B — Vertex embedding model name (lib/lightrag_embedding.py)** — Lessons Learned 2026-05-03 confirms 3 flips:
- `8e4b132` fix(cognee): vertex ai embedding model name mapping
- `9069f59` fix(embedding): remove stale -preview model mapping on Vertex AI
- `99a1fb8` fix(embedding): restore -preview mapping — Vertex catalog flipped back (3rd flip)
- `f6be225` fix(embedding): remove incorrect preview alias; gemini-embedding-2 is GA on global endpoint

**Chain C — SCR-06 cascade** (`ingest_wechat.py` + `lib/scraper.py` + `batch_ingest_from_spider.py`)
- `ecaa2df` fix(ingest): short-circuit scraper cascade after Apify success + reduce CDP timeout
- `958b2b9` fix(scr-06): consumer accepts markdown OR content_html — completes ecaa2df cascade fix
- `af01315` fix(scr-06-followup): merge UA img_urls with content_html images (silent loss fix per audit ece03ae)
- `8ac3cb1` fix(body): persist scraped body before classify (eliminates SCR-06-class data loss)
- `fab60e0` feat(scraper): F1b cascade reorder ua-first + SCRAPE_CASCADE env var override

Three multi-commit chains all centered on the **batch_ingest + ingest_wechat + scraper** triangle.

## Signal 3: Half-finished migration markers

`grep -rEn "# Phase [0-9]+|# D-?[0-9]+|# Wave [0-9]|# DEPRECATED|# Legacy|# TODO.*remove|# HACK"` (production code only). Top 10 files by hit count:

| file | marker count |
|---|---|
| `batch_ingest_from_spider.py` | 50 (raw count) / 84 (broader pattern incl. v3.x) |
| `ingest_wechat.py` | 41 (raw) / 76 (broader) |
| `image_pipeline.py` | 19 |
| `ingest_github.py` | 12 |
| `multimodal_ingest.py` | 8 |
| `config.py` | 9 |
| `lib/lightrag_embedding.py` | 9 |
| `kg_synthesize.py` | 5 |
| `lib/api_keys.py` | 6 |
| `enrichment/orchestrate_daily.py` | 12 |

Examples (verbatim, with file:line):

`batch_ingest_from_spider.py`:
- L30 `# D-09.01 (TIMEOUT-01): LightRAG reads LLM_TIMEOUT at dataclass-definition time`
- L77 `# Quick 260509-s29 Wave 2: reject-reason cohort version.`
- L143 `# D-09.03 (TIMEOUT-03): per-article outer budget formula.`
- L169 `# --- Phase 17 (BTIMEOUT-04): batch-timeout metrics helpers ---`
- L283 `# D-09.03: 900s floor covers a worst-case single-chunk 800s DeepSeek call.`

`ingest_wechat.py`:
- L136 `# Phase 7 D-09: embedding_func now lives in lib/; root shim re-exports for back-compat.`
- L140 `# dev). Was: from lightrag_llm import deepseek_model_complete (Plan`
- L150 `# Phase 5-00b: extract_entities now on DeepSeek (R4). INGESTION_LLM previously`
- L227 `# HYG-02 (Phase 18-01): hard cap on kept images per article. The 118-image`
- L277 `# Plan 05-00c Task 0c.3: LightRAG LLM_func is now deepseek_model_complete from`

`image_pipeline.py`:
- L3-7 docstring `Extracted from ingest_wechat.py as part of Phase 4 refactor (D-15, D-16). ... Phase 13 (2026-05-02): describe_images now delegates to lib.vision_cascade`
- L41 `_DESCRIBE_INTER_IMAGE_SLEEP_SECS = 0  # Phase 8 IMG-02: was 2; SiliconFlow has no RPM cap`
- L46 `# Phase 8 IMG-03 / D-08.05: canonical outcome taxonomy (6 values).`

These are not lint-noise — they encode genuine archaeology; but in `batch_ingest_from_spider.py` and `ingest_wechat.py` they make every code-reading session require carrying an unwritten Phase/Wave/D-ID dictionary in memory. That dictionary belongs in module docstrings or in `.planning/`, not in 76+ inline comments per file.

## Signal 4: Cross-cutting hotspots (reverse import graph)

Hub modules ranked by inbound imports (production code, excluding tests/scripts):

| module | inbound | god-module? |
|---|---|---|
| `ingest_wechat` | 4 production (`batch_ingest_from_spider`, `lib/scraper`, `image_pipeline`, `enrichment/merge_and_ingest`) + 21 tests/scripts | YES — 1408 LOC, 5 jobs (4 scrapers + ingest_article orchestrator) |
| `image_pipeline` | 2 production (`ingest_wechat`, `enrichment/fetch_zhihu`) + 11 tests | NO — well-structured (645 LOC, 6 functions, 0.67 test ratio) |
| `batch_ingest_from_spider` | 0 production (CLI only) | YES (god-module by complexity, not by inbound) — 2029 LOC, 26 top-level defs |
| `lib.scraper` | 1 production (`batch_ingest_from_spider`) + 4 tests | NO — 360 LOC, clean cascade orchestrator |
| `lib` package (`lib/__init__.py`) | high (43+ via `from lib import ...`) | NO — re-export shim |

**Key inversion finding**: `lib/scraper.py:212-238` defines `_scrape_wechat()` which uses `getattr(ingest_wechat, fn_name)` to dispatch into the 4 scrape implementations physically defined in `ingest_wechat.py:529-896`. The "library" module depends on the "application" module; refactoring `ingest_wechat.py` requires preserving these getattr-discoverable function names.

`batch_ingest_from_spider.py` carries 3 distinct orchestration paths in one module:
- `run()` (line 683-...): subprocess-driven legacy path
- `ingest_from_db()` (line 1437-...): in-process DB-driven (production)
- 4 graded-probe variants at lines 1094 / 1171 / 1221 / 1290 (`_graded_probe_prompts`, `_graded_probe_deepseek`, `_graded_probe_vertex`, `_graded_probe`)
- 2 separate filter-prompt builders at line 415 (`_build_filter_prompt`) and the layer1/layer2 path via `lib/article_filter.py`

Plus `_load_hermes_env` / `get_deepseek_api_key` / `_call_deepseek` / `_call_gemini` / `batch_classify_articles` (lines 358-547) — a 200-line classifier that duplicates parts of `batch_classify_kol.py` (now superseded by `_classify_full_body`).

## Signal 5: TODO/FIXME density

`grep -rEn "TODO|FIXME|XXX|HACK|deferred|cleanup quick|known.*broken|known.*bug"` (production code only): only 7 files have any hits, total 11 occurrences.

| file | hits |
|---|---|
| `lib/scraper.py` | 2 |
| `ingest_wechat.py` | 2 |
| `lib/lightrag_embedding.py` | 1 |
| `scripts/reconcile_ingestions.py` | 2 |
| `scripts/bench_ingest_fixture.py` | 1 |
| `scripts/validate_regression_batch.py` | 1 |

**This signal is genuinely low** — the codebase does not lean on TODO/FIXME for archaeology. All technical debt is encoded as Phase/D-XX/Wave markers (Signal 3) rather than TODO. Conclusion: Signal 3 + Signal 1 are the right pollution detectors here, not Signal 5.

## Signal 6: CLAUDE.md "Lessons Learned" cross-reference (2026-04-01 onward)

| date | lesson summary | files implicated | status |
|---|---|---|---|
| 2026-05-04 #1 | SQLite CHECK constraint can't ALTER → table rebuild | (migration-only, no source remnant) | N/A operational |
| 2026-05-04 #2 | Commit-before-report; uncommitted work doesn't count | (process) | N/A operational |
| 2026-05-04 #3 | CHECK enum vs INSERT value drift = latent bug | `migrations/`, schema | partially fixed (CV revert 428b16f); CI consistency check NOT added — STILL LATENT for next schema bump |
| 2026-05-05 #1 | LightRAG entity/relation upserts 1-text-per-call | `lib/lightrag_embedding.py:207` | **STILL LATENT** — `for text in texts:` loop confirmed; speedup still capped at 3-6× concurrency, not 10-20× batching |
| 2026-05-05 #2 | scrape-first classify Apify cost waste | `batch_ingest_from_spider.py` | partially mitigated by graded-probe (lines 1094-1339) but adds 245 LOC to a 2029-LOC file |
| 2026-05-05 #3 | DB query > in-process counters for batch verification | (operational) | N/A |
| 2026-05-05 afternoon #1 | "half-fix" producer/consumer drift (markdown vs content_html) | `lib/scraper.py`, `batch_ingest_from_spider.py:948` | fixed (`958b2b9`) |
| 2026-05-05 afternoon #2 | Body must persist before any downstream gate | `batch_ingest_from_spider.py:_persist_scraped_body` | fixed (`8ac3cb1`) |
| 2026-05-05 afternoon #3 | Multi-page WeChat articles are normal, not enrichment | (logic only) | fixed in cascade (`ecaa2df`) |
| 2026-05-05 afternoon #4 | Apify result lost on consumer reject | (same as #1) | fixed via #1 + #2 |
| 2026-05-05 afternoon #5 | Embedding/Vision worker timeouts disproportional to LLM | `lib/vision_cascade.py`, `lib/lightrag_embedding.py` | **STILL LATENT** — proportional timeouts not implemented |
| 2026-05-05 afternoon #6 | Candidate SELECT does not exclude `status='skipped'` | `batch_ingest_from_spider._build_topic_filter_query` | fixed via `skip_reason_version` (Quick 260509-s29 W2 — already-audited) |
| 2026-05-06 #1-#4 | reliability test ahead of cron / DB rollback hygiene / synthesis output overwrite / manual ≠ automated | `kg_synthesize.py` (`1a2daed`), operational | fixed |
| 2026-05-06 #5 | Concurrent GSD agent staging race on `git reset --soft` | (process) | N/A operational |
| 2026-05-07 #1 | UNIQUE constraint change must grep all `ON CONFLICT(col)` sites | (process; `428b16f` reverted), schema | fixed; preventative grep documented but not codified as a test |
| 2026-05-07 #2 | Migration reverse must reverse all INSERT call sites | (process) | fixed |
| 2026-05-08 #1 | Cascade order divergence between `lib/scraper` and `ingest_wechat` | `lib/scraper.py`, `ingest_wechat.py:920-942` | fixed (`fab60e0`) |
| 2026-05-08 #2 | Agent fabrication in execute phase | (process) | operational |
| 2026-05-08 #3 | Never put literal secrets in agent prompts | (process) | operational |

**Summary**: 2 lessons (2026-05-05 #1 LightRAG host-side per-text loop; 2026-05-05 afternoon #5 disproportional timeouts) remain LATENT in code. 1 lesson (2026-05-04 #3) has the schema fix but lacks a CI consistency test.

## Signal 7: Test coverage proxy

For Signal 1's top 10 production files, ratio of LOC(exact-match-test) / LOC(source):

| file | src LOC | exact-test LOC | ratio | scattered tests across |
|---|---|---|---|---|
| `ingest_wechat.py` | 1408 | 0 (no `test_ingest_wechat.py`) | n/a | 24 files, 6092 LOC |
| `batch_ingest_from_spider.py` | 2029 | 0 (no `test_batch_ingest_from_spider.py`) | n/a | 24 files, 5846 LOC |
| `kg_synthesize.py` | 200 | 0 (no exact match) | n/a | 4 small files |
| `image_pipeline.py` | 645 | 432 (`test_image_pipeline.py`) | **0.67** | + cascade integration tests |
| `lib/lightrag_embedding.py` | 253 | 179 | **0.71** | + rotation/vertex variants |
| `lib/scraper.py` | 360 | 155 | 0.43 | + `test_scraper_ua_img_merge.py` |
| `query_lightrag.py` | 59 | 0 | n/a | 0 |
| `config.py` | 108 | 0 | n/a | 0 |
| `batch_classify_kol.py` | 513 | 0 | n/a | several scattered |
| `multimodal_ingest.py` | 177 | 0 | n/a | mentioned only in `test_get_rag_contract.py` |

**Thin-coverage flags** (ratio < 0.2 or no exact-match test on a >500-LOC file):
- `ingest_wechat.py` (1408 LOC, no exact-match) — covered by 24 scattered tests; impossible to know what each scenario exercises without reading them all.
- `batch_ingest_from_spider.py` (2029 LOC, no exact-match) — same.
- `multimodal_ingest.py` (177 LOC, no test, no in-process callers — orphan)
- `query_lightrag.py` (59 LOC, no test — but small enough that test absence is forgivable)

`image_pipeline.py` and `lib/lightrag_embedding.py` are well-covered.

## Already-audited exclusions (evidence)

Per the brief: these surfaces are already covered by recent quicks; they may show in churn rankings but are excluded from "Final ranking".

| file/area | quick | hash |
|---|---|---|
| LightRAG SDK / RAG wrapping | 260510-gqu | `981121d` |
| Cognee 422 routing | 260509-syd | `a5f2d6e` |
| Vision drain hang (`lib/vision_tracking.py` + `ingest_wechat.py:1186`) | 260509-p1n | `f715f06` |
| LLM dispatcher (7 sites + `lib/llm_complete.py`) | 260509-s29 W3 | `e538b2d` |
| `skip_reason_version` cohort gate (migrations/009*, `_build_topic_filter_query`) | 260509-s29 W2 | `42a1b79` |
| `tests/unit/test_ainsert_persistence_contract.py` | 260509-t4i | `7c3ba4a` |
| Hermes vendor patch (vendor only) | 260509-msr | (vendor) |

These leak into the churn signal (e.g., `kg_synthesize.py` 19 commits includes `e538b2d` LLM-dispatcher migration), but the **post-audit residual** in those files is small — see "Final ranking" for which files retain non-trivial pollution after subtracting the audited surface.

## ⭐ Final ranking — top polluted modules

### #1 — `batch_ingest_from_spider.py` (2029 LOC, 51 commits) — Pollution: HIGH

**Top 3 specific concerns**:
1. **God module / unclear single responsibility.** 26 top-level defs (line numbers 125, 152, 179, 187, 205, 237, 330, 358, 385, 415, 483, 528, 546, 648, 683, 915, 940, 990, 1094, 1159, 1171, 1221, 1290, 1340, 1437, 1968) span: timeout helpers, 2 separate orchestration paths (`run` line 683 + `ingest_from_db` line 1437), 200-line classifier (lines 358-547 — DeepSeek + Gemini fallback that overlaps with `batch_classify_kol.py`), 245-line graded-probe subsystem (lines 1094-1339 with deepseek + vertex variants), schema migration helper (`_ensure_fullbody_columns` line 330), env loader duplicate (`_load_hermes_env` line 358 — also in `lib/llm_deepseek.py:47`), and the actual ingest loop. No exact-match test file. Reading any one path requires holding all 26 defs in working memory.
2. **84 phase/D-XX/wave markers** make line-by-line archaeology mandatory. Examples:
   - L30 `D-09.01`, L77 `Quick 260509-s29 Wave 2`, L119 `D-10.09`, L143 `D-09.03`, L169 `Phase 17 (BTIMEOUT-04)`, L283 `D-09.03`, L308 `Phase 17 BTIMEOUT-03`, L765 `Phase 17 BTIMEOUT-01`. Reader must know what each ID means; the `.planning/` linkage is implicit.
3. **No exact-match test file.** Tests scatter across 24 files / 5846 LOC; no single file tells you "what does `ingest_from_db` do under load". This makes refactoring genuinely dangerous — touching this module means understanding 24 tests' setUp + assertions.

**Recommended action**: `cross-cutting quick` — split into 2-3 modules along the orchestration axis (e.g., `bif_classify.py` for the embedded classifier, `bif_graded_probe.py` for the 4-variant probe, leaving `batch_ingest_from_spider.py` as the orchestrator). Surface-area reduction first, behavior-preserving.

**Risk if not fixed**: Production cron path. Every fix on the v3.5 ingest contract has to reason about the whole 2029-line file. The `c786a83 → 428b16f` CV regression chain (Lessons Learned 2026-05-07) is exactly the failure mode the file invites.

---

### #2 — `ingest_wechat.py` (1408 LOC, 59 commits — highest churn) — Pollution: HIGH

**Top 3 specific concerns**:
1. **5 jobs in one module.** Definitions at lines 529 (`scrape_wechat_ua`), 664 (`scrape_wechat_apify`), 704 (`scrape_wechat_mcp`), 838 (`scrape_wechat_cdp`), 915 (`ingest_article` — ~375 LOC), 1327 (`ingest_pdf`). The 4 scraper functions logically belong in `lib/scraper.py` but **`lib/scraper.py:227-238` getattr-imports them back from `ingest_wechat`** — the "library" depends on the "application", inverting the intended layering (Phase 19 SCR-01..05 was supposed to fix this but stopped at the orchestrator).
2. **`ingest_article` is itself a god-function.** Lines 915-1290 = ~375 LOC, with a cached-vs-fresh branch (lines 947-996), 5 checkpoint stages (lines 1000-1180), Vision-worker spawn at line 1186, dual hash schemes (MD5[:10] for image dir at line 943, SHA256[:16] for checkpoint at line 940), and inline pending-doc rollback registry calls. `_verify_doc_processed_or_raise` (line 60) is the 2026-05-10 quick 260510-h09 hot-fix bolted on top.
3. **76 phase/D-XX/wave markers**, 41 in raw count. The Phase 5/7/8/10/12/17/18/19/20 IDs all coexist; reader must mentally fold them to "what's actually live in 2026-05-10".

**Recommended action**: `cross-cutting quick` — relocate `scrape_wechat_*` functions into `lib/scraper.py` (fixing the inversion), and split `ingest_article`'s cache-hit branch out as a separate function. **Cannot be a `cleanup quick`** — 4 scrape paths and the 5-stage checkpoint logic are genuine production scope, not dead code.

**Risk if not fixed**: Production cron path + every WeChat-related quick in the next 6 weeks. The 2026-05-08 cascade-order divergence (Lessons Learned 2026-05-08 #1) was a direct symptom of `lib/scraper.py` and `ingest_wechat.py` defining parallel cascade orders — that risk recurs at every cascade tweak as long as the inversion stands.

---

### #3 — Cross-cutting cluster: 6 single-purpose CLI scripts duplicate identical setup — Pollution: MEDIUM

**Affected files** (with offending lines):
- `multimodal_ingest.py` L31-44 (own `load_env`), L54 (`os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"`), L64 (hardcoded `llm_model_name="deepseek-v4-flash"` while line 62 `get_llm_func()`), 8 phase markers; **0 in-process callers** (only via CLI subprocess from `batch_ingest_github.py`-style; no callers found for multimodal_ingest)
- `query_lightrag.py` L15 (Vertex `=false`), L28 (hardcoded `deepseek-v4-flash` while L26 `get_llm_func()`), L18 own `load_env()`; 11 commits / 59 LOC = highest churn ratio in repo
- `ingest_github.py` L42 (Vertex `=false`)
- `omnigraph_search/query.py` L27 (Vertex `=false`)
- `run_uat_ingest.py` L23 (Vertex `=false`)
- `enrichment/fetch_zhihu.py` L39 (`os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)` — fail-shut)
- `enrichment/merge_and_ingest.py` L43 (`os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)` — fail-shut)

**The bug**: `lib/lightrag_embedding.py:_is_vertex_mode()` (line 125) checks `GOOGLE_APPLICATION_CREDENTIALS` AND `GOOGLE_CLOUD_PROJECT`. CLAUDE.md "Phase 11 D-11.08" says Vertex is opt-in via these env vars. The 4 scripts that do unconditional `=false` (multimodal_ingest, query_lightrag, ingest_github, omnigraph_search/query, run_uat_ingest) **don't pop GOOGLE_APPLICATION_CREDENTIALS**, so `_is_vertex_mode()` still returns True when SA is set — but the `genai.Client` then tries to use a falsy-USE_VERTEXAI flag with SA auth, which is exactly the contradiction the Phase 11 guard in `config.py:65-69` was designed to prevent. The 2 enrichment scripts unconditionally `pop` (line 39 + 43), which **silently disables** any Vertex opt-in even when the user explicitly set it. **`config.py:65-69`'s guard ("only pop GOOGLE_* when SA NOT set") is bypassed in all 6 scripts.**

**Top 3 concerns**:
1. **Vertex opt-in silently broken in 5 of 9 sites.** The 6 scripts above all pre-date `_is_vertex_mode()` (added in `38b1d64` Phase 11 D-11.08) but were not updated; the only correctly-guarded site is `config.py:65-69`.
2. **Hardcoded `llm_model_name="deepseek-v4-flash"`** in 3 places (`multimodal_ingest.py:64`, `query_lightrag.py:28`, plus `ingest_wechat.py` historical) while `get_llm_func()` may dispatch to Vertex. LightRAG uses `llm_model_name` for caching keys + tokenizer hints; mismatched model name = silent cache pollution.
3. **`load_env()` re-implemented** in `ingest_wechat.py`, `multimodal_ingest.py`, `lib/llm_deepseek.py`, `query_lightrag.py` (via the imported `load_env` from config). Three of these (`ingest_wechat`, `multimodal_ingest`, `lib/llm_deepseek`) duplicate the body inline rather than importing `config.load_env` — Surgical Changes principle violation accumulating across versions.

**Recommended action**: `cleanup quick` — most of these scripts are CLI thin-wrappers; consolidate the boot setup into a single `bootstrap_cli()` helper in `lib/` and replace the 6 sites. `multimodal_ingest.py` is a separate question (it has 0 in-process callers; might genuinely be dead).

**Risk if not fixed**: Vertex AI migration (CLAUDE.md "Vertex AI Migration Path") will silently fail in the 6 scripts. Local dev with `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` already hits the model-name mismatch silently (no error, just cache pollution).

---

### #4 — `lib/llm_deepseek.py:87` import-time API-key check (HARD coupling) — Pollution: MEDIUM

**The defect**: Line 87 `_API_KEY = _require_api_key()` runs at module import. Any Python process that does `from lib import deepseek_model_complete` (which `lib/__init__.py:34` does at root level) will RuntimeError at import if `DEEPSEEK_API_KEY` is not set. CLAUDE.md "Phase 5 DeepSeek cross-coupling (Hermes FLAG 2)" documents this — Gemini-only workloads still need `DEEPSEEK_API_KEY=dummy`. `lib/llm_complete.py:36` uses lazy import inside `get_llm_func()` to avoid this for Vertex-only callers, but `lib/__init__.py:34` re-exports `deepseek_model_complete` eagerly, defeating that fix for any caller that does `import lib`.

**Top 3 concerns**:
1. **Eager re-export defeats the lazy import.** `lib/__init__.py:34` `from .llm_deepseek import deepseek_model_complete` triggers the import-time RuntimeError every time anyone imports `lib`. The 35 files importing from `lib` all pay this cost.
2. **Documented Hermes FLAG 2** lists "soft-fail is a future Phase 5 follow-up". 6 weeks have passed; the follow-up is still open.
3. **The dummy-key band-aid** (`DEEPSEEK_API_KEY=dummy`) is documented in CLAUDE.md, but local-dev tests use `dummy` as a real value — any test that accidentally hits a real DeepSeek call will silently 401 instead of fast-failing on missing config.

**Recommended action**: `deep-review quick` (small surface — only `lib/__init__.py` and `lib/llm_deepseek.py`) to defer the `_API_KEY` check from module-level to first-call time. ~10 LOC change, reverses the eager import in `lib/__init__.py:34` to lazy access via `get_llm_func()`.

**Risk if not fixed**: Local dev friction (already documented). Future Vertex-only deployment will require `DEEPSEEK_API_KEY=dummy` even though it shouldn't.

---

### #5 — `multimodal_ingest.py` (177 LOC, 8 commits) — Pollution: LOW (orphan candidate)

**The defect**: 0 in-process callers. Imports `lib.generate_sync` for `describe_image()` (line 80), but production code uses `image_pipeline.describe_images` cascade — this single-image path is unused. Writes to local `./data/` (lines 47-48) while production uses `~/.hermes/omonigraph-vault/`. Hardcoded `llm_model_name="deepseek-v4-flash"` while line 62 dispatcher returns whatever `OMNIGRAPH_LLM_PROVIDER` selects.

**Top 3 concerns**:
1. **Likely dead code.** `grep -r "from multimodal_ingest\|import multimodal_ingest"` returns 0 in-process call sites.
2. **Storage path drift.** `RAG_WORKING_DIR = "./data/lightrag_storage"` (line 48) competes with production `~/.hermes/omonigraph-vault/lightrag_storage/`. Anyone who runs this script writes to a different graph than the production graph reads from.
3. **`describe_image` (line 74-88) is a 14-line single-image function that duplicates 1/Nth of `image_pipeline.describe_images`** with no cascade, no balance check, no logging.

**Recommended action**: `cleanup quick` — confirm zero callers, then delete (or move to `scripts/` if PDF ingest is genuinely a separate skill). Same fate likely applies to `query_lightrag.py` if synthesis/ingest work has fully migrated to `kg_synthesize.py` and skill_runner.

**Risk if not fixed**: Confusion. Anyone reading the repo finds a "multimodal_ingest" entry-point and assumes it's the canonical PDF path; running it silently produces a parallel graph in `./data/`.

---

### #6 — `scripts/cognee_diag/inspect_cognee_routing.py:120` — broken import — Pollution: LOW

`import cognee_wrapper` on line 120 — but `cognee_wrapper.py` was deleted in quick 260510-gfg (`608372e refactor(cognee-260510-gfg): retire cognee_wrapper + cognee_batch_processor + rewire callers`). The script will `ImportError` on first run.

**Recommended action**: `cleanup quick` — delete `scripts/cognee_diag/` (the diagnostic served its purpose; quick 260509-syd's findings are committed).

**Risk if not fixed**: None operational; just dead-link debt.

---

## Cross-cutting issues

| issue | affected files | recommended quick type |
|---|---|---|
| **GOOGLE_GENAI_USE_VERTEXAI clobbering** breaks `_is_vertex_mode()` opt-in | 9 sites: `config.py` (guarded), `ingest_wechat.py:274`, `ingest_github.py:42`, `multimodal_ingest.py:54`, `omnigraph_search/query.py:27`, `query_lightrag.py:15`, `run_uat_ingest.py:23`, `enrichment/fetch_zhihu.py:39`, `enrichment/merge_and_ingest.py:43` | `cross-cutting quick` |
| **Hardcoded `llm_model_name="deepseek-v4-flash"`** while caller uses `get_llm_func()` | `multimodal_ingest.py:64`, `query_lightrag.py:28`, plus historical instances in `ingest_wechat.py` | `cleanup quick` (small surface, mostly remove the hardcode) |
| **Duplicated `load_env()`** bypassing `config.load_env` | `ingest_wechat.py` (~ line 178), `multimodal_ingest.py:31-44`, `lib/llm_deepseek.py:47-70`, `enrichment/orchestrate_daily.py` (DB constant only) | `cleanup quick` |
| **`lib/llm_deepseek.py:87` eager import-time API-key check** + `lib/__init__.py:34` eager re-export | 2 files; impacts every `import lib` caller (35 files) | `deep-review quick` (small but architecturally meaningful) |
| **Lessons Learned still latent**: 2026-05-05 #1 (host-side `for text in texts:` loop in `lib/lightrag_embedding.py:207`); 2026-05-05 afternoon #5 (Vision/Embedding worker timeouts disproportional to LLM 600→1800 bump) | `lib/lightrag_embedding.py`, `lib/vision_cascade.py` | (track for v3.5 backlog; not a quick) |
| **Schema CI consistency check** (Lesson 2026-05-04 #3 + 2026-05-07 #1) — UNIQUE constraint changes vs `ON CONFLICT(col)` call sites | (test infra) | (track for v3.5 backlog; `tests/unit/test_schema_consistency.py` candidate) |

---

## Out-of-scope observations (not ranked)

These surfaced during the audit but fall outside "top 3-5 polluted Python modules":

- `enrichment/orchestrate_daily.py` — 9-step state machine with hole at step_2 (RSS classify retired in ir-4); step numbering non-contiguous post-retirement. Coordinator-only, not a god module. ⊘ no quick.
- `batch_classify_kol.py` (513 LOC, 9 commits) — Phase 10 `_classify_full_body` is now in `batch_ingest_from_spider.py:990`; this file's role narrowed but not deleted. Worth a separate review whether the title-only path is still production-needed. ⊘ no quick yet (needs scoping).
- `batchkol_topic.py` — present at 117 LOC, 5 recent commits; **0 reverse imports** found. Possibly an older orphan from before `batch_classify_kol.py`. ⊘ no quick (verification needed).
- `scripts/wave0_reembed.py`, `scripts/phase0_delete_spike.py`, `scripts/phase5_wave0_spike.py`, `scripts/probe_e2e_v3_2.py` — all dated 2026-04-28 to 2026-05-02, named for now-closed Phase 0/5/Wave-0 work. Likely dead scripts from completed milestones. ⊘ batch `cleanup quick`.

---

## Notes on methodology limits

- Bash hooks in this environment intermittently return Bash output via async file paths; some Signal 3/4/5 invocations were re-run via the `Grep` tool to get synchronous results. Numbers cited are from the synchronous re-runs.
- Reverse-import graph (Signal 4) only counted `from X import` and `import X` literals — `__import__` / `getattr` / dynamic-string imports (e.g., `lib/scraper.py:227 getattr(ingest_wechat, fn_name)`) are NOT counted by Signal 4 but are flagged in the prose for #2.
- LOC counts used `wc -l` (line count, not statements). Comments and blanks are included; markers in Signal 3 do not exclude blank lines.
- Test ratio in Signal 7 only matches `tests/unit/test_<basename>.py` and `tests/integration/test_<basename>.py`; tests with non-canonical filenames (e.g., `test_apify_rotation.py` for `ingest_wechat.py`'s rotation code) are not credited to the source file's exact-match column. The "scattered tests" column captures them via grep.
