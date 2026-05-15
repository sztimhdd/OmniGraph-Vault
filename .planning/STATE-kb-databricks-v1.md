# STATE — kb-databricks-v1

> Parallel-track state file. Main `STATE.md` belongs to v3.4 / v3.5 main track.
> Sibling state files: `STATE-KB-v2.md`, `STATE-Agentic-RAG-v1.md`,
> `STATE-v3.5-Ingest-Refactor.md`. **Untouched by this milestone.**

## Current Position

- **Milestone:** kb-databricks-v1 (parallel track)
- **Phase:** Not started — REQ + ROADMAP rev 2 ready, awaiting user approval
- **Plan:** —
- **Status:** REQUIREMENTS-kb-databricks-v1.md + ROADMAP-kb-databricks-v1.md rev 2 (incorporates user P0/P1/P2 adjustments)
- **Last activity:** 2026-05-15 — REQ + ROADMAP rev 2 committed; 36 REQs / 10 categories / 3-4 phases

## Milestone-base commit hash (LOCKED)

**`7df6e5b`** — `docs(kb-databricks-v1): REQ (30 across 9 cats) + ROADMAP (3 phases + conditional kdb-1.5)`

This is the anchor for **CONFIG-DBX-01** ("zero `kb/` source-tree edits across this milestone"). At kdb-3 close, verify with:

```bash
git log 7df6e5b..HEAD --grep '(kdb-' --name-only -- kb/
# Expected: empty output
```

The `--grep '(kdb-'` filter scopes the diff to this milestone's commits only. Unrelated kb-v2.1 / kb-4 / debug commits authored after `7df6e5b` are ignored — those belong to other tracks and don't violate kb-databricks-v1's "zero kb/ edits" invariant.

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

REQ + ROADMAP rev 2 await user approval. After approval: `/gsd:plan-phase kdb-1`.

Status of upstream artifacts:
- ✅ PROJECT-kb-databricks-v1.md (committed `88ba32a`)
- ✅ Research (4 dimensions + SUMMARY, committed `406c2d0`)
- ✅ REQUIREMENTS-kb-databricks-v1.md rev 2 (committed `0b06395`, 36 REQs / 10 categories)
- ✅ ROADMAP-kb-databricks-v1.md rev 2 (committed `0b06395`, 3 phases + conditional kdb-1.5, kdb-1 waved)
- ⏳ User approval gate
- ⏳ `/gsd:plan-phase kdb-1` (Wave 1 PREFLIGHT first)

## Research (COMPLETED)

| Dimension | Output | Status |
|-----------|--------|--------|
| STACK | `.planning/research/kb-databricks-v1/STACK.md` | ✅ Verbatim app.yaml schema (MS Learn) + CLI v0.260.0 sub-help + Apps SP auto-injected env vars |
| FEATURES | `.planning/research/kb-databricks-v1/FEATURES.md` | ✅ LightRAG source-grep with line refs (`os.makedirs` at every storage init, `write_json` non-atomic) + decision matrix |
| ARCHITECTURE | `.planning/research/kb-databricks-v1/ARCHITECTURE.md` | ✅ Read-side topology + 3 sync options + 5-step manual sync runbook + App SP flow |
| PITFALLS | `.planning/research/kb-databricks-v1/PITFALLS.md` | ✅ 22 pitfalls / 7 categories / phase coverage matrix |
| Synthesis | `.planning/research/kb-databricks-v1/SUMMARY.md` | ✅ Top-5 pitfalls + kdb-1.5 trigger rule + 5 verification questions for spike |

Research committed in `406c2d0` (raw evidence in `raw/` subdir for audit traceability). Hand-driven by main session — gsd-project-researcher subagents spawned earlier hit 600s watchdog (web tools blocked / unavailable in subagents on this Databricks-hosted Claude); main-session synthesis was the salvage path. Findings drove all rev 2 P0/P1/P2 adjustments.

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
