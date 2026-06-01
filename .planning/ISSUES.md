# OmniGraph-Vault Issue Tracker

**Status:** Living document — single source of truth for known unfixed issues outside active phases.
**Owner:** Orchestrator (main session) maintains; agents read but do not delete entries.
**Created:** 2026-05-30
**Last updated:** 2026-06-01 (260601-ipo Aliyun ingest OOM mitigation IN FLIGHT — #4 marked stale + replaced by #25 RAM-mitigation entry; commit 91b33f1 deployed) + perf-fix-B HT-4 halt — reconcile follow-up filed (#26) + #27 kb-api hydrate throttle DoS-by-restart filed post double-deploy

---

## How to use this file

This is the **issue tracker** for known problems / tech debt / deferred work that is NOT currently in flight. Active phase work lives in `.planning/phases/<milestone>/STATE-*.md`. Active quick work lives in `.planning/quick/<slug>/`. Once a phase or quick closes, issues that surfaced during it but were filed as out-of-scope follow-up land HERE.

**Lifecycle of an entry:**

1. Surfaced (during phase / quick / orchestration) → orchestrator adds row with severity + slug
2. Picked up by a quick / phase → entry annotated `In flight: <quick-slug>` (don't move; let it block in place)
3. Resolved → entry annotated `RESOLVED <date> <commit>` and moved to "Resolved (recent)" section
4. After 30 days in Resolved, moved to `archive/issues-resolved-YYYY-MM.md`

**Severity levels:**

- 🔴 **P0** — Blocks main line / breaks user experience / data correctness. Fix in next available cycle.
- 🟡 **P1** — Important but not blocking. Schedule within ~1 week.
- 🟠 **P2** — Cleanup / tech debt. Schedule when matched cleanup window is open.
- 🟢 **P3** — Future scope. Park; revisit on milestone boundaries.
- 🔵 **Doc** — Configuration / documentation gap. Fix opportunistically.

**Update policy:**

- Orchestrator updates this file when new issues surface or when status changes.
- Agents may **read** to inform decisions but should NOT edit; they file new issues by reporting them in their close-out summary, orchestrator adds the row.
- When closing a quick / phase, orchestrator MUST scan the close-out report for newly surfaced issues and add rows here BEFORE marking quick CLOSED.

---

## Open issues

### 🔴 P0 — Blocking / Data correctness

| # | Issue | Suggested slug | Notes |
|---|---|---|---|
| 1 | id=24 (and 11 other rows) `body=''` permanently untranslatable — translate cron SQL filter `body != ''` skips them. They have `layer2_verdict='ok'` so DATA-07 still surfaces them on KB pages with original-only text. | `260530-id24-body-empty-cleanup` | 12 stuck rows total (~3.9% of 310 layer2='ok'). Either backfill body via re-scrape or flip verdict to 'reject'. Filed 2026-05-30 P2-3 prep. |
| 2 | Vertex 429 RESOURCE_EXHAUSTED on Layer 1 batch 4 burst (30 articles stay NULL classification). | `260530-vertex-burst-isolation` | Daily-ingest auto-retries next cron. Watch for chronic accumulation; if persistent across 3+ days, isolate to its own GCP project. Filed 2026-05-30. |
| 25 | **Aliyun all-in-one + LightRAG nano-vectordb full-load is the structural OOM root cause.** 260601-ipo capped peak via systemd `MemoryMax=4G` + `Conflicts=` mutex + LightRAG concurrency 4→2 + `gc.collect()` per article. This is band-aid; treats symptom not root. **Real fix: LightRAG → Qdrant migration** (user wrote design doc PR #4 `ops/qdrant-migration` branch). After migration the full-vdb load that drives 3 GB baseline RSS goes away — Qdrant serves vectors over network, ingest worker holds only the working set. **2026-06-01 update — UPGRADED P0 + #26 + part of #27 FOLDED IN per orchestrator decision.** Single Aliyun kb-api restart will ship 3 changes together (Qdrant cutover + perf-fix-B rerank env block + #27 hydrate-throttle structural fix), minimizing #27 hydrate-throttle blast radius vs running 3 separate restarts. **Acceptance criteria expanded:** (1) Qdrant docker run + LightRAG `vector_storage="QdrantVectorDBStorage"` (Aliyun ingest path); (2) re-ingest 287 KOL articles to populate Qdrant collection; (3) batch_ingest Python RSS ≤1 GB peak (was 10.9 GB OOM); (4) **MUST append 4 `OMNIGRAPH_LLM_RERANK_*` env lines to `/etc/systemd/system/kb-api.service.d/override.conf` (folded from #26)**; (5) **MUST cover HT-6 N=4 concurrent /api/synthesize lock-break verification on Aliyun (transferred A→B→#26→#25 chain)**; (6) Aliyun kb-api hydrate ≤30s (was 56min — #27 closes when this passes); (7) Cross-station design — Databricks/Hermes read-side strategy (path 1 LightRAG QdrantVectorDBStorage local file mode if viable; OR path 2 Aliyun dual-write maintaining vdb_*.json for sync-replication). 调研 prompt already authored; awaits dispatch when user triggers. | `v1.1-qdrant-migration` (user-owned doc) | **UPGRADED 2026-06-01 P3→P1→P0** — folded #26 reconcile + structural #27 hydrate fix together. Triggered when user dispatches the cross-station调研 followed by plan-phase. Single-restart-shipping-three-changes minimizes hydrate-throttle exposure. |

<!-- Issue #21 resolved 2026-05-31 — see Resolved (recent) row R18 below. -->

### 🟡 P1 — Important but not blocking

| # | Issue | Suggested slug | Notes |
|---|---|---|---|
| 3 | **Wiki body single-language** — only outer chrome (breadcrumb / sources label / pill) is bilingual; wiki body markdown is whatever the .md author wrote (currently English for Copilot Studio entities). EN/中 toggle leaves body unchanged. | `260530-wiki-bilingual-decide` | Three paths: A manual dual-section per .md, B SSG-bake auto-translate (mirrors articles pipeline), C accept current. Decision delegated to user. Filed 2026-05-30. |
| 4 | ~~`daily-ingest.service` single-article LightRAG ainsert can run 8h+~~ | ~~`260530-ainsert-budget-timeout`~~ | **STALE — ALREADY SHIPPED** Phase 17 BTIMEOUT (2026-05-17). `_SINGLE_CHUNK_FLOOR_S=1200s` floor + chunk + image budget via `asyncio.wait_for` (`batch_ingest_from_spider.py:395`); env override `OMNIGRAPH_BATCH_TIMEOUT_SEC` (`batch_ingest_from_spider.py:298`). Verified during 260601-ipo Phase 0. Move to Resolved on next ISSUES update. |
<!-- Issue #25 promoted to P0 section above on 2026-06-01 — see #25 row under "🔴 P0 — Blocking / Data correctness". -->
| 5 | `kb/wiki/_suggestions/` (W1 hook fire-and-forget output) has no review queue; suggestions accumulate without human gate. | TBD | Post-Wave-3 wiki workflow audit. Decision needed: keep W1 gate, retire it, or build review UI. |
| 6 | `test_css_budget_within_2100` pre-existing failure — `kb/static/style.css` 2172 lines vs budget 2150. Last css change e05d597 (kb-3-qa F1+F2). | `260530-css-budget-overrun` | Two paths: trim style.css to ≤2150 (audit + remove unused tokens) or raise budget to 2200 with diff justification. NOT in P2-3 scope (SC#5 / HT-5). Filed 2026-05-30 P2-3 T4. |
| 22 | **v1.1.P2-3-perf-fix-B Aliyun Vertex Gemini rerank parity** — A (Databricks) ships dispatcher; B adds `lib/vertex_gemini_rerank.py` Vertex helper + `lib/llm_rerank.py` vertex_gemini route + Aliyun systemd env update + Aliyun deploy + smoke. **In flight 2026-05-31** as `v1.1.P2-3-perf-fix-B` plan-phase. PLAN.md + CONTEXT.md committed; plan-checker PASS iteration 1; LoC est revised to ~+154 net (above original +65 — 7-task scope with parse-scores duplicate + integration tests + halt-and-document T6 path). **MUST cover HT-6 deferred from A:** N=4 concurrent /api/synthesize lock-break test (P5 contract verification) was DEFERRED in A close because Databricks Apps OAuth proxy rejects local PAT pytest with 502. Aliyun has direct SSH + uvicorn access — B Track 4 UAT MUST run N=4 lock break against deployed Aliyun kb-api and cite log evidence in B-VERIFICATION.md. **2026-06-01 update:** B execute-phase shipped T1-T5 (5 commits `e01f874`..`62fc544`, +154 net LoC); T6 Aliyun deploy halted at HT-4 substantive systemd drift; T7 wrote VERIFICATION.md status `code-shipped-aliyun-deploy-deferred`. **HT-6 N=4 lock-break verification transferred to reconcile follow-up (#26).** SC#3 + SC#4 (lifespan layer) + SC#5 + SC#7 PASS; SC#1-Aliyun + SC#2-Aliyun + SC#6 smoke deferred along with deploy. | `v1.1.P2-3-perf-fix-B` | Plan-phase status: PLAN+CONTEXT ready, plan-checker PASS. Execute waiting on user trigger. |
| 27 | **kb-api restart triggers ~8min Aliyun public network throttle — DoS-by-restart risk.** 2026-06-01 double-deploy session: post `systemctl restart kb-api.service`, LightRAG hydrate took wall_s=3362.65 (56min) loading 31777 entities + 45839 relations + 31777 entity_chunks + 45852 relation_chunks @ 3072-dim. During the first ~8min of hydrate (12:22-12:30 CST), full Aliyun ECS public network throttled — SSH banner timeout, Caddy timeout, ICMP 100% loss, BUT vitaclaw cohabiting on the same ECS stayed reachable per user console probe. Recovery happened on its own without operator intervention. Inferred root: hydrate I/O+RAM saturation triggered SLB / network-stack cross-border throttling; not a kernel panic, not a kb-api crash, not the OOM-fix from 91b33f1. Any future routine kb-api restart (deploy / config update / OOM cap edit) will reproduce. **Mitigation paths:** (a) lazy hydrate — defer LightRAG init until first /api/synthesize request, (b) background warmup — uvicorn lifespan returns ready, hydrate runs in `asyncio.create_task` background, /api/synthesize blocks on ready-event, (c) Caddy 504 graceful degrade during hydrate window, (d) deeper: structural fix is `v1.1-qdrant-migration` (#25) which cuts hydrate time by orders of magnitude (Qdrant mmap vs full JSON load). | `260601-kb-api-hydrate-throttle` (suggested) OR fold into `v1.1-qdrant-migration` (#25) | Filed 2026-06-01 by orchestrator post double-deploy completion. P1 because every kb-api restart is now a 56min slow-start + 8min public-network outage; mitigates with #25 Qdrant migration but standalone path (a)/(b) is single-quick scope. Decision: pick standalone or fold into Qdrant migration. |
| 26 | **v1.1.P2-3-perf-fix-B reconcile follow-up — Aliyun systemd drift + apply rerank env + HT-6 N=4 lock-break verification.** B execute-phase 2026-06-01 halted at T6 HT-4 because live `/etc/systemd/system/kb-api.service` on Aliyun has substantive drift vs repo template `kb/deploy/kb-api.service` (User=root vs kb, /root vs /home/kb paths, `EnvironmentFile=/root/.hermes/.env` unique to live, no sandboxing block in live, Aliyun-only `OMNIGRAPH_LLM_PROVIDER=deepseek` + `OMNIGRAPH_BASE_DIR` Environment= lines). Wholesale `cp` would clobber live customizations. **Recommended path:** systemd drop-in `/etc/systemd/system/kb-api.service.d/override.conf` is already used for Aliyun-specific overrides (MemoryMax=12G, KB_DEFAULT_LANG=zh-CN, KB_SYNTHESIZE_TIMEOUT=240, KB_LIGHTRAG_INNER_TIMEOUT=150, LIGHTRAG_EMBEDDING_TIMEOUT=90) — append the 4 rerank `Environment=` lines there; zero touch to base unit; trivial rollback. **MUST cover HT-6 N=4 concurrent /api/synthesize lock-break test (P5 contract verification on Aliyun)** — transferred from #22 because B's T6 was the original carrier and is now deferred. **Pre-flight already verified 2026-06-01 in B's T6:** SA JSON present at `/root/.hermes/gcp-paid-sa.json`, `GOOGLE_CLOUD_PROJECT/LOCATION/CREDENTIALS` set in `/root/.hermes/.env`, `/etc/hosts` Vertex pin in place. Backup `/etc/systemd/system/kb-api.service.bak-pre-perf-fix-B` taken pre-halt. **Acceptance:** SC#1-Aliyun (cold-start ≤60s after `systemctl restart`), SC#2-Aliyun (3 zh-CN smoke wall_s ≤65s mode='mix'), SC#6 (UNSET-env baseline still works), HT-6 (N=4 lock-break passes), evidence captured to `.planning/phases/v1.1-roadmap/<reconcile-slug>/aliyun-evidence/`. Closes HC-6 Aliyun parity gate. **2026-06-01 update — FOLDED INTO #25 per orchestrator decision** (orchestrator option (c)): rerank env block + HT-6 N=4 verification will be applied as part of the #25 Qdrant migration's Aliyun kb-api restart, minimizing #27 hydrate-throttle blast radius (single restart ships Qdrant cutover + rerank env + structural hydrate fix together). #26 not closed-as-WONTFIX — work still happens, just inside #25's restart window. Acceptance criteria + evidence path moved to #25. | `v1.1-qdrant-migration` (folded into #25) | Filed 2026-06-01 from B execute-phase HT-4 halt. Plan-phase tier (multi-step ops). Drift diff captured in `.planning/phases/v1.1-roadmap/P2-3-perf-fix-B/aliyun-evidence/systemd-drift-diff.txt`. **No standalone reconcile phase will run** — all reconcile work happens inside #25 plan-phase. |

### 🟠 P2 — Cleanup / Tech debt

| # | Issue | Suggested slug | Notes |
|---|---|---|---|
| 7 | `.planning/quick/20260525-200047-synthesize-audit/` untracked directory, several days. | `260530-stale-quick-gc` | Re-evaluated 2026-05-30: dir contains real audit doc + 4 logs (synthesize deep audit that surfaced FTS5 syntax bug → resolved later via e05d597). NOT empty residue. Action revised: archive to `.planning/quick/archive/` rather than delete. |
| 8 | `databricks-deploy/_aliyun_pull/` ~4.4 GB local sync residue from manual sync runs. | TBD | gc; can re-pull on next sync. .databricksignore already covers it. |
| 9 | `.scratch/sync-to-databricks-*.log` (2 files) + `.scratch/databricks-deploy-*.log` accumulating in scratch. | TBD | gitignored; opportunistic local cleanup. |
| 11 | `.planning/STATE.md` "Quick Tasks Completed" table style inconsistent — early entries are 1000+ char single-line dumps; recent (260530-d8j, 260530-gf1) entries use concise multi-line summary. | TBD | Decide canonical format and either reformat history or leave drift annotation. |
| 23 | **Trim `sentence-transformers` + `torch` from requirements files** after `v1.1.P2-3-perf-fix-B` closes. Saves ~1.2 GB deploy + faster pip install. Currently retained in `requirements.txt` + `databricks-deploy/requirements.txt` for Rollback Plan #4 (partial revert path keeps BGE wrapper restorable). Cleanup, not blocking. | TBD (post-B) | Filed 2026-05-31 P2-3-perf-fix-A RESEARCH §8. Surgical Changes principle delays this trim until rollback option no longer needed. |
| 24 | **Markdown lint cleanup** — `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/PLAN.md` + several other planning files have MD022/MD031/MD032 (heading/list/fence blank-line) + MD060 (table-pipe-spacing) warnings. Cosmetic; lint never enforced repo-wide. | TBD | Opportunistic cleanup. Filed 2026-05-31. |

### 🟢 P3 — Future scope (parked)

| # | Issue | Suggested slug | Notes |
|---|---|---|---|
| 13 | **P1 K2 citation revisit** (α path ~+14 LoC) — extract `full_doc_id` from LightRAG chunk metadata to replace LLM-output regex citation. Deferred 2026-05-28 (γ choice) until P5 ships; P5 shipped 2026-05-29, can re-evaluate. | `v1.1.P1-revisit` | Low priority — user has not raised citation accuracy as a complaint. Plan-phase tier when picked up. |
| 14 | **P4.0 / P4.1 ARAG audit + salvage** — read-only audit `lib/research/*` (P4.0), then mutating salvage + frontend "Deep Research" tab (P4.1). | `v1.1.P4-0` / `v1.1.P4-1` | Wave 3, blocked on Wave 1 + Wave 2. Path locked C (self-build) 2026-05-29 after MS ARAG evaluation. |
| 15 | **P6.1 fixture drift audit** — full pass over `tests/unit/_ingest_fixtures.py` schema vs production migrations + `test_search_kg_job_completes` mock rewire. | `v1.1.P6-1` | Wave 4 housekeeping. Schedule after Wave 2 stabilizes. |
| 16 | **P7 Pydantic mode-arg silent ignore** — `/api/search/kg` accepts `mode` arg but body schema silently drops it. ~1 line + 1 test. | `v1.1.P7` | Side decision — fold into P1 if P1 shipping window aligns, else standalone v1.1.x quick. |
| 17 | **wiki-bilingual-ssg-bake** — long-term: SSG bake auto-translates wiki body via DeepSeek/Vertex pipeline (mirrors `articles` `body_translated` pattern). Replaces Issue #3 path B. | `260530-wiki-bilingual-ssg-bake` | 1-2 day phase-tier. Triggered when Issue #3 decision = path B. |
| 18 | **Databricks PAT rotation** — token leaked once in earlier `env \| grep ANTHROPIC` Bash output. | TBD | Rotate at user's convenience. Not blocking; new PAT must update `~/.databrickscfg` `[dev]` profile. |

### 🔵 Doc / Config gaps

(currently empty — #19 and #20 resolved 2026-05-30 via `260530-gf1`)

---

## Resolved (recent — last 30 days)

| # | Issue | Resolved | Commit(s) | Quick / Phase |
|---|---|---|---|---|
| R1 | `daily_rebuild.sh` Phase 1 silent-fail since 2026-05-20 (KB_DB_PATH not exported, subprocess fell to nonexistent path). | 2026-05-30 | `f56a4a6` | `260530-d8j` |
| R2 | `/var/www/kb/` 9 days stale, no auto-sync from `kb/output/` after SSG bake. | 2026-05-30 | `f56a4a6` (Phase 5 rsync) | `260530-d8j` |
| R3 | `KB_BASE_PATH` empty default broke Aliyun KB site after `260530-d8j` shipped — HTML emitted bare `/static/*`, Caddy `/kb/*` handle never matched, all CSS/img 404. | 2026-05-30 | `d7b3749` | hot-fix follow-up to `260530-d8j` |
| R4 | Wiki SSG bake (`kb/export_knowledge_base.py:_convert_wiki_citations`) only handled legacy `^[article:hash]` tokens; SCHEMA-2026-05-20 introduced GFM `[^N]` + multi-type sources but bake path was not updated. | 2026-05-29 | `b4a87ce` | `260529-hlu` |
| R5 | Aliyun translate cron never registered as systemd timer; body translation backlog grew indefinitely without auto-trigger. | 2026-05-29 | `241d7dd` | `260529-arm-translate-cron` |
| R6 | `.scratch/deploy_inline_*.sh` recurring drift (2026-05-25 inline missed 3 critical `--include` flags → arx-3 singleton REGRESSION). | 2026-05-29 | `c2cfe0c` | `260529-d3p` |
| R7 | No script for Aliyun → Databricks data sync; the 22-step manual procedure from `260528-f1s` was not reusable. | 2026-05-29 | `7544234` | `260529-arx` |
| R8 | LightRAG version pin drift — root `requirements.txt` 1.4.16 ≠ `databricks-deploy/requirements.txt` 1.4.15 ≠ venv 1.4.15. P2-3 plan-phase Phase 0 surfaced. | 2026-05-30 | `2b922d0` | P2-3 Phase 0 cleanup |
| R9 | `databricks-deploy/requirements.txt` `python-frontmatter` line dirty for 5 days (2026-05-25 hot-fix slipped commit). | 2026-05-30 | `20a4094` | P2-3 Phase 0 cleanup |
| R10 | `sync_to_databricks.sh` `read -p` lost stdin when run as background task → silent abort exit 0 in 30s instead of 70-min full sync. | 2026-05-30 | `149130a` (`--yes` flag) | 4-cleanup batch |
| R11 | `sync_to_databricks.sh` Step 9c race: `apps start` auto-creates pending SNAPSHOT deployment that locks Step 9c `apps deploy` for 20+ min. | 2026-05-30 | `149130a` (poll-pending fix) | 4-cleanup batch |
| R12 | Aliyun SSH manual trigger silently 401s (`DEEPSEEK_API_KEY=dummy` fallback) because `EnvironmentFile=/root/.hermes/.env` is systemd-only, plain SSH shell doesn't source. | 2026-05-30 | `f6b3b97` (`run_with_env.sh`) | 4-cleanup batch |
| R13 | Tavily Python module not installed in Aliyun `venv-aim1` → translate cron WARNINGs every run (non-fatal but degrades quality). | 2026-05-30 | (Aliyun pip install only, no commit needed) | 4-cleanup Step 1 |
| R14 | CLAUDE.md PRINCIPLE #3 (Surgical Changes) didn't document "wiki cross-link reverse edits to other people's wiki pages = boundary breach". Captured 2026-05-29 commit f5da904 lesson but not propagated to CLAUDE.md until now. | 2026-05-30 | `ce59612` | `260530-gf1` |
| R15 | `databricks-deploy/deploy.sh` (Databricks deploy) and `kb/scripts/daily_rebuild.sh` (Aliyun) had asymmetric `KB_BASE_PATH` requirement (Databricks empty, Aliyun `/kb`) undocumented; future readers would copy one into the other. | 2026-05-30 | `1a1e31d` | `260530-gf1` |
| R16 | `databricks-deploy/_ssg/` build artifact path confusing (suggests committed source, actually gitignored). | 2026-05-30 | `758e21b` (`databricks-deploy/_ssg/.README.md` written) | `260530-gf1` |
| R17 | Memory `aliyun_drift_recovery_260528_lessons.md` Lesson 1 v3 + v4 wording overlap (same root mechanism: systemd `Requires=` cascade described twice). | 2026-05-30 | (out-of-tree memory file edit, no repo commit) | `260530-gf1` |
| R18 | **P2-3 reranker DEPLOYED-DISABLED** (BGE_FORCE_LOAD_FAIL=1 escape) — replaced with LLM-as-reranker (Databricks Haiku batch JSON). All 6 SC PASS on `01f15d1bcce2189db0557d701a97bf9f`: cold-start 28.15s, qa_seed mean 59.43s, prod-batch 21.07s, token-overlap 1.00 perfect, graceful-degrade verified, kb/static+templates 0 touches, legacy BGE env retained for rollback compat. | 2026-05-31 | `6feb210` `c257c64` `a26ea01` `664c14c` `b8f3baf` + T6 | `v1.1.P2-3-perf-fix-A` |

---

## Cross-references

- **Phase milestone state:** `.planning/phases/v1.1-roadmap/STATE-v1.1.md`
- **Roadmap & success criteria:** `.planning/phases/v1.1-roadmap/ROADMAP.md`
- **Project guide:** `CLAUDE.md` (PRINCIPLE #10 governs this file's update discipline)
- **Memory index:** `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/MEMORY.md`

---

## Adding a new issue

When orchestrator (or any agent during close-out) surfaces a new issue:

1. Choose severity (P0/P1/P2/P3/Doc).
2. Add a row to the appropriate table with:
   - Short title (≤ 100 chars)
   - Suggested slug (`260530-<short>` if known, `TBD` if not)
   - Notes (1-3 sentences: root cause / decision / next action)
3. If the issue had a triggering quick / phase, link the relevant SUMMARY in Notes.
4. Update `Last updated:` at top.

**Do NOT** delete entries when fixed — move them to `Resolved (recent)` with date + commit. The history matters for postmortem and pattern detection.
