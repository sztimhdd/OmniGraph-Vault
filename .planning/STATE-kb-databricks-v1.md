# STATE — kb-databricks-v1

> Parallel-track state file. Main `STATE.md` belongs to v3.4 / v3.5 main track.
> Sibling state files: `STATE-KB-v2.md`, `STATE-Agentic-RAG-v1.md`,
> `STATE-v3.5-Ingest-Refactor.md`. **Untouched by this milestone.**

## Current Position

- **Milestone:** kb-databricks-v1 (parallel track)
- **Phase:** Not started — defining requirements
- **Plan:** —
- **Status:** Milestone scaffold landed; 4 research agents to spawn next
- **Last activity:** 2026-05-14 — milestone initialized via `/gsd:new-milestone kb-databricks-v1`

## Locked Defaults (snapshot, full table in PROJECT-kb-databricks-v1.md)

| # | Slot | Locked value |
|---|------|--------------|
| 1 | UC catalog | `mdlg_ai_shared` (live; old `mdlg_ai` decommissioned 2026-02-05) |
| 2 | UC schema | `kb_v2` (to be created in kdb-1) |
| 3 | UC volume | `omnigraph_vault` (managed) |
| 4 | Volume layout | `/data/kol_scan.db` · `/images/{hash}/...` · `/lightrag_storage/...` · `/output/...` |
| 5 | Apps app name | `omnigraph-kb` |
| 6 | App auth → UC | App Service Principal (Apps runtime auto-injects credentials) |
| 7 | App port | `:8080` (Apps runtime hardcoded) |
| 8 | Q&A LLM | DeepSeek (status quo); workspace secret + `valueFrom: secretKeyRef` |
| 9 | Hermes → UC sync | Manual `databricks fs cp` from Windows dev (v1) |

## Next Step

`/gsd:plan-phase kdb-1` — but only after:

1. Research phase completes (4 parallel agents → SUMMARY.md)
2. REQUIREMENTS-kb-databricks-v1.md gathered + scoped
3. ROADMAP-kb-databricks-v1.md created (3 phases default; conditional kdb-1.5
   if LightRAG `working_dir=/Volumes/...` incompatibility surfaces)

## Pending Research (about to spawn)

| Agent | Focus | Output |
|-------|-------|--------|
| STACK | Databricks Apps runtime constraints, `app.yml` `secretKeyRef` syntax, secret scope CLI steps, Python deps, Apps-injected env vars | `.planning/research/kb-databricks-v1/STACK.md` |
| FEATURES | LightRAG `working_dir=/Volumes/...` cloud-storage compatibility (PRIMARY UNCERTAINTY), UC Volume vs Delta for binary blobs, SQLite WAL on Volume, FUSE mount semantics | `.planning/research/kb-databricks-v1/FEATURES.md` |
| ARCHITECTURE | Hermes → UC Volume sync options (3 alternatives with tradeoffs); App service principal ↔ UC Volume read flow; in-App static file serving from `/Volumes/...` | `.planning/research/kb-databricks-v1/ARCHITECTURE.md` |
| PITFALLS | Common Apps deploy traps (cold start, port binding, request timeouts, log access); secret-leak failure modes; quota/auth foot-guns | `.planning/research/kb-databricks-v1/PITFALLS.md` |

After all 4 complete: synthesizer agent → `SUMMARY.md`.

## Constraints in Force

- **Cross-milestone contracts read-only** — KB-v2 C1 / C2 signatures untouched
- **Zero `kb/` code changes** — v1 ships purely via env var + `app.yml`
- **Zero literal secrets in any commit** — `DEEPSEEK_API_KEY` via Databricks
  workspace secret scope + `valueFrom: secretKeyRef` only
- **Parallel-track tooling caveat** (memory `feedback_parallel_track_gates_manual_run.md`):
  `gsd-tools.cjs init` does NOT recognize suffix files. Orchestrator hand-drives
  every gate (UI Design Contract, Nyquist, Coverage). No silent skips
- **Subagent web-tool caveat** (CLAUDE.md): Databricks proxy strips `tool_reference`
  blocks; subagents cannot call `mcp__context7__*` or `mcp__brave-search__*`.
  Main session pulls context7 docs upfront → researchers consume via `<files_to_read>`

## Accumulated Context

- KB-v2 milestone (sibling) is mid-flight: kb-1 closed 2026-05-13, kb-2 in flight
  via quick `260514-d3p` (Aliyun deploy). kb-databricks-v1 deliberately does NOT
  block on KB-v2 closure — Databricks deploy reads the same artifacts KB-v2
  produces; both deploy targets (Aliyun public, Databricks internal-preview)
  consume identical `kb/` source
- OmniGraph v1.0 declared 2026-05-13 (Knowledge Collection + Ingestion). Ingest
  pipeline is stable; daily-ingest cron continues on Hermes throughout this
  milestone. No Hermes changes required for kb-databricks-v1
- DBX workspace: `https://adb-2717931942638877.17.azuredatabricks.net`
- DBX CLI profile: `dev` (in `~/.databrickscfg`), default warehouse `eaa098820703bf5f`
- User has Windows dev box with Databricks Connect + OAuth login + PAT configured
