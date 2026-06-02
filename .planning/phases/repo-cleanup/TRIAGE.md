# Repo Cleanup — Phase 2 TRIAGE

**Status:** READ-ONLY proposed actions. No mutation performed. Halt for user approval before Phase 3.
**Author:** repo-cleanup phase, 2026-05-26.
**Inputs:** `INVENTORY.md` (Phase 1 ground truth), `RESEARCH.md` (Phase 0 best practices), filesystem re-verification this session, `.scratch/vulture_strict_260526.txt` + `.scratch/vulture_60_260526.txt`.

---

## arx-3 RESPECT BLOCK (verbatim — DO NOT TOUCH any of these in Phase 3)

The following paths belong to the in-flight **arx-3** workstream (synthesize/search/research-router). **No row in this TRIAGE proposes any action against any of these.**

- `kb/services/synthesize.py`
- `kb/services/search_index.py`
- `kb/api_routers/search.py`
- `kb/api_routers/synthesize.py`
- `kb/static/qa.js`
- `kb/static/qa.html`
- `tests/unit/test_synthesize*`
- `tests/integration/kb/**`
- `kg_synthesize.py`
- `lib/research/__init__.py` (working-tree uncommitted)
- `lib/research/orchestrator.py` (working-tree uncommitted)
- `.planning/quick/20260525-200047-synthesize-audit/` (HOLD)
- `databricks-deploy/requirements.txt` (working-tree uncommitted)
- `databricks-deploy/app.yaml` (working-tree uncommitted)
- `kb/api.py` (working-tree uncommitted)
- `kb/api_routers/research.py` (untracked, arx-3 lane)
- `tests/integration/test_research_router.py` (untracked, arx-3 lane)

**Discovered this session:** `.planning/phases/arx-3/` (created 2026-05-26 15:26, contains only `RESEARCH.md`) — added to HOLD list (was missing from INVENTORY because phase dir was created post-INVENTORY).

---

## Phase 3 Serialization Constraint (forward note)

Phase 3 (mutation) MUST serialize with arx-3 Phase 3:

1. Before any commit in Phase 3: run `git pull --ff-only` AND `git status` check.
2. If arx-3 has commits not in local main → pull, re-verify arx-3 territory list above (arx-3 may add files).
3. If arx-3 still in-flight (no closure announcement in MEMORY.md or ROADMAP) → halt Phase 3 of cleanup, await arx-3 close OR explicit user approval to proceed during overlap.
4. Per-category atomic commits (one category at a time, never bundled), each cited to a `.scratch/<log>` artifact and to the line ranges of files moved/edited.

---

## Action Legend

| Action | Meaning |
|---|---|
| **ARCHIVE** | `git mv` to `archive/2026-05-26/<original-path>` (history preserved at `-M90`). Reversible. |
| **COMPACT** | Trim section in place to a 1–3 line pointer + delete bulk content. Bulk content may go to `docs/lessons/<archive>.md` if reusable, else just deleted. |
| **EXTRACT** | Move section out of CLAUDE.md into a topic doc under `docs/`, leave a 1-line pointer in CLAUDE.md. May include corrections (e.g., D3 stale-path fix). |
| **HARD-DELETE** | Outright delete (no archive). Reserved for unambiguously regenerable artifacts (build logs, vulture txt files we author ourselves, 0-byte residue). |
| **LEAVE** | No action. May be revisited in v1.1 cleanup pass. |
| **HOLD** | In-flight workstream — do not touch. Owner outside this phase. |

---

## Decision Anchors (D1–D5 — verbatim ack)

- **D1 (Q(a) arx-2 holding):** ar-1..ar-4 + `.scratch/arx-2/` + `260524-arx-A-images/` = arx-2 workstream. **All HOLD. No row in this TRIAGE.**
- **D2 (cutoff):** MEDIUM = pre-2026-05-17 (anything mtime ≥ 2026-05-17 = LEAVE within 7d post-v1.0.y buffer).
- **D3 (CLAUDE.md A21 fix-on-extract):** Extract A21 → `docs/architecture.md`; in the new file, replace all `~/.hermes/kg-vault/` with `~/.hermes/omonigraph-vault/` (typo `omonigraph` is CANONICAL — `kg-vault` is the older deprecated path); replace A21 in CLAUDE.md with 1-line pointer; single atomic commit.
- **D4 (.scratch/ cleanup):** ~360 MB recovery approved. HOLD: `.scratch/arx-2/`, `.scratch/wiki-rebuild-probe-claude-code-global.md` (only tracked file). Bulk-delete: untracked AND >30 days OR not cited from any committed `.md`/`.py`. Per-batch grep cross-check; halt+ask if cited.
- **D5 (vulture install):** APPROVED. `venv/Scripts/pip install vulture` complete (vulture-2.16). Scoped to `lib/`, `scripts/`, root `*.py`. Excluded: `kb/services/`, `kb/api_routers/`, `tests/` (arx-3 territory).

---

## Bucket A — CLAUDE.md Sections (23 entries)

CLAUDE.md is currently ~870 lines / ~16k tokens at session start. Goal: reduce by ~50% via EXTRACT + COMPACT, leaving the load-bearing HARD CONSTRAINTS / HIGHEST PRIORITY PRINCIPLES (lines 1–117) **untouched** per Constraint #1.

| # | Section (heading slug) | Lines | Action | Target / Notes |
|---|---|---|---|---|
| A1 | HIGHEST PRIORITY PRINCIPLES (1–7) | 1–117 | **LEAVE** | Load-bearing. Per Constraint #1, do not touch. |
| A2 | Project-Specific Disciplines → Behavior-Anchor Harness | ~30 | LEAVE | Active discipline for `ingest_from_db`. Cited from MEMORY. |
| A3 | Project Summary | ~6 | LEAVE | Already minimal. |
| A4 | Release Status → v1.0 + v1.0.x patches | ~30 | **COMPACT** | Trim to 5-line "v1.0 baseline declared 2026-05-13; v1.0.x/y/z closed; see `docs/releases/v1.0.md` for full status". Move detail to `docs/releases/v1.0.md`. |
| A5 | Common Commands (manual section) | ~25 | **COMPACT** | All commands now go through `scripts/local_e2e.sh`. Trim to 8-line stub: harness + 1 example per mode + pointer to `local_e2e.sh help`. |
| A6 | Local E2E testing (Cisco Umbrella corp network aware) | ~80 | **EXTRACT** | → `docs/local-e2e-runbook.md`. Replace with: "Local E2E harness: `scripts/local_e2e.sh`. Corp network reachability matrix + provider blocks: see `docs/local-e2e-runbook.md`." |
| A7 | Architecture → Ingestion Flow | ~15 | LEAVE | Useful diagram. Keep. |
| A8 | Architecture → Query/Synthesis Flow + Key Integration Points | 113 lines (per INVENTORY) | **EXTRACT** | → `docs/architecture.md` (alongside D3 A21 extract — combine into one architecture doc). |
| A9 | Environment Variables (basic table) | ~10 | LEAVE | Compact, useful at session start. |
| A10 | Phase 7 scoped env vars | ~12 | **COMPACT** | Phase 7 closed. Trim to 3 lines pointing to `Deploy.md`. |
| A11 | Phase 5 DeepSeek cross-coupling | ~8 | LEAVE | Active gotcha — `DEEPSEEK_API_KEY=dummy` still required at import. |
| A12 | Local dev env vars (quick task 260504-g7a) | ~25 | **COMPACT** | Trim table to 5 most-used vars (`OMNIGRAPH_LLM_PROVIDER`, `OMNIGRAPH_BASE_DIR`, `OMNIGRAPH_VISION_SKIP_PROVIDERS`, `OMNIGRAPH_PROCESSED_RETRY`, `OMNIGRAPH_DEEPSEEK_TIMEOUT`). Full table → `docs/LOCAL_DEV_SETUP.md` (already exists per the pointer). |
| A13 | Development Conventions | ~5 | LEAVE | Compact. Useful. |
| A14 | OpenClaw / Hermes Skill Writing Standards | ~110 | **EXTRACT** | → `docs/skills/SKILL_STANDARDS.md`. Replace with 2-line pointer. This is a writing guide, not a session-start invariant. |
| A15 | Testing the CDP / MCP Scraping Path | ~40 | **EXTRACT** | → `docs/testing/cdp-mcp-paths.md`. Manual test recipe — only needed when actively testing scraper. |
| A16 | Remote Hermes Deployment | ~30 | **COMPACT** | Most content is now in MEMORY (`hermes_ssh.md`). Trim to 5 lines + pointer to memory file. |
| A17 | Lessons Learned (header + 2 evergreen invariants + recent archives) | ~12 | LEAVE | Already minimal post-2026-05-25 cleanup. The 2 evergreens (`omonigraph-vault` typo + `CDP_URL` dual-mode) are load-bearing. |
| A18 | Vertex AI Migration Path | ~30 | **COMPACT** | Spec frozen, deferred post-Milestone B. Trim to 4 lines + pointer to `docs/VERTEX_AI_MIGRATION_SPEC.md`. |
| A19 | Checkpoint Mechanism | 64 lines (per INVENTORY) | **EXTRACT** | → `docs/operations/checkpoint.md`. Operator-facing detail. |
| A20 | Vision Cascade | 64 lines (per INVENTORY) | **EXTRACT** | → `docs/operations/vision-cascade.md`. Operator-facing detail. |
| A21 | SiliconFlow Balance Management | 83 lines (per INVENTORY, **stale path bug**) | **EXTRACT + FIX (D3)** | → `docs/architecture.md` (combined with A8); fix `~/.hermes/kg-vault/` → `~/.hermes/omonigraph-vault/`; replace with 1-line pointer in CLAUDE.md. **Atomic single commit per D3.** |
| A22 | Batch Execution + MAX_ARTICLES tri-governor | ~30 | LEAVE | The tri-governor warning is load-bearing. Recently added per v1.0.y closure. |
| A23 | Known Limitations | ~12 | LEAVE | Useful at session start. |
| — | Project / Constraints / Technology Stack / Conventions / Architecture / GSD Workflow / Developer Profile (auto-generated tail blocks) | ~150 | LEAVE | Auto-generated by gsd tooling. Do not edit manually. |

**Execution order within Bucket A:** A21 fix-on-extract first (D3 explicit), then A8 + A20 + A19 + A14 + A6 + A15 (other extracts), then COMPACTs (A4, A5, A10, A12, A16, A18). All as separate atomic commits to keep diffs reviewable.

**Phase 4 token-delta scaffold (estimate):**

- EXTRACTs (A6 + A8 + A14 + A15 + A19 + A20 + A21): ~430 lines → ~7 lines pointers = **−423 lines / ~−7,400 tokens**
- COMPACTs (A4 + A5 + A10 + A12 + A16 + A18): ~140 lines → ~25 lines = **−115 lines / ~−2,000 tokens**
- **Total estimated reduction: ~538 lines / ~9,400 tokens (~58% of CLAUDE.md before HARD CONSTRAINTS).**

---

## Bucket B — Memory Files (53 indexed entries; ~17 actionable rows)

Memory directory: `C:\Users\huxxha\.claude\projects\c--Users-huxxha-Desktop-OmniGraph-Vault\memory\`. `MEMORY.md` is the index.

### B.1 — Stale-indexed candidates (mention superseded events / closed phases)

| # | File | Indexed reason | Action | Notes |
|---|---|---|---|---|
| B-1 | `feedback_validation_approach.md` | "Primary validation tool all phases" | LEAVE | Still load-bearing — skill_runner is canonical. |
| B-2 | `vertex_ai_smoke_validated.md` | Smoke 2026-04-30 finding | **COMPACT** | Trim to "non-obvious model name suffix" finding only; drop date-anchored validation log. |
| B-3 | `project_rss_classify_state.md` | "Option D batch+multi-topic deferred" | LEAVE | Still describing deferred state; not closed. |
| B-4 | `project_day1_readiness_2026_05_04.md` | Cron postmortem 2026-05-04 | **ARCHIVE** | Postmortem — date-locked. Move to `docs/lessons/2026-05-archive.md` if not already there; remove memory file. |
| B-5 | `hermes_agent_cron_timeout.md` | Activity-based timeout finding | LEAVE | Still load-bearing operational gotcha. |
| B-6 | `overnight_check_2026_05_05_0633_CRITICAL.md` | Snapshot 2026-05-05 | **ARCHIVE** | Snapshot — superseded by Phase 2b+ check. Drop. |
| B-7 | `morning_analysis_2026_05_05.md` | Snapshot 2026-05-05 | **ARCHIVE** | Same — date-anchored. |
| B-8 | `phase2b_plus_check_2026_05_05_2227.md` | Snapshot 2026-05-05 | **ARCHIVE** | Same — date-anchored. |
| B-9 | `reliability_5_check_2026_05_06_1612.md` | Snapshot 2026-05-06 | **ARCHIVE** | Same. |
| B-10 | `project_layer1_v1_shipped_260512.md` | "Layer 1 prompt v1 shipped" | LEAVE | Still useful baseline reference. |
| B-11 | `project_v1_0_final_declared_260513.md` | Closure marker | LEAVE | Reference for v1.0 baseline. |
| B-12 | `project_t1_b1_validated_260513.md` | Single-fix validation | **COMPACT** | Trim to 1-line "T1-b1 disk fallback validated 2026-05-13 (commit d767580)". |
| B-13 | `project_patch_a_validated_260513_evening.md` | Single-fix validation | **COMPACT** | Same — trim to 1-line. |
| B-14 | `project_v1_0_z_imc_deployed_260513.md` | Closure marker | **COMPACT** | Trim to 1-line. |
| B-15 | `project_ghost_success_observed_260514.md` | Rare event | LEAVE | Still active probability anchor (0.5% rate). |
| B-16 | `project_v1_0_x_closure_260516.md` | Closure marker | LEAVE | Same as v1_0_final — reference. |
| B-17 | `project_v1_0_y_closure_260517.md` | Closure marker | LEAVE | Same. |
| B-18 | `project_aim2_closed_260524.md` | Closure marker | LEAVE | Recent — Hermes RO-until-2026-06-22 still active. |
| B-19 | `project_agentic_rag_v1_closed_260524.md` | Closure marker | LEAVE | Active — V1.1-E flagged as P0 blocker. |
| B-20 | `project_aim3_closed_260524.md` | Closure marker | LEAVE | Active — Aliyun cron LIVE. |
| B-21 | `project_ssg_bake_v4pro_validated_260522.md` | Validation snapshot | **COMPACT** | Trim to 1-line. |
| B-22 | `project_260522_clt_pass2_translation.md` | Validation snapshot | **COMPACT** | Trim to 1-line. |

### B.2 — Orphans (not indexed in MEMORY.md, no inbound references)

Per INVENTORY:
| # | File | Action |
|---|---|---|
| B-23 | `feedback_kwarg_zero_ambiguity.md` | **HARD-DELETE** — orphan, no MEMORY entry, no inbound references. |
| B-24 | `project_kol_scan_db_path.md` | **HARD-DELETE** — same. |

### B.3 — Backups

| # | File | Action |
|---|---|---|
| B-25 | `MEMORY.original.md` | **HARD-DELETE** — backup file. Per INVENTORY priority #1. Git history preserves original. |

**Execution order:** B-23, B-24, B-25 (orphan hard-deletes first, single commit). Then B.1 ARCHIVE batch (all date-anchored snapshots, single commit). Then B.1 COMPACT batch (trim closure-marker memories, single commit). Total: 3 commits.

---

## Bucket C.1 — `.planning/phases/` (46 dirs total; 26 ARCHIVE + 8 HOLD + 12 LEAVE)

**Note:** INVENTORY claimed 44 phase dirs; actual `ls` returns 46. Delta = `arx-3` (created 2026-05-26 post-INVENTORY) + `repo-cleanup` (current).

### C.1.HOLD (8 dirs — DO NOT TOUCH)

| Dir | Reason | mtime |
|---|---|---|
| `ar-1-mvp-vertical-slice` | arx-2 workstream (D1) | 2026-05-23 |
| `ar-2-reasoner-vision-deepening` | arx-2 workstream (D1) | 2026-05-23 |
| `ar-3-verifier-web-tools` | arx-2 workstream (D1) | 2026-05-23 |
| `ar-4-telemetry-streaming-smoke` | arx-2 workstream (D1) | 2026-05-24 |
| `aim-4-daily-sync` | in-flight | 2026-05-24 |
| `aim-5-stability-watch` | in-flight | 2026-05-24 |
| `repo-cleanup` | this phase | 2026-05-26 |
| `arx-3` | NEW since INVENTORY (synthesize/research lane) | 2026-05-26 |

### C.1.LEAVE (12 dirs — post-2026-05-17 D2 buffer)

| Dir | mtime |
|---|---|
| `kb-v2.1-stabilization` | 2026-05-17 |
| `kdb-2.5-reindex-lightrag-storage` | 2026-05-18 |
| `kb-v2.2-translation-and-kg-search` | 2026-05-20 |
| `kdb-3-uat-close` | 2026-05-20 |
| `llm-wiki-integration` | 2026-05-21 |
| `aim-0-readiness-aliyun-ecs` | 2026-05-22 |
| `kdb-2-databricks-app-deploy` | 2026-05-22 |
| `kb-4-ubuntu-deploy-cron-smoke` | 2026-05-22 |
| `aim-1-code-env-deploy` | 2026-05-23 |
| `aim-2-lightrag-storage-migration` | 2026-05-23 |
| `aim-3-cutover` | 2026-05-24 |
| `v1.0.y` | 2026-05-25 |

### C.1.ARCHIVE (26 dirs — pre-2026-05-17; bulk `git mv` to `archive/2026-05-26/phases/`)

| # | Dir |
|---|---|
| 1 | `04-knowledge-enrichment-zhihu` |
| 2 | `05-pipeline-automation` |
| 3 | `06-graphify-addon-code-graph` |
| 4 | `07-model-key-management` |
| 5 | `08-image-pipeline-correctness` |
| 6 | `09-timeout-state-management` |
| 7 | `10-classification-and-ingest-decoupling` |
| 8 | `11-e2e-verification-gate` |
| 9 | `12-checkpoint-resume` |
| 10 | `13-vision-cascade` |
| 11 | `14-regression-fixtures` |
| 12 | `15-docs-runbook` |
| 13 | `16-vertex-ai-design` |
| 14 | `17-batch-timeout-management` |
| 15 | `18-daily-ops-hygiene` |
| 16 | `19-generic-scraper-schema-kol-hotfix` |
| 17 | `20-rss-full-body-classify-multimodal-ingest-rewrite-cognee-routing-fix` |
| 18 | `21-stuck-doc-spike` |
| 19 | `ir-1-real-layer1-and-kol-ingest-wiring` |
| 20 | `ir-2-real-layer2-and-fullbody-scoring` |
| 21 | `ir-4-rss-integration-and-cleanup` |
| 22 | `kb-1-ssg-export-i18n-foundation` |
| 23 | `kb-2-topic-pillar-entity-pages` |
| 24 | `kb-3-fastapi-bilingual-api` |
| 25 | `kdb-1-uc-volume-and-data-snapshot` |
| 26 | `kdb-1.5-lightrag-databricks-provider-adapter` |

**Execution:** single `git mv` batch (one commit) — `git mv .planning/phases/<each> archive/2026-05-26/phases/<each>`. Use `-M90` similarity threshold to preserve history. `git log --follow archive/2026-05-26/phases/04-knowledge-enrichment-zhihu/...` will trace.

---

## Bucket C.2 — `.planning/quick/` (86 dirs total; 66 ARCHIVE + 7 HOLD + 13 LEAVE)

### C.2.HOLD (7 dirs — DO NOT TOUCH)

| Dir | Reason |
|---|---|
| `20260525-200047-synthesize-audit` | arx-3 explicit (RESPECT block) |
| `260524-arx-A-images` | arx-2 workstream (D1) |
| `260524-tk5-kb-longform-c1-hang` | synthesize/longform — possibly arx-3 territory; very recent |
| `260524-tk5b-databricks-sdk-deterministic-llm-hang` | databricks SDK hang — possibly arx-3 lane; very recent |
| `260524-tvg-wechat-session-hardening` | very recent (May 24); ingest territory still in flux |
| `260525-c1-no-content-at-64s` | very recent; C1 timeout debugging — likely tied to arx-2/arx-3 |
| `260525-vnj-vitaclaw-news-3shot-ingest` | very recent (May 25) |

### C.2.LEAVE (13 dirs — post-2026-05-17 D2 buffer; not HOLD)

`260517-fyb-hotfix-kb-v2-1-x-synthesize-wrapper-stal`, `260517-lok-lightrag-embedding-worker-timeout-kg`, `260517-riq-260517-rgd-v1-0-y-closure-trio-bidirecti`, `260518-non-pytest-harness-for-ingest-from-db-orches`, `260518-t2r-h3-wrap-ingest-from-db-in-contextlib-clo`, `260519-hwr-r1-add-4-behavior-anchor-tests-for-run-k`, `260519-ijn-f1-fix-5-test-fixture-drift-typeerrors-a`, `260519-s65-fix-long-form-image-url-citation-bugs`, `260520-m1p-260520-trans-inc-add-incremental-transla`, `260520-rou-kdb-agent-fix-databricks-apps-broken-ima`, `260520-sho-260520-a0g-aim-0-plan-robustness-verific`, `260521-kbq`, `260522-em8-ssg-bake-body-prompt-hardcode-deepseek-v`.

### C.2.ARCHIVE (66 dirs — pre-2026-05-17; bulk `git mv` to `archive/2026-05-26/quick/`)

| Date band | Count | Dirs |
|---|---|---|
| 260429 | 1 | `260429-got-extend-batch-ingest-from-spider-py-to-su` |
| 260503 | 5 | `260503-jn6-…`, `260503-lq7-…`, `260503-m4q-…`, `260503-sd7-…`, `260503-v9z-…` |
| 260504 | 4 | `260504-g7a-…`, `260504-lt2-…`, `260504-x3s-…`, `260504-x9l-…` |
| 260505 | 5 | `260505-ee5-…`, `260505-m9e-…`, `260505-s1h-…`, `260505-seu-…`, `260505-sjk-…` |
| 260506 | 4 | `260506-en4-…`, `260506-pa7-…`, `260506-rjs-…`, `260506-se5-…` |
| 260507 | 2 | `260507-ent-…`, `260507-lai-…` |
| 260508 | 1 | `260508-ev2-…` |
| 260509 | 6 | `260509-elc-…`, `260509-msr-…`, `260509-p1n-…`, `260509-s29-…`, `260509-syd-…`, `260509-t4i-…` |
| 260510 | 13 | `260510-gfg-…`, `260510-gkw-…`, `260510-gqu-…`, `260510-h09-…`, `260510-k5q-…`, `260510-kne-…`, `260510-l14-…`, `260510-onk-…`, `260510-oxq-…`, `260510-p1s-…`, `260510-rl2-…`, `260510-t1o-…`, `260510-uai-…` |
| 260511 | 12 | `260511-b3y-…`, `260511-b4k-…`, `260511-d7m-…`, `260511-kxd-…`, `260511-lmc-…`, `260511-lmw-…`, `260511-lmx-…`, `260511-lyj-…`, `260511-n0b-…`, `260511-rsp-…`, `260511-skb-…`, `260511-utl-…` |
| 260512 | 2 | `260512-bcy-…`, `260512-rln-…` |
| 260513 | 3 | `260513-d1d-…`, `260513-g0d-…`, `260513-q15-…` |
| 260514 | 3 | `260514-av8-…`, `260514-d3p-…`, `260514-eji-…` |
| 260515 | 1 | `260515-cvh-…` |
| 260516 | 4 | `260516-bls-…`, `260516-img-…`, `260516-rqk-…`, `260516-rr6-…` |
| **Total** | **66** | |

**Execution:** single `git mv` batch (one commit) — `git mv .planning/quick/<each> archive/2026-05-26/quick/<each>`. Single commit message citing the 66 dirs by full name in commit body.

**Reversibility:** `archive/2026-05-26/{phases,quick}/` are the canonical archive sink. To restore any single phase/quick: `git mv archive/2026-05-26/phases/<dir> .planning/phases/<dir>`.

---

## Bucket D — `.scratch/` (top-level 607 / recursive ~13,824 / ~3.66 GB)

### D.1 — HARD HOLDs (do not touch under any circumstance)

| Path | Reason |
|---|---|
| `.scratch/arx-2/` (recursive — entire subtree, ~3.1 GB) | arx-2 workstream (D1) — `lr_storage_arx2.tgz` + LightRAG storage staging |
| `.scratch/wiki-rebuild-probe-claude-code-global.md` | only tracked file in `.scratch/` (committed) |

### D.2 — Cleanup protocol per D4

Approved: ~360 MB recovery. Untracked AND >30 days OR not cited from any committed `.md`/`.py` file.

**Per-batch protocol (mandatory):**

1. List candidates in batches of ≤50 paths; write each batch to `.scratch/cleanup-batch-NN.txt` (gitignored).
2. For each batch, run `git grep -F -l <basename>` across `*.md *.py` (excluding `.scratch/`).
3. If any candidate is cited → halt batch, surface to user, ask before deleting that file.
4. Else: bulk delete via `rm -f` (untracked files; not `git rm` since they're untracked).
5. Per batch: log final action list to `.scratch/cleanup-batch-NN-done.txt` (kept until next batch or end of phase, then hard-delete).

### D.3 — Surfaced anomalies (need user decision)

| Path | Issue | Proposed |
|---|---|---|
| `.scratch/UsershuxxhaDesktopOmniGraph-Vault.scratchaliyun-search-probe.json` | Path-escape bug from cross-platform tool — clearly malformed filename. | **HARD-DELETE** with explicit user ack. |
| `.scratch/cognee_batch.log` | 0 bytes; cognee retired 2026-05-10 | **HARD-DELETE** (regenerable; 0 bytes). |
| Vulture txt files this phase authored (`vulture_strict_260526.txt`, `vulture_60_260526.txt`, `quick_list_260526.txt`) | Phase work product. Will move to `.planning/phases/repo-cleanup/` if cited from VERIFICATION; else **HARD-DELETE** at end of Phase 4. | Decide at Phase 4 boundary. |

### D.4 — Estimated recovery

Based on prior-session du: top-level (excluding arx-2) ≈ 360–550 MB across logs, screenshots, probe outputs, fixture dumps. Final number reported in CLEANUP-REPORT.md after Phase 3.

---

## Bucket E — Code Dead-Code Audit

### E.1 — Vulture STRICT (≥80% confidence) — 7 findings, scoped per D5

```
batch_scan_kol.py:30: unused import 'MAX_RETRIES' (90% confidence)
batch_scan_kol.py:30: unused import 'RATE_LIMIT_SLEEP_PAGES' (90% confidence)
lib\vertex_gemini_complete.py:168: unused variable 'keyword_extraction' (100% confidence)
scripts\bench_ingest_fixture.py:39: unused import 'urllib' (90% confidence)
scripts\bench_ingest_fixture.py:40: unused import 'urllib' (90% confidence)
scripts\lightrag_diag\probe_ainsert_timing.py:46: unused import 'DocStatus' (90% confidence)
scripts\lightrag_diag\probe_ainsert_timing.py:69: unused variable 'keyword_extraction' (100% confidence)
```

**Proposed action per row:**

| # | Item | Action | Notes |
|---|---|---|---|
| E-1 | `batch_scan_kol.py:30` `MAX_RETRIES` import | **HARD-DELETE import** | Single-line edit. Also see E-9 — `batch_scan_kol.py` itself may be STALE (root .py audit). |
| E-2 | `batch_scan_kol.py:30` `RATE_LIMIT_SLEEP_PAGES` import | **HARD-DELETE import** | Same as E-1. |
| E-3 | `lib/vertex_gemini_complete.py:168` `keyword_extraction` var | **HARD-DELETE var** | 100% confidence. Single-file local var. |
| E-4 | `scripts/bench_ingest_fixture.py:39` `urllib` import | **HARD-DELETE import** | Bench script — not in hot path. |
| E-5 | `scripts/bench_ingest_fixture.py:40` `urllib` import | **HARD-DELETE import** | Same. |
| E-6 | `scripts/lightrag_diag/probe_ainsert_timing.py:46` `DocStatus` import | **HARD-DELETE import** | Diag script — see E-9 stale-script audit. |
| E-7 | `scripts/lightrag_diag/probe_ainsert_timing.py:69` `keyword_extraction` var | **HARD-DELETE var** | 100% confidence. |

**Execution:** single commit "chore: vulture strict cleanup (7 unused imports/vars)" with each file edit. Run smoke `venv/Scripts/python -m pytest tests/unit -q` after edit; commit only if green.

### E.2 — Vulture SURFACED (60–79% confidence) — 51 additional findings

Full list at `.scratch/vulture_60_260526.txt`. **Action: SURFACE ONLY in this TRIAGE — no delete proposed.** 60% confidence is too low to act on without per-file audit. Pull-quote candidates that are likely real-but-need-audit:

| # | Item | Action |
|---|---|---|
| E-S1 | `config.py:31` `FIRECRAWL_API_KEY` | **AUDIT — likely STALE** (Firecrawl never adopted; env var never set in any deployed config). Propose remove in v1.1. |
| E-S2 | `config.py:80–104` (8 vars: `ENRICHMENT_*`, `ZHIHAO_SKILL_NAME`, `IMAGE_SERVER_BASE_URL`) | **AUDIT — enrichment subdir status?** If `enrichment/` is being retired (per ir-4 promise), all 8 are dead. Defer to dedicated cleanup task. |
| E-S3 | `lib/research/stages/{reasoner,verifier}.py:59,78` unused `_LLMDecision` class | **HOLD — arx-3 territory** (`lib/research/`). Don't touch. |
| E-S4 | `lib/research/types.py:65,100` unused `fact_check_summary_md`, `images_embedded` | **HOLD — arx-3 territory.** Don't touch. |
| E-S5 | All other surfaced findings | LEAVE for future cleanup pass. |

### E.3 — Stale root `*.py` (per INVENTORY)

| File | Status | Action |
|---|---|---|
| `batchkol_topic.py` | INVENTORY-flagged STALE | **AUDIT — propose ARCHIVE to `archive/2026-05-26/code/`** if no inbound references in `git grep`. |
| `batch_ingest_kol_mvp.py` | INVENTORY-flagged STALE | Same — AUDIT + ARCHIVE. |
| `test_mcp_approaches.py` | INVENTORY-flagged STALE; root-level test (not in `tests/`) | Same — AUDIT + ARCHIVE. |
| `batch_scan_kol.py` (linked from E-1, E-2) | If imports are unused AND no `git grep` calls → STALE | AUDIT alongside above. |

**Execution:** before any root-`*.py` archive, `git grep -F <module_name>` across the repo. Halt+ask if any non-test file imports it.

### E.4 — Cognee residue

| File | Action |
|---|---|
| `.scratch/cognee_batch.log` (0 bytes) | **HARD-DELETE** (covered by D.3 above). |
| `lib/cognee*` | None present (verified via `ls lib/ | grep -i cognee` returns empty). |

---

## Bucket F — Tests / docs / specs / skills

### F.1 — `tests/`

Per D5, **tests/ is OUT OF SCOPE for this cleanup phase** — owned by arx-3 (test-fixture drift owner). Per INVENTORY, 96 fixture files KEPT — no action proposed. **LEAVE entire `tests/` tree.**

### F.2 — `docs/`

INVENTORY flagged ~10 v3.x archive candidates. Per D2 cutoff, anything not actively cited from current CLAUDE.md or active phase plans is archive-eligible. Specific candidates need per-file audit.

| Path | Status | Action |
|---|---|---|
| `docs/architecture.md` | new file (target of D3 + A8 + A20 extracts) | CREATE in Phase 3 |
| `docs/skills/SKILL_STANDARDS.md` | new file (target of A14 extract) | CREATE in Phase 3 |
| `docs/local-e2e-runbook.md` | new file (target of A6 extract) | CREATE in Phase 3 |
| `docs/operations/checkpoint.md` | new file (target of A19 extract) | CREATE in Phase 3 |
| `docs/operations/vision-cascade.md` | new file (target of A20 extract) | CREATE in Phase 3 |
| `docs/testing/cdp-mcp-paths.md` | new file (target of A15 extract) | CREATE in Phase 3 |
| `docs/releases/v1.0.md` | new file (target of A4 compact) | CREATE in Phase 3 |
| `docs/lessons/2026-05-archive.md` | exists | LEAVE |
| `docs/VERTEX_AI_MIGRATION_SPEC.md` | exists, cited from CLAUDE.md | LEAVE |
| `docs/LOCAL_DEV_SETUP.md` | exists, cited from CLAUDE.md | LEAVE |
| `docs/research/rss-flow-as-of-260508.md` | exists, cited from CLAUDE.md | LEAVE |
| `docs/design/agentic_rag_internal_api.md` | exists, cited from CLAUDE.md | LEAVE |
| Other v3.x design docs (per INVENTORY ~10 candidates) | per-file audit needed | **AUDIT in Phase 3 step F-A** — list candidates, grep cite-check, propose ARCHIVE batch. |

### F.3 — `specs/`

INVENTORY flagged 6 archive candidates. Per RESEARCH best practices, `specs/` should be lean and current.

**Action: AUDIT in Phase 3 step F-B.** Grep cite-check from current CLAUDE.md and active phases. Propose ARCHIVE batch.

### F.4 — `skills/`

INVENTORY flagged 4 archive candidates + 2 confirm-needed.

**Action: AUDIT in Phase 3 step F-C.**

### F.5 — `agents/`, `.agents/`

Not flagged by INVENTORY; not in scope this cleanup. LEAVE.

---

## Phase 4 Token-Delta Scaffold

To be measured pre-Phase 3 vs post-Phase 3 by `wc -l` and a simple token-estimate (4 chars/token):

| Surface | Pre (lines / est tokens) | Post (lines / est tokens) | Delta |
|---|---|---|---|
| `CLAUDE.md` | ~870 / ~16,000 | ~330 / ~6,000 | **−540 lines / −10,000 tokens (−63%)** |
| `MEMORY.md` index | ~53 entries (~150 lines) | ~46 entries (~120 lines) | −7 entries (orphans + archived snapshots) |
| memory/ files | ~55 files | ~48 files | −7 (3 hard-deletes + 4 archived to lessons doc) |
| `.planning/phases/` | 46 dirs | 20 dirs (8 HOLD + 12 LEAVE) | 26 archived |
| `.planning/quick/` | 86 dirs | 20 dirs (7 HOLD + 13 LEAVE) | 66 archived |
| `.scratch/` | ~3.66 GB | ~3.30 GB (arx-2 retained) | ~360 MB recovered |
| Code dead-code | 7 strict findings | 0 | −7 imports/vars |

**Key invariant:** the actual session-start context drop is **measured** in `CLAUDE.md` reduction (since memory files are loaded on-demand, not at session start). Target: ~10,000 tokens / 63% reduction.

---

## Execution Order Recommendation (Phase 3)

Each step = single atomic commit. Pull --ff-only before EACH commit. Halt + arx-3 status check before EACH commit.

| Step | Bucket | Action | Commit msg prefix |
|---|---|---|---|
| 0 | — | `git pull --ff-only` + arx-3 status check | (no commit) |
| 1 | A21 | EXTRACT A21 → `docs/architecture.md` (with kg-vault → omonigraph-vault fix per D3) + 1-line pointer in CLAUDE.md | `docs(repo-cleanup): extract A21 SiliconFlow + fix kg-vault stale path` |
| 2 | A8, A20, A19 | EXTRACT A8 (Q/Synthesis Flow) + A20 (Vision Cascade) + A19 (Checkpoint) into `docs/architecture.md` and `docs/operations/{vision-cascade,checkpoint}.md`; pointers in CLAUDE.md | `docs(repo-cleanup): extract architecture+operations sections` |
| 3 | A14, A15, A6 | EXTRACT A14 (Skill Standards) + A15 (CDP/MCP Testing) + A6 (Local E2E corp) into `docs/skills/`, `docs/testing/`, `docs/local-e2e-runbook.md`; pointers | `docs(repo-cleanup): extract skill+testing+e2e runbooks` |
| 4 | A4, A5, A10, A12, A16, A18 | COMPACT in CLAUDE.md (release status, commands, env tables, Hermes deploy, Vertex spec) | `docs(repo-cleanup): compact CLAUDE.md release+ops sections` |
| 5 | C.1 | bulk `git mv` 26 phase dirs → `archive/2026-05-26/phases/` | `chore(repo-cleanup): archive 26 closed phase dirs` |
| 6 | C.2 | bulk `git mv` 66 quick dirs → `archive/2026-05-26/quick/` | `chore(repo-cleanup): archive 66 closed quick dirs` |
| 7 | B.2, B.3 | HARD-DELETE 2 orphan memory files + `MEMORY.original.md` | `chore(repo-cleanup): remove orphan + backup memory files` |
| 8 | B.1 | ARCHIVE 4 date-anchored memory snapshots to `docs/lessons/2026-05-archive.md`; remove memory files; update MEMORY.md index | `docs(repo-cleanup): archive 4 date-anchored memory snapshots` |
| 9 | B.1 | COMPACT 6 closure-marker memory files in place to 1-liners | `docs(repo-cleanup): compact 6 closure-marker memory files` |
| 10 | E.1 | vulture-strict cleanup (7 findings) + `pytest tests/unit -q` smoke | `chore(repo-cleanup): vulture strict cleanup (7 unused imports/vars)` |
| 11 | E.3 | AUDIT root *.py STALE candidates → propose ARCHIVE batch (separate halt for user ack) | `chore(repo-cleanup): archive stale root *.py modules` |
| 12 | D | `.scratch/` cleanup per D4 protocol (per-batch grep + halt-on-cite) | `chore(repo-cleanup): scratch cleanup batch NN` (one commit per batch) |
| 13 | F.2, F.3, F.4 | AUDIT docs/specs/skills → propose ARCHIVE batches (separate halts) | `docs(repo-cleanup): archive stale docs/specs/skills` |
| 14 | — | Phase 4: `CLEANUP-REPORT.md` with measured token deltas + diff stats + reversibility manifest | (no commit, planning artifact) |

---

## Halt Point

**Phase 2 deliverable complete.** No mutation performed.

**Authorize Phase 3 with one of:**

- **`approve all`** — execute steps 1–13 in order, with serialization/halt protocol per spec.
- **`approve A,C,D`** (or any subset) — execute only the named buckets.
- **`skip <X>`** — execute everything except `<X>` (e.g., `skip B` to defer memory cleanup).
- **`halt revise: <Y>`** — pause; revise this TRIAGE in response to feedback `<Y>` before authorizing.

**Reminder:** any Phase 3 commit MUST be preceded by `git pull --ff-only` + arx-3 status check, per Phase 3 Serialization Constraint.
