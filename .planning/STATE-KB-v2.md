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
Last activity: 2026-05-19 — **kb-v2.2-7 (bilingual-by-site-language) COMPLETE**. Replaces kb-v2.2-2 F1' on-demand button-based UX with site-language-driven static SSG rendering: dual-`<span data-lang>` h1 + dual-`<article class="article-body lang-block" data-lang>` body siblings; `KB_DEFAULT_LANG` env var injected per-deploy as `window.KB_DEFAULT_LANG` (Aliyun=zh-CN, Databricks=en); `lang.js` first-visit cookie persistence + `data-fixed-lang` runtime guard removed; F1' API surface (POST/GET `/api/translate`, `?lang=` query, `_load_translation`, `kb/services/translation.py`, translate-row UI) deleted. Translation production via `databricks-deploy/translate_kb.py` single-file notebook (manual "Run all" trigger, no automation). Wave 6 UAT discovered + patched 2 Wave-4 regressions (article.html standalone missed base.html injection; pre-existing `.nav-links a span { display: inline }` CSS override at desktop viewport blocked dual-span nav flip). Commits: `9fd518c` PLAN, `5d14560` Wave 1 data layer, `25791df` Wave 2 notebook, `36e10b7` Wave 3 deletion, `f9968a1` Wave 4 SSG, `bac0706` Wave 5 lang.js, _(Wave 6 commit pending finalization)_. Verification: `.planning/phases/kb-v2.2-translation-and-kg-search/kb-v2.2-7-bilingual-by-site-language-VERIFICATION.md`. Local UAT artifacts: `.playwright-mcp/kb-v2-2-7-uat-*.html|css|js|png` (10 files).

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
| **kb-2** | Topic Pillar + Entity Pages + Cross-Link Network | **12** | M (1.5-2d) | TBD | **NEW 2026-05-13** — revived from "skipped" after Hermes prod data verification |
| kb-3 | FastAPI Backend + Bilingual API + Search + Q&A | 18 | L | TBD | not started |
| kb-4 | Ubuntu Deploy + Cron + Smoke Verification | 5 | S | TBD | not started (UI-04 carry-forward gate) |

Total: **62/62 v2.0 REQs** mapped (was 50; +12 from kb-2 revival). kb-1: 26/27 satisfied + 1 deferred-by-approval (UI-04). kb-2/3/4: 35 REQs pending.

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

## Performance Metrics

(populated as plans complete)

## Session Continuity

Last session: 2026-05-17 (kb-v2.2 milestone-open + tonight's Aliyun storage stale-snapshot debug)
Stopped at: kb-v2.2 INPUT.md committed; 7 phases queued across 3 waves; F9 already shipped prod-side; F12 elevated to P0 prereq based on stale-snapshot empirical finding
Resume file: `.planning/phases/kb-v2.2-translation-and-kg-search/INPUT.md`
Next command: `/gsd:plan-phase kb-v2.2-1` (F12 sync mechanism — Wave 1 P0 prereq)
