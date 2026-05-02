---
phase: 05-pipeline-automation
plan: 00
subsystem: embedding-migration
tags: [embedding, migration, lightrag, gemini, wave0, rotation, deepseek]
status: complete
created: 2026-04-28
completed: 2026-04-29
---

# Plan 05-00 SUMMARY — Embedding migration and consolidation (3072-dim native)

**Status:** Complete
**Completed:** 2026-04-29 (user-run on Hermes host; orchestrator reconciled)
**Total attempts for runtime completion:** 6 (5 orchestrator-driven, all blocked on Gemini free-tier quota; 1 user-driven on Hermes after Plan 05-00c shipped, which succeeded)

---

## 1. What Shipped

### Static code deliverables (Tasks 0.1–0.6)

| Task | Artifact | Status |
|------|---------|--------|
| 0.1 | `scripts/phase5_wave0_spike.py` + `docs/spikes/embedding-002-contract.md` | Spike: `recommendation: proceed`; `multimodal_works: true`; `rpm_ceiling: 100`; `batch_api_available: false` on free tier |
| 0.2 | `lightrag_embedding.py` shared module (3072-dim native, in-band multimodal, `_priority` pop, task-prefix routing) | 5/5 unit tests pass |
| 0.3 | 6 duplicate `embedding_func` sites consolidated; `cognee_wrapper.py` uses `gemini-embedding-2`; remote `.env` has `EMBEDDING_MODEL=gemini-embedding-2` | Done |
| 0.4 | `scripts/wave0_reembed.py` — NanoVectorDB wipe + re-ingest for 3072-dim migration | Done |
| 0.5 | `tests/verify_wave0_benchmark.py` + `tests/verify_wave0_crossmodal.py` + `tests/fixtures/wave0_golden_queries.json` | Authored; cross-modal passed on isolated smoke doc |
| 0.6 | PRD §2.4 `embedding-002` → `gemini-embedding-2` + 3 supersession notes | Done |

Files (relative to repo root):

- `lib/lightrag_embedding.py` — implementation (Plan 05-00c later added key rotation on top)
- `lightrag_embedding.py` — back-compat re-export shim
- `scripts/wave0_reembed.py`
- `tests/unit/test_lightrag_embedding.py` (5 tests) + `test_lightrag_embedding_rotation.py` (6 tests added by 05-00c)
- `tests/verify_wave0_benchmark.py`, `tests/verify_wave0_crossmodal.py`
- `tests/fixtures/wave0_golden_queries.json`
- `docs/spikes/embedding-002-contract.md`, `docs/spikes/wave0c_smoke_log.md`

### Runtime completion (Hermes-side user execution per `docs/phase5-00c-execution-report.md`)

- 303 KOL articles classified via Deepseek (v4-flash) in ~8 min — zero 429s, zero failures
- Both Gemini keys verified producing 3072-dim embeddings in production
- LightRAG graph at 3072 dim: **263 nodes / 301 edges / 29 docs / 19 chunks**
- Dual-key rotation working
- Deepseek LLM pipeline working end-to-end

---

## 2. Final graph state

```
embedding_model:     gemini-embedding-2
embedding_dim:       3072
nodes:               263
edges:               301
docs:                29
chunks:              19
LLM (entity extr):   deepseek-v4-flash (via Plan 05-00c)
embed key rotation:  GEMINI_API_KEY + GEMINI_API_KEY_BACKUP (round-robin + 429 failover)
```

---

## 3. Deviations from the original plan

1. **Baseline + 60% top-5 overlap check skipped (Option A).** Plan Task 0.5 required capturing a baseline on the old `-001 @ 768` graph BEFORE the wipe, then comparing post-migration top-5 overlap. This became architecturally unreachable when the plan was edited mid-flight to target 3072 dim natively — NanoVectorDB's dim-equality assertion blocks any query on the old graph with the new `embedding_func` at 3072. User chose Option A: skip baseline, use cross-modal verifier as the sole automated quality gate, document the deviation.

2. **Cross-modal verifier not formally re-run on the final 29-doc graph.** `tests/verify_wave0_crossmodal.py` was authored (Task 0.5) and passed on 1 isolated doc in Plan 05-00c's smoke test at 3072 dim, but was not re-run on the final 29-doc production graph after the user's Hermes-side ingest. The smoke-test result plus dual-key and Deepseek production evidence substitute for a formal verifier run. Follow-up: run the verifier against the production graph when convenient.

3. **Doc count differed from plan assumption** — plan referenced 22 docs (from the Phase 4 STATE.md snapshot of 18 + growth during discuss-phase); final graph has 29 docs. Plan's intent (migrate all content to 3072 dim) was achieved on everything in the graph.

4. **Plan 05-00c was created mid-execution as a prerequisite.** When 5 runtime attempts failed on Gemini free-tier quota, Plan 05-00c (key rotation + Deepseek LLM swap) was drafted and shipped to unblock Wave 0. Its SUMMARY is at `.planning/phases/05-pipeline-automation/05-00c-SUMMARY.md`. Plan 05-00 depended on 05-00c for its final runtime pass.

5. **Per-doc embed cost was ~5× higher than the research-doc estimate.** Initial sizing assumed ~60 embed calls per doc; observed ~300 (8 chunks + ~142 entity vectors + ~154 relation vectors at 3072 dim for a medium-sized doc). Future plans (05-00b, daily RSS cron) should budget against ~300/doc, not ~60. Steady-state daily pipeline at 2–4 articles × 300 calls = 600–1200 calls/day, which fits within 2 free-tier keys (~2000/day) but with thin margin.

6. **Migration required 6 attempts.** Attempts 1–5 were orchestrator-driven and blocked on quota exhaustion across multiple key configurations (free-tier single key; prepaid-depleted Tier 1 key; drained backup key; UTC-reset free-tier key still insufficient). Attempt 6 was user-driven on Hermes after Plan 05-00c shipped.

7. **Rotation silently collapsed to 1 key in one orchestrator attempt.** Cognee's `__init__.py:11` calls `dotenv.load_dotenv(override=True)` which reads a gitignored repo-root `.env` (stale leftover) and overwrites `GEMINI_API_KEY`, collapsing the 2-key pool to 1 without warning. Executor diagnosed via `os.environ.__setitem__` instrumentation. Patched at runtime on remote. Follow-up: delete the repo-root `.env` leftover OR re-assert env in `cognee_wrapper.py` post-import.

---

## 4. Success criteria reconciliation vs. plan frontmatter

| Criterion | Status |
|-----------|--------|
| Spike report recommends "proceed" | Done |
| 6 duplicate `embedding_func` sites consolidated into 1 shared module + 1 env-var change | Done |
| LightRAG docs re-embedded at 3072 dim via NanoVectorDB wipe + re-ingest | Done (29 docs; plan had assumed 22) |
| Post-migration `vdb_chunks.json` shows `embedding_dim: 3072` | Done |
| Chinese retrieval top-5 overlap ≥ 60% per golden query | Skipped under Option A (see Deviation 1) |
| Cross-modal text→image retrieval hits ≥ 1 of 2 golden queries | Verifier authored and passed on 05-00c smoke doc; formal re-run on 29-doc graph deferred as follow-up |
| PRD §2.4 typo fixed; 3 supersession notes added | Done |

---

## 5. `EMBEDDING_MODEL` env-var diff

```diff
# ~/.hermes/.env on remote WSL
+ EMBEDDING_MODEL=gemini-embedding-2
```

Plan 05-00c introduced `GEMINI_API_KEY_BACKUP` alongside `GEMINI_API_KEY` for rotation.

---

## 6. Timeline

| Stage | When | Outcome |
|-------|------|---------|
| Static deliverables (Tasks 0.1–0.6) | 2026-04-28 | All 6 committed; unit tests pass |
| Attempt 1 — initial runtime | 2026-04-28 | Blocked: prepaid credits depleted on `mO_s` key |
| Attempt 2 — mO_s replaced with `6AMw` | 2026-04-28 | Blocked: `6AMw` drained same day |
| Attempt 3 — `_g7g` probe | 2026-04-28 | Blocked: same-day free-tier drained |
| Attempt 4 — per-project quota diagnosis | 2026-04-28 | Diagnosis only, no execution progress |
| Attempt 5 — `_g7g` retry | 2026-04-28 | 253×429 before any doc finished |
| Plan 05-00c authored + executed | 2026-04-28 → 2026-04-29 UTC midnight | Shipped: key rotation, Deepseek swap, 12 unit tests, smoke test on 1 doc passed |
| Attempt 6 — orchestrator with rotation + Deepseek | 2026-04-29 early UTC | Partial (1/22): Cognee `load_dotenv(override=True)` bug collapsed pool; both keys drained post-fix |
| User Hermes-side run | 2026-04-29 | Complete per execution report — 303 articles classified, 9 Wave 0b articles ingested, final graph 263 / 301 / 29 at 3072 dim |

---

## 7. Commits (key moments)

Static deliverables: `e1c3adb`, `cfaddaa`, 0.3–0.6 commits, `5a9c2a6` (wipe-list fix), `65e33bb`, `e83cc24`, `36ef9c0`.

Plan 05-00c (unblocking Wave 0 runtime): `ebdd095` → `f877dba` (12 commits — see `05-00c-SUMMARY.md`).

User execution report: `5df626a docs(05-00c): execution report — classification + keyword-guided catch-up ingest`.

Final SUMMARY + STATE reconciliation: this commit.

---

## 8. Follow-up items (not blocking plan completion)

1. **Cognee `dotenv(override=True)` permanent fix** — delete the gitignored repo-root `.env` leftover OR re-assert env after Cognee import. Infrastructure hygiene.
2. **Formal cross-modal verifier run on the 29-doc production graph** — `python tests/verify_wave0_crossmodal.py` on remote.
3. **Plan 05-00b subprocess-deadlock fix** — 22 KOL catch-up articles still blocked on `subprocess.run(capture_output=True)` pipe deadlock; fix via Popen + threaded reader OR switch to `batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2`. Belongs to 05-00b, not 05-00.
4. **Multi-keyword `--topic-filter` support** in `batch_ingest_from_spider.py` per D-11 of 05-CONTEXT. Belongs to 05-00b.
5. **Schema consistency** — `content_preview` vs `digest` across codebase. Belongs to 05-00b / Wave 1.

---

## 9. Hand-off

Plan 05-00 is complete. Next: **05-00b** (KOL catch-up filtered), already ~30% underway thanks to the user's Hermes-side run (classifications table populated via Deepseek; 9/31 keyword-matched articles ingested). Remaining scope is the subprocess-deadlock fix + completing the other 22 articles + multi-keyword `--topic-filter` implementation.

Phase 5 current blockers are engineering bugs (subprocess deadlock, schema gap, multi-keyword filter), not quota — the Deepseek + rotation infrastructure from 05-00c is holding up well on real workloads.

---

# Wave 0 Close-Out Addendum — 2026-05-02

**This section appends to the 2026-04-29 SUMMARY above, covering Tasks 0.7 + 0.8 and the final Wave 0 gate verification.**

**Head at close:** `0109c02` on origin/main
**Wave 0 verdict:** ✅ CLOSED at "3-article-sample + mechanism-validated" bar

## A. Scope extensions added after 2026-04-29

Between the original 2026-04-29 close (263 nodes / 29 docs) and the formal Wave 0 gate on 2026-05-02, two scope extensions landed:

- **Task 0.7** (Hermes commit `2f576b1`): retrieval-binding fix — parent doc `[Image N from article 'TITLE']: URL` + sub-doc `[image N]: desc (URL)` so `kg_synthesize` can produce `![desc](url)` inline markdown.
- **Task 0.8** (Claude commit `585aa3b` + Hermes commit `0109c02`): `aget_docs_by_ids` verification hook before DB `content_hash` write + full reset and re-ingest to eliminate the 57-row DB/LightRAG ghost-article drift discovered in the 2026-04-29 end state.

The 2026-04-29 graph (263 nodes / 29 docs) was **fully wiped** during the 2026-05-02 full reset; post-reset graph state documented in §B below.

## B. Final gate data — the 2026-05-02 three-gate pass

### P0 — Re-ingest + anti-ghost hook

| Metric | Value |
|---|---|
| Filter+classify scope | 67 KOL articles (post D-10 keyword filter) |
| Ingested | **3** (halted at 4/67 — 118-image outlier hung LightRAG entity merge ~14 min) |
| LightRAG docs after | **7** (3 parent + 4 async-Vision sub-docs from Phase 10 ARCH-02) |
| DB `content_hash` written | **3** — exactly matches LightRAG → **0 ghost articles** |
| `aget_docs_by_ids` skip events | Fired as designed on non-PROCESSED (left `content_hash=NULL` for batch retry) |
| Async timeouts | **0** (Hermes commit `137d39f` async fix held under multi-image load) |

### P1 — Embedding benchmarks

| Gate | Target | Actual | Verdict |
|---|---|---|---|
| Chinese top-5 overlap (6 golden queries) | ≥ 60% avg | 60% (6/6 PASS) | ✅ formal; caveat: 3-article corpus thin; re-run after Wave 1 accumulation |
| Cross-modal text→image hit | ≥ 1/5 | **2/2 hit** | ✅ 🎯 chunks contain `localhost:8765/...` — URL binding end-to-end validated |

### P2 — Synthesis with inline images

Initial attempt with `response_type="Detailed Markdown Article"`: retrieval delivered **16 image URLs** into LLM context, but default prompt did not instruct URL preservation → 0 inline images.

Custom prompt with `CRITICAL ... include as ![description](url) INLINE` directive: **2/2 inline images** + 1466 chars output. **P2 PASS.**

Finding: Task 0.7 URL binding is necessary but not sufficient — synthesis prompt must explicitly preserve URLs. Matters for query-time skills (`omnigraph_query`, `omnigraph_synthesize`); N/A for 05-05 daily digest (SQL+Markdown templating, no LLM synthesis pass).

## C. Five substantive fixes landed during Wave 0 close window

| # | Fix | Commit | Planned? |
|---|---|---|---|
| A | Multi-image `_build_contents` (`re.search` → `re.findall`, cap 6 images/chunk) | `2f576b1` | Yes (Task 0.2b) |
| B | URL retrieval binding (parent Reference with title, sub-doc with `(localhost:8765/...)`) | `2f576b1` | Yes (Task 0.7) |
| C | `aget_docs_by_ids` verification hook before `content_hash` write | `585aa3b` | Yes (Task 0.8 verification sub-task) |
| D | `_fetch_image_part` + `_build_contents` → `async` with `run_in_executor` + `asyncio.gather` | `137d39f` | **No** — P0 run-time discovery; sync `requests.get` blocked asyncio loop under dense-image load |
| E | `kg_synthesize.py`: DeepSeek synthesis + Cognee removed + image-preservation prompt | `0109c02` | **No** — three root causes surfaced together at P2 |

Fixes D + E are **incident-driven**, not plan-driven. Fixture smoke could not surface them. Wave 0's real-batch re-ingest caught them.

**Sub-incident (discovered 2026-05-02 by GSD:quick session during Cognee fix)**: commit `0dc4b2b` (2026-05-02 02:58) had silently NULLed `_resolve_model()`'s Vertex-mode `gemini-embedding-2 → -preview` mapping with a comment "gemini-embedding-2-preview deprecated by Vertex AI". Empirical probe on 2026-05-02 disproved this — `gemini-embedding-2` still returns Vertex 404 NOT_FOUND; `-preview` is still the working name. The ~17-hour window between `0dc4b2b` and `8e4b132` left the LightRAG Vertex path silently broken for anyone who actually exercised it (Hermes's P0 re-ingest apparently tolerated it because the embedding init path hit a different resolution cache). Restored by GSD:quick in `8e4b132`. **Recorded as operational lesson**: any change to `_resolve_model()` or model-name constants should require an automated smoke-probe against real provider endpoints, not just visual review of a comment. Filed as a v3.3 hygiene item.

## D. Decisions locked / revised during this window

### D-07 REVISED 2026-05-02 + new D-19 (committed `315cf8c`)

Enrichment policy: KOL-only, RSS excluded, forward-only (no backfill of today's Wave 0 batch). See `05-CONTEXT.md` § infra_composition.

### Phase 7 D-09 supersession (effective `0109c02`)

Phase 7 D-09 pinned `SYNTHESIS_LLM = "gemini-2.5-flash"`. This conflicted with CLAUDE.md routing rule ("LLM → DeepSeek, Gemini only for Vision+Embedding"). Resolution: **production `kg_synthesize.py` uses DeepSeek V4 Pro** (Hermes) / **local dev uses Gemini 2.5-flash-lite via Vertex AI** (Claude dev machine, Umbrella workaround).

**Local dev Umbrella workaround**: Windows dev cannot reach `api.deepseek.com` (TLS blocked). For local `kg_synthesize` smoke, monkey-patch routes synthesis through Gemini 2.5-flash-lite via Vertex AI. Production stays DeepSeek. Dev-only, does NOT ship.

Phase 7 Done region NOT edited (closed); supersession recorded here. To be re-visited in v3.3 Vertex AI migration phase.

### Cognee removal from `kg_synthesize.py` synthesize flow — **interim**

`0109c02` dropped `import cognee` + `recall_previous_context()` / `remember_synthesis()` from `kg_synthesize.py`. Two root causes:

1. Cognee's LiteLLM→Vertex AI chain used literal `"gemini-embedding-2"` → 404 (needs `-preview`).
2. Cognee module-level import triggered async pipelines that blocked the event loop — newly discovered.

Feature impact: `kg_synthesize` loses "past-query memory". Ingestion-side Cognee (`remember_article` in `ingest_wechat.py`, `cognee_batch_processor.py`) is **untouched** — entities still recorded.

**A parallel GSD:quick session repairs the Vertex model name mismatch** by reusing `lib.lightrag_embedding._resolve_model()` from `cognee_wrapper.py`. Post-landing, follow-up decision: restore Cognee recall/remember into `kg_synthesize` OR leave removed. Tracked as Phase 5 backlog; does NOT gate Wave 0 close.

## E. Wave 0 exit state — what Wave 1 inherits

| Asset | State |
|---|---|
| `lib/lightrag_embedding.py` async multi-image embedding | ✅ main @ `137d39f` |
| Shared `embedding_func` consolidation | ✅ (2026-04-29 Plan 05-00) |
| `EMBEDDING_MODEL=gemini-embedding-2` on Hermes `~/.hermes/.env` | ✅ |
| `_resolve_model()` `-preview` mapping (LightRAG path) | ✅ main @ `2f576b1` |
| `_resolve_model()` `-preview` mapping (Cognee path) | ⏳ GSD:quick in-flight |
| LightRAG `kv_store_full_docs.json` count | 7 (post-reset) |
| DB `articles.content_hash IS NOT NULL` | 3 (aligned via Task 4.2 hook) |
| `aget_docs_by_ids` hook in `ingest_wechat.py` | ✅ main @ `585aa3b`; 3 unit tests pass |
| `kg_synthesize.py` inline `![](url)` | ✅ main @ `0109c02`; 2/2 validated |
| 118-image edge case | Known; Phase 9 timeout truncates ~17 min; deferred item |
| Prompt-dependent image rendering | Documented; query-time skills need directive, digest N/A |

**Wave 1 unblocked.** Plans 05-01 → 05-03b may begin planning/execution.

## F. What Wave 0 did NOT close (intentional deferral)

- Full 67-article catch-up: halted at 3/67; remaining 63 will come in via Wave 1 daily-ingest cron naturally.
- Cognee recall/remember in `kg_synthesize`: parallel GSD:quick fix in flight; restoration decision deferred.
- P1 benchmark statistical rigor: 60% overlap on 3-article corpus is formally passing but thin. Re-run after Wave 1 accumulates ≥ 30 articles.

## G. Honest Wave 0 assessment

Task 0.8 re-ingest scoped as ~90 min routine full-reset. Actual cost ~7 h elapsed + ~$8-12 real API spend. It surfaced **2 bugs (D, E) that fixture smoke could not find**: multi-image async blocking only triggers at dense-image × concurrency; Cognee module-level blocking only surfaces when async loop is already loaded.

Delta cost of real-batch vs fixture smoke ≈ $7-11 + 6 h. Value of bugs caught ≥ prevented 2 am Wave 1 cron incidents → real-batch was worth it.

**Recorded for future:** for infra changes that alter async/concurrency behavior, a multi-article real-batch (even 5-10) is cheaper than discovering in Wave 1 cron. Don't conflate "Wave 0 benchmark validation" with "pre-production smoke" — both worth running.

---

*Wave 0 Close-Out Addendum 2026-05-02 · Authors: Claude (dev) + Hermes (prod) · Head `0109c02` on origin/main*
