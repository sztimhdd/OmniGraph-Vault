# OmniGraph-Vault — Parallel Milestone: kb-databricks-v1

> Sibling milestone running parallel to v3.4 (closed) / v3.5 (Ingest Refactor) /
> Agentic-RAG-v1 / KB-v2.
> Main project context lives in `PROJECT.md`. This file scopes kb-databricks-v1 only.
> Phase directories use the `kdb-N-*` prefix to avoid collision with other milestones.
>
> **rev 3 — strategic restructure 2026-05-15.** All LLM + embedding traffic moves to
> Databricks MosaicAI Model Serving. Databricks deploy is a fully self-contained
> system with no Hermes runtime dependency. See "rev 3 changes" below for delta.

## What This Milestone Is

Port OmniGraph's **read-side surfaces** (KB site + storage + Q&A) to run inside
**Databricks Workspace** as an internal preview, **fully decoupled from Hermes** —
Databricks operates as its own self-contained system after the initial seed.
Deliver a deployable Databricks-native v1 without repeating the Hermes-style
"1-day basic E2E + 2-week wall-chasing" debug loop.

Three things move to Databricks in v1:

1. **Storage** — `data/kol_scan.db` (SQLite file) + images + LightRAG storage all
   land on UC Volume `mdlg_ai_shared.kb_v2.omnigraph_vault` (managed). Article DB
   + images SCP'd from Hermes ONCE at v1 setup. LightRAG storage **re-indexed in
   Databricks** with MosaicAI Qwen3 embedding (the original Hermes LightRAG storage
   was Vertex/Gemini-indexed; embedding spaces are incompatible)
2. **KB site** — FastAPI + Jinja2 SSG (per KB-v2 D-08) deployed as a Databricks App
   `omnigraph-kb`, reading from the UC Volume, **all LLM + embedding via MosaicAI**
3. **Q&A endpoint** — `/synthesize` exposed as in-App FastAPI route, reusing
   `kg_synthesize.synthesize_response()` (with `kb/` exemption: `lib/llm_complete.py`
   + `kg_synthesize.py` extended for `databricks_serving` provider — see
   CONFIG-EXEMPTIONS.md)

**No ongoing Hermes ↔ Databricks sync.** v1 is "seeded once, runs independently".
Future incremental data updates = v2+ work (own ingest pipeline OR re-seed).

## Goal

把 OmniGraph 的读端(KB 站 + 存储 + Q&A)整体搬进 Databricks Workspace,作为 EDC
内部预览。**Databricks 是完全自包含的独立系统,不依赖 Hermes 任何 runtime 资源**。
只在 v1 setup 一次性 SCP 文章 + 图片 + DB(seed),然后 Databricks 内部跑 LightRAG
re-index Job 重建 KG storage 用 MosaicAI 模型。

**v1 = 上线一个内部团队能在浏览器里点开看的 KB**,LLM + embedding 全部走 MosaicAI
Model Serving。允许动 `lib/llm_complete.py` 和 `kg_synthesize.py` 接 dispatcher
(CONFIG-EXEMPTIONS.md 记录),其他 `kb/` 仍坚持零改动。

最重要的是不要重蹈 Hermes 部署的覆辙 —— 基础 E2E 1 天跑通,timeout/quota/auth
撞墙调 2 周。本 milestone 起手做 4 个 parallel research(已完成)+ kdb-1 Wave 1
PREFLIGHT 把 Model Serving + UC grant 高风险问题前置。

## Locked Architectural Choices (do NOT re-discuss)

These 9 defaults are locked. **rev 3 updates #8 + #9** to MosaicAI / one-time seed.

| # | Slot | Locked value | Rationale |
|---|------|--------------|-----------|
| 1 | UC catalog | `mdlg_ai_shared` | EDC workspace existing catalog |
| 2 | UC schema | `kb_v2` (to be created in kdb-1) | Matches sibling-style naming (`aicoe_genai_dasf`, `aicoe_spec_map`) |
| 3 | UC volume | `omnigraph_vault` (managed) | Mirrors Hermes `~/.hermes/omonigraph-vault/` (typo NOT carried — fresh env) |
| 4 | Volume layout | `/data/kol_scan.db` · `/images/{hash}/...` · `/lightrag_storage/...` · `/output/...` | 4 data classes, 1 Volume, sub-directory separation |
| 5 | Apps app name | `omnigraph-kb` | — |
| 6 | App auth → UC + Model Serving | App Service Principal — Apps runtime auto-injects `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`; `WorkspaceClient()` default config picks them up. **No external secret scope needed for LLM** (MosaicAI auth uses same SP) | v1 single-tenant: every internal user sees the same KB; no per-user filtering. OBO `X-Forwarded-Access-Token` deferred to v2 (audit) |
| 7 | App port | `:8080` (`os.getenv("DATABRICKS_APP_PORT")`) | Apps runtime hardcoded; `:8766` cannot be used inside Apps |
| **8** | **LLM + embedding provider** (rev 3) | **MosaicAI Model Serving via Databricks SDK** — synthesis: `databricks-claude-sonnet-4-6`; embedding: `databricks-qwen3-embedding-0-6b` (中英双语友好,优于 BGE/GTE 的英文优化版) | Replaces rev 2.x DeepSeek lock. EDC constraint: all LLM via MosaicAI internal endpoints. No external API keys |
| **9** | **Hermes ↔ Databricks sync** (rev 3) | **One-time seed only** — user SCPs Hermes `data/kol_scan.db` + `images/` to UC Volume during kdb-1; LightRAG storage re-indexed in Databricks Job (kdb-2.5). **No ongoing sync**. v2+ owns whether to add fresh-data flow | Replaces rev 2.x "manual ongoing `databricks fs cp` per refresh". User explicit: Databricks doesn't depend on Hermes runtime |

### Additional v1 constraints (not part of the 9, but binding)

- **App user authentication** — workspace SSO, internal preview only. Public access
  (zero-login) is Aliyun's job (KB-v2 / kb-4), not this milestone's
- **Secrets never in commit** — Apps SP auto-injection covers Model Serving auth;
  no API key needs to leave the workspace. Memory `feedback_no_literal_secrets_in_prompts.md`
  captures the prior Hermes incident; same rule applies here
- **Cross-milestone contracts read-only** — KB-v2 contracts C1
  (`kg_synthesize.synthesize_response()`) and C2 (`omnigraph_search.query.search()`)
  signatures are NOT touched. Internal call dispatching to a different LLM provider
  is implementation, not contract change
- **Zero `kb/` code changes EXCEPT** `lib/llm_complete.py` + `kg_synthesize.py`
  (provider dispatcher integration) — **explicit exemption recorded in
  `databricks-deploy/CONFIG-EXEMPTIONS.md`**. C1/C2 signatures still read-only;
  what changes is the underlying provider dispatch. Rev 2.x's "zero kb/ touches"
  is relaxed here because LLM+embedding swap requires it. Other kb/ paths remain
  read-only

## Out of Scope (v1)

| Item | Why excluded | Tracked for |
|------|--------------|-------------|
| **SQLite → Delta migration** | SQLite is a file, not a table. Migrating to Delta = rewriting every SQL query in `kb/`, `omnigraph_search/`, `kg_synthesize.py`. Months of work. v1 keeps SQLite on UC Volume as a file | v2+ (only if a concrete pain point materializes — likely never) |
| **Hermes sunset** | Ingest pipeline stays on Hermes; Hermes remains the upstream writer for ITS OWN data. v1 just decouples Databricks from Hermes (no read-side dependency) — Hermes continues serving Aliyun KB | Maybe v2/v3, maybe never |
| **Ongoing Hermes → UC Volume sync** | v1 is "seed once, run independently". Adding fresh data later = re-seed manually OR design a sync mechanism in v2. Either way, not v1 | v2+ (design phase before implementation) |
| **Ingest pipeline on Databricks** | Daily ingest = scheduled work + LLM + scrape; Databricks Apps cannot run scheduled scripts (would need Workflows + Jobs, plus migrating Apify/CDP/Vision providers). Big lift, separate milestone | Future (`kb-ingest-databricks-vN`) |
| **Public access / zero-login KB on Databricks** | Apps gates on workspace SSO. Public access happens on the Aliyun deploy (KB-v2 / kb-4) | KB-v2 (Aliyun) |
| **Per-user OBO auth** | All v1 users see same KB; no row filtering. v2 if we add private documents | v2 |
| **Ingest-side LightRAG `ainsert()` to UC Volume from Hermes** | Hermes does NOT mount UC Volume. v1 SCP's the seed; v2+ decides if Hermes ever pushes to UC | v2+ |
| **Apps horizontal scaling / multi-instance** | Single instance. LightRAG `write_json` is non-atomic (verified `lightrag/utils.py:1255`); concurrent writes risk corruption. v1 doesn't scale-out | v2 (atomic write_json upstream patch OR adapter pattern) |
| **DeepSeek / SiliconFlow as LLM providers** | EDC constraint: all LLM via MosaicAI Model Serving. v1 ships with MosaicAI from day 1 (rev 3 strategic shift) | Out permanently for Databricks deploy |

## Cross-Milestone Contracts (read-only consumer)

This milestone is a **pure consumer** of the following contracts. C1/C2 signatures
are read-only. Implementation INSIDE the wrappers (which provider dispatched to)
is allowed to change per CONFIG-EXEMPTIONS.md.

| # | Contract | Provider milestone | Status |
|---|----------|-------------------|--------|
| **C1** | `kg_synthesize.synthesize_response(query_text: str, mode: str = "hybrid")` | KB-v2 | Signature read-only; internal LLM provider switches to MosaicAI |
| **C2** | `omnigraph_search.query.search(query_text: str, mode: str = "hybrid") -> str` | KB-v2 | Signature read-only |
| **C3** | `kol_scan.db` schema (`articles` / `classifications` / `extracted_entities` / `entity_canonical` / `ingestions` / `rss_articles`) | OmniGraph main + KB-v2 | Read-only file consumer |
| **C4** | `images/{hash}/final_content.md` + `metadata.json` | OmniGraph main | Read-only file consumer |

C3/C4 ship via the SQLite file + filesystem snapshot copied to UC Volume.
KB-v2 deploy on Aliyun (kb-4) reads the same SQLite + filesystem from local disk.
Same `kb/` source mostly — only `lib/llm_complete.py` + `kg_synthesize.py` get the
`databricks_serving` provider branch (LightRAG instantiation in App startup).

## Smoke Test (acceptance criterion)

3 manual scenarios run after kdb-3 closes. Mirrors KB-v2 PROJECT.md Smoke 1/2/3
verbatim where possible — same `kb/` codebase serves Aliyun + Databricks,
user-flow tests are identical:

### Smoke 1 — App is reachable + reads UC Volume

1. Browser visits the Databricks Apps URL for `omnigraph-kb` → workspace SSO prompt
2. After SSO → KB home page renders (article count > 0, topic chips visible)
3. App logs (`/Workspace/Users/.../logs/`) show `OMNIGRAPH_BASE_DIR=/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault` and successful SQLite open / image-mount
4. Apps "Logs" tab in Databricks UI shows zero ERROR entries during cold start

### Smoke 2 — Search + article detail end-to-end (KB-v2 Smoke 2 verbatim)

1. Search "AI Agent" → ≥ 3 hits in zh-CN UI
2. Switch UI to en → search "langchain framework" → ≥ 3 hits in en articles
3. Click any English article → detail page renders `<html lang="en">` + 标"English" badge + 内容原文(英文)+ images load via UC Volume `/static/img/...`
4. Click any Chinese article → detail page renders `<html lang="zh-CN">` + 标"中文" badge
5. og:image / og:title metadata correct (sharing renders preview)

### Smoke 3 — RAG Q&A round-trip + MosaicAI Model Serving confirmation

1. Submit "LangGraph 和 CrewAI 有什么区别?" (zh) → async returns Chinese markdown answer + sources
2. Submit "What is the difference between LangGraph and CrewAI?" (en) → async returns English markdown answer + sources
3. App logs show MosaicAI Model Serving call succeeded (HTTP 200 from Apps internal Model Serving endpoint; LLM = `databricks-claude-sonnet-4-6`; embedding = `databricks-qwen3-embedding-0-6b`)
4. (Negative path 1) Stop / break LightRAG storage path → `/synthesize` returns FTS5-fallback markdown with `confidence: "fts5_fallback"`, NOT 500 (KB-v2 D-19 contract preserved)
5. (Negative path 2 — kg_unavailable) Misconfigure Model Serving endpoint name → `kg_synthesize` short-circuits to `_fts5_fallback` BEFORE LightRAG init, NEVER 500 (kb-v2.1-1 KG hardening pattern preserved)

**Pass conditions** (all must hold):
- 3 smoke scenarios PASS
- Re-index Job (kdb-2.5) completed successfully — UC Volume `/lightrag_storage/` populated with MosaicAI-Qwen3-indexed graphml + nano-vector-db json
- Zero `kb/` source-tree edits in the kb-databricks-v1 commit history EXCEPT documented exemptions (`lib/llm_complete.py` + `kg_synthesize.py` — listed in `databricks-deploy/CONFIG-EXEMPTIONS.md`)
  - Audit: `git log --name-only kb/ -- 'main..HEAD'` excluding lib/ + kg_synthesize.py shows nothing
- Zero literal API token (no `sk-...` etc.) in any commit (audit: `git log -p databricks-deploy/ | grep -E 'sk-[a-zA-Z0-9]{20,}'` returns empty). MosaicAI uses Apps SP auto-injection, no external keys

## Tech Stack (additions only)

Existing: see main `PROJECT.md` and `PROJECT-KB-v2.md`.

**New tooling for this milestone:**

- Databricks CLI (already installed on dev box per CLAUDE.md)
- Databricks Apps runtime (Python 3.11 base image, FastAPI compatible)
- `databricks-sdk` (Python) — for UC Volume + Model Serving access; `WorkspaceClient()`
  picks up Apps-injected service principal credentials
- `databricks fs cp` for **one-time seed only** (Hermes → UC Volume, kdb-1 step)
- Databricks Job for **kdb-2.5 re-index** (LightRAG ainsert with MosaicAI provider)

**Python deps additions to `databricks-deploy/requirements.txt`:**

- `databricks-sdk` (for Model Serving SDK calls)
- All KB-v2 stack ships unchanged (FastAPI, uvicorn, Jinja2, markdown, pygments, lightrag, etc.)

## File Pattern (parallel-track convention)

Following the KB-v2 / Agentic-RAG-v1 / v3.5-Ingest-Refactor parallel-track precedent:

```
.planning/
├── PROJECT-kb-databricks-v1.md       (this file)
├── REQUIREMENTS-kb-databricks-v1.md  (rev 3)
├── ROADMAP-kb-databricks-v1.md       (rev 3)
├── STATE-kb-databricks-v1.md         (rev 3, milestone-base hash locked)
└── phases/
    ├── kdb-1-uc-volume-and-data-snapshot/
    ├── kdb-1.5-lightrag-storage-adapter/  (conditional)
    ├── kdb-2-databricks-app-deploy/
    ├── kdb-2.5-lightrag-reindex/           (NEW in rev 3)
    └── kdb-3-uat-and-close/

databricks-deploy/
├── app.yaml
├── requirements.txt
├── lightrag_databricks_provider.py        (NEW: LightRAG ↔ MosaicAI adapter)
├── CONFIG-EXEMPTIONS.md                   (NEW: documents kb/ + lib/ exemptions)
├── Makefile                               (deploy / logs / stop recipes)
└── RUNBOOK.md                             (operator instructions)
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
kdb-1   PREFLIGHT (Model Serving query smoke + UC grant capability) + UC schema/volume/seed
        — half day; gates everything else; PREFLIGHT ❌ blocks milestone

kdb-1.5 LightRAG ↔ Databricks SDK provider adapter spike (conditional)
        — 30-min hard timer; trigger if SPIKE 01a-01e ❌ or INCONCLUSIVE

kdb-2   omnigraph-kb Databricks App deploy (app.yaml + Apps SP grants + Smoke 1+2)
        — half day; Smoke 1+2 PASS gate

kdb-2.5 ⭐NEW: Re-index LightRAG storage with MosaicAI Qwen3 embedding (Databricks Job)
        — half day - 1 day Job time; ~$20-100 Model Serving cost
        — One-shot v1 step; NOT v2 ingest migration
        — UC Volume /lightrag_storage/ populated with MosaicAI-indexed state

kdb-3   UAT close (Smoke 3 + audits + RUNBOOK + sign-off)
        — half day
```

T-shirt size: **M** (rev 3 — kdb-2.5 re-index Job time pushes from rev 2's S to M).

## Future Milestones (after kb-databricks-v1)

Direction-only, not scheduled:

- **v2 — Automated Hermes → UC Volume sync** — design phase + Workflow / Job
  implementation; replaces one-time seed if recurring data refresh is wanted
- **v2 — Per-user OBO auth** — `X-Forwarded-Access-Token` integration if we add
  private documents
- **v2 — Atomic LightRAG write_json** — upstream patch OR adapter pattern;
  needed only if App ever writes to Volume
- **v3 — Ingest pipeline on Databricks** — separate milestone, daily-ingest cron
  → Workflow + Jobs, scrape providers re-evaluated for Apps runtime constraints
- **v3 — Hermes sunset** — only if v3 ingest ships and is stable

## Last Updated

2026-05-15 (rev 3) — **Strategic restructure** absorbing user constraints:
all LLM + embedding via MosaicAI (DeepSeek + Vertex/Gemini retired);
Databricks fully self-contained from Hermes (no ongoing sync; v1 = one-time seed);
LLM-DBX + SEED-DBX categories added in REQ rev 3; new conditional phase
kdb-2.5 re-index Job; t-shirt S → M. Locked defaults #8 (LLM provider) and
#9 (Hermes sync) updated. "Zero kb/ changes" rule relaxed for `lib/llm_complete.py`
+ `kg_synthesize.py` provider dispatcher (CONFIG-EXEMPTIONS.md). Removed
"FM swap to Databricks" from future requirements (now v1 in-scope). Removed
"DeepSeek secret scope" from acceptance criteria. Smoke 3 verifies MosaicAI
Model Serving call instead of `api.deepseek.com`. Aligned with REQ + ROADMAP
+ STATE rev 3 (commits `cfe47b4` + `f4248cc`).

2026-05-15 (rev 2.2) — Absorb kb-v2.1-1 KG MODE HARDENING (KG_MODE_AVAILABLE
flag pattern; kdb-1.5 trigger threshold raised — kdb-1 spike materially less
stake-y).

2026-05-15 (rev 2.1) — Doc self-consistency cleanup (30→36 REQ count fixes;
risks #2 #3 mitigations now reference PREFLIGHT-DBX-01/02 closure path).

2026-05-15 (rev 2) — User P0/P1/P2 adjustments: SPIKE split into 5 sub-items,
new PREFLIGHT category, DEPLOY-07/08, OPS verbatim KB-v2 smokes, etc.

2026-05-14 — Milestone initialized via `/gsd:new-milestone kb-databricks-v1`.
9 architectural defaults locked in setup conversation. 4 parallel research agents
spawned (STACK / FEATURES / ARCHITECTURE / PITFALLS) before requirements.
