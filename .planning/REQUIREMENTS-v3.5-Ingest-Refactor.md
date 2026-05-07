# Requirements: v3.5-Ingest-Refactor

**Defined:** 2026-05-07
**Core value:** Replace independent classify cron + `classifications` table with
runtime two-layer LLM filtering inside the ingest run; eliminate the entire
class of cross-component-state bugs (e.g. 2026-05-07 CV mass-classify) and cut
monthly LLM cost from ~¥210 to <¥10.

**Source of truth:**

- `.planning/PROJECT-v3.5-Ingest-Refactor.md` (6 D-decisions + Layer 1 v0
  prompt + success criteria)
- `.planning/MILESTONE_v3.5_CANDIDATES.md` § Section 1 (fragility inventory)
- `.scratch/layer1-validation-20260507-151608.md` (Layer 1 validated on 30
  random articles)
- `.planning/quick/260507-lai-v3-5-foundation-bypass-classify-gate-wir/260507-lai-PLAN.md`
  (Foundation Quick PLAN — placeholder interface contract)

REQ-IDs use `LF-` prefix (Layer Filter). Categories: Layer 1 (LF-1.x), Layer 2
(LF-2.x), Wiring (LF-3.x), Operator (LF-4.x), Cleanup (LF-5.x).

---

## v1 Requirements

### Layer 1 — pre-scrape filter (LF-1)

Maps PROJECT § D-LF-1, D-LF-3, D-LF-4. Replaces the always-pass placeholder
shipped by Foundation Quick 260507-lai with a real Gemini Flash Lite call.

- [ ] **LF-1.1**: `lib/article_filter.layer1_pre_filter(articles: list[ArticleMeta]) -> list[FilterResult]` is implemented as a real LLM call. Input list is up to 30 articles; output list is 1:1 with input order, each carrying `verdict ∈ {"candidate", "reject"}`, `reason: str` (≤ 30 中文 chars), and a stable `prompt_version` string.
- [ ] **LF-1.2**: Layer 1 batch size = 30 articles per LLM call (D-LF-3). Caller passes batches of up to 30; the function never internally fan-outs to multiple parallel calls. Wall-clock budget ≤ 15s per batch under normal Gemini latency.
- [ ] **LF-1.3**: Layer 1 model is `gemini-3.1-flash-lite-preview` (validated by spike). Routed via `lib/vertex_gemini_complete.py` if `OMNIGRAPH_LLM_PROVIDER == "vertex_gemini"`, else via the legacy `gemini_model_complete` path. No new env var.
- [ ] **LF-1.4**: Layer 1 prompt body is the verbatim text in `PROJECT-v3.5-Ingest-Refactor.md` § "Layer 1 v0 Prompt". Editing the prompt requires re-running the spike + bumping `prompt_version`. The `prompt_version` constant lives at module level in `lib/article_filter.py` and is included in every persisted row.
- [ ] **LF-1.5**: Failure mode (D-LF-4): LLM call timeout / non-JSON / partial JSON / row-count-mismatch → return `FilterResult(verdict=None, reason="<error class>", prompt_version=...)` for **every** article in the batch. No partial-batch persistence. No max-retry counter.
- [ ] **LF-1.6**: Migration 006 — additive: `articles` and `rss_articles` each gain `layer1_verdict TEXT NULL`, `layer1_reason TEXT NULL`, `layer1_at TEXT NULL` (ISO-8601), `layer1_prompt_version TEXT NULL`. Existing rows keep all four columns NULL. Migration is idempotent (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` semantics or `PRAGMA table_info` guard — implementer picks).
- [ ] **LF-1.7**: Layer 1 verdicts are persisted before the batch returns. A successful batch UPDATEs all 30 source rows in one transaction; a failed batch UPDATEs none (rows stay NULL, picked up next run). Persistence is **non-destructive** to other columns: only the 4 layer1_* columns are written.
- [ ] **LF-1.8**: Re-running ingest on an article that already has a non-NULL `layer1_verdict` with the **same** `layer1_prompt_version` skips the LLM call. Different prompt_version → re-evaluate (this is the prompt-bump pattern).
- [ ] **LF-1.9**: Unit tests for Layer 1: (a) batch of 30 → all rows persisted; (b) LLM timeout → all NULL; (c) partial JSON → all NULL; (d) JSON returns 29 instead of 30 entries → all NULL with reason "row_count_mismatch"; (e) prompt_version bump invalidates prior verdicts.

### Layer 2 — post-scrape full-body score (LF-2)

Maps PROJECT § D-LF-2 (Layer 2 columns), D-LF-3 (batch=5–10). Replaces the
always-pass placeholder shipped by Foundation Quick 260507-lai with a real
DeepSeek call.

- [ ] **LF-2.1**: `lib/article_filter.layer2_full_body_score(articles: list[ArticleWithBody]) -> list[FilterResult]` is implemented as a real DeepSeek call. Input list is 5–10 articles each carrying `(id, source, title, body)`; output list is 1:1 with input order.
- [ ] **LF-2.2**: Layer 2 batch size = 5–10 articles per LLM call (D-LF-3). Implementer picks the exact value within that range based on per-call token budget at Phase ir-2 plan time. Wall-clock budget ≤ 60s per batch.
- [ ] **LF-2.3**: Layer 2 model is `deepseek-chat` (default LLM, on-prem, no GCP coupling). Routed via existing `lib/llm_deepseek.py`.
- [ ] **LF-2.4**: Layer 2 prompt design — Phase ir-2 plan-phase produces the prompt and validates on a sibling spike (`.scratch/layer2-validation-<ts>.md`, structured similarly to the Layer 1 spike report). Prompt must (a) score each article `depth_score ∈ {1, 2, 3}`, (b) judge `relevant: bool` against the same agent/LLM/RAG/prompt scope as Layer 1, (c) emit strict JSON 1:1 with input. Pass criterion for the spike: zero 误杀 + zero 漏放 in a 20-article hand-curated set.
- [ ] **LF-2.5**: Migration 007 — additive: `articles` and `rss_articles` each gain `layer2_verdict TEXT NULL`, `layer2_reason TEXT NULL`, `layer2_at TEXT NULL`, `layer2_prompt_version TEXT NULL`. Same idempotency requirement as migration 006. **Layer 2 verdict semantics**: NULL = not yet evaluated; "ok" = passed (proceed to ainsert); "reject" = full body indicates off-scope (skip ainsert, write `ingestions` row with `status='skipped'`, reason from layer2_reason).
- [ ] **LF-2.6**: Failure mode same as LF-1.5 — whole-batch NULL on LLM error / bad JSON / row-count-mismatch. Article stays "scrape-done, layer2-NULL" and is re-evaluated on the next ingest tick. The scrape result (`articles.body`) is **not** discarded.
- [ ] **LF-2.7**: Re-running ingest on an article with non-NULL `layer2_verdict` (same prompt_version) skips the Layer 2 LLM call (same pattern as LF-1.8). prompt_version bump → re-evaluate.
- [ ] **LF-2.8**: Unit tests for Layer 2: (a) batch of 8 → all rows persisted; (b) LLM timeout → all NULL; (c) partial JSON → all NULL; (d) row-count-mismatch → all NULL; (e) prompt_version bump invalidates prior verdicts; (f) "reject" verdict writes `ingestions` row with `status='skipped'`, never reaches LightRAG ainsert.

### Wiring — ingest loop integration (LF-3)

Maps PROJECT § D-LF-1 (placement), D-LF-5 (inline trigger). Foundation Quick
260507-lai already wired the **placeholder** call sites; these REQs replace
placeholder calls with the real LF-1 / LF-2 functions and add the persistence
glue.

- [ ] **LF-3.1**: `batch_ingest_from_spider.py` ingest loop — at the position where Foundation Quick installed the Layer 1 placeholder call, the call now reads candidate batch (≤ 30) from the candidate SQL, invokes `layer1_pre_filter(...)`, persists verdicts via the layer1_* columns, and filters the batch to `verdict == "candidate"` rows before scrape. Layer 1 reject rows write `ingestions` with `status='skipped'`, reason `"layer1_reject:" + verdict.reason`.
- [ ] **LF-3.2**: After scrape (and atomic `articles.body` persist), the ingest loop invokes `layer2_full_body_score(...)` on a batch of 5–10 successfully-scraped rows. Layer 2 verdicts persist on layer2_* columns; only `verdict == "ok"` rows proceed to LightRAG ainsert.
- [ ] **LF-3.3**: Layer 2 reject rows write `ingestions` with `status='skipped'`, reason `"layer2_reject:" + verdict.reason`. The article's `body` stays in `articles.body` (do NOT delete) for potential future re-evaluation under a bumped prompt_version.
- [ ] **LF-3.4**: Candidate SQL (`_build_topic_filter_query` or its successor) selects unscraped rows where `layer1_verdict IS NULL` for Layer 1 stage; selects scraped rows where `layer1_verdict='candidate' AND layer2_verdict IS NULL` for Layer 2 stage. The original `--topic-filter` and `--min-depth` CLI flags are silently ignored (back-compat per Foundation Quick design — they no longer drive any logic).
- [ ] **LF-3.5**: All filter-related logging (verdict per article, batch wall-clock, LLM cost estimate per batch) routes to the existing batch logger. No new log file. Existing log line format is preserved; new lines tagged `[layer1]` / `[layer2]` for grep-ability.
- [ ] **LF-3.6**: `--dry-run` flag continues to work end-to-end: Layer 1 + Layer 2 are still invoked (cost = real LLM calls; this is intentional — `--dry-run` validates the filter pipeline), but no scrape, no ainsert, no `ingestions` writes.

### Operator — Hermes deploy + observation (LF-4)

Maps PROJECT § Cross-milestone contract + 1-week observation gate.

- [ ] **LF-4.1**: Hermes runbook for Phase ir-1 deploy: `.planning/phases/ir-1-*/HERMES-DEPLOY.md`. Steps: pull main, apply migration 006, edit `daily-ingest-kol` cron command if needed (Foundation Quick already removed `daily-classify-kol`), resume cron, smoke 5 articles. Includes rollback (revert + drop columns).
- [ ] **LF-4.2**: Hermes runbook for Phase ir-2 deploy: `.planning/phases/ir-2-*/HERMES-DEPLOY.md`. Same shape; adds migration 007.
- [ ] **LF-4.3**: 1-week observation criteria (Phase ir-3): zero cron failures for 7 consecutive days; reject rate stays in 50–70% band; operator-audit 30-article sample shows zero 误杀; measured monthly cost extrapolates to < ¥10. Criteria recorded in `.planning/phases/ir-3-*/OBSERVATION.md` with daily entries.
- [ ] **LF-4.4**: (Optional, ir-4) RSS path integration runbook: `.planning/phases/ir-4-*/HERMES-DEPLOY.md`. Adds `rss_ingest.py` wiring to `layer1_pre_filter` + `layer2_full_body_score` (same module, source-agnostic by design); operator runbook covers `daily-rss-fetch` cron edit.

### Cleanup — retire dead code + drop empty tables (LF-5)

Maps PROJECT § Out of Scope's dead-code retirement (folded back in here). All
LF-5 items execute in Phase ir-4 (or end of ir-3 if observation passes early).

- [ ] **LF-5.1**: Delete `_classify_full_body`, `_call_deepseek_fullbody`, `_build_fullbody_prompt` functions from `batch_ingest_from_spider.py`. Foundation Quick already removed the call site; LF-5.1 deletes the dead bodies. Verify with grep: `grep -rn "_classify_full_body\|_call_deepseek_fullbody\|_build_fullbody_prompt" .` returns zero hits across `lib/` + `*.py` at repo root.
- [ ] **LF-5.2**: Delete `batch_classify_kol.py` entirely. The script is the entrypoint for the retired `daily-classify-kol` cron; no caller remains after Foundation Quick + LF-3 land. Remove all imports of it across the repo.
- [ ] **LF-5.3**: Migration 008 (optional): `DROP TABLE IF EXISTS classifications; DROP TABLE IF EXISTS rss_classifications;`. Idempotent. Run **only** after operator confirms no consumer reads these tables (grep + tail-of-classifications-write-logs for 7 days post-cleanup). Migration is gated behind an explicit `--include-classifications-drop` flag to the migration runner so it is never accidentally applied.

### Out of Scope (explicit, do NOT include in any phase)

| Item | Why excluded |
|------|--------------|
| `unified_articles` schema unification | v3.6 candidate; v3.5 keeps the two-table split. `lib/article_filter.py` source-agnostic by design at the function-signature level. |
| Cognee inline retire (Phase 20 Wave 3 COG-03) | Already an independent operator gate; not blocked by v3.5 and not blocking v3.5. Keep on its own track. |
| Reject-reason versioning (v3.5 Section 2 candidate) | Distinct concern from filter refactor; follow-up milestone. |
| Embed worker timeout proportional scaling (Section 2 candidate) | Same. |
| systemd timer migration for Hermes cron | Operational hardening; runs in parallel if user prioritizes, but not gated by this milestone. |
| Cost cap mechanism / hard quota guard | Single-user scale; spike measured ¥0.001/article on Layer 1, ¥0.04/article on Layer 2. Total < ¥10/month at observed candidate-pool sizes (~200 articles/day). |
| Multi-LLM A/B for filter quality | Spike already validated Gemini Flash Lite for Layer 1; DeepSeek for Layer 2 inherits production-default LLM. No A/B in v3.5. |
| Cron-loop simulation infrastructure (Lesson 6 from CLAUDE.md) | Tracked as v3.5 candidate, not blocking. |

---

## Future Requirements (deferred)

Tracked but not in current roadmap.

### Filter quality improvements (FQ)

- **FQ-01**: Layer 1 prompt v1 — incorporate operator-audit findings from
  Phase ir-3 observation window into a v1 prompt.
- **FQ-02**: Layer 2 prompt v1 — same.
- **FQ-03**: Confidence score on each verdict (currently binary verdict) — only
  add if observation surfaces ambiguous-edge cases that a confidence threshold
  would resolve.

### RSS path stretch (RSS)

- **RSS-01**: `rss_ingest.py` wired identically to KOL via `lib/article_filter.py`
  (LF-4.4 captures the runbook; this REQ tracks the actual code wiring if it
  is not folded into ir-4).

### Schema unification (SCHEMA)

- **SCHEMA-01**: `unified_articles` table merging `articles` + `rss_articles`
  — v3.6 milestone candidate.

---

## Traceability

Populated by `gsd-roadmapper` at `/gsd:autonomous v3.5-Ingest-Refactor` start.
Phase distribution target (per ROADMAP-v3.5-Ingest-Refactor.md):

| Phase | Count | REQs (target) |
|-------|-------|---------------|
| ir-1 | 11 | LF-1.1..1.9, LF-3.1, LF-3.4, LF-3.5, LF-3.6, LF-4.1 |
| ir-2 | 10 | LF-2.1..2.8, LF-3.2, LF-3.3, LF-4.2 |
| ir-3 | 1 | LF-4.3 |
| ir-4 | 4 | LF-4.4, LF-5.1, LF-5.2, LF-5.3 |

(ir-1 carries 13, ir-2 11, ir-3 1, ir-4 4 → 29 total. `gsd-planner` may shift
LF-3.x distribution if Phase content rebalances.)

| Requirement | Phase | Status |
|-------------|-------|--------|
| LF-1.1 | ir-1 | Pending |
| LF-1.2 | ir-1 | Pending |
| LF-1.3 | ir-1 | Pending |
| LF-1.4 | ir-1 | Pending |
| LF-1.5 | ir-1 | Pending |
| LF-1.6 | ir-1 | Pending |
| LF-1.7 | ir-1 | Pending |
| LF-1.8 | ir-1 | Pending |
| LF-1.9 | ir-1 | Pending |
| LF-2.1 | ir-2 | Pending |
| LF-2.2 | ir-2 | Pending |
| LF-2.3 | ir-2 | Pending |
| LF-2.4 | ir-2 | Pending |
| LF-2.5 | ir-2 | Pending |
| LF-2.6 | ir-2 | Pending |
| LF-2.7 | ir-2 | Pending |
| LF-2.8 | ir-2 | Pending |
| LF-3.1 | ir-1 | Pending |
| LF-3.2 | ir-2 | Pending |
| LF-3.3 | ir-2 | Pending |
| LF-3.4 | ir-1 | Pending |
| LF-3.5 | ir-1 | Pending |
| LF-3.6 | ir-1 | Pending |
| LF-4.1 | ir-1 | Pending |
| LF-4.2 | ir-2 | Pending |
| LF-4.3 | ir-3 | Pending |
| LF-4.4 | ir-4 | Pending |
| LF-5.1 | ir-4 | Pending |
| LF-5.2 | ir-4 | Pending |
| LF-5.3 | ir-4 | Pending |

**Coverage:**

- v1 requirements: 30 total (LF-1: 9 / LF-2: 8 / LF-3: 6 / LF-4: 4 / LF-5: 3)
- Mapped to phases: 30 ✓
- Unmapped: 0 ✓
- Phase distribution: ir-1 (13) / ir-2 (11) / ir-3 (1) / ir-4 (5) = 30 ✓

---
*Requirements defined: 2026-05-07.*
*Last updated: 2026-05-07 — initial charter; phase distribution committed by milestone author, refinable by `gsd-roadmapper` during /gsd:autonomous run.*
