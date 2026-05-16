# STATE — kb-databricks-v1 (rev 3)

> Parallel-track state file. Main `STATE.md` belongs to v3.4 / v3.5 main track.
> Sibling state files: `STATE-KB-v2.md`, `STATE-Agentic-RAG-v1.md`,
> `STATE-v3.5-Ingest-Refactor.md`. **Untouched by this milestone.**

## Current Position

- **Milestone:** kb-databricks-v1 (parallel track)
- **Phase:** kdb-1.5 — LightRAG-Databricks Provider Adapter (COMPLETE; both plans landed)
- **Plan:** kdb-1.5-01 (storage adapter — STORAGE-DBX-05) ✅ + kdb-1.5-02 (factory file + dry-run e2e — LLM-DBX-03) ✅
- **Status:** kdb-1.5 phase complete. ROADMAP success criteria 1-3 PASS; #4 (`app.yaml` wiring) explicitly deferred to kdb-2 DEPLOY-DBX-04. 9/9 tests green (5 unit + 4 dry-run against REAL MosaicAI). Risk #2 (SDK shape) + Risk #3 (Qwen3 bilingual) both resolved PASS. Ready for kdb-2 (Databricks App Deploy).
- **Last activity:** 2026-05-16 — kdb-1.5 plan 02 factory + dry-run e2e shipped: `databricks-deploy/lightrag_databricks_provider.py` + `tests/test_provider_dryrun.py` (4 tests against REAL Model Serving) + 5 fixture articles + pytest.ini. 4/4 dry-run PASS in 156s wallclock @ <$0.10 cost. Wave 1+2 commit hashes (forward-only, no `--amend`): `545e726` (Plan 01 RED tests) → `bd96e1b` (Plan 01 GREEN impl) → `dad2e85` (Plan 01 docs+STATE+VERIFICATION) → `7af1164` (Plan 01 SUMMARY) → `bb56562` (Plan 02 factory+fixtures+pytest deps) → `9edc3c0` (Plan 02 dry-run tests + ChatMessageRole .lower() fix + dim-walk improvement).

## Milestone-base commit hash (LOCKED — rev 3)

**`cfe47b4`** — `docs(kb-databricks-v1): rev 3 strategic restructure (MosaicAI / Hermes-separation / sonnet-4-6 / qwen3-0.6b / kb-exemption)`

This is the anchor for **CONFIG-DBX-01** (rev 3 — relaxed). At kdb-3 close, verify with:

```bash
git log cfe47b4..HEAD --grep '(kdb-' --name-only -- kb/ lib/ \
  | grep -v -E '^lib/llm_complete\.py$|^kg_synthesize\.py$' \
  | sort -u
# Expected: empty output
```

The `--grep '(kdb-'` filter scopes the diff to this milestone's commits only. The trailing `grep -v` line allows the two explicit exemptions per rev 3 constraint #5 (`lib/llm_complete.py` + `kg_synthesize.py`). Unrelated kb-v2.1 / kb-4 / debug commits authored after the rev-3 commit are ignored — those belong to other tracks and don't violate kb-databricks-v1's scope.

**Allowed `kb/`-relative edits in this milestone (whitelisted via CONFIG-EXEMPTIONS.md):**

- `lib/llm_complete.py` — add `databricks_serving` provider branch (LLM-DBX-01)
- `kg_synthesize.py` — route LLM call through dispatcher (LLM-DBX-02)

Any other path edit requires explicit user approval before merge.

## Locked Defaults (rev 3 — full table in PROJECT-kb-databricks-v1.md)

| # | Slot | Locked value (rev 3) |
|---|------|----------------------|
| 1 | UC catalog | `mdlg_ai_shared` (live; old `mdlg_ai` decommissioned 2026-02-05) |
| 2 | UC schema | `kb_v2` (to be created in kdb-1) |
| 3 | UC volume | `omnigraph_vault` (managed) |
| 4 | Volume layout | `/data/kol_scan.db` · `/images/{hash}/...` · `/lightrag_storage/...` · `/output/...` |
| 5 | Apps app name | `omnigraph-kb` |
| 6 | App auth → UC | App Service Principal (Apps runtime auto-injects `DATABRICKS_CLIENT_ID/SECRET/HOST`) |
| 7 | App port | `:8080` (Apps runtime hardcoded — `$DATABRICKS_APP_PORT` substituted in `command:`) |
| 8 | **Q&A LLM (synthesis)** | **`databricks-claude-sonnet-4-6` via MosaicAI Model Serving** (rev 3) |
| 9 | **Embedding model** | **`databricks-qwen3-embedding-0-6b` via MosaicAI Model Serving** (rev 3, dim 1024, bilingual zh/en) |
| 10 | **Hermes touchpoint** | **One-shot user upload (SEED-DBX-01) only** — no ongoing sync; runtime is fully Databricks-self-contained (rev 3) |

**Removed in rev 3:**
- ~~"DeepSeek (status quo); workspace secret + `valueFrom: secretKeyRef`"~~ — rev 2.x slot 8, retired
- ~~"Manual `databricks fs cp` from Windows dev (v1)"~~ — rev 2.x slot 9, replaced by one-shot SEED-DBX-01

## Next Step

Proceed to kdb-2 (Databricks App Deploy). DEPLOY-DBX-04 will add the storage-adapter `command:` invocation + 4 literal env vars (`OMNIGRAPH_BASE_DIR=/tmp/omnigraph_vault` + `OMNIGRAPH_LLM_PROVIDER=databricks_serving` + `KB_LLM_MODEL=databricks-claude-sonnet-4-6` + `KB_EMBEDDING_MODEL=databricks-qwen3-embedding-0-6b`) to `app.yaml`. LLM-DBX-01 + LLM-DBX-02 (lib/llm_complete.py + kg_synthesize.py CONFIG-EXEMPTIONS path) ship in kdb-2 alongside the deploy.

## Research (COMPLETED — pre-rev-3, still applicable)

| Dimension | Output | Status |
|-----------|--------|--------|
| STACK | `.planning/research/kb-databricks-v1/STACK.md` | ✅ Verbatim app.yaml schema (MS Learn) + CLI v0.260.0 sub-help + Apps SP auto-injected env vars. **Note:** secret-scope sections still in research file; no longer needed for rev 3 (DeepSeek retired) but retained as reference for v2 if Foundation Model swap needs different auth |
| FEATURES | `.planning/research/kb-databricks-v1/FEATURES.md` | ✅ LightRAG source-grep with line refs (`os.makedirs` at every storage init, `write_json` non-atomic) + decision matrix. **Unchanged by rev 3** — these are intrinsic LightRAG behaviors |
| ARCHITECTURE | `.planning/research/kb-databricks-v1/ARCHITECTURE.md` | ✅ Read-side topology + 3 sync options. **rev 3 supersedes "ongoing sync" → one-shot SEED.** Three-options analysis still useful for v3 ingest-pipeline-on-Databricks future milestone |
| PITFALLS | `.planning/research/kb-databricks-v1/PITFALLS.md` | ✅ 22 pitfalls / 7 categories / phase coverage matrix. **DeepSeek-related pitfalls (egress, key leakage) effectively dead in rev 3** but retained for v3 / future-state reference |
| Synthesis | `.planning/research/kb-databricks-v1/SUMMARY.md` | ✅ Top-5 pitfalls + kdb-1.5 trigger rule + 5 verification questions for spike. **Rev 3 keeps the 5 spike questions, modifies SPIKE-DBX-01e from DeepSeek-egress to in-app Model Serving call** |

Research committed in `406c2d0`. Findings drove rev 2 P0/P1/P2 adjustments; rev 3 strategic restructure is a user-driven scope change, not a research-driven one.

## Constraints in Force (rev 3)

- **Cross-milestone contracts read-only** — KB-v2 C1 / C2 signatures untouched. **C1 internal implementation modified per rev 3 LLM-DBX-02** (`kg_synthesize.synthesize_response` now routes through `lib/llm_complete.py` dispatcher), but external signature + return-type contract preserved
- **`kb/` source-tree edits restricted to exemption list** (CONFIG-DBX-01 rev 3) — `lib/llm_complete.py` + `kg_synthesize.py` only. All other paths locked
- **No DeepSeek references in `databricks-deploy/` or v1 deploy artifacts** — DeepSeek fully retired in rev 3. Existing DeepSeek code paths in `lib/` may remain reachable via `OMNIGRAPH_LLM_PROVIDER=deepseek` env var (for non-Databricks deploys), but v1 deploy locks `databricks_serving`
- **No Hermes runtime touchpoints after kdb-1 SEED-DBX-01** — one-shot user upload is the entire Hermes interaction. Runtime Databricks is self-contained
- **Parallel-track tooling caveat** (memory `feedback_parallel_track_gates_manual_run.md`): `gsd-tools.cjs init` does NOT recognize suffix files. Orchestrator hand-drives every gate (UI Design Contract, Nyquist, Coverage). No silent skips
- **Subagent web-tool caveat** (CLAUDE.md): Databricks proxy strips `tool_reference` blocks; subagents cannot call `mcp__context7__*` or `mcp__brave-search__*`. Main session must pull docs upfront → any future research consumed via `<files_to_read>`

## Accumulated Context

- KB-v2 milestone (sibling) is mid-flight: kb-1 closed 2026-05-13, kb-2 in flight via quick `260514-d3p` (Aliyun deploy). kb-databricks-v1 deliberately does NOT block on KB-v2 closure — Databricks deploy reads the same artifacts KB-v2 produces; both deploy targets (Aliyun public, Databricks internal-preview) consume identical `kb/` source (with the rev 3 exemption — `kg_synthesize.py` will be modified, both targets benefit since the dispatcher pattern is provider-agnostic)
- OmniGraph v1.0 declared 2026-05-13 (Knowledge Collection + Ingestion). Ingest pipeline is stable; daily-ingest cron continues on Hermes throughout this milestone. **No Hermes changes required for kb-databricks-v1** (strengthened from rev 2.x: now also no Hermes runtime dependency at all post-SEED-DBX-01)
- DBX workspace: `https://adb-2717931942638877.17.azuredatabricks.net`
- DBX CLI profile: `dev` (in `~/.databrickscfg`), default warehouse `eaa098820703bf5f`
- User has Windows dev box with Databricks Connect + OAuth login + PAT configured

### kb-v2.1-1 KG MODE HARDENING (closed 2026-05-15, commit `eff934f` + STATE backfill `a226140`)

Sibling-track quick task — NOT kb-databricks-v1 work, but materially relevant downstream. Aliyun root cause was env-file content drift (path baked into a copied `~/.hermes/.env`), not code; remediated with proactive file-existence probe.

**Shipped:**

- `KG_MODE_AVAILABLE` flag pattern at [kb/services/synthesize.py:74-105](../kb/services/synthesize.py#L74-L105) — EAFP 1-byte read probe + 3 reason codes: `{kg_disabled, kg_credentials_missing, kg_credentials_unreadable}` + one-shot WARNING (no path leak)
- New env var `KB_KG_GCP_SA_KEY_PATH` in [kb/config.py](../kb/config.py) with `GOOGLE_APPLICATION_CREDENTIALS` fallback
- Aliyun systemd unit at `kb/deploy/kb-api.service` (irrelevant to Databricks Apps)
- Operator runbook at `kb/deploy/RUNBOOK-aliyun-systemd-refresh.md` (Aliyun-specific)
- Tests: `tests/integration/kb/test_kg_mode_hardening.py` 8/8 PASS · 4/4 Local UAT scenarios · 436/436 no regression

**Implications carried into kb-databricks-v1 rev 3:**

- The 3 reason codes (`kg_disabled` / `kg_credentials_missing` / `kg_credentials_unreadable`) extend by 1 in rev 3 (`kg_serving_unavailable` per LLM-DBX-04) — total 4 reason codes verified in QA-DBX-03
- `KG_MODE_AVAILABLE` graceful-degrade pattern is the foundation that makes rev 3's "Model Serving 503 → FTS5 fallback" not require new code, just provider-specific reason-code addition
- `KB_KG_GCP_SA_KEY_PATH` env var stays in code but is **deliberately unset** in `app.yaml` (DEPLOY-DBX-09) since rev 3 doesn't use Vertex/GCP

### rev 3 strategic restructure (2026-05-15)

User-locked 5 constraints supersede rev 2.2's DeepSeek-based architecture:

1. ALL LLM (synthesis + entity extraction + embedding) via MosaicAI Model Serving — DeepSeek fully retired in v1
2. Hermes runtime fully separated — one-shot user-driven SEED replaces ongoing SYNC; Databricks self-contained post-seed
3. Synthesis model: `databricks-claude-sonnet-4-6` (locked, v2 may upgrade to opus or successor)
4. Embedding model: `databricks-qwen3-embedding-0-6b` (locked, bilingual zh/en, dim 1024)
5. "Zero `kb/` edits" hard rule **relaxed** — `lib/llm_complete.py` + `kg_synthesize.py` are exempted via CONFIG-EXEMPTIONS.md to allow MosaicAI provider integration

**Net structural changes vs rev 2.2:**

- Removed: SECRETS-DBX category (5 REQs), SYNC-DBX category (3 REQs), DeepSeek-flavored PREFLIGHT-01, "FM-DBX swap" future requirement (now in v1)
- Added: LLM-DBX category (5 REQs), SEED-DBX category (3 REQs), kdb-2.5 NEW phase (re-index Job)
- Modified: DEPLOY-DBX-04/07/08, QA-DBX-02/03, PREFLIGHT-DBX-01, AUTH-DBX-04, CONFIG-DBX-01/02, SPIKE-DBX-01e, OPS-DBX-03/05, STORAGE-DBX-04 (Hermes wording dropped)
- Phase shape: was 3 + conditional 1.5 → now 4 + conditional 1.5 (added kdb-2.5)
- T-shirt: S → M (driver: kdb-2.5 re-index half-day to 1-day Job time + $20–100 cost)

**CONFIG-DBX-01 invariant verification:** the rev 3 verification command (with `lib/llm_complete.py` + `kg_synthesize.py` exemption filter) replaces rev 2.x's strict `kb/`-only filter. kb-v2.1-1 commits and any other parallel-track commits remain excluded by `--grep '(kdb-'`. The rev-3-commit-hash anchor is recorded in this file (above) and will be used by kdb-3 audit.

## 2-forward-commit pattern (rev 3)

This file is part of the rev 3 forward commit (`cfe47b4`). The hash placeholder above will be backfilled in a second forward commit immediately after the rev 3 main commit lands. **No `git commit --amend`, no `git reset` — both forbidden per concurrent-quick safety lesson (260515-cvh / 0b06395).** Pattern follows kb-v2.1-1 closeout precedent (`a226140` STATE backfill of `eff934f`).
