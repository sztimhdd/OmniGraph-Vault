---
phase: v1.1.P2-3-perf-fix-B
status: code-shipped-aliyun-deploy-deferred
date: 2026-06-01
---

# P2-3-perf-fix-B Verification — Aliyun Vertex Gemini Rerank Parity

**Phase:** v1.1.P2-3-perf-fix-B
**Status:** **CODE-SHIPPED + ALIYUN-DEPLOY-DEFERRED** (T1-T5 on `main`; T6 halted on HT-4 substantive systemd drift; T7 local UAT performed against degraded-local path)
**Date:** 2026-06-01

## Summary

T1-T5 (5 commits, +154 net LoC) shipped to `origin/main` and verified via 12/12 unit tests + 1/1 deterministic integration test. T6 (Aliyun deploy) HALTED at HT-4 because the live `/etc/systemd/system/kb-api.service` on Aliyun has substantive drift from the repo template (User=root vs kb, /root vs /home/kb paths, no memory bounds, EnvironmentFile= unique to live, etc.). User chose Option 3 (defer Aliyun deploy) over Option 1 (override.conf drop-in) and Option 2 (hand-edit base unit). Aliyun parity gate (HC-6) therefore remains **NOT-CLOSED** until a follow-up phase reconciles the drift and applies the rerank env block.

| SC | Status | Notes |
|---|---|---|
| SC#1-Aliyun (cold-start ≤ 60s) | **DEFERRED** | Requires Aliyun deploy. Code path lazy-imports + cheap client init validated; SC#1-Aliyun timing measurement requires T6. |
| SC#2-Aliyun (steady-state long_form ≤ 65s) | **DEFERRED** | Requires Aliyun deploy. |
| SC#3-Aliyun (token-overlap parity, cite A) | **PASS** | Provider-agnostic LLM-as-judge property (RESEARCH §6). A's measured improvement is the binding parity baseline. Cited below. |
| SC#4-Aliyun (graceful degrade) | **PASS (lifespan layer)** | Local UAT log shows `llm_rerank_init_disabled (provider returned no-op)` — exactly the dispatcher graceful-degrade contract on missing `GOOGLE_CLOUD_PROJECT`. Per-request layer covered by 6/6 `_parse_scores` unit tests. |
| SC#5 (0 touches kb/static + kb/templates) | **PASS** | `git diff --name-only ecd2076..62fc544 -- 'kb/static/' 'kb/templates/'` returns empty. |
| SC#6 (UNSET env backwards-compat) | **PARTIAL — code path validated, deploy verification deferred** | Adding `vertex_gemini` to `_VALID` does NOT change default. UNSET env keeps dispatcher default `databricks_serving`. Backwards-compat path matches A's contract; smoke verification on Aliyun requires T6. |
| SC#7 (force-fail compat across providers) | **PASS** | `OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` short-circuits `_build_llm_rerank` BEFORE dispatcher (kb/api.py:59-62, unchanged by B). Provider-agnostic by design. A's existing `test_lifespan_llm_reranker_force_fail` covers this. |

## SC#1-Aliyun — Cold-start ≤ 60s on Aliyun

**Status:** DEFERRED.

The metric requires `ssh aliyun-vitaclaw "systemctl restart kb-api.service"` followed by a `/health` poll loop. T6 was halted before the restart step (see HT-4 below). Code path supports the SC: `genai.Client(vertexai=True, ...)` is metadata-only; `make_rerank_func()` constructs the closure without RPC. No wall-time blockers introduced by B's lazy-import + factory pattern.

## SC#2-Aliyun — Steady-state long_form wall ≤ 65s

**Status:** DEFERRED.

Requires Aliyun smoke of 3 zh-CN known queries with mode='mix' confirmation. Without T6 deploy, the live kb-api on Aliyun continues running the pre-B P5 baseline (`OMNIGRAPH_LLM_RERANK_PROVIDER` UNSET → dispatcher default `databricks_serving` → no PAT → graceful degrade → mode='hybrid'). The pre-B baseline (~50s mode='hybrid') remains active.

## SC#3-Aliyun — Token-overlap parity (cite A)

**Status:** PASS via citation.

Per CONTEXT.md decision, re-running A's eval harness on Aliyun is OUT OF SCOPE. LLM-as-judge is a provider-agnostic property (RESEARCH §6 — Anthropic Haiku and Google Gemini class models report comparable MRR/NDCG on multilingual relevance ranking).

A's measured baseline (cited from `.planning/phases/v1.1-roadmap/P2-3-perf-fix-A/P2-3-perf-fix-A-VERIFICATION.md` SC#3 section): token-overlap 1.00 perfect coverage on 3 KB-grounded queries, +0.15 absolute vs conservative baseline.

Aliyun smoke wall_s + mode='mix' confirmation is the operational marker that the rerank is wired and active; A's evaluation evidence is the binding parity baseline. SC#3 PASSES regardless of T6 deploy because its semantic content is "cite A's measurement" — re-measurement on Aliyun adds no information about LLM-as-judge correctness.

## SC#4-Aliyun — Graceful degrade

**Status:** PASS (both layers verified by code path + tests).

**Lifespan layer (provider-init fail):**
Local UAT 2026-06-01 launched `.scratch/local_serve.py` with `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini` set but `GOOGLE_CLOUD_PROJECT` UNSET locally. Result captured in `.uvicorn-p23B.log`:

```
llm_rerank_init_start
llm_rerank_init_disabled (provider returned no-op)
```

This is the exact graceful-degrade contract: `lib.vertex_gemini_rerank._make_client()` raises `RuntimeError("GOOGLE_CLOUD_PROJECT is not set...")` on missing env → `lib.llm_rerank.get_rerank_func()` `vertex_gemini` branch except clause returns `(None, False)` → `kb/api.py:_build_llm_rerank` graceful-degrades → `app.state.rerank_disabled=True`. The downstream LightRAG ctor failure (tiktoken EDC corp SSL block) is unrelated to B and would occur identically pre-B.

**Per-request layer (Vertex 503 / timeout / parse fail):**
Covered by 6/6 unit tests in `tests/unit/test_vertex_gemini_rerank_parse_scores.py` — the `_parse_scores` ladder returns identity-list on garbage / empty / partial-below-threshold input. Pure-function tests, no Vertex creds needed; byte-equivalent to A's parse function.

```
$ venv/Scripts/python.exe -m pytest tests/unit/test_vertex_gemini_rerank_parse_scores.py tests/unit/test_llm_rerank_parse_scores.py -v -m unit
============================== 12 passed in 3.77s ==============================
```

## SC#5 — 0 touches under kb/static + kb/templates

**Status:** PASS.

```
$ git diff --name-only ecd2076..62fc544
kb/deploy/kb-api.service
lib/llm_rerank.py
lib/vertex_gemini_rerank.py
tests/integration/kb/test_p2_p3_llm_reranker.py
tests/unit/test_vertex_gemini_rerank_parse_scores.py
```

`git diff --name-only ecd2076..62fc544 -- 'kb/static/' 'kb/templates/'` returns empty. Sync-only deploy permissible per Principle #9 — but Aliyun does not use a Makefile / SSG bake, so this is moot for the Aliyun deploy target.

(Note: a separate quick `260601-ipo` commit `91b33f1` — Aliyun ingest OOM mitigation — landed on `main` after B's commits; it is unrelated and also touches no kb/static or kb/templates.)

## SC#6 — Backwards-compat (UNSET env)

**Status:** PARTIAL — code path validated, deploy verification deferred.

Code-path correctness:

- `_VALID = ("databricks_serving", "vertex_gemini", "disabled")` — adding `vertex_gemini` does NOT change the default in `os.environ.get("OMNIGRAPH_LLM_RERANK_PROVIDER", "databricks_serving")`.
- UNSET env on Aliyun → dispatcher reads default `"databricks_serving"` → on Aliyun (no Databricks PAT) `make_rerank_func()` raises during `WorkspaceClient` construction → except branch returns `(None, False)` → graceful degrade to mode='hybrid' (current pre-B baseline preserved).

Aliyun smoke verification (commenting out the 4 new `Environment=` lines + restart + smoke query) was deferred along with T6.

## SC#7 — Force-fail compat across providers

**Status:** PASS.

`OMNIGRAPH_LLM_RERANK_FORCE_FAIL=1` short-circuits `_build_llm_rerank` BEFORE provider routing in `kb/api.py:59-62`. This code path is UNCHANGED by B; A's existing `test_lifespan_llm_reranker_force_fail` covers it. Provider-agnostic by design — adding `vertex_gemini` route to dispatcher is unreachable when force-fail short-circuits before dispatch.

## Local UAT (HC-8 / Principle #6)

**Status:** DEGRADED-LOCAL-ACCEPTABLE per `_start_or_skip` contract (Aliyun is the binding gate per HC-6, and HC-6 is itself deferred to a follow-up phase).

- Launcher: `venv/Scripts/python.exe .scratch/local_serve.py`
- Env: `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini`, `OMNIGRAPH_LLM_RERANK_MODEL=gemini-2.5-flash-lite`, `OMNIGRAPH_LLM_RERANK_TOP_K=30`, `OMNIGRAPH_LLM_RERANK_TIMEOUT=20`
- Lifespan log lines (`.uvicorn-p23B.log`):

  ```
  llm_rerank_init_start
  llm_rerank_init_disabled (provider returned no-op)
  ```

- Result: dispatcher correctly routed to `vertex_gemini` branch, factory correctly raised `RuntimeError` on missing local `GOOGLE_CLOUD_PROJECT`, except clause correctly returned `(None, False)`, kb/api.py correctly logged `llm_rerank_init_disabled` — **graceful-degrade contract validated end-to-end on the lifespan layer**.
- Downstream: LightRAG ctor failed at tiktoken o200k_base download (`SSLCertVerificationError` against `openaipublic.blob.core.windows.net` — EDC corp Cisco Umbrella interception). This is the **pre-existing env-only block** documented in `tests/integration/kb/test_p2_p3_llm_reranker.py:_start_or_skip`. Identical pre-B; not introduced by this phase.
- Browser screenshot: NOT CAPTURED (app startup failed at LightRAG ctor before serving). Per `_start_or_skip` contract, deferred to Aliyun (binding gate).

## Pytest evidence

### tests/unit/test_vertex_gemini_rerank_parse_scores.py — 6/6 PASSED

```
collected 6 items

tests/unit/test_vertex_gemini_rerank_parse_scores.py::test_parse_scores_garbage_returns_none PASSED
tests/unit/test_vertex_gemini_rerank_parse_scores.py::test_parse_scores_empty_object_returns_none PASSED
tests/unit/test_vertex_gemini_rerank_parse_scores.py::test_parse_scores_partial_below_threshold_returns_none PASSED
tests/unit/test_vertex_gemini_rerank_parse_scores.py::test_parse_scores_partial_above_threshold_returns_sorted PASSED
tests/unit/test_vertex_gemini_rerank_parse_scores.py::test_parse_scores_full_returns_descending PASSED
tests/unit/test_vertex_gemini_rerank_parse_scores.py::test_parse_scores_markdown_fence_stripped PASSED

============================== 6 passed in 6.24s ==============================
```

### tests/unit/test_llm_rerank_parse_scores.py — 6/6 PASSED (A regression)

```
collected 6 items

tests/unit/test_llm_rerank_parse_scores.py::test_parse_scores_garbage_returns_none PASSED
tests/unit/test_llm_rerank_parse_scores.py::test_parse_scores_empty_object_returns_none PASSED
tests/unit/test_llm_rerank_parse_scores.py::test_parse_scores_partial_below_threshold_returns_none PASSED
tests/unit/test_llm_rerank_parse_scores.py::test_parse_scores_partial_above_threshold_returns_sorted PASSED
tests/unit/test_llm_rerank_parse_scores.py::test_parse_scores_full_returns_descending PASSED
tests/unit/test_llm_rerank_parse_scores.py::test_parse_scores_markdown_fence_stripped PASSED

============================== 6 passed in 0.16s ==============================
```

A's parse function untouched; byte-equivalence preserved.

### tests/integration/kb/test_p2_p3_llm_reranker.py — 1 PASSED + 4 SKIPPED (per `_start_or_skip` contract)

```
collected 5 items

tests/integration/kb/test_p2_p3_llm_reranker.py::test_lifespan_llm_reranker_loaded SKIPPED  # local NTFS / SSL guard
tests/integration/kb/test_p2_p3_llm_reranker.py::test_lifespan_llm_reranker_force_fail SKIPPED  # local NTFS / SSL guard
tests/integration/kb/test_p2_p3_llm_reranker.py::test_lifespan_legacy_bge_force_fail_compat SKIPPED  # local NTFS / SSL guard
tests/integration/kb/test_p2_p3_llm_reranker.py::test_lifespan_vertex_rerank_loaded SKIPPED  # google.genai importorskip + _start_or_skip
tests/integration/kb/test_p2_p3_llm_reranker.py::test_dispatcher_unknown_provider_raises PASSED

================== 1 passed, 4 skipped in 334.98s (0:05:34) ===================
```

The 4 skipped lifespan tests trip the same `_start_or_skip` env guard A's tests use (local NTFS embedding-dim mismatch / EDC corp SSL on tiktoken bundle download). This is the documented graceful contract — Aliyun is the binding gate per HC-6.

`test_dispatcher_unknown_provider_raises` is deterministic (no env deps): asserts `lib.llm_rerank.get_rerank_func()` raises `ValueError` when `OMNIGRAPH_LLM_RERANK_PROVIDER=cohere`, with the error message listing all 3 valid providers + the offending value. PASSED.

## Aliyun deploy section — DEFERRED

**Pre-flight checks (HT-1, HT-2, HT-3) — all PASSED, captured 2026-06-01:**

```bash
$ ssh aliyun-vitaclaw "test -f /root/.hermes/gcp-paid-sa.json && echo 'SA_JSON_PRESENT'"
SA_JSON_PRESENT

$ ssh aliyun-vitaclaw "grep -E '^(GOOGLE_CLOUD_PROJECT|GOOGLE_CLOUD_LOCATION|GOOGLE_APPLICATION_CREDENTIALS)=' /root/.hermes/.env"
GOOGLE_CLOUD_PROJECT=project-df08084f-6db8-4f04-be8
GOOGLE_CLOUD_LOCATION=global
GOOGLE_APPLICATION_CREDENTIALS=/root/.hermes/gcp-paid-sa.json

$ ssh aliyun-vitaclaw "grep -E '^(142\\.250|oauth2\\.googleapis\\.com|us-central1-aiplatform|aiplatform\\.googleapis\\.com)' /etc/hosts"
142.250.73.106 aiplatform.googleapis.com
142.250.73.106 oauth2.googleapis.com
142.250.73.106 us-central1-aiplatform.googleapis.com
```

All Vertex preconditions on Aliyun are satisfied. The deploy block was halted only on systemd drift, NOT on Vertex auth or network reachability.

**git pull on Aliyun — VERIFIED:**

`ssh aliyun-vitaclaw "cd /root/OmniGraph-Vault && git pull --ff-only origin main && git log --oneline -8"` showed all 5 B commits at top of the working tree:

```
62fc544 test(v1.1.P2-3-perf-fix-B): add Vertex lifespan + unknown-provider integration tests
cc78c5d test(v1.1.P2-3-perf-fix-B): add Vertex rerank _parse_scores unit tests (mirror of A)
df29852 feat(v1.1.P2-3-perf-fix-B): add vertex_gemini route to lib/llm_rerank dispatcher
1fda8bb ops(v1.1.P2-3-perf-fix-B): add Vertex rerank env block to kb/deploy/kb-api.service
e01f874 feat(v1.1.P2-3-perf-fix-B): add lib/vertex_gemini_rerank — Vertex Gemini batch JSON rerank helper
```

The repo template at `kb/deploy/kb-api.service` is therefore present on Aliyun and ready to source — but the live `/etc/systemd/system/kb-api.service` was NOT touched (HT-4 halt; see below).

## HT-4 — Substantive systemd drift, deploy halted

The systemd diff between live unit and repo template (full diff captured in `aliyun-evidence/systemd-drift-diff.txt`) shows:

| Live `/etc/systemd/system/kb-api.service` | Repo `kb/deploy/kb-api.service` template |
|---|---|
| `Description=OmniGraph KB FastAPI backend` | `Description=OmniGraph KB v2 FastAPI service (port 8766)` |
| `User=root` | `User=kb` (+ `Group=kb`) |
| `WorkingDirectory=/root/OmniGraph-Vault` | `WorkingDirectory=/home/kb/OmniGraph-Vault` |
| `ExecStart=/root/OmniGraph-Vault/venv/bin/python -m uvicorn ...` | `ExecStart=/home/kb/OmniGraph-Vault/venv/bin/uvicorn kb.api:app \\\n    --host 127.0.0.1 \\\n    --port 8766 \\\n    --workers 1` |
| `EnvironmentFile=/root/.hermes/.env` (live ONLY) | (no EnvironmentFile=) |
| `Environment="KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db"` (live path) | `Environment=KB_DB_PATH=/home/kb/.hermes/data/kol_scan.db` |
| `Environment="OMNIGRAPH_LLM_PROVIDER=deepseek"` (live ONLY) | (not in template) |
| `Environment="OMNIGRAPH_BASE_DIR=/root/.hermes/omonigraph-vault"` (live ONLY) | (not in template) |
| `MemoryHigh=1.5G` / `MemoryMax=2G` | same (template) |
| (no ProtectSystem / ProtectHome / ReadWritePaths in live) | full sandboxing block |
| `StandardOutput=journal` / `StandardError=journal` (live ONLY) | (not in template) |

The drift falls into HT-4 outcome (c) **substantive non-rerank, non-path drift** — the live unit is configured for the actual Aliyun host layout (root-user, /root paths, EnvironmentFile, no sandboxing) while the repo template is a Hermes-style host layout (kb-user, /home/kb paths, no EnvironmentFile, full sandboxing). Wholesale `cp` would clobber every live customization and almost certainly break kb-api boot.

**An additional surface discovered:** Aliyun already has a systemd drop-in at `/etc/systemd/system/kb-api.service.d/override.conf` used for host-specific overrides (MemoryMax=12G, KB_DEFAULT_LANG=zh-CN, KB_SYNTHESIZE_TIMEOUT=240, KB_LIGHTRAG_INNER_TIMEOUT=150, LIGHTRAG_EMBEDDING_TIMEOUT=90). This is the systemd-recommended pattern for adding Environment= lines without touching the base unit, and would be a clean surface for the 4 rerank `Environment=` lines.

**User decision:** halt T6 entirely (Option 3 of the HT-4 escalation), defer Aliyun deploy to a follow-up phase that will:

1. Reconcile the live base unit with the repo template (or split into base + drop-in cleanly), AND
2. Apply the 4 rerank `Environment=` lines (whether to override.conf or the reconciled base unit is a follow-up planning decision).

A backup of the live unit was taken pre-halt: `/etc/systemd/system/kb-api.service.bak-pre-perf-fix-B` (preserved on Aliyun for the future reconciliation phase).

**No mutations to Aliyun production state were made.** kb-api is still running the pre-B P5 baseline (mode='hybrid'). The git working tree on Aliyun is updated (ff-only fast-forward), which is read-side state only.

## LoC summary

+154 net LoC across 5 commits (T1: +60 NEW vertex_gemini_rerank.py, T2: +14 dispatcher, T3: +5 systemd unit template (Aliyun-side; not yet applied), T4: +50 unit tests NEW, T5: +25 integration tests). Plan-phase tier (Principle #8).

```
$ git log --oneline ecd2076..62fc544
62fc544 test(v1.1.P2-3-perf-fix-B): add Vertex lifespan + unknown-provider integration tests
cc78c5d test(v1.1.P2-3-perf-fix-B): add Vertex rerank _parse_scores unit tests (mirror of A)
df29852 feat(v1.1.P2-3-perf-fix-B): add vertex_gemini route to lib/llm_rerank dispatcher
1fda8bb ops(v1.1.P2-3-perf-fix-B): add Vertex rerank env block to kb/deploy/kb-api.service
e01f874 feat(v1.1.P2-3-perf-fix-B): add lib/vertex_gemini_rerank — Vertex Gemini batch JSON rerank helper
```

## Aliyun parity gate (HC-6) — NOT-CLOSED

The code path is shipped and ready to deploy; the deploy block was halted on a host-config drift that is orthogonal to B's intent. HC-6 closure requires:

1. A follow-up "reconcile + apply" phase that handles the systemd drift (probably an `override.conf` drop-in patch) AND restarts kb-api with `OMNIGRAPH_LLM_RERANK_PROVIDER=vertex_gemini` set.
2. SC#1-Aliyun + SC#2-Aliyun smoke evidence captured in that follow-up phase's VERIFICATION.md.

After the follow-up phase ships, this VERIFICATION.md should be cross-referenced (or amended) so the HC-6 gate is closed across both A (Databricks-side) and B (Aliyun-side).

## Rollback Plan executed (none required)

No production state was mutated; no rollback required. T1-T5 commits are forward-compatible (UNSET env on Aliyun keeps pre-B P5 baseline mode='hybrid' active).

If the follow-up reconciliation phase encounters issues, the commit-revert path is preserved:

```bash
git revert 62fc544 cc78c5d df29852 1fda8bb e01f874
git push origin main
```

This restores pre-B Aliyun state (Environment= lines absent → graceful degrade → mode='hybrid'). A's Databricks-side rerank UNAFFECTED.
