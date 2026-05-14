# OmniGraph-Vault — Parallel Milestone: kb-databricks-v1

> Sibling milestone running parallel to v3.4 (closed) / v3.5 (Ingest Refactor) /
> Agentic-RAG-v1 / KB-v2.
> Main project context lives in `PROJECT.md`. This file scopes kb-databricks-v1 only.
> Phase directories use the `kdb-N-*` prefix to avoid collision with other milestones.

## What This Milestone Is

Port OmniGraph's **read-side surfaces** (KB site + storage + Q&A) to run inside
**Databricks Workspace** as an internal preview, while keeping the ingest pipeline
on Hermes. Deliver a deployable Databricks-native v1 without repeating the
Hermes-style "1-day basic E2E + 2-week wall-chasing" debug loop.

Three things move to Databricks in v1:

1. **Storage** — `data/kol_scan.db` (SQLite file) + images + LightRAG storage all
   land on UC Volume `mdlg_ai_shared.kb_v2.omnigraph_vault` (managed)
2. **KB site** — FastAPI + Jinja2 SSG (per KB-v2 D-08) deployed as a Databricks App
   `omnigraph-kb`, reading from the UC Volume
3. **Q&A endpoint** — `/synthesize` exposed as in-App FastAPI route, reusing
   `kg_synthesize.synthesize_response()`, LLM provider remains DeepSeek (injected
   as Databricks workspace secret)

Plus one mechanism: **Hermes → UC Volume sync** (manual user-driven `databricks fs cp`
for v1; automated sync deferred).

## Goal

把 OmniGraph 的读端(KB 站 + 存储 + Q&A)整体搬进 Databricks Workspace,作为 EDC
内部预览。Ingest pipeline 留在 Hermes 上;Databricks 只读 UC Volume,不再依赖
Hermes 的 systemd / cron / SSH。**v1 = 上线一个内部团队能在浏览器里点开看的 KB**,
不解决 Hermes 退役、不切 LLM provider、不动 kb/ 主分支代码。

最重要的是不要重蹈 Hermes 部署的覆辙 —— 基础 E2E 1 天跑通,timeout/quota/auth
撞墙调 2 周。本 milestone 起手做 4 个 parallel research 把已知未知问题前置摸清楚。

## Locked Architectural Choices (do NOT re-discuss)

These 9 defaults are locked from the 2026-05-14 setup conversation and apply to
every phase in this milestone.

| # | Slot | Locked value | Rationale |
|---|------|--------------|-----------|
| 1 | UC catalog | `mdlg_ai_shared` | EDC workspace existing catalog |
| 2 | UC schema | `kb_v2` (to be created in kdb-1) | Matches sibling-style naming (`aicoe_genai_dasf`, `aicoe_spec_map`) |
| 3 | UC volume | `omnigraph_vault` (managed) | Mirrors Hermes `~/.hermes/omonigraph-vault/` (typo NOT carried — fresh env) |
| 4 | Volume layout | `/data/kol_scan.db` · `/images/{hash}/...` · `/lightrag_storage/...` · `/output/...` | 4 data classes, 1 Volume, sub-directory separation |
| 5 | Apps app name | `omnigraph-kb` | — |
| 6 | App auth → UC | App Service Principal — Apps runtime auto-injects `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`; `WorkspaceClient()` default config picks them up | v1 single-tenant: every internal user sees the same KB; no per-user filtering. OBO `X-Forwarded-Access-Token` deferred to v2 (audit) |
| 7 | App port | `:8080` (`os.getenv("DATABRICKS_APP_PORT")`) | Apps runtime hardcoded; `:8766` cannot be used inside Apps |
| 8 | LLM provider for Q&A | DeepSeek (status quo) — `DEEPSEEK_API_KEY` injected as Databricks workspace secret + `app.yml` `valueFrom: secretKeyRef` | Foundation Model `databricks-claude-sonnet-4-6` swap bundled into v2 with ingest-LLM swap |
| 9 | Hermes → UC sync strategy | Manual user-driven (user runs `databricks fs cp` from Windows dev with local Hermes-pulled snapshot) | Automated sync deferred to v2; v1 accepts "snapshot-style refresh, user pushes when they want" |

### Additional v1 constraints (not part of the 9, but binding)

- **App user authentication** — workspace SSO, internal preview only. Public access
  (zero-login) is Aliyun's job (KB-v2 / kb-4), not this milestone's
- **Secrets never in commit** — `DEEPSEEK_API_KEY` lives in a Databricks workspace
  secret scope (`databricks secrets create-scope` + `databricks secrets put-secret`).
  `app.yml` references via `valueFrom: secretKeyRef`. **Zero literal tokens in any
  commit.** Memory `feedback_no_literal_secrets_in_prompts.md` captures the prior
  Hermes incident; same rule applies here
- **Cross-milestone contracts read-only** — KB-v2 contracts C1
  (`kg_synthesize.synthesize_response()`) and C2 (`omnigraph_search.query.search()`)
  signatures are NOT touched by this milestone
- **Zero `kb/` code changes** — v1 ships purely via env var + deploy config:
  `OMNIGRAPH_BASE_DIR=/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` + `app.yml`. If kdb-2
  reveals a code change is needed, that's a deviation requiring approval, not
  silently absorbed

## Out of Scope (v1)

| Item | Why excluded | Tracked for |
|------|--------------|-------------|
| **SQLite → Delta migration** | SQLite is a file, not a table. Migrating to Delta = rewriting every SQL query in `kb/`, `omnigraph_search/`, `kg_synthesize.py`. Months of work. v1 keeps SQLite on UC Volume as a file | v2+ (only if a concrete pain point materializes — likely never) |
| **Foundation Model `databricks-claude-sonnet-4-6` swap** | Bundled with the ingest-LLM swap in v2 — both Q&A and ingest LLMs cut over together for consistency | v2 |
| **Automated Hermes → UC Volume sync** | Manual is fine for internal preview. Automation needs sync orchestration design (push from Hermes? pull from Databricks Workflow? incremental? full refresh?) — explicit v2 design phase | v2 |
| **Public access / zero-login KB on Databricks** | Apps gates on workspace SSO. Public access happens on the Aliyun deploy (KB-v2 / kb-4) | KB-v2 (Aliyun) |
| **Hermes sunset** | Ingest pipeline stays on Hermes; Hermes remains the upstream writer | Maybe v2/v3, maybe never |
| **Ingest pipeline on Databricks** | Daily ingest = scheduled work + LLM + scrape; Databricks Apps cannot run scheduled scripts (would need Workflows + Jobs, plus migrating Apify/CDP/Vision providers). Big lift, separate milestone | Future (`kb-ingest-databricks-vN`) |
| **Per-user OBO auth** | All v1 users see same KB; no row filtering. v2 if we add private documents | v2 |
| **Ingest-side LightRAG `ainsert()` to UC Volume** | Requires Hermes to mount UC Volume (auth + driver) — risky. v1 keeps ainsert on Hermes local fs, then user `databricks fs cp` snapshot up | v2 |

## Cross-Milestone Contracts (read-only consumer)

This milestone is a **pure consumer** of the following contracts. No signature changes.

| # | Contract | Provider milestone | Status |
|---|----------|-------------------|--------|
| **C1** | `kg_synthesize.synthesize_response(query_text: str, mode: str = "hybrid")` | KB-v2 | Read-only |
| **C2** | `omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` | KB-v2 | Read-only |
| **C3** | `kol_scan.db` schema (`articles` / `classifications` / `extracted_entities` / `entity_canonical` / `ingestions` / `rss_articles`) | OmniGraph main + KB-v2 | Read-only file consumer |
| **C4** | `images/{hash}/final_content.md` + `metadata.json` | OmniGraph main | Read-only file consumer |

All four contracts ship via the SQLite file + filesystem snapshot copied to UC Volume.
KB-v2 deploy on Aliyun (kb-4) reads the same SQLite + filesystem from local disk.
Same code, two deploy targets — verified by the "zero `kb/` code changes" constraint.

## Smoke Test (acceptance criterion)

3 manual scenarios run after kdb-3 closes:

### Smoke 1 — App is reachable + reads UC Volume

1. Browser visits the Databricks Apps URL for `omnigraph-kb` → workspace SSO prompt
2. After SSO → KB home page renders (article count > 0, topic chips visible)
3. App logs (`/Workspace/Users/.../logs/`) show `OMNIGRAPH_BASE_DIR=/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` and successful SQLite open / image-mount
4. Apps "Logs" tab in Databricks UI shows zero ERROR entries during cold start

### Smoke 2 — Search + article detail end-to-end

1. Search "AI Agent" → ≥ 3 hits in zh-CN UI
2. Switch UI to en → search "langchain" → ≥ 3 hits
3. Click any article → detail page renders title + body + images (images served
   from UC Volume via in-App static handler, NOT `localhost:8765`)
4. Article metadata (title, lang badge, og:image) all correct

### Smoke 3 — RAG Q&A round-trip + DeepSeek secret confirmation

1. Submit Q&A "What is LangGraph?" → async returns markdown answer + sources
2. App logs show DeepSeek call succeeded (no `KeyError: 'DEEPSEEK_API_KEY'`,
   no 401 from `api.deepseek.com`)
3. `app.yml` is committed with `valueFrom: secretKeyRef` (NOT literal token) —
   `git log -p app.yml` shows zero literal `sk-` strings ever
4. Workspace secret scope `omnigraph-kb` exists with key `DEEPSEEK_API_KEY` set
5. (Negative path) Stop LightRAG / break storage path → `/synthesize` returns
   FTS5-fallback markdown with `confidence: "fts5_fallback"`, NOT 500 (KB-v2 D-19
   contract preserved across deploy targets)

**Pass conditions** (all must hold):
- 3 smoke scenarios PASS
- Manual sync round-trip works: user runs `databricks fs cp` from Windows dev,
  re-deploys (or App auto-picks up new files), refreshed article appears in App
- Zero `kb/` source-tree edits in the kb-databricks-v1 commit history
  (`git log --name-only kb/ -- 'main..HEAD'` shows nothing in `kb/`)
- Zero literal `DEEPSEEK_API_KEY` value in any commit (audit:
  `git log -p | grep -E 'sk-[a-zA-Z0-9]{20,}'` returns empty)

## Tech Stack (additions only)

Existing: see main `PROJECT.md` and `PROJECT-KB-v2.md`.

**New tooling for this milestone:**

- Databricks CLI (already installed on dev box per CLAUDE.md)
- Databricks Apps runtime (Python 3.11 base image, FastAPI compatible)
- `databricks-sdk` (Python) — for any UC Volume programmatic access; `WorkspaceClient()`
  picks up Apps-injected service principal credentials
- `databricks fs cp` for manual sync

**No new Python deps in `requirements.txt`.** The KB-v2 stack (FastAPI, uvicorn,
Jinja2, markdown, pygments, etc.) ships unchanged.

## File Pattern (parallel-track convention)

Following the KB-v2 / Agentic-RAG-v1 / v3.5-Ingest-Refactor parallel-track precedent:

```
.planning/
├── PROJECT-kb-databricks-v1.md       (this file)
├── REQUIREMENTS-kb-databricks-v1.md  (next: gathered in Step 9)
├── ROADMAP-kb-databricks-v1.md       (next: spawned by gsd-roadmapper in Step 10)
├── STATE-kb-databricks-v1.md         (this commit: initial scaffold)
└── phases/
    ├── kdb-1-uc-volume-and-data-snapshot/
    ├── kdb-2-databricks-app-deploy/
    └── kdb-3-uat-and-close/
```

Main `PROJECT.md` / `REQUIREMENTS.md` / `ROADMAP.md` / `STATE.md` are owned by
v3.4 / v3.5 main track. **Untouched by this milestone.**

Per `feedback_parallel_track_gates_manual_run.md`: `gsd-tools.cjs init` does NOT
parse suffix files — orchestrator hand-drives every gate (UI Design Contract Gate,
Nyquist, Coverage). No silent skips allowed.

## Phase Numbering

kb-databricks-v1 phases use **`kdb-N-*` prefix**, decoupled from `phase-NN` (main),
`kb-N-*` (KB-v2), `ir-N-*` (v3.5), `ar-N-*` (Agentic-RAG-v1).

```
kdb-1 → UC Volume create + initial Hermes snapshot upload + manual sync runbook
kdb-2 → omnigraph-kb Databricks App deploy (app.yml + secret scope + smoke 1+2)
kdb-3 → UAT close (smoke 3 RAG round-trip + secret audit + sign-off)
```

**Conditional kdb-1.5** — if STACK / FEATURES research surfaces that LightRAG
`working_dir=/Volumes/...` is **not** compatible with cloud storage (FUSE mount
limitations, locking semantics, fsync contract, sqlite WAL on Volume etc.), we
insert `kdb-1.5-lightrag-storage-adapter` between kdb-1 and kdb-2 to cache /
snapshot LightRAG state to App-local `/tmp` at startup. Otherwise stays at 3 phases.

T-shirt size: **S** (1–2 days end-to-end, assuming research closes the LightRAG
uncertainty cheaply).

## Future Milestones (after kb-databricks-v1)

Direction-only, not scheduled:

- **v2 — Foundation Model + ingest-LLM swap** — DeepSeek → `databricks-claude-sonnet-4-6`
  for both Q&A and ingest paths, single cutover
- **v2 — Automated Hermes → UC Volume sync** — design phase + Workflow / Job
  implementation; replaces manual `databricks fs cp`
- **v2 — Per-user OBO auth** — `X-Forwarded-Access-Token` integration if we add
  private documents
- **v3 — Ingest pipeline on Databricks** — separate milestone, daily-ingest cron
  → Workflow + Jobs, scrape providers re-evaluated for Apps runtime constraints
- **v3 — Hermes sunset** — only if v3 ingest ships and is stable

## Last Updated

2026-05-14 — Milestone initialized via `/gsd:new-milestone kb-databricks-v1`.
9 architectural defaults locked in setup conversation. 4 parallel research agents
spawned next (STACK / FEATURES / ARCHITECTURE / PITFALLS) before requirements.
