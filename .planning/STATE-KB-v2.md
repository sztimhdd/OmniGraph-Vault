---
gsd_state_version: 1.0
milestone: KB-v2
milestone_name: — KB-v2 (parallel-track)
status: kb-v2.1-stabilization-closed-kb-v2.2-open
last_updated: "2026-05-18T00:00:00Z"
last_activity: "2026-05-17 — kb-v2.1 stabilization closed (7 phases + 2 quicks shipped, all live on Aliyun: v2.1-1 KG hardening / v2.1-2 image paths / v2.1-3 hero strip / v2.1-4 structured synthesize / v2.1-5 long-form MVP / v2.1-6 image rendering / v2.1-7 lang detection / v2.1-8 wechat data-src / v2.1-9 baseline triage). kb-v2.2 milestone opened with 7-phase scope locked (F12 sync + F1' bidirectional translation + F8' KG search default + FU-1 citation/image + F5/F6 hygiene + F10 optional cleanup); F9 KG mode already enabled prod-side 2026-05-17 night via systemd override + GCP creds + /etc/hosts oauth pin (memory aliyun_oauth_pin.md). Tonight's stale-storage finding (Aliyun 2026-05-08 snapshot, 25% of Hermes data; 4603 vs 1189 image URLs; 172 vs 44 articles with images) reshaped F12 from optional → P0 prereq for Wave 2. CUT-FINAL 2026-05-17: F2 (merged into F1'), F3/F4 cross-language search/Q&A, F11 Path B (violates feedback_lightrag_is_core_asset_no_bypass), 7 long-form UX items (Preview/Save/Export/Versioning/research-page/image-curation/citation-rich). F7 11 prod-drift xfail items unbundled to v2.2.x quick set."
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 33
  completed_plans: 33
  v2_1_stabilization_phases_shipped: 7
  v2_1_stabilization_quicks_shipped: 2
  v2_2_phases_planned: 7
  v2_2_phases_complete: 5
---

# Project State — KB-v2 (parallel)

## Project Reference

- This milestone: `.planning/PROJECT-KB-v2.md`
- Parent project: `.planning/PROJECT.md`
- Design docs: `kb/docs/01-PRD.md` (§4 SEO 章节作废) + `kb/docs/02-DECISIONS.md`
  (D-01 ~ D-20) + `kb/docs/03-ARCHITECTURE.md` + `kb/docs/09-AGENT-QA-HANDBOOK.md`
- Roadmap: `.planning/ROADMAP-KB-v2.md`
- Requirements: `.planning/REQUIREMENTS-KB-v2.md`

## Current Position

Milestone: KB-v2 (parallel-track to v3.4 / v3.5 / Agentic-RAG-v1)
Sub-milestone: **kb-v2.1-stabilization closed 2026-05-17** (7 phases + 2 quicks shipped, all live on Aliyun production)
Active sub-milestone: **kb-v2.2-translation-and-kg-search opened 2026-05-17** (7 phases queued, 1 already shipped)
Status: **kb-v2.2-7 (bilingual-by-site-language) COMPLETE 2026-05-19** — all 6 waves shipped; 568/568 tests PASS; 9/9 UAT scenarios PASS; 2 Wave-4 regressions (Bug A article.html missing KB_DEFAULT_LANG injection + Bug B pre-existing CSS override blocking nav-flip) surfaced by UAT and patched in Wave 6 per orchestrator scope-expanded GO Option A.

**Attribution drift note (Wave 6):** Wave 6 deliverables landed in HEAD via concurrent commit `3c2f7e4` (`feat(llm-wiki-W0): scaffold kb/wiki/`) instead of a dedicated `feat(kb-v2.2-7-wave6)` commit. Concurrent llm-wiki agent's `git add` swept staged Wave 6 files (kb/templates/article.html, kb/static/style.css, 3 baseline test files, .planning/STATE-KB-v2.md, kb-v2.2-7-bilingual-by-site-language-VERIFICATION.md) into its own commit between my `git add` and `git commit -F`. Content is correct in HEAD — Bug A (kb/templates/article.html line 196 KB_DEFAULT_LANG injection), Bug B (kb/static/style.css:1548-1552 deletion + 8-line explanatory comment), 5 baseline test fixes, STATE update, and full VERIFICATION.md all present. Only commit-message attribution is misleading; to find the Wave 6 changes, look at `3c2f7e4` diff filtered to the 7 files listed above, NOT the llm-wiki-W0 commit body. Per `feedback_git_add_explicit_in_parallel_quicks.md` + `feedback_no_amend_in_concurrent_quicks.md`: fix is forward-only documentation (this STATE row), not amend/reset of `3c2f7e4`. Wave 6 commit-body content preserved at `.scratch/wave6-commit-msg.txt` for audit trail.
Last activity: 2026-05-21 (afternoon) — **Databricks Apps Issue #2 (bilingual cards) — DEPLOYED**. UAT-driven quick fix for homepage/articles/topic/entity card titles + snippets staying zh on en-default Databricks deploy. Scope: 4 templates dual-`<span data-lang>` wrap (index/articles_index/topic/entity), `kb/export_knowledge_base.py:_record_to_dict` adds `snippet_translated` field via `rewrite_translated_body(rec.body_translated)` then `_make_snippet`, integration test `test_kb_v2_2_7_bilingual_ssg.py::test_homepage_card_snippets_dual_span` regex scoped to `data-source` attribute (article cards) to exclude topic cards (which keep single-lang `t.localized_desc` intentionally). 16/16 tests PASS. Deploy: `make deploy` recipe replicated inline via bash (Pass 0/0b/0c/0d) + PowerShell databricks CLI (Pass 1+2 sync + apps deploy). deployment_id `01f155284b111278b8c03b745eb44758` state=SUCCEEDED 15:20:55Z. Workspace export of `_ssg/index.html` confirms 157 `data-lang="en"` + 157 `data-lang="zh"` + 1 `<html lang="en">`. **Behavior caveat:** en spans currently render zh content via Jinja `{{ x_translated or x }}` fallback because `body_translated`/`title_translated` columns are NULL for the production DB attached to Databricks Apps (different DB than Hermes Phase-5 backfilled one). Step 4 (UC Volume DB schema migration + 233-article translation backfill) is the unblocker for actual English content rendering. Verification doc: `databricks-deploy/_kdb_issue2_bilingual_cards_VERIFICATION.md`.

**Attribution drift note (Issue #2 bilingual cards):** Step 2 deliverables (kb/export_knowledge_base.py + 4 templates kb/templates/{index,articles_index,topic,entity}.html + tests/integration/kb/test_kb_v2_2_7_bilingual_ssg.py) landed in HEAD via concurrent commit `e11b474` (`docs(state): Gate 1 closed — kb-4-lite + aim-N path correction (Option A)`) instead of a dedicated `fix(kdb-uat)` commit. Concurrent gate-closure agent's `git add` swept my staged Step-2 files into its own commit between my explicit-path `git add` and `git commit -F`. Content is correct in HEAD — `_record_to_dict` `snippet_translated` patch (4 lines), 4 templates dual-span wrap (5+5+9+9 lines), test regex scoping refinement — all present. Verified via `git show e11b474 --stat`. Only commit-message attribution is misleading; to find Issue #2 changes, look at `e11b474` diff filtered to those 6 files, NOT the gate-closure body. **3rd occurrence** of this failure mode (260511 lmc/lmx; 260518 v2.2-1 PLAN; 260521 e11b474). Per `feedback_git_add_explicit_in_parallel_quicks.md` + `feedback_no_amend_in_concurrent_quicks.md`: fix is forward-only documentation (this STATE row), NOT amend/reset of `e11b474`.

Prior activity: 2026-05-21 — **kb-v2.2-7 Phase 5 (Translation Backfill) — CLOSED**. 译: 234/238 (169 KOL + 65 RSS),失败 4 RSS (id=45/60/1394/5144 JSON-parse 撞 4-call retry budget;`title_translated` 留 NULL 由下次 backfill UNION-ALL 兜底)。模型: `databricks-claude-opus-4-7` · 成本: $0 · Hermes apply 0.1s。Hermes live DB 终态: 170 articles + 67 rss_articles = 237 行 `title_translated NOT NULL`。Pre-apply backup: `data/kol_scan.db.backup-pre-phase5-20260520-194310`。报告: `.scratch/translate-backfill-260520.md`。Known design risk(单 batch / 无增量 flush / 无 resume guard)已入报告,排 v2.2-future,不立 phase。

Prior activity: 2026-05-19 — **kb-v2.2-7 (bilingual-by-site-language) COMPLETE**. Replaces kb-v2.2-2 F1' on-demand button-based UX with site-language-driven static SSG rendering: dual-`<span data-lang>` h1 + dual-`<article class="article-body lang-block" data-lang>` body siblings; `KB_DEFAULT_LANG` env var injected per-deploy as `window.KB_DEFAULT_LANG` (Aliyun=zh-CN, Databricks=en); `lang.js` first-visit cookie persistence + `data-fixed-lang` runtime guard removed; F1' API surface (POST/GET `/api/translate`, `?lang=` query, `_load_translation`, `kb/services/translation.py`, translate-row UI) deleted. Translation production via `databricks-deploy/translate_kb.py` single-file notebook (manual "Run all" trigger, no automation). Wave 6 UAT discovered + patched 2 Wave-4 regressions (article.html standalone missed base.html injection; pre-existing `.nav-links a span { display: inline }` CSS override at desktop viewport blocked dual-span nav flip). Commits: `9fd518c` PLAN, `5d14560` Wave 1 data layer, `25791df` Wave 2 notebook, `36e10b7` Wave 3 deletion, `f9968a1` Wave 4 SSG, `bac0706` Wave 5 lang.js, _(Wave 6 commit pending finalization)_. Verification: `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-VERIFICATION.md`. Local UAT artifacts: `.playwright-mcp/kb-v2-2-7-uat-*.html|css|js|png` (10 files).

Prior activity: 2026-05-18 — kb-v2.2-4 (FU-1) QA citation format fix shipped: `_QA_PROMPT_TEMPLATE_ZH/EN` added to `kb/services/synthesize.py`, `_wrap_question_for_mode` handles `mode='qa'`, dispatch updated. Root cause: bare question → Chinese `(来源:X)` citations → `_SOURCE_HASH_PATTERN` missed → `confidence='no_results'`. Fix: template instructs `[/article/{hash}.html]` citation format + image `![alt](URL)` instruction. 8 new tests (5 unit `test_synthesize_qa_prompt.py` + 3 integration `test_synthesize_citation_format.py`); 2 existing wrapper tests updated (startswith→in assertions). 22/22 pass, 0 regressions. Local UAT: `/ask/` zh+en pages render, API `POST /api/synthesize` → `status=done` (NEVER-500 preserved). Screenshots `.playwright-mcp/-playwright-mcp-fu1-uat-01.png` (zh) + `-fu1-uat-02.png` (en).

Prior activity: 2026-05-18 — kb-v2.2-3 (F8') KG search default shipped: `kb/api_routers/search.py` default changed fts→kg; KG-unavailable response changed from HTTP 200 degraded to HTTP 503 + `Retry-After: 60`; FTS5 preserved as explicit mode=fts. 2 new tests in `test_api_search.py` (default mode is kg, 503 contract); 2 updated tests in `test_kg_mode_hardening.py` (200→503). Local UAT: curl smoke confirmed HTTP 503 on default/explicit kg, HTTP 200 on mode=fts, retry-after:60 header present. Homepage screenshot `.playwright-mcp/c-Users-huxxha-Desktop-OmniGraph-Vault-playwright-mcp-f8-prime-uat-01.png`. Full pytest exit 0.

Prior activity: 2026-05-18 — kb-v2.2-1 (F12) lightrag_storage sync orchestrator shipped: `kb/scripts/sync_lightrag_storage.py` (540 lines, frozen dataclasses, two-hop rsync, atomic swap, proactive OOM probe `monitor_post_restart_memory`, automatic rollback, growth prediction via linear regression, idempotency guard, JSON state file with rolling 20-entry history). `kb/scripts/check_aliyun_kg_memory.py` standalone probe. 15 tests (13 unit + 2 integration, all fully mocked — no real network in CI). `kb/docs/RUNBOOK-lightrag-storage-sync.md` §1-§7 (weekly checklist, recovery, escalation, MemoryMax guidance, OOM playbook with 2026-05-18 empirical anchors, growth prediction). Trailing-slash bug in `atomic_swap`/`rollback` found and fixed during integration test run. Full pytest: all tests pass, 0 regressions. Wave 1 (F12+F5+F6+F9) complete; Wave 2 now unblocked.

Prior activity: 2026-05-18 — kb-v2.2-6 (F6) SSG data-lang regularization shipped: `_canonical_lang()` helper in `kb/export_knowledge_base.py` maps legacy short `zh` → canonical `zh-CN` at the data-layer-to-template boundary; applied at 3 SSG emission sites (`_record_to_dict` article cards + article-detail page lang + url-index sidecar). 8 new tests (6 unit + 2 integration with synthetic fixture DB exercising legacy-zh data). Full pytest: 1284 passed, 0 failed (+8 from F6, no regression vs F5 baseline). Wave 1 (F5+F6+F9) complete; Wave 2 (F1'+F8'+FU-1) still blocked on F12 P0 prereq.

Prior activity: 2026-05-18 — kb-v2.2-5 (F5) test-isolation autouse fixture shipped: `lib.api_keys._reset_cycle_for_tests()` helper + autouse fixture in `tests/conftest.py` resets both LLM cycle (`_cycle`/`_current`) AND embedding cycle (`_embedding_cycle`/`_current_embedding`) before/after each test. Root cause was embedding cycle never being reset (only LLM cycle was). Plus secondary `lib.article_filter` parent-attribute force-set in `test_vision_worker.py` for Python import-cache quirk. 5/5 target xfails converted to PASS (4 rotation + 1 vision_worker). Baseline triage: 5/16 closed.

Prior activity: 2026-05-18 — kb-v2.2-1 PLAN.md addendum landed (3 OOM-evidence-driven additions: proactive memory probe `monitor_post_restart_memory()` + RUNBOOK §6 OOM Recovery Playbook + RUNBOOK §7 vdb Size Growth Prediction + SYNC-04 acceptance criteria extension). **Attribution drift note:** addendum content was authored by orchestrator as a forward-only commit on top of 272ef46, but a concurrent quick (260517-rgd-3, commit fd7cc74) swept the staged PLAN.md changes into its own commit alongside CLAUDE.md MAX_ARTICLES update. Content is correct in HEAD; only commit-message attribution is misleading. To find the F12 OOM addenda, look at fd7cc74 PLAN.md diff, NOT the rgd-3 commit message body. This is exactly the failure mode `feedback_git_add_explicit_in_parallel_quicks.md` warns about — concurrent agents share the staging area; one agent's `git add` (likely `-A` or sweeping) absorbed sibling work. Per `feedback_no_amend_in_concurrent_quicks.md`, fix is forward-only documentation (this STATE row), not amend/reset of fd7cc74.

Prior activity: 2026-05-17 — kb-v2.2 milestone-open completed via hand-driven setup (parallel-track suffix files; gsd-tools.cjs init does not parse PROJECT-KB-v2.md so /gsd:new-milestone bypassed per memory `feedback_parallel_track_gates_manual_run.md`). INPUT.md created at `.planning/phases/kb-v2.2-translation-and-kg-search/INPUT.md`; DEFERRED.md updated with 11 CUT-FINAL items; PROJECT-KB-v2.md v2.2 section expanded. F9 (Aliyun KG mode) already shipped prod-side via systemd override + GCP creds + /etc/hosts oauth pin (2026-05-17 night). Wave 1 (F12 + F5 + F6) parallelizable on milestone-open.

### Phase plan

| Phase | Goal | REQs | T-shirt | Plans | Status |
|-------|------|------|---------|-------|--------|
| kb-1 | SSG Export + i18n Foundation (data layer + Jinja2 + bilingual chrome) | 27 | L+0.5d redesign | 10+1 (kb-1-10 gap) + redesign-quick | ✅ **COMPLETE pre-redesign** (26/27 codebase-satisfied; UI-04 logo deferred to kb-4); UI redesign quick task in progress 2026-05-13 to close design-dimension audit |
| **kb-2** | Topic Pillar + Entity Pages + Cross-Link Network | **12** | M (1.5-2d) | 10/10 | ✅ **COMPLETE 2026-05-13** (12/12 REQs; 58 integration tests; 12/12 Playwright UAT viewports; `kb/templates/{topic,entity}.html` + `kb/data/article_query.py` query layer + `kb/output/{topics,entities}/` baked SSG; see `kb-2-VERIFICATION.md`) |
| kb-3 | FastAPI Backend + Bilingual API + Search + Q&A | 18 | L | 12/12 | ✅ **COMPLETE 2026-05-14** (19/19 REQs incl. DATA-07 + I18N-07 + API-01..08 + SEARCH-01..03 + QA-01..05 + CONFIG-02; 256 tests; all 5 endpoint families live in `kb/api.py`; later re-hosted onto Databricks by kb-databricks-v1; see `kb-3-VERIFICATION.md`) |
| kb-4 | Ubuntu Deploy + Cron + Smoke Verification | 5 | S | 8 plans | ✅ **COMPLETE 2026-05-22** (5/5 DEPLOY REQs; 3 smoke PASS; Aliyun cron `0 12 * * *` installed; prod-shape PASS 16-poll NEVER-500; cgroup MemoryHigh=infinity/MemoryMax=8G; see `kb-4-VERIFICATION.md`) |

Total: **62/62 v2.0 REQs** mapped (was 50; +12 from kb-2 revival). kb-1: 26/27 satisfied + 1 deferred-by-approval (UI-04). **kb-2/3/4: all COMPLETE (kb-2 2026-05-13, kb-3 2026-05-14, kb-4 2026-05-22) — v2.0 milestone fully shipped.** (2026-06-12 doc-reconcile: this Progress Table row for kb-2/kb-3 was stale "TBD/not started" despite frontmatter `completed_phases:4` + ROADMAP `[x]` + VERIFICATION docs — the parallel-track suffix-file manual-sweep gap per memory `feedback_parallel_track_gates_manual_run`. Corrected to match reality.)

> **Note:** kb-2 (Topic Pillar + Entity pages + cross-link) **revived 2026-05-13**. Hermes prod has `classifications` 3945 rows + `extracted_entities` 5257 rows / 91 entities at ≥5-article frequency — sufficient for v2.0 scope. v2.1 dependencies (CANON-* LLM canonicalize, TYPED-* entity_type, TOPIC-HIER-* taxonomy) remain deferred and won't block v2.0.

### kb-1 Verification Summary (2026-05-13)

| Source | Result |
|---|---|
| `kb-1-VERIFICATION.md` (gsd-verifier, 2026-05-13 13:00 UTC) | gaps_found → complete after kb-1-10 |
| `kb-1-10-final-verification` (post-gap-closure) | 4/8 truths VERIFIED + 4 human-verifiable |
| `kb-1-HUMAN-UAT.md` (Playwright MCP, 2026-05-13 17:00 UTC) | 3/4 PASS (UAT 1+2+3) + 1 deferred (UAT 4 logo PNG → kb-4) |
| Real-DB SSG run | 1800 articles HTML, 0 errors, idempotency byte-match verified |
| Test count | 73/73 passing (was 71/71 pre-gap-closure) |
| Score | 26/27 REQs (was 22/27 pre-gap-closure) |

### Immediate next step

**kb-v2.2-1 PLAN ready** at `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-1-lightrag-storage-sync-PLAN.md`
(authored 2026-05-18). 3 tasks (sync script + tests + runbook/probe), 11 test
cases (9 unit + 2 integration), 7 SYNC-* requirements, 7 pre-locked decisions
baked in (D1-D7 from 2026-05-17 evening session), 3 Skills declared
(python-patterns + writing-tests + search-first).

`/gsd:execute-phase kb-v2.2-1` — execute F12 Hermes → Aliyun lightrag_storage sync mechanism.

This is the **Wave 1 P0 prereq**: F8' (kb-v2.2-3) and FU-1 (kb-v2.2-4) both depend
on F12 because Aliyun's storage is currently a 2026-05-08 stale snapshot (only
~25% of Hermes content; 1189 vs 4603 image URLs). Without F12 sync, KG search
quality + image-rich answers are bounded by stale data.

Wave 1 (parallel, no deps): F12 + F5 (test-isolation autouse) + F6 (data-lang
regularization). After Wave 1 (F12) ships: plan kb-v2.2-2 (F1' bidirectional
translation) + kb-v2.2-3 (F8' KG search default) in parallel; kb-v2.2-4 (FU-1
citation+image) after kb-v2.2-3 settles.

## Parallel-Track Boundary

This STATE file tracks **KB-v2 ONLY**. v3.4 / v3.5 / Agentic-RAG-v1 progress remain
in their own STATE files.

The KB-v2 milestone shares with the parent project:

- The same git working tree (commits land on `main`)
- The same Ubuntu deployment target (single server, KB will run alongside any other
  services there — but does NOT depend on Hermes agent runtime)
- The 4 cross-milestone contracts C1-C4 (see PROJECT-KB-v2.md "Cross-Milestone Contracts")

The KB-v2 milestone does NOT share with sibling milestones:

- Phase numbering — KB uses `kb-N-*` prefix, separate from main `19/20/21/22` and
  from `ar-N-*` (Agentic-RAG-v1)
- REQ-ID namespace — KB uses `KB-*` / `UI-*` / `I18N-*` / etc., separate from
  v3.4's `SCR-* / RIN-* / ...`
- Planning files — KB has its own `PROJECT-KB-v2.md` / `REQUIREMENTS-KB-v2.md` /
  `ROADMAP-KB-v2.md` / `STATE-KB-v2.md` (parallel-track suffix pattern)

## Accumulated Context (for resumption)

### Roadmap Evolution

- 2026-05-12 — Milestone KB-v2 initialized parallel to v3.4 / v3.5 / Agentic-RAG-v1.
  Sibling-files layout chosen; `kb-N` phase prefix; design docs (`kb/docs/01-09`)
  treated as final, no research stage spawned.
- 2026-05-12 — REQUIREMENTS-KB-v2.md committed. 9 categories: I18N (8), DATA (6),
  EXPORT (6), UI (7), API (8), SEARCH (3), QA (5), DEPLOY (5), CONFIG (2) —
  total 50 REQs (REQUIREMENTS-KB-v2.md header text says "37" but that is stale;
  category breakdown sums to 50).
- 2026-05-12 — ROADMAP-KB-v2.md created by `gsd-roadmapper`. Decomposition:
  layered foundation → service → ops across 3 phases (kb-1 / kb-3 / kb-4),
  explicit kb-2 skip. All 50 REQs mapped, no orphans, no duplicates. Traceability
  table in REQUIREMENTS file populated.

### Decisions

Decisions are logged in `PROJECT-KB-v2.md` § "Locked Architectural Choices" and
in `kb/docs/02-DECISIONS.md` (D-01 ~ D-20).

This-session decisions:

- 2026-05-12 — Sibling-files layout (`PROJECT-KB-v2.md` etc.) chosen over
  subdirectory or worktree, preserving v3.4 / v3.5 / Agentic-RAG-v1 GSD tooling
  untouched
- 2026-05-12 — Phase prefix `kb-N` chosen over continuing `23+` numbering, to
  preserve cross-reference compatibility with `kb/docs/04-KB1` / `06-KB3` /
  `07-KB4` execution specs
- 2026-05-12 — Research stage skipped — `kb/docs/01-09` covers design end-to-end
  per user instruction; no `gsd-project-researcher` agents spawned
- 2026-05-12 — **Layered foundation → service → ops decomposition** chosen over
  vertical-slice MVP-first. Three drivers: (1) data-shape risks (lang IS NULL
  rows, KOL-vs-RSS hash format divergence, body fallback chain) are concentrated
  in the data layer; layered surfaces them all in kb-1; (2) the SSG export is
  itself the natural end-to-end thin slice — no further verticalization needed;
  (3) kb-3 only adds HTTP semantics on top of a working data layer, kb-4 is pure
  ops — sequential dependency is honest. Full rationale in ROADMAP-KB-v2.md
  § "Phase decomposition rationale".
- 2026-05-12 — **3 phases**, with kb-2 explicitly skipped. kb-2 (entity pages +
  topic Pillar pages) deferred to v2.1 because only 13 canonical entities exist
  today, can't support a real entity-page surface (per PROJECT-KB-v2.md "Out of
  Scope" + `kb/docs/09-AGENT-QA-HANDBOOK.md` Q3 K-3).
- **2026-05-13 — REVISED to 4 phases.** kb-2 un-skipped after SSH verification against Hermes prod DB found:
  - `classifications` table: 3945 rows (5 topics × 789 articles) — local dev DB had 0 rows, leading to wrong "deferred" judgment
  - `extracted_entities`: 5257 rows / 3319 distinct names; 91 entities at ≥5-article freq, 26 at ≥10-article freq
  - kb-2 viable today using raw `extracted_entities` + frequency threshold (skip canonicalization). v2.1 dependencies (CANON-* / TYPED-* / TOPIC-HIER-*) remain deferred.
  - 12 new REQs: TOPIC-01..05 + ENTITY-01..04 + LINK-01..03. Total 62/62. T-shirt M (1.5-2 days).
  - **Lesson captured in memory `feedback_parallel_track_gates_manual_run.md`:** always verify against Hermes prod data before deferring scope — local dev DB is sparse and misleading.
- **2026-05-21 — kb-4 SCOPE REDUCED to "kb-4-lite"** post Gate 1 SSH-probe of Aliyun ECS (101.133.154.49). Probe findings: HEAD=`4eaef45` (2026-05-16 v1.0.x); working tree dirty (30+ modified + 40+ untracked from manual SCP/rsync, including kb/wiki/, kb/services/wiki_inject.py, databricks-deploy/translate_kb.py, kb/data/migrations/); kb-api running on `/root/OmniGraph-Vault/` + serving via Caddy `/kb/api/*` → `127.0.0.1:8766`; `/etc/systemd/system/kb-api.service` + `/etc/caddy/Caddyfile` already wired; **no `daily_rebuild.sh`, no SSG/FTS5/lang-detect rebuild cron** (only `gen_agent_news.sh` at 09:30). DEPLOY-01 + DEPLOY-02 + DEPLOY-03 already done-by-side-effect. kb-4-lite remaining scope = **DEPLOY-04** (`daily_rebuild.sh` + 12:00 cron: detect_article_lang.py → export_knowledge_base.py → rebuild_fts.py) + **DEPLOY-05** (3 smoke scenarios). 8-plan structure (kb-4-01..08) collapses to ~2 plans (rebuild-cron + smoke-verification) plus working-tree cleanup commit. Gate 1 chosen path = Option A "kb-4-lite first, then aim-N spec correction" — execution order locked.

- **2026-05-21 evening — kb-4 plan-by-plan supersession map** (executor reference; 8 PLANs from 2026-05-14 retained as artifacts, status overlaid here):

  | Plan | Scope | Gate 1 verdict | Action |
  | --- | --- | --- | --- |
  | kb-4-01-systemd-caddy | `kb/deploy/kb-api.service` + Caddyfile | SUPERSEDED-BY-SIDE-EFFECT (live `/etc/systemd/system/kb-api.service` + `/etc/caddy/Caddyfile` on Aliyun) | NO-OP — write SUMMARY citing prod state via `ssh aliyun-vitaclaw 'systemctl cat kb-api'` |
  | kb-4-02-install-bootstrap | `kb/deploy/install.sh` | SUPERSEDED-BY-SIDE-EFFECT (kb-api running on `/root/OmniGraph-Vault/` from manual deploy; install.sh never executed) | NO-OP — write SUMMARY noting skipped (path differs from spec; documented in aim-N follow-up) |
  | kb-4-03-logo-png-source | `kb/static/VitaClaw-Logo-v0.png` | SUPERSEDED-BY-SIDE-EFFECT (PNG 2048×2048 RGBA sourced 2026-05-15, present in repo + Aliyun via prior SCP) | NO-OP — minor cleanup `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` removal can land in any commit |
  | kb-4-04-daily-rebuild-cron | `kb/scripts/daily_rebuild.sh` + 12:00 cron | LIVE (no `daily_rebuild.sh` on Aliyun; only `gen_agent_news.sh` at 09:30) | EXECUTE — adapt path: cron entry on Aliyun `/root/OmniGraph-Vault/kb/scripts/daily_rebuild.sh` |
  | kb-4-05-local-uat | `.scratch/local_serve.py` UAT | LIVE (PRINCIPLE 6 KB UAT mandatory; `.dev-runtime` baseline) | EXECUTE — local-only |
  | kb-4-06-smoke-3-scenarios | 3 smoke scenarios on `.dev-runtime` | LIVE | EXECUTE — local-only |
  | kb-4-07-hermes-prodshape-smoke | smoke against Hermes prod-shape DB (closes kb-3-12 deferral) | RETARGETED to Aliyun (Aliyun IS the new prod target post-aim-N; ALSO Aliyun prod kb-api already serves real DB) | EXECUTE — but probe Aliyun directly (`ssh aliyun-vitaclaw 'sqlite3 /root/OmniGraph-Vault/data/kol_scan.db ".tables"'` + curl kb-api endpoints) instead of scp from Hermes |
  | kb-4-08-verification-close | `kb-4-VERIFICATION.md` | LIVE | EXECUTE — final close |

  **kb-4-lite execution path = run kb-4-04 → 05 → 06 → 07 (Aliyun-retargeted) → 08; mark 01/02/03 NO-OP via SUMMARY.** This unlocks aim-N plan-phase per Gate 1 Option A.

### What's locked (do not re-discuss)

- **Goal:** bilingual (zh-CN / en) Agent-tech content site, Ubuntu deploy, public
  zero-login access, no SEO framing
- **Tech stack:** Python 3.11+ / FastAPI + uvicorn / Jinja2 SSG / SQLite FTS5 trigram
- **Bilingual:** UI chrome 双语 + 文章原文不翻译 + cookie/query lang 切换
- **Search:** SQLite FTS5 trigram (built-in 3.34+, 中英通杀)
- **Q&A:** kg_synthesize 包装,KB 层注入 lang directive,**不破契约 C1**
- **URL:** `/article/{md5[:10]}` content_hash 运行时计算 (K-2)
- **Deploy:** Ubuntu systemd unit + Caddy 反代,**不依赖 Hermes agent runtime**
- **File pattern:** parallel-track suffix files (PROJECT-KB-v2.md etc.)
- **Out of scope:** 内容自动翻译 / 跨语言搜索 / KB-2 实体页 / Databricks 部署 /
  rate limiting / Repository 抽象 / SEO 推送
- **No research step** — kb/docs/ 已有完整设计,research 跳过

### Things to remember when resuming

1. **kb/docs/01-PRD.md §4 SEO 章节、所有 SEO-* / PAGE-* / LINK-* REQs 整组废止** —
   实施时按本 milestone 定义的 scope 走。但保留 web 礼仪基线(sitemap.xml / robots.txt
   / og:tags / JSON-LD,含 inLanguage 字段)
2. **数据现状(本地 dev)**:KOL 4/653 篇有 content_hash(0.6%)— 运行时 fallback;
   RSS 1600/1600 全有完整 md5(截取 [:10]);entity_canonical 仅 13 行(撑不起 KB-2)
3. **`articles.lang` / `rss_articles.lang` 列不存在** — kb-1 phase 第一步就是一次性
   migration + detect 脚本,**这是 schema-extending non-breaking 改动**(C3 不破)
4. **vitaclaw-site brand assets 复用**:logo `VitaClaw-Logo-v0.png` / favicon
   `favicon.svg` / 品牌色 `#0f172a` / 品牌名"企小勤"(英文辅助"VitaClaw")
5. **失败降级策略**:/synthesize 失败 → FTS5 top-3 摘要拼接 + 置信度标记,**不返 500**
6. **REQUIREMENTS-KB-v2.md header text says "37 REQs"; actual count is 50.**
   Roadmap and traceability use 50. Header is stale; reconciliation is a
   separate doc-fix task.

### Pending Todos

None tracked. Awaiting `/gsd:discuss-phase kb-1` or `/gsd:plan-phase kb-1`
invocation.

### Blockers/Concerns

- **None for milestone init or roadmap.** All 4 cross-milestone contracts (C1-C4)
  are read-only; the only schema change (DATA-01 nullable `lang` column) is
  C3-additive non-breaking.
- **Operator-side dependencies** (deferred to kb-4): Ubuntu host with SQLite
  ≥ 3.34 (FTS5 trigram tokenizer support); Caddy installed; cron available;
  optional `KB_DB_PATH` / `KB_IMAGES_DIR` overrides if not deploying same-host
  with `~/.hermes/omonigraph-vault/`. None of these block kb-1 or kb-3
  development.

### v2.2-future / 已识别但未排期

- **translate_kb.py 增量 flush + resume guard** (kb-v2.2-7 Phase 5 backfill 后识别 2026-05-21) — 当前 `databricks-deploy/translate_kb.py` 单 batch 全跑无 checkpoint(5h 22min wallclock 跑 234 行译文,中断即丢全部 in-memory 结果),无增量 `apply.sql` flush,无 resume guard。下次大批量(>200 行)backfill 前需补:每 N 行 flush 一次 apply.sql + 每行写 progress marker + 启动时检查 marker 跳已译。来源 `.scratch/translate-backfill-260520.md`。Forward-only register,不立 phase,等下次实需触发。

## Performance Metrics

(populated as plans complete)

## Session Continuity

Last session: 2026-05-17 (kb-v2.2 milestone-open + tonight's Aliyun storage stale-snapshot debug)
Stopped at: kb-v2.2 INPUT.md committed; 7 phases queued across 3 waves; F9 already shipped prod-side; F12 elevated to P0 prereq based on stale-snapshot empirical finding
Resume file: `.planning/phases/kb-v2.2-translation-and-kg-search/INPUT.md`
Next command: `/gsd:plan-phase kb-v2.2-1` (F12 sync mechanism — Wave 1 P0 prereq)
