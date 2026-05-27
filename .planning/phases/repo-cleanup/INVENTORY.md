# Repo Cleanup — Phase 1 INVENTORY (read-only)

**Phase:** 1 of 4 — read-only inventory
**Date:** 2026-05-26
**Mode:** No mutations. No `git mv`, no `git rm`, no Edit/Write outside this phase dir.
**Next step:** await user `go triage` → produce TRIAGE.md (Phase 2).

> **Scope of this document.** Surface candidates by 6-bucket schema (A–F) with evidence + cross-refs. Classifications are DRAFT, not verdicts. Mutation never happens in Phase 1. The user adjudicates in Phase 2.

---

## In-flight HOLD-LIST (verified — must NOT appear in any candidate row below)

Confirmed present on filesystem; cross-checked against every "stale" candidate in this document:

**Phases (`.planning/phases/`)**
- `aim-4-daily-sync/` — 10 files (May 24 21:23, modified May 24 22:03 youngest)
- `aim-5-stability-watch/` — 9 files (May 24 22:03)
- `ar-1-mvp-vertical-slice/` (May 23 19:48)
- `ar-2-reasoner-vision-deepening/` (May 23 19:48)
- `ar-3-verifier-web-tools/` (May 23 19:48)
- `ar-4-telemetry-streaming-smoke/` (May 24 18:28)
- `repo-cleanup/` (this phase, May 26)

**Quicks (`.planning/quick/`)**
- `20260525-200047-synthesize-audit/` (May 25 20:08, untracked per `git status`)
- `260525-c1-no-content-at-64s/` (May 26 12:44 — youngest)
- `260524-tk5-kb-longform-c1-hang/` (May 24 21:22)
- `260524-tvg-wechat-session-hardening/` (May 24 21:33)
- `260525-vnj-vitaclaw-news-3shot-ingest/` (May 25 10:44 — within 48h, treat as in-flight unless triage flips)
- `260524-arx-A-images/` (May 25 09:34 — see Q(a))
- `260524-tk5b-databricks-sdk-deterministic-llm-hang/` (May 25 09:47 — within 48h)

**Working-tree uncommitted (other agents' lanes — must NOT touch)**
- `databricks-deploy/requirements.txt` (modified, per `git status`)
- *(historical: `databricks-deploy/app.yaml`, `kb/api.py`, `lib/research/__init__.py`, `lib/research/orchestrator.py`, `kb/services/synthesize.py` — none currently appear in `git status`, but treat all `databricks-deploy/`, `kb/`, `lib/research/` paths as agent-owned)*

**Hard-do-not-touch (load-bearing strings/paths)**
- The literal string `omonigraph` (typo is canonical; deployed)
- `~/.hermes/omonigraph-vault/` — Hermes runtime data root
- LightRAG storage paths (`lightrag_storage/`, `RAG_WORKING_DIR`, `vdb_*.json`, `kv_store_*.json`, `graph_chunk_entity_relation.graphml`)
- CLAUDE.md lines 1–117 (HIGHEST PRIORITY PRINCIPLES 1–7)
- `MEMORY.md` entries actively pointed-to by load-bearing memory files (cross-checked in Bucket B)

---

## Bucket A — CLAUDE.md sections (`CLAUDE.md`, 929 lines, ~57 KB)

> **Method:** parsed `^#`/`^##`/`^###` headings; classified by content recency + duplication with archived sources.
> **Token-delta column intentionally deferred to Phase 4** (per user accept-R2). Phase 2 will only see line-range estimates.

| § | Section | Lines | Bucket | Reason / Cross-ref |
|---|---|---|---|---|
| A1 | `# HIGHEST PRIORITY PRINCIPLES` 1–7 | 5–117 | **KEEP — load-bearing** | Listed in user's HARD-CONSTRAINT 1. Must not change. |
| A2 | `## Project-Specific Disciplines` → Behavior-Anchor Harness | 119–133 | **KEEP — load-bearing** | Active rule, cited by `tests/unit/test_ingest_from_db_orchestration.py`. |
| A3 | `## Project Summary` | 135–143 | KEEP | Stable, 9 lines. |
| A4 | `## Release Status` | 145–171 | **CANDIDATE COMPACT** | v1.0 + v1.0.x retrospective; v1.0.y closure already in MEMORY (`project_v1_0_y_closure_260517.md`). Patch A/T1 marked "in flight" but both shipped/validated per memory. Could shrink to "v1.0 baseline + see MEMORY index for closure dates". |
| A5 | `## Common Commands` (incl. Local E2E sub-section) | 174–258 | **CANDIDATE COMPACT** | Local E2E section (lines 210–258, ~48 lines) duplicates info in `scripts/local_e2e.sh help` output — could shrink to "see `./scripts/local_e2e.sh help`". Reachability table (line 232–246) is pinned-2026-05-08 snapshot — maybe move to a dated runbook. |
| A6 | `## Architecture` (Ingestion / Query / Key Integration / Env Vars / Local dev env vars) | 260–329 | KEEP (mostly) | env-var tables are reference material. `Local dev env vars (quick task 260504-g7a)` block cites a 2026-05-04 quick — content still valid; cross-cite OK. |
| A7 | `## Development Conventions` | 331–338 | KEEP | 8 lines, stable. |
| A8 | `## OpenClaw / Hermes Skill Writing Standards` | 340–453 | **CANDIDATE EXTRACT** | ~113 lines of standards copy-pasted from external docs (`docs.openclaw.ai`, `dench.com/blog/...`, etc.). Could move to `docs/skills/SKILL_STANDARDS.md` and replace with a 3-line @-pointer. Largest single compaction win. |
| A9 | `## Testing the CDP / MCP Scraping Path` | 456–500 | **CANDIDATE EXTRACT** | Manual test runbook; not consulted at session-start. Move to `docs/runbooks/cdp_mcp_test_paths.md`. |
| A10 | `## Remote Hermes Deployment` | 503–545 | KEEP (trim) | Memory `[[hermes_ssh]]` already stores SSH details. Lines 519–525 (workflow) duplicate Principle #5; could collapse the workflow numbering. |
| A11 | `## Lessons Learned` | 547–555 | KEEP | Already compacted (2026-05-25); points to `docs/lessons/2026-05-archive.md`. Q(d) confirms this is the canonical archive. |
| A12 | `## Vertex AI Migration Path` | 557–589 | **CANDIDATE EXTRACT** | ~32 lines design context; full spec already at `docs/VERTEX_AI_MIGRATION_SPEC.md`. Could shrink to 5-line "when-to-trigger" + pointer. |
| A13 | `## Checkpoint Mechanism` | 592–612 | **CANDIDATE EXTRACT** | ~20 lines runbook. Move to `docs/runbooks/checkpoints.md`. |
| A14 | `## Vision Cascade` | 614–627 | KEEP (trim) | Active operational behavior; trim duplication of cascade order with `## SiliconFlow Balance Management` below. |
| A15 | `## SiliconFlow Balance Management` | 629–642 | **CANDIDATE EXTRACT** | ~14 lines balance/depletion runbook. Move to `docs/runbooks/siliconflow_balance.md`. |
| A16 | `## Batch Execution` (incl. MAX_ARTICLES tri-governor) | 644–679 | KEEP | Tri-governor block (665–679) cited by memory `[[project_v1_0_y_closure_260517]]`. |
| A17 | `## Known Limitations` | 681–686 | KEEP | 6 lines, stable. |
| A18 | `## Project` (constraints + value statement) | 688–703 | KEEP | 16 lines, stable. |
| A19 | `## Technology Stack` (Languages / Runtime / Frameworks / Key Dependencies / Configuration / Platform Requirements) | 705–759 | **CANDIDATE COMPACT** | Auto-generatable from `requirements.txt` + `python --version`. Many bullets are stale (e.g. "kuzu — installed, used by LightRAG for graph storage" — Cognee/kuzu retired 2026-05-10). |
| A20 | `## Conventions` (Naming / Code Style / Imports / Error / Logging / Comments / Function / Module / Async / Antipatterns) | 762–826 | **CANDIDATE EXTRACT** | ~64 lines auto-derived style notes. Move to `docs/conventions.md`. Several entries flagged "Not consistently applied" — anti-rules. |
| A21 | `## Architecture` (Pattern / Layers / Data Flow / Key Abstractions / Entry Points / Error Handling / Cross-Cutting) | 827–910 | **CANDIDATE EXTRACT** | ~83 lines auto-generated layered architecture description. References stale paths (`~/.hermes/kg-vault/` instead of `omonigraph-vault/`) — needs correction OR extraction. Largest stale-content block. |
| A22 | `## GSD Workflow Enforcement` | 912–922 | KEEP | 11 lines, active rule. |
| A23 | `## Developer Profile` (placeholder) | 925–929 | KEEP | 4 lines, GSD-managed placeholder. |

**Summary — A:** 23 sections; ~7 candidate-COMPACT, ~6 candidate-EXTRACT (move to `docs/`), 10 KEEP. Largest extraction wins: A8 (Skill standards, 113 lines), A21 (auto-arch, 83 lines), A20 (auto-conventions, 64 lines), A19 (tech-stack, 54 lines).

> ⚠ **A21 contains a stale-path bug** (`~/.hermes/kg-vault/` instead of canonical `~/.hermes/omonigraph-vault/`). Two options for triage: (1) extract to `docs/architecture.md` with corrected paths; (2) hard-correct in place. Surface as triage decision.

---

## Bucket B — `MEMORY.md` + memory files

> **Location:** `C:\Users\huxxha\.claude\projects\c--Users-huxxha-Desktop-OmniGraph-Vault\memory\`
> **Index:** `MEMORY.md` (53 active entries)
> **Files in dir:** 53 referenced + 2 orphans + 1 backup = 56 total `.md` files

### B.1 — Orphan files (NOT referenced by `MEMORY.md`)

| File | Size | Last modified | Status |
|---|---|---|---|
| `feedback_kwarg_zero_ambiguity.md` | 3025 B | (memory dir) | **ORPHAN** — `grep` of `MEMORY.md` returns 0 hits. Never indexed. |
| `project_kol_scan_db_path.md` | 1652 B | (memory dir) | **ORPHAN** — `grep` of `MEMORY.md` returns 0 hits. Never indexed. |
| `MEMORY.original.md` | 8436 B | (memory dir) | **BACKUP** — caveman-compress pre-trim snapshot. Already replaced by current `MEMORY.md`. |

### B.2 — Stale-by-content candidates (still indexed in MEMORY.md)

> **Method:** entries dated ≤ 2026-05-08 whose subject is closed (project superseded / phase complete / postmortem absorbed into archive). Did NOT pre-judge — these are surfaced for user adjudication.

| MEMORY.md entry | File | Date | Why surface |
|---|---|---|---|
| Day-1 cron postmortem 2026-05-04 | `project_day1_readiness_2026_05_04.md` | 2026-05-04 | Postmortem; root cause now in `docs/lessons/2026-05-archive.md`. Q(d). |
| Hermes agent cron wrong host | `hermes_agent_cron_timeout.md` | 2026-05-04 | Same cron-timeout incident; superseded by aim-3 systemd-timer cutover (2026-05-24, still indexed as load-bearing). |
| Overnight check 2026-05-05 06:33 | `overnight_check_2026_05_05_0633_CRITICAL.md` | 2026-05-05 | One-night snapshot, root cause absorbed. |
| Morning Analysis 2026-05-05 | `morning_analysis_2026_05_05.md` | 2026-05-05 | Same incident continuation. |
| Phase 2b+ check 2026-05-05 22:27 | `phase2b_plus_check_2026_05_05_2227.md` | 2026-05-05 | Pre-cron snapshot; cron has since fired hundreds of times. |
| Reliability 5-test 2026-05-06 | `reliability_5_check_2026_05_06_1612.md` | 2026-05-06 | Pre-cutover smoke; 5/5 OK; consumed by v1.0 declaration. |
| Hermes vendor patch 260509-msr | `hermes_vendor_patch_msr.md` | 2026-05-09 | Vendor-patch; aim-3 cutover (2026-05-24) means Hermes is now RO until 2026-06-22 — patch is no longer re-applied. |
| Layer 1 prompt v1 shipped | `project_layer1_v1_shipped_260512.md` | 2026-05-12 | Shipped, validated; superseded by Patch A v1 entry. |
| Patch A Layer 2 v1 prompt validated | `project_patch_a_validated_260513_evening.md` | 2026-05-13 | Validated → in production for 13+ days. |
| v1.0.z imc D2 image_count deployed | `project_v1_0_z_imc_deployed_260513.md` | 2026-05-13 | Closed by v1.0.x closure (260516 entry below). |
| Ghost success race 2026-05-14 | `project_ghost_success_observed_260514.md` | 2026-05-14 | One observation; defended by RETRY=300; superseded by v1.0.y closure trio. |
| T1-b1 disk fallback validated | `project_t1_b1_validated_260513.md` | 2026-05-13 | Closed; absorbed into v1.0.x. |
| OmniGraph v1.0 final declared | `project_v1_0_final_declared_260513.md` | 2026-05-13 | Replaced by v1.0.y closure (260517). |
| v1.0.x stable closed | `project_v1_0_x_closure_260516.md` | 2026-05-16 | Replaced by v1.0.y closure (260517). |

**Bucket B — KEEP (load-bearing references)**: `hermes_ssh.md`, `aliyun_vitaclaw_ssh.md`, `vertex_ai_smoke_validated.md`, `cdp_mcp_dual_mode.md`, `aliyun_oauth_pin.md`, `corp_pem_rebuild_pattern.md`, `databricks_llm_api_local_invocation.md`, `databricks_apps_logs_websocket.md`, `databricks_sdk_query_no_timeout_kwarg.md`, all `feedback_*` rules (process discipline, not dated incidents), `project_v1_0_y_closure_260517`, `project_aim2_closed_260524`, `project_aim3_closed_260524`, `project_agentic_rag_v1_closed_260524`, `feedback_pending_symptom_check_dim_first` (newest, 2026-05-25).

**Summary — B:** 53 indexed entries → 14 stale-candidates (~26%) + 39 KEEP. 2 orphans (deletable on confirm). 1 backup (deletable on confirm). User adjudicates per-row in Phase 2.

---

## Bucket C — `.planning/phases/` + `.planning/quick/`

### C.1 — `.planning/phases/` (44 dirs total)

| Dir | Date | Bucket |
|---|---|---|
| `04-knowledge-enrichment-zhihu` | Apr 27 | **CANDIDATE ARCHIVE → archive/2026-05-26/.planning/phases/** |
| `05-pipeline-automation` | May 6 | CANDIDATE ARCHIVE |
| `06-graphify-addon-code-graph` | Apr 28 | CANDIDATE ARCHIVE |
| `07-model-key-management` | Apr 29 | CANDIDATE ARCHIVE |
| `08-image-pipeline-correctness` | Apr 30 | CANDIDATE ARCHIVE |
| `09-timeout-state-management` | Apr 30 | CANDIDATE ARCHIVE |
| `10-classification-and-ingest-decoupling` | Apr 30 | CANDIDATE ARCHIVE |
| `11-e2e-verification-gate` | Apr 30 | CANDIDATE ARCHIVE |
| `12-checkpoint-resume` | May 1 | CANDIDATE ARCHIVE |
| `13-vision-cascade` | May 1 | CANDIDATE ARCHIVE |
| `14-regression-fixtures` | May 3 | CANDIDATE ARCHIVE |
| `15-docs-runbook` | May 1 | CANDIDATE ARCHIVE |
| `16-vertex-ai-design` | May 1 | CANDIDATE ARCHIVE |
| `17-batch-timeout-management` | May 3 | CANDIDATE ARCHIVE |
| `18-daily-ops-hygiene` | May 3 | CANDIDATE ARCHIVE |
| `19-generic-scraper-schema-kol-hotfix` | May 3 | CANDIDATE ARCHIVE |
| `20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix` | May 7 | CANDIDATE ARCHIVE |
| `21-stuck-doc-spike` | May 6 | CANDIDATE ARCHIVE |
| `aim-0-readiness-aliyun-ecs` | May 22 | CANDIDATE ARCHIVE (closed; aim-3 cutover absorbed it) |
| `aim-1-code-env-deploy` | May 23 | CANDIDATE ARCHIVE (closed) |
| `aim-2-lightrag-storage-migration` | May 23 | CANDIDATE ARCHIVE (closed per `[[project_aim2_closed_260524]]`) |
| `aim-3-cutover` | May 24 | CANDIDATE ARCHIVE (closed per `[[project_aim3_closed_260524]]`) |
| **`aim-4-daily-sync`** | May 24 | **HOLD — in-flight** |
| **`aim-5-stability-watch`** | May 24 | **HOLD — in-flight** |
| **`ar-1-mvp-vertical-slice`** | May 23 | **HOLD — in-flight (Q(a))** |
| **`ar-2-reasoner-vision-deepening`** | May 23 | **HOLD — in-flight (Q(a))** |
| **`ar-3-verifier-web-tools`** | May 23 | **HOLD — in-flight (Q(a))** |
| **`ar-4-telemetry-streaming-smoke`** | May 24 | **HOLD — in-flight (Q(a))** |
| `ir-1-real-layer1-and-kol-ingest-wiring` | May 7 | CANDIDATE ARCHIVE |
| `ir-2-real-layer2-and-fullbody-scoring` | May 7 | CANDIDATE ARCHIVE |
| `ir-4-rss-integration-and-cleanup` | May 9 | CANDIDATE ARCHIVE (closed; v1.0 declared 2026-05-13) |
| `kb-1-ssg-export-i18n-foundation` | May 13 | CANDIDATE ARCHIVE |
| `kb-2-topic-pillar-entity-pages` | May 13 | CANDIDATE ARCHIVE |
| `kb-3-fastapi-bilingual-api` | May 14 | CANDIDATE ARCHIVE (kb subsystem reached v2.2) |
| `kb-4-ubuntu-deploy-cron-smoke` | May 22 | **CONFIRM** — within 4 days; verify closure |
| `kb-v2.1-stabilization` | May 17 | CANDIDATE ARCHIVE |
| `kb-v2.2-translation-and-kg-search` | May 20 | CANDIDATE ARCHIVE |
| `kdb-1-uc-volume-and-data-snapshot` | May 15 | CANDIDATE ARCHIVE |
| `kdb-1.5-lightrag-databricks-provider-adapter` | May 16 | CANDIDATE ARCHIVE |
| `kdb-2-databricks-app-deploy` | May 22 | **CONFIRM** — within 4 days; verify closure |
| `kdb-2.5-reindex-lightrag-storage` | May 18 | CANDIDATE ARCHIVE |
| `kdb-3-uat-close` | May 20 | CANDIDATE ARCHIVE |
| `llm-wiki-integration` | May 21 | **CONFIRM** — verify closure |
| **`repo-cleanup`** | May 26 | **HOLD — this phase** |
| `v1.0.y` | May 25 | **CONFIRM** — closure trio shipped 2026-05-17 per memory; phase dir dated May 25 (probable doc-update); verify before archive |

**Summary — C.1:** 44 dirs → 7 HOLD (in-flight + this phase), 4 CONFIRM, 33 CANDIDATE ARCHIVE.

### C.2 — `.planning/quick/` (86 dirs total)

> **Method:** sort by mtime; HOLD any within last 48h; bucket older as ARCHIVE candidate; surface ones whose `SUMMARY.md` doesn't yet exist as `INCOMPLETE`.

**HOLD (in-flight, ≤ 48h or in user's explicit list):** `260525-c1-no-content-at-64s` (May 26 12:44), `20260525-200047-synthesize-audit` (May 25 20:08, untracked), `260525-vnj-vitaclaw-news-3shot-ingest` (May 25 10:44), `260524-tk5b-databricks-sdk-deterministic-llm-hang` (May 25 09:47), `260524-arx-A-images` (May 25 09:34, see Q(a)), `260524-tk5-kb-longform-c1-hang` (May 24 21:22), `260524-tvg-wechat-session-hardening` (May 24 21:33). **= 7 HOLD.**

**CANDIDATE ARCHIVE (closed quicks, dated 2026-04-29 → 2026-05-22):** ~79 dirs (86 total – 7 HOLD). Date span:
- Pre-v1.0 (Apr 29 – May 13): ~60 dirs — bulk archival candidates
- v1.0.x window (May 14 – May 22): ~19 dirs — many cited by closed memory entries

**Examples of "definitely closed" quicks (sample, full list to be enumerated in TRIAGE.md per user adjudication):**
- `260429-got-...`, `260430-...`, `260501-...` — first-week post-v3.x stabilization
- `260504-g7a-enablement-local-testing-blockers-infras` (cited in CLAUDE.md A6 — keep referenced or convert ref to archive path)
- `260505-ee5-repo-cleanup` (a previous repo-cleanup quick! — probably has reusable triage logic)
- `260506-hgr-...`, `260506-rjs` (memory `[[feedback_no_amend_in_concurrent_quicks]]`)
- `260508-ev2`, `260508-dep` (memory `[[feedback_no_literal_secrets_in_prompts]]`)
- `260509-msr` (memory `[[hermes_vendor_patch_msr]]` — itself a candidate-stale memory)
- `260510-gfg`, `260510-h09b` (Cognee retire + h09 retry-tune, both shipped)
- `260513-lyt` (Patch A — shipped per memory)
- `260516-bls`, `260517-fyb`, `260517-lok`, `260517-riq` (v1.0.y closure quicks — shipped)

**Summary — C.2:** 86 quicks → 7 HOLD, ~79 CANDIDATE ARCHIVE. **Pre-archive dependency check required:** for each quick that is referenced by an open phase plan or by `MEMORY.md`, replace the reference with the archive path before moving (TRIAGE.md will list per-row).

---

## Bucket D — `.scratch/` debris

| Metric | Value |
|---|---|
| Entries (top-level) | **607** |
| Total disk usage | **94.1 MB** |
| Entries tracked by git | **1** (`.scratch/wiki-rebuild-probe-claude-code-global.md`) |
| Date range observed | All May 2026 (no Apr or earlier surviving) |
| `.gitignore` coverage | `.scratch/*` ignored except 1 explicit unignore |

**Status:** effectively a debris bucket — only 1 of 607 items is committed. Bulk hard-delete is safe (zero git history loss because nothing tracked).

**Cross-ref concern:** committed files (commit messages, REPORT.md, SUMMARY.md, AUDIT.md) cite `.scratch/<filename>` as evidence (e.g. v1.0.x bug reports). **Citations are dangling pointers regardless of cleanup** — the citation format implies a temporary local-only artifact. Hard-delete does not break correctness; users who want to revisit must re-run.

**Surfaced for triage:**
- D.1 — Hard-delete every `.scratch/*` entry except `.scratch/wiki-rebuild-probe-claude-code-global.md` (the one tracked file). 94 MB recovered. Safe.
- D.2 — Optional: also hard-delete the tracked `wiki-rebuild-probe-claude-code-global.md` if user confirms it's spike output.

**Summary — D:** 1 candidate (606 untracked + optionally 1 tracked).

---

## Bucket E — Code-level dead weight (`lib/`, `kb/`, `scripts/`, root `*.py`)

> **Method:** grep cross-reference each candidate; classified as STALE only if 0 references in active code paths (excluding self-reference + retired-quicks + retired phase docs).
> **Vulture confidence-80 output**: deferred (DRAFT). Hi-confidence vulture findings will be re-run before TRIAGE.md if user requests.

### E.1 — Root `*.py` (21 files)

**Active (REFERENCED, kept):** `batch_classify_kol.py`, `batch_ingest_from_spider.py`, `batch_validation.py`, `config.py`, `ingest_wechat.py`, `kg_synthesize.py`, `list_entities.py`, `multimodal_ingest.py`, `orchestrate_daily.py`, `query_lightrag.py`, `seed_test_db.py`, `skill_runner.py` + a few others — verified via Grep against `tests/`, `kb/`, `scripts/`, `skills/`.

**STALE-CANDIDATE (suspected dead):**

| File | Date | Inbound refs (excl. self) | Bucket |
|---|---|---|---|
| `batchkol_topic.py` | Apr 29 | 2 retired quick SUMMARY.md (260504-g7a, 260509-s29) + 4 retired phase docs (05/07) — **no active code path** | CANDIDATE STALE |
| `batch_ingest_kol_mvp.py` | Apr 23 | 1 retired quick (260505-ee5) + `specs/PRD_TDD.md` + 4 retired phase docs — **no active code path** | CANDIDATE STALE (verify `specs/PRD_TDD.md` not load-bearing) |
| `test_mcp_approaches.py` | May 4 | `.databricksignore` + 1 retired audit + 1 retired quick (260504-g7a) + 2 retired phase docs (07, 17) — **spike, no active path** | CANDIDATE STALE |

> ⚠ **Re-verify step needed before any `git rm`:** confirm `specs/PRD_TDD.md` is not load-bearing — file is dated Apr 27 (471 lines). Likely candidate for archive itself; surface in Bucket F via `specs/`.

### E.2 — `lib/`, `kb/`, `scripts/`

**No mutations attempted.** Vulture not run yet (DRAFT promised). Phase 2 will request vulture run with confidence ≥ 80, then per-finding adjudication.

**Pre-vulture observations:**
- `lib/llm_complete.py` is the live dispatcher; legacy hardcoded-DeepSeek paths (`enrichment/rss_classify.py:129`, `enrichment/rss_ingest.py:367`) flagged in CLAUDE.md A5 as ir-4 retire candidates — partially executed (ir-4 phase exists, May 9). Confirm whether retire happened.
- `cognee_*.py` — Cognee retired 2026-05-10 (`[[feedback_lightrag_is_core_asset_no_bypass]]`). Any remaining `cognee_*` modules at root or in `lib/` are CANDIDATE STALE.

### E.3 — Other suspicious top-level

| Path | Date | Status |
|---|---|---|
| `cognee_batch.log` | (root) | **0 bytes** — empty stale file. Hard-delete safe. |
| `omnigraph_vault.egg-info/` | May 22 | Generated by `pip install -e .`; gitignored (verify). Hard-delete safe. |
| `__pycache__` (root + 106 nested) | various | 107 dirs / 830 .pyc files. Gitignored. Regenerable. Hard-delete safe. |
| `.dev-runtime/` | (in-flight) | Local-dev sandbox per CLAUDE.md A6. **HOLD — active runtime data.** |
| `.playwright-mcp/` | (in-flight) | UAT screenshot output. Gitignored. **HOLD — active.** |
| `.pytest_cache/` | (in-flight) | Pytest temp. Gitignored. Regenerable. |
| `entity_buffer/` | (in-flight) | Live ingest buffer. **HOLD — pipeline working state.** |
| `data/` | various | Active SQLite DBs. **HOLD.** |

**Summary — E:** 3 root `*.py` STALE candidates, ~3 hard-delete-safe artifacts (`cognee_batch.log`, `omnigraph_vault.egg-info/`, `__pycache__/*`), Cognee residue TBD by directory grep in Phase 2.

---

## Bucket F — Tests + docs orphans

### F.1 — `tests/` (204 tracked files)

- ❌ No `*.original.*` files
- ❌ No `*.bak` files
- ❌ No `*disabled*` files
- ❌ No `*.skip` files
- ⚠ Did NOT scan for commented-out test bodies (vulture-equivalent for tests). Surface as Phase 2 ask.
- ✅ `tests/unit/test_bench_harness.py` confirms `test/` (singular) at repo root **IS NOT orphan** — referenced as benchmark fixture root (`test/fixtures/gpt55_article/` etc.)

### F.2 — `test/` (singular, repo root, 96 tracked files)

| Subdir | Files | Status |
|---|---|---|
| `test/fixtures/dense_image_article/` | (1 of 5 article fixtures) | **KEEP** — referenced by `tests/unit/test_bench_harness.py` |
| `test/fixtures/gpt55_article/` | (default fixture) | KEEP |
| `test/fixtures/mixed_quality_article/` | KEEP |
| `test/fixtures/sparse_image_article/` | KEEP |
| `test/fixtures/text_only_article/` | KEEP |

**Bucket F.2:** `test/` is NOT orphan despite naming collision with `tests/`. Naming is awkward (suggests rename to `tests/_fixtures/` or `test_fixtures/`) — **not a cleanup target this phase**; surface as future-rename ask.

### F.3 — `docs/`

| Path | Concern | Bucket |
|---|---|---|
| `docs/queries/hermes_session_2026_05_06/` | 2 JSON files, 588 KB total | **CANDIDATE ARCHIVE** — single-day session capture; likely no active reference. Verify with grep. |
| `docs/HERMES_V3.2_PUNCH_LIST*.md` | v3.2 era (pre-v1.0) | CANDIDATE ARCHIVE |
| `docs/MILESTONE_v3.1_CLOSURE.md` | v3.1 era | CANDIDATE ARCHIVE |
| `docs/MILESTONE_v3.2_EXECUTION_REPORT.md` | v3.2 era | CANDIDATE ARCHIVE |
| `docs/UAT_v3.2*.md` | v3.2 era | CANDIDATE ARCHIVE |
| `docs/research/lightrag_internals_2026-05-04.md` | dated research note | KEEP — cited by `docs/lessons/2026-05-archive.md` |
| `docs/lessons/2026-05-archive.md` | canonical archive | **KEEP — load-bearing (Q(d))** |
| `docs/VERTEX_AI_MIGRATION_SPEC.md` | active design | KEEP (CLAUDE.md A12 points here) |
| `docs/LOCAL_DEV_SETUP.md` | active runbook | KEEP |
| `docs/design/agentic_rag_internal_api.md` | active design | KEEP |
| `docs/skills/` (if exists) | proposed extract target | N/A — to be created in Phase 3 |
| `docs/runbooks/` (if exists) | proposed extract target | N/A — to be created in Phase 3 |
| `docs/testing/04-06-test-results.md` | dated (phase 04) | CANDIDATE ARCHIVE |
| `docs/bugreports/` | post-mortems | KEEP (cited by archive) — verify per-file in Phase 2 |

### F.4 — `specs/`

| File | Date | Bucket |
|---|---|---|
| `specs/EMBEDDING_STRATEGY_DECISION.md` | Apr 23 | CANDIDATE ARCHIVE — pre-Vertex-AI decision; superseded by `docs/VERTEX_AI_MIGRATION_SPEC.md`. Verify. |
| `specs/MODEL_KEY_MGMT_DESIGN.md` | Apr 28 | CANDIDATE ARCHIVE — phase 07 (retired). |
| `specs/OMNIGRAPH_PRODUCT_BRIEF.md` | Apr 23 | CANDIDATE ARCHIVE — pre-v1.0 product brief. |
| `specs/PRD_TDD.md` | Apr 27 | CANDIDATE ARCHIVE — referenced only by `batch_ingest_kol_mvp.py` (also stale candidate per E.1). Decoupled archive. |
| `specs/PRDTDD_GRAPHIFY_ADDON.md` | Apr 28 | CANDIDATE ARCHIVE — phase 06. |
| `specs/SKILL_PACKAGING_GUIDE.md` | Apr 22 | CANDIDATE ARCHIVE — superseded by CLAUDE.md A8 (which is itself an extract candidate; consolidate at extract time). |

### F.5 — `skills/` (11 root dirs)

| Skill dir | Date | Bucket |
|---|---|---|
| `enrich_article` | Apr 27 | CANDIDATE ARCHIVE (legacy enrichment path) |
| `hermes_claude_code_bridge` | Apr 27 | CANDIDATE ARCHIVE (legacy bridge) |
| `omnigraph_architect` | Apr 29 | CANDIDATE STALE — 0 active code refs found (Phase 2 to verify with deeper grep) |
| `omnigraph_cloud_synthesize` | May 8 | **CONFIRM** — verify against agentic-rag-v1 (kdb-3 closure) |
| `omnigraph_ingest` | May 20 | **KEEP** (active per CLAUDE.md A8) |
| `omnigraph_query` | May 20 | **KEEP** (active) |
| `omnigraph_research` | May 23 | **KEEP** (active per agentic-rag-v1) |
| `omnigraph_scan_kol` | May 20 | **KEEP** (active) |
| `omnigraph_search` | Apr 28 | **CONFIRM** — same name as repo-root `omnigraph_search/` Python package (active). Verify whether skill `omnigraph_search/` and code `omnigraph_search/` are same or different artifacts. |
| `wechat-cdp-credential-refresh` | May 24 | **KEEP** (memory `[[feedback_wechat_cookie_refresh_runbook]]`) |
| `zhihu-haowen-enrich` | Apr 27 | CANDIDATE ARCHIVE (legacy zhihu enrichment) |

**Summary — F:** 96 fixture files KEPT. Tests bucket clean. `docs/` ~6 v3.x dated archives + 1 large session JSON candidate. `specs/` 6 of 6 are pre-v1.0 candidates. `skills/` 4 candidates + 2 confirms.

---

## Open Questions — findings (NOT pre-answered)

> Per user instruction: "5 open questions Q(a)-Q(e): do NOT pre-answer. Surface findings in INVENTORY.md and let me adjudicate." Findings below are filesystem ground truth + observed cross-refs; recommendations belong in Phase 2.

### Q(a) — `arx-2-*` vs `ar-1..ar-4` naming

**Filesystem ground truth (`ls .planning/phases/`):**
- ✅ `ar-1-mvp-vertical-slice/` (May 23)
- ✅ `ar-2-reasoner-vision-deepening/` (May 23)
- ✅ `ar-3-verifier-web-tools/` (May 23)
- ✅ `ar-4-telemetry-streaming-smoke/` (May 24)
- ❌ NO `arx-2-*/` exists at any phase path

**Filesystem ground truth (`ls .planning/quick/`):**
- ✅ `260524-arx-A-images/` (May 25 09:34) — uses `arx-A` naming, dated post-ar-4
- ❌ NO `arx-2-*/` exists at any quick path

**Cross-reference (`Grep "arx-2"`):** 0 hits in committed files (the only "arx-2" mentions are in user's prompt + recent commit messages `arx-2-bump180`, `arx-2-http`).

**Observation:** the user's "arx-2-*" terminology in the cleanup prompt likely refers to the `260524-arx-A-images` quick + recent commits like `4b7971a fix(arx-2)`. The phase dirs `ar-1..ar-4` (Agentic-RAG roadmap) appear to be a separate workstream named `ar-*`, not `arx-*`. **`arx-*` appears to be a quick-only namespace** (currently 1 dir: `260524-arx-A-images`).

**Implication for HOLD-LIST:** all `ar-1..ar-4` phase dirs and the `260524-arx-A-images` quick are HELD. No `arx-2-*` phase exists.

**Decision needed (user):** confirm `ar-1..ar-4` ≡ user's "arx-2-*" hold intent, OR clarify if a different namespace was meant.

### Q(b) — Date cutoff for "recent" quicks → ARCHIVE candidate

**Observation:** quick directory date span is **2026-04-29 → 2026-05-26** (28 days). Mode of activity is dense (3–6 quicks per active day). No natural breakpoint visible by mtime alone.

**Reference points usable for cutoff:**
- v1.0 declared: 2026-05-13 (61 of 86 quicks pre-date this)
- v1.0.y closure: 2026-05-17 (70 of 86 quicks pre-date)
- aim-3 cutover (production fully-live on Aliyun): 2026-05-24 (79 of 86 quicks pre-date)
- 48h-from-now: 2026-05-24 (matches user's HOLD list of 7)

**Decision needed (user):** which date cutoff defines ARCHIVE candidate for quicks? Surface 4 options:
- **Aggressive:** archive everything pre-2026-05-24 (79 dirs)
- **Medium:** archive everything pre-2026-05-17 (v1.0.y closure, 70 dirs)
- **Conservative:** archive everything pre-2026-05-13 (v1.0 declaration, 61 dirs)
- **Pre-v1.0 only:** archive everything dated 2026-04-29 → 2026-05-12 (~60 dirs)

### Q(c) — Memory file inbound-reference graph

**Findings:**
- 53 entries in `MEMORY.md` (all referenced)
- 2 orphan files in memory dir (NOT in `MEMORY.md`): `feedback_kwarg_zero_ambiguity.md`, `project_kol_scan_db_path.md`
- 1 backup: `MEMORY.original.md`
- Memory files reference each other via `[[name]]` markdown links; full graph not enumerated this phase (read-only constraint preserves token budget)

**Cross-ref (`grep '\[\[' MEMORY.md`):** index file itself does NOT use `[[`; cross-refs live inside individual memory files. Per-file cross-link audit deferred to Phase 2.

**Decision needed (user):**
- Are the 2 orphans usable (un-index them was intentional?), or stale (delete safe)?
- Is the `MEMORY.original.md` backup needed, or stale (delete safe)?

### Q(d) — CLAUDE.md ↔ `docs/lessons/2026-05-archive.md` duplication

**Finding:** archive header (verified, line 3) reads:

> *"Archived from project CLAUDE.md on 2026-05-25 to reduce session-start context load. The two evergreen invariants (`omonigraph-vault` typo, `CDP_URL` dual-mode) remain in CLAUDE.md."*

**Verification:** CLAUDE.md `## Lessons Learned` (lines 547–555) contains only 2 evergreen bullets + a pointer to the archive. Duplication is **near-zero**. Archive is the canonical source for dated postmortems.

**Decision needed (user):** none — archive is canonical, no merge action needed. Surface this as resolved.

### Q(e) — Vulture confidence calibration

**Finding:** vulture not run in Phase 1 (per user instruction "treat vulture confidence 80 output as DRAFT, not verdict").

**Plan for Phase 2:**
- Run `vulture lib/ kb/ scripts/ --min-confidence 80` (high signal, high false-negative)
- Run `vulture lib/ kb/ scripts/ --min-confidence 60` (medium, manual triage)
- Per-finding adjudication: each candidate cross-checked against `tests/`, `skills/`, `kb/api_routers/`, in-flight phase plans (`aim-4`, `aim-5`, `ar-*`)

**Decision needed (user):** confidence threshold preference for triage (80 strict, 60 broad)? Default if no answer: 80 strict + 60 surfaced as "review-only".

---

## Count summary

| Bucket | Total scanned | KEEP | CANDIDATE COMPACT/EXTRACT | CANDIDATE ARCHIVE | CANDIDATE STALE | HOLD (in-flight) |
|---|---:|---:|---:|---:|---:|---:|
| **A — CLAUDE.md sections** | 23 | 10 | 13 | 0 | 0 | 0 |
| **B — Memory files** | 56 | 39 (indexed) | 0 | 0 | 14 indexed + 2 orphans + 1 backup = 17 | 0 |
| **C.1 — Phases** | 44 | 0 | 0 | 33 (+ 4 confirm) | 0 | 7 |
| **C.2 — Quicks** | 86 | 0 | 0 | ~79 (per Q(b) cutoff) | 0 | 7 |
| **D — `.scratch/`** | 607 | 0 | 0 | 0 | 606 (+ 1 tracked confirm) | 0 |
| **E — Code-level** | ~21 root .py + lib/kb/scripts (vulture deferred) | ~18 root | 0 | 0 | 3 root .py + 3 artifacts | 0 |
| **F.1/F.2 — Tests + fixtures** | 204 + 96 | 300 | 0 | 0 | 0 | 0 |
| **F.3 — docs/** | ~55 tracked | ~45 | 0 | ~10 (dated v3.x + session JSON) | 0 | 0 |
| **F.4 — specs/** | 6 | 0 | 0 | 6 | 0 | 0 |
| **F.5 — skills/** | 11 | 5 | 0 | 4 | 1 | 0 (active 5 are KEEP) |
| **TOTALS** | ~1119 | ~417 | 13 | ~136 | ~628 | 14 |

**Disk-recovery estimate (rough):**
- `.scratch/` hard-delete: ~94 MB
- `__pycache__/` hard-delete: ~5–10 MB (gitignored already; tooling impact only)
- `omnigraph_vault.egg-info/`: ~50 KB
- `docs/queries/hermes_session_2026_05_06/`: ~588 KB
- Phase + quick archival: not a delete (git history preserved via `git mv`); pure name-space hygiene
- Total recovery: **~95 MB on-disk**, plus measurable session-start context reduction (Phase 4 will measure A1–A23 token deltas).

---

## Constraints honored this phase

- ✅ 100% read-only — no `git mv`, no `git rm`, no Edit/Write outside `.planning/phases/repo-cleanup/`
- ✅ Cross-checked every "fully-stale" classification against `grep` across `kb/`, `lib/`, `scripts/`, `tests/`, `.planning/`, `skills/`, `docs/lessons/`
- ✅ Treated vulture confidence-80 as DRAFT (deferred to Phase 2)
- ✅ Did NOT pre-answer Q(a)–Q(e); surfaced findings only
- ✅ For Q(a): trusted `ls .planning/phases/` filesystem over user's prompt list (ground truth = `ar-1..ar-4`, no `arx-2-*` phase exists)
- ✅ Verified each in-flight phase's files do NOT appear in any candidate-action row (HOLD list above)
- ✅ Honored HARD CONSTRAINT 1: did NOT touch LightRAG paths, "omonigraph" string, HIGHEST PRIORITY PRINCIPLES (CLAUDE.md 1–117), in-flight phase dirs, working-tree uncommitted files, MEMORY.md entries with active inbound refs

---

## Halt point

**This is the end of Phase 1. No further action will be taken until user replies `go triage`.**

**On `go triage`, Phase 2 will produce `TRIAGE.md` containing:**
- Per-row proposed action (`ARCHIVE → archive/2026-05-26/<path>` | `COMPACT → CLAUDE.md inline rewrite` | `EXTRACT → docs/<new_path>` | `HARD-DELETE` | `LEAVE`)
- Per-row reversibility floor: `git mv` preferred; `git rm` only for unambiguously regenerable artifacts
- Decision points for Q(a)–Q(e)
- Per-row dependency notes (which references must be updated before move)
- Vulture run output (≥80 strict + 60 surfaced)
- Per-section CLAUDE.md proposed token deltas (Phase 4 measure scaffold)

Phase 3 execute is gated on per-category user approval.
