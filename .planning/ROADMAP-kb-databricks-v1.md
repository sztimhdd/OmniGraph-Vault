# Roadmap — kb-databricks-v1

> Parallel-track milestone. Phases use `kdb-N-*` prefix. Sibling roadmaps: `ROADMAP-KB-v2.md` (`kb-N-*`), `ROADMAP-Agentic-RAG-v1.md` (`ar-N-*`), `ROADMAP-v3.5-Ingest-Refactor.md` (`ir-N-*`). Main `ROADMAP.md` is owned by v3.4 / v3.5 main track.

## Milestone size

T-shirt **S** — 1–2 days end-to-end if kdb-1 spike comes back clean. 2–3 days if kdb-1.5 fires.

## Phase summary

| # | Phase | Goal | REQs covered | Success criteria | T-shirt |
|---|-------|------|--------------|------------------|---------|
| **kdb-1** | UC Volume + Data Snapshot + Spike | Volume + initial snapshot in place; viability of `/Volumes/...` runtime access proven OR adapter need confirmed | STORAGE-DBX-01..05, SPIKE-DBX-01, SYNC-DBX-01..02 | 4 | XS (≤ half-day) |
| **kdb-1.5** | LightRAG Storage Adapter (conditional) | Copy-to-/tmp adapter at App startup if spike blockers found | STORAGE-DBX-05 (alt path) | 2 | XS (≤ half-day) |
| **kdb-2** | Databricks App Deploy | App created + secret resource bound + grants set + first deploy reaches RUNNING + Smoke 1+2 PASS | AUTH-DBX-01..05, SECRETS-DBX-01..04, DEPLOY-DBX-01..06, OPS-DBX-01, OPS-DBX-02 | 5 | S (1 day) |
| **kdb-3** | UAT Close | Smoke 3 + sync round-trip + secret-leak audit + zero-`kb/`-edits audit + runbook + sign-off | SECRETS-DBX-05, CONFIG-DBX-01..02, SYNC-DBX-03, QA-DBX-01..03, OPS-DBX-03..05 | 5 | XS (half-day) |

**Default path:** kdb-1 → kdb-2 → kdb-3 (3 phases). Insert kdb-1.5 between kdb-1 and kdb-2 only if SPIKE-DBX-01 surfaces a blocker.

---

## Phase kdb-1 — UC Volume + Data Snapshot + Spike

**Goal:** Lay down the storage layer (schema + volume + initial snapshot) AND prove whether `/Volumes/...` is usable from the Apps runtime, before committing to the deploy phase.

**Requirements:** STORAGE-DBX-01, STORAGE-DBX-02, STORAGE-DBX-03, STORAGE-DBX-04, STORAGE-DBX-05 (verify only), SPIKE-DBX-01, SYNC-DBX-01, SYNC-DBX-02

**Success criteria:**

1. `mdlg_ai_shared.kb_v2.omnigraph_vault` volume created with 4 sub-directories populated by initial Hermes snapshot
2. `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/data` lists `kol_scan.db` (no `-wal`/`-shm` sidecars)
3. `kdb-1-SPIKE-FINDINGS.md` answers all 5 viability questions with evidence (each Q has either ✅ + log excerpt or ❌ + reproduction)
4. `databricks-deploy/RUNBOOK.md` Section 1 (initial sync) authored with the exact commands that produced the snapshot

**Non-goals:** App creation, deploy, secrets, grants — all in kdb-2.

**Decision gate at end of phase:**
- All 5 spike questions ✅ → proceed directly to kdb-2
- Any blocker (`os.makedirs` raises, SQLite refuses to open, no FUSE mount) → insert kdb-1.5

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

30 REQs in REQUIREMENTS → 30 mapped to phases (table below). 100% coverage.

| REQ-ID | Phase | Verification mechanism |
|--------|-------|------------------------|
| STORAGE-DBX-01 | kdb-1 | `databricks-mcp-server list_schemas mdlg_ai_shared` shows `kb_v2` |
| STORAGE-DBX-02 | kdb-1 | `databricks fs ls dbfs:/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` succeeds |
| STORAGE-DBX-03 | kdb-1 | Same `ls` shows 4 sub-dirs |
| STORAGE-DBX-04 | kdb-1 | `databricks fs ls dbfs:/Volumes/.../data` shows `kol_scan.db` only (no sidecars) |
| STORAGE-DBX-05 | kdb-1 spike OR kdb-1.5 | Spike result OR adapter test |
| SPIKE-DBX-01 | kdb-1 | `kdb-1-SPIKE-FINDINGS.md` answers 5/5 Qs |
| SYNC-DBX-01 | kdb-1 | `databricks-deploy/RUNBOOK.md` Section 1 written |
| SYNC-DBX-02 | kdb-1 | First sync executed; Volume populated |
| AUTH-DBX-01..03 | kdb-2 | `SHOW GRANTS ... TO \`app-omnigraph-kb\`` |
| AUTH-DBX-04 | kdb-2 | `databricks secrets list-acls --scope omnigraph-kb` |
| AUTH-DBX-05 | kdb-2 | App URL prompts SSO (manual UAT) |
| SECRETS-DBX-01 | kdb-2 | `databricks secrets list-scopes` shows `omnigraph-kb` |
| SECRETS-DBX-02 | kdb-2 | `databricks secrets list-secrets --scope omnigraph-kb` shows key |
| SECRETS-DBX-03 | kdb-2 | `databricks apps get omnigraph-kb -o json` resources block |
| SECRETS-DBX-04 | kdb-2 | `cat databricks-deploy/app.yaml` shows `valueFrom:` |
| SECRETS-DBX-05 | kdb-3 | Final `git log --all -p` audit |
| DEPLOY-DBX-01..06 | kdb-2 | `databricks apps get omnigraph-kb` returns RUNNING + URL + smoke 1 |
| CONFIG-DBX-01 | kdb-3 | `git diff <base>..HEAD -- kb/` empty |
| CONFIG-DBX-02 | kdb-3 | `ls databricks-deploy/` shows all config files |
| QA-DBX-01..03 | kdb-3 | Smoke 3 evidence in VERIFICATION |
| OPS-DBX-01 | kdb-2 | Smoke 1 evidence |
| OPS-DBX-02 | kdb-2 | Smoke 2 evidence |
| OPS-DBX-03 | kdb-3 | Smoke 3 evidence |
| OPS-DBX-04 | kdb-3 | `kdb-3-VERIFICATION.md` authored |
| OPS-DBX-05 | kdb-3 | `databricks-deploy/RUNBOOK.md` complete |

---

## Risks (top 3)

1. **kdb-1 spike surfaces multiple blockers** → kdb-1.5 cost expands beyond half-day → milestone slips from S to M. **Mitigation:** spike scoped to 30 min hard timebox; if 30 min in we have no answers, default to copy-to-/tmp adapter without further spiking.
2. **Apps runtime egress to `api.deepseek.com` is blocked by EDC network policy** → Smoke 3 fails permanently → milestone blocked. **Mitigation:** test outbound HTTPS from Apps in kdb-2 EARLY (before full smoke), get networking exception filed if blocked. Fallback v1.x: route DeepSeek calls through a workspace HTTPS proxy. Worst case: forced FM-DBX swap pulled into v1 scope.
3. **App SP grants are workspace-admin-only operations** → user (`hhu@edc.ca`) may not have admin → grant request adds days. **Mitigation:** verify grant capabilities in kdb-1 (try a test grant on a throwaway volume); if blocked, escalate to workspace admin BEFORE kdb-2 starts.

---

## ROADMAP CREATED

3 phases (4 with conditional kdb-1.5) | 30 REQs mapped | All covered ✓
