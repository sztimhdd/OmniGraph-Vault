# Roadmap — kb-databricks-v1

> Parallel-track milestone. Phases use `kdb-N-*` prefix. Sibling roadmaps: `ROADMAP-KB-v2.md` (`kb-N-*`), `ROADMAP-Agentic-RAG-v1.md` (`ar-N-*`), `ROADMAP-v3.5-Ingest-Refactor.md` (`ir-N-*`). Main `ROADMAP.md` is owned by v3.4 / v3.5 main track.

## Milestone size

T-shirt **S** — 1–2 days end-to-end if kdb-1 spike comes back clean. 2–3 days if kdb-1.5 fires.

## Phase summary

| # | Phase | Goal | REQs covered | Success criteria | T-shirt |
|---|-------|------|--------------|------------------|---------|
| **kdb-1** | UC Volume + Snapshot + Preflight + Spike | Volume + initial snapshot in place; PREFLIGHT confirms DeepSeek egress OK + grant capability OK; SPIKE 5/5 confirms (or rejects) `/Volumes/...` Apps-runtime access | STORAGE-DBX-01..05 (verify only), PREFLIGHT-DBX-01..02, SPIKE-DBX-01a..01e, SYNC-DBX-01..02 | 6 | XS-S (½ to 1 day; longer if PREFLIGHT escalation needed) |
| **kdb-1.5** | LightRAG Storage Adapter (conditional) | Copy-to-/tmp adapter at App startup if any SPIKE sub-check ❌ or INCONCLUSIVE-at-30-min | STORAGE-DBX-05 (alt path) | 2 | XS (≤ half-day) |
| **kdb-2** | Databricks App Deploy | App created + secret resource bound + grants set + first deploy reaches RUNNING + Smoke 1+2 (KB-v2 verbatim) PASS | AUTH-DBX-01..05, SECRETS-DBX-01..04, DEPLOY-DBX-01..08, OPS-DBX-01, OPS-DBX-02 | 5 | S (1 day) |
| **kdb-3** | UAT Close | Smoke 3 (KB-v2 verbatim) + sync round-trip + secret-leak audit (databricks-deploy/) + zero-`kb/`-edits audit (vs commit `7df6e5b`) + runbook + sign-off | SECRETS-DBX-05, CONFIG-DBX-01..02, SYNC-DBX-03, QA-DBX-01..03, OPS-DBX-03..05 | 5 | XS (half-day) |

**Default path:** kdb-1 → kdb-2 → kdb-3 (3 phases). Insert kdb-1.5 between kdb-1 and kdb-2 only if SPIKE-DBX-01 surfaces a blocker.

---

## Phase kdb-1 — UC Volume + Data Snapshot + Preflight + Spike

**Goal:** Lay down the storage layer (schema + volume + initial snapshot), preflight the two highest-risk milestone blockers (DeepSeek egress + grant capability), AND prove whether `/Volumes/...` is usable from the Apps runtime — before committing to the deploy phase.

**Requirements:** STORAGE-DBX-01..04, STORAGE-DBX-05 (verify only), PREFLIGHT-DBX-01, PREFLIGHT-DBX-02, SPIKE-DBX-01a..01e, SYNC-DBX-01, SYNC-DBX-02

**Phase wave structure:**

- **Wave 1 (preflight, ~30 min):** PREFLIGHT-DBX-01 (DeepSeek egress test) + PREFLIGHT-DBX-02 (grant capability test). These run on a workspace serverless notebook BEFORE building anything; either ❌ blocks the rest of the phase pending escalation
- **Wave 2 (storage, ~30 min):** STORAGE-DBX-01..04 + SYNC-DBX-01..02 — create schema + volume + populate sub-directories + run initial Hermes snapshot
- **Wave 3 (spike, 30-min hard timer):** SPIKE-DBX-01a..01e — deploy a throwaway test-app `omnigraph-kb-spike`, run the 5 sub-checks against the populated volume

**Success criteria:**

1. PREFLIGHT-DBX-01 ✅ + PREFLIGHT-DBX-02 ✅ (both must pass before Wave 2 starts)
2. `mdlg_ai_shared.kb_v2.omnigraph_vault` volume created with 4 sub-directories populated by initial Hermes snapshot
3. `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data` lists `kol_scan.db` (no `-wal`/`-shm` sidecars); post-sync integrity check passes (1 known article queryable with matching `content_hash`)
4. `kdb-1-PREFLIGHT-FINDINGS.md` documents PREFLIGHT-01/02 outcomes with evidence (HTTP response codes, grant SQL output)
5. `kdb-1-SPIKE-FINDINGS.md` answers all 5 sub-checks (01a-01e) with evidence (each sub-check has either ✅ + log excerpt or ❌ + reproduction or `INCONCLUSIVE` if 30-min timer elapsed)
6. `databricks-deploy/RUNBOOK.md` Section 1 (initial sync) authored with the exact commands that produced the snapshot

**Non-goals:** Production App creation, deploy, secrets, grants — all in kdb-2. (The kdb-1 spike test-app is throwaway and uses minimal config.)

**Decision gate at end of phase:**

| Outcome | Action |
|---------|--------|
| PREFLIGHT-01 ❌ | Milestone BLOCKED. Escalate to EDC networking. Do NOT proceed to spike or kdb-2. Mitigation paths in `kdb-1-PREFLIGHT-FINDINGS.md` |
| PREFLIGHT-02 ❌ | Spike CAN proceed (uses pre-existing volume); kdb-2 BLOCKED pending workspace-admin grant escalation |
| All PREFLIGHT ✅ + all SPIKE 01a-01e ✅ | Proceed directly to kdb-2 (3-phase happy path) |
| All PREFLIGHT ✅ + ANY SPIKE 01a-01e ❌ | Insert kdb-1.5 (LightRAG storage adapter pattern) |
| All PREFLIGHT ✅ + ANY SPIKE INCONCLUSIVE-at-30-min | Insert kdb-1.5 (don't burn more time investigating; default to adapter). Hard timer rule: phase orchestrator stops the spike at 30 min wall-clock from Wave 3 start; whatever's still INCONCLUSIVE counts as ❌ |

---

## Phase kdb-1.5 — LightRAG Storage Adapter (conditional)

**Goal:** Implement the copy-to-/tmp adapter so App can read `/Volumes/...` once at startup, then operate against `/tmp/` — bypassing FUSE / read-only mount issues.

**Requirements:** STORAGE-DBX-05 (alternative satisfaction path)

**Success criteria:**

1. New module `databricks-deploy/startup_adapter.py` (NOT under `kb/`) implements the copy-on-startup pattern using either `shutil.copytree` (if FUSE) or `databricks-sdk` `w.files.download_directory` (if Files API only)
2. Adapter is invoked from `app.yaml` `command:` via wrapper shell or pre-uvicorn step
3. Adapter is idempotent — repeated App restarts don't re-download if `/tmp/` already populated and Volume mtime unchanged
4. Local test on Apps runtime confirms LightRAG instantiates against `/tmp/lightrag_storage` after adapter run

**Triggered by:** SPIKE-DBX-01 finding 1+ blocker in kdb-1.

---

## Phase kdb-2 — Databricks App Deploy

**Goal:** Stand up `omnigraph-kb` App, get to RUNNING state, prove Smoke 1 + Smoke 2 work end-to-end.

**Requirements:** AUTH-DBX-01..05, SECRETS-DBX-01..04, DEPLOY-DBX-01..06, OPS-DBX-01, OPS-DBX-02

**Success criteria:**

1. `databricks apps get omnigraph-kb` shows `state: RUNNING` and a non-null URL
2. Secret scope `omnigraph-kb` exists with key `deepseek_api_key`; `databricks secrets list-acls --scope omnigraph-kb` shows App SP with READ
3. App SP grants verifiable: `SHOW GRANTS ON CATALOG mdlg_ai_shared TO \`app-omnigraph-kb\`` returns USE_CATALOG; same for SCHEMA + READ_VOLUME on volume
4. **Smoke 1 PASS:** App URL renders home page after SSO; Apps Logs tab shows zero ERROR during cold start; logs confirm `OMNIGRAPH_BASE_DIR` resolved correctly
5. **Smoke 2 PASS:** `/api/search?q=AI+Agent` returns ≥3 zh-CN hits; `/api/search?q=langchain&lang=en` returns ≥3 en hits; clicking any article renders detail page with images served via `/static/img/...`

**Hard constraints (verified during phase):**
- `app.yaml` at root of `--source-code-path`
- `command:` uses `$DATABRICKS_APP_PORT` substitution
- `DEEPSEEK_API_KEY` set via `valueFrom:` (NOT literal)
- All commits free of literal `sk-...` token strings (rolling audit)

**Phase deliverables:**
- `databricks-deploy/app.yaml` (committed)
- `databricks-deploy/Makefile` (`make deploy`, `make logs`, `make stop` recipes)
- Apps Logs evidence captured in `kdb-2-SMOKE-EVIDENCE.md`

---

## Phase kdb-3 — UAT Close

**Goal:** Final smoke (Smoke 3 RAG round-trip), sync round-trip retest, all audits, sign-off.

**Requirements:** SECRETS-DBX-05, CONFIG-DBX-01..02, SYNC-DBX-03, QA-DBX-01..03, OPS-DBX-03..05

**Success criteria:**

1. **Smoke 3 PASS:** `/synthesize` round-trips with markdown answer; Apps logs confirm DeepSeek call succeeded (HTTP 200 from `api.deepseek.com`); negative-path test returns FTS5 fallback (NOT 500)
2. **Sync round-trip PASS:** Hermes-side ingest 1 new article → run runbook sync → restart App → new article visible in browser
3. **Secret-leak audit PASS:** `git log --all -p -- databricks-deploy/app.yaml | grep -iE 'sk-[a-zA-Z0-9]{20,}'` returns empty; `git log --all -p` filtered to whole-repo new content also clean
4. **Zero-`kb/`-edits audit PASS:** `git diff <kdb-databricks-v1-base>..HEAD -- kb/` returns empty
5. `databricks-deploy/RUNBOOK.md` complete: first-deploy, manual-sync, App-restart, secret-rotation, troubleshoot sections all written + tested
6. `VERIFICATION-kb-databricks-v1.md` authored with all 30 REQs ✅ (or noted as deferred with reasoning); milestone marked complete in `STATE-kb-databricks-v1.md` and `MILESTONES-kb-databricks-v1.md` (or appended to main `MILESTONES.md`)

**Phase deliverables:**
- `kdb-3-VERIFICATION.md` — checkbox status of all 30 REQs with evidence
- `databricks-deploy/RUNBOOK.md` complete
- Final state-update commit + sign-off

---

## Wave / parallelization analysis

This milestone is **mostly sequential** (kdb-1 → kdb-2 → kdb-3) because each phase strictly depends on the previous. Within phases, parallelization is limited:

- **kdb-1 internal parallelism:** the spike (SPIKE-DBX-01) and the snapshot upload (SYNC-DBX-02) can run concurrently if a workspace cluster is available for the spike notebook. Most users will run them serially.
- **kdb-2 internal parallelism:** secret-scope creation + ACL grants can run concurrently with `app.yaml` authoring. Expect ~2 lanes for ~30 min then merge.
- **kdb-3 internal parallelism:** Smoke 3 + secret-leak audit + zero-kb-edits audit are independent; can run concurrently.

No cross-phase parallelization. Phase boundaries are fenced by either a deploy gate (kdb-1 spike → kdb-2 OK to deploy) or a smoke gate (kdb-2 RUNNING → kdb-3 UAT).

## Coverage validation (orchestrator hand-driven, per parallel-track caveat)

36 REQs in REQUIREMENTS → 36 mapped to phases (table below). 100% coverage.

| REQ-ID | Phase | Verification mechanism |
|--------|-------|------------------------|
| STORAGE-DBX-01 | kdb-1 | `databricks-mcp-server list_schemas mdlg_ai_shared` shows `kb_v2` |
| STORAGE-DBX-02 | kdb-1 | `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` succeeds |
| STORAGE-DBX-03 | kdb-1 | Same `ls` shows 4 sub-dirs |
| STORAGE-DBX-04 | kdb-1 | `databricks fs ls dbfs:/Volumes/.../data` shows `kol_scan.db` only (no sidecars); 1-article integrity check passes |
| STORAGE-DBX-05 | kdb-1 spike OR kdb-1.5 | SPIKE 01a-01e result OR adapter test |
| PREFLIGHT-DBX-01 | kdb-1 (Wave 1) | Notebook DeepSeek POST returns HTTP 200; logged in `kdb-1-PREFLIGHT-FINDINGS.md` |
| PREFLIGHT-DBX-02 | kdb-1 (Wave 1) | Test grant SQL succeeds (or escalation path documented if denied) |
| SPIKE-DBX-01a | kdb-1 (Wave 3) | `os.path.ismount(...)` + `os.listdir(...)` from test-app |
| SPIKE-DBX-01b | kdb-1 (Wave 3) | `os.makedirs(..., exist_ok=True)` no-raise from test-app with READ VOLUME only |
| SPIKE-DBX-01c | kdb-1 (Wave 3) | `sqlite3.connect("file:.../kol_scan.db?mode=ro", uri=True)` + `SELECT count(*)` succeeds |
| SPIKE-DBX-01d | kdb-1 (Wave 3) | Time test-app start → `/health` 200; < 60s |
| SPIKE-DBX-01e | kdb-1 (Wave 3) | In-app DeepSeek call HTTP 200 |
| SYNC-DBX-01 | kdb-1 | `databricks-deploy/RUNBOOK.md` Section 1 written |
| SYNC-DBX-02 | kdb-1 | First sync executed; Volume populated |
| AUTH-DBX-01..03 | kdb-2 | `SHOW GRANTS ... TO 'app-omnigraph-kb'` |
| AUTH-DBX-04 | kdb-2 | `databricks secrets list-acls --scope omnigraph-kb` |
| AUTH-DBX-05 | kdb-2 | App URL prompts SSO (manual UAT) |
| SECRETS-DBX-01 | kdb-2 | `databricks secrets list-scopes` shows `omnigraph-kb` |
| SECRETS-DBX-02 | kdb-2 | `databricks secrets list-secrets --scope omnigraph-kb` shows key |
| SECRETS-DBX-03 | kdb-2 | `databricks apps get omnigraph-kb -o json` resources block |
| SECRETS-DBX-04 | kdb-2 | `cat databricks-deploy/app.yaml` shows `valueFrom:` |
| SECRETS-DBX-05 | kdb-3 | `git log --all -p -- databricks-deploy/` audit |
| DEPLOY-DBX-01..06 | kdb-2 | `databricks apps get omnigraph-kb` returns RUNNING + URL + Smoke 1 |
| DEPLOY-DBX-07 | kdb-2 | `cat databricks-deploy/requirements.txt` lists kb runtime deps |
| DEPLOY-DBX-08 | kdb-2 | `cat databricks-deploy/app.yaml` shows `OMNIGRAPH_LLM_PROVIDER=deepseek` literal |
| CONFIG-DBX-01 | kdb-3 | `git log 7df6e5b..HEAD --grep '(kdb-' --name-only -- kb/` returns empty |
| CONFIG-DBX-02 | kdb-3 | `ls databricks-deploy/` shows all config files |
| QA-DBX-01..03 | kdb-3 | Smoke 3 evidence in VERIFICATION |
| OPS-DBX-01 | kdb-2 | KB-v2 Smoke 1 evidence (双语 UI 切换) |
| OPS-DBX-02 | kdb-2 | KB-v2 Smoke 2 evidence (双语搜索 + 详情页 + UC Volume image render) |
| OPS-DBX-03 | kdb-3 | KB-v2 Smoke 3 evidence (双语 RAG + 降级 + DeepSeek 200) |
| OPS-DBX-04 | kdb-3 | `kdb-3-VERIFICATION.md` authored |
| OPS-DBX-05 | kdb-3 | `databricks-deploy/RUNBOOK.md` complete |

---

## Risks (top 3)

1. **kdb-1 spike surfaces multiple blockers** → kdb-1.5 cost expands beyond half-day → milestone slips from S to M. **Mitigation:** spike scoped to 30 min hard timebox; if 30 min in we have no answers, default to copy-to-/tmp adapter without further spiking.
2. **Apps runtime egress to `api.deepseek.com` is blocked by EDC network policy** → Smoke 3 fails permanently → milestone blocked. **Mitigation:** test outbound HTTPS from Apps in kdb-2 EARLY (before full smoke), get networking exception filed if blocked. Fallback v1.x: route DeepSeek calls through a workspace HTTPS proxy. Worst case: forced FM-DBX swap pulled into v1 scope.
3. **App SP grants are workspace-admin-only operations** → user (`hhu@edc.ca`) may not have admin → grant request adds days. **Mitigation:** verify grant capabilities in kdb-1 (try a test grant on a throwaway volume); if blocked, escalate to workspace admin BEFORE kdb-2 starts.

---

## ROADMAP CREATED

3 phases (4 with conditional kdb-1.5) | 36 REQs mapped | All covered ✓

**Revision history:**
- 2026-05-15 rev 2 — incorporated user P0/P1/P2 adjustments: SPIKE split into 5 sub-items (01a-01e), new PREFLIGHT category front-loaded into kdb-1 Wave 1, DEPLOY-07/08 (requirements.txt + LLM_PROVIDER lock), OPS verbatim KB-v2 Smoke 1/2/3, CONFIG-01 milestone-base anchor `7df6e5b`, SPIKE 30-min hard timer + INCONCLUSIVE→kdb-1.5 rule
- 2026-05-15 rev 1 — initial draft, 30 REQs / 9 categories
