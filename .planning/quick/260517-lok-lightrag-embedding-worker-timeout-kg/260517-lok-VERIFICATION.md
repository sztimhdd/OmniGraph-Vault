---
phase: quick-260517-lok
verified: 2026-05-18T03:15:00Z
status: passed_partial
score: 5/6 must-haves verified (LOK-01..05 confirmed via Aliyun retest; LOK-06 partially blocked by SEPARATE next-layer bottleneck — outer KB_SYNTHESIZE_TIMEOUT=240s)
aliyun_retest:
  date: "2026-05-18 03:11-03:15 ADT"
  scp_target: /root/OmniGraph-Vault/kg_synthesize.py
  pid_after_restart: 171703
  startup_warning: "(none — KG_MODE_AVAILABLE=True)"
  lok_05_journal_evidence: |
    May 18 03:11:35 INFO: LLM func: 4 new workers initialized (Timeouts: Func: 180s, Worker: 360s, Health Check: 375s)
    May 18 03:11:40 INFO: Embedding func: 8 new workers initialized (Timeouts: Func: 90s, Worker: 180s, Health Check: 195s)
  lok_05_verdict: "PASSED — exact 90/180/195 ratio matches plan target; was 30/60/75 pre-fix"
  worker_timeout_grep: "EMPTY (zero `Worker timeout` / `Query failed` events during 246s qa run)"
  worker_timeout_verdict: "PASSED — LightRAG embedding worker timeout layer is no longer the bottleneck"
  qa_smoke:
    job_id: ded7f574728c
    total_seconds: 246
    confidence: no_results
    fallback_used: true
    error: "C1 timeout"
    markdown_len: 120
    sources: 0
    note: "Outer wrapper KB_SYNTHESIZE_TIMEOUT=240 fired — this is a SEPARATE deployment-layer bottleneck, NOT a LightRAG-internal worker timeout. The fix this quick targeted (LOK-01..05) IS working: zero worker timeout warnings during the 246s window."
gaps:
  - id: NEXT-LAYER-OUTER-TIMEOUT
    severity: deployment-config
    in_scope_for_this_quick: false
    description: |
      Cross-border Aliyun→GCP-Singapore LightRAG hybrid query cold-start total wall-clock exceeds outer KB_SYNTHESIZE_TIMEOUT=240s.
      LightRAG internal: query embed (~5-10s) + multi-step entity retrieval + multi-step relation retrieval + DeepSeek synthesis call.
      With internal embedding worker timeout now properly sized (180s allows 1 cold-start embed + retries), the cumulative wall-clock for a full hybrid query exceeds 240s on this path.
      Plan hard-scoped this quick to "do NOT touch systemd unit (KB_SYNTHESIZE_TIMEOUT=240 already configured)" — so addressing this is a follow-up.
    suggested_followup: |
      Next quick should bump KB_SYNTHESIZE_TIMEOUT 240→600 in /etc/systemd/system/kb-api.service.d/override.conf,
      OR investigate whether LightRAG hybrid mode internal step count can be reduced (config kwargs like top_k or only_need_context).
      The SCP-and-restart pattern from this quick can be reused.
human_verification:
  - test: "Aliyun systemd restart + journal grep"
    expected: "journalctl shows: Embedding func: 8 new workers initialized (Timeouts: Func: 90s, Worker: 180s, Health Check: 195s)"
    why_human: "Requires SSH to aliyun-vitaclaw prod host, systemctl restart, and live journal inspection — no local proxy to Aliyun ECS"
  - test: "POST /api/synthesize mode=qa smoke"
    expected: "curl returns JSON with error=null and non-empty markdown field"
    why_human: "Endpoint only reachable from Aliyun ECS localhost:8000; cross-border WireGuard path required to reproduce the original timeout condition"
  - test: "POST /api/synthesize mode=long_form smoke"
    expected: "JSON with error=null, markdown_len > 2000, sources array >= 1 entry"
    why_human: "Same — Aliyun-only endpoint; also depends on real KG content (LangChain/LangGraph articles)"
  - test: "No Worker timeout warnings during smoke"
    expected: "journalctl grep for 'worker timeout' returns empty (echo 'NO WORKER TIMEOUT — clean')"
    why_human: "Worker timeout behavior only reproducible on actual cross-border Aliyun→GCP-Singapore embedding path"
---

# Quick 260517-lok: LightRAG Embedding Worker Timeout Fix — Verification Report

**Phase Goal:** Pass `default_embedding_timeout=90` (env-overridable via `LIGHTRAG_EMBEDDING_TIMEOUT`) to `LightRAG()` in `kg_synthesize.py` so cross-border Aliyun→GCP-Singapore embedding calls don't hit LightRAG's internal 60s Worker timeout.

**Verified:** 2026-05-17T19:30:00Z
**Status:** human_needed — all local automated checks pass; Aliyun runtime verification (LOK-05, LOK-06) requires operator action
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LightRAG() in kg_synthesize.py receives `default_embedding_timeout=90` by default | VERIFIED | `grep -n "default_embedding_timeout" kg_synthesize.py` → line 127; `python -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"` → `90` |
| 2 | `LIGHTRAG_EMBEDDING_TIMEOUT` env var overrides default at startup | VERIFIED | Test 2 `test_lightrag_embedding_timeout_env_override` passes; import smoke with env=120 → 120 (SUMMARY) |
| 3 | Non-numeric env value falls back to 90 without raising | VERIFIED | Test 3 `test_lightrag_embedding_timeout_invalid_env_falls_back_to_default` passes; `_embedding_timeout_default()` has `try/except (TypeError, ValueError): return 90` at lines 58-60 |
| 4 | 4 unit tests covering all three env paths pass with no network calls | VERIFIED | `pytest tests/unit/test_lightrag_embedding_timeout.py -v` → 4 passed in 11.63s |
| 5 | Aliyun journal shows Func: 90s / Worker: 180s / Health Check: 195s on restart | ? HUMAN NEEDED | Requires SSH + systemctl restart + journalctl on aliyun-vitaclaw |
| 6 | POST /api/synthesize returns non-empty markdown (qa + long_form) with error=null | ? HUMAN NEEDED | Aliyun-only endpoint, cross-border path required |

**Score:** 4/6 truths verified (automated); 2/6 pending human action

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `kg_synthesize.py` | `_embedding_timeout_default()` helper + `default_embedding_timeout=_embedding_timeout_default()` kwarg in `LightRAG()` | VERIFIED | Helper at lines 47-61; kwarg at line 127; `grep -c "default_embedding_timeout" kg_synthesize.py` → 1 |
| `tests/unit/test_lightrag_embedding_timeout.py` | 4 unit tests, min 60 lines, stub-based (no network) | VERIFIED | File is 140 lines; 4 tests all PASS; no real LightRAG import; monkeypatch stub pattern used throughout |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `kg_synthesize.py:127` | `lightrag.lightrag.LightRAG.__init__` | `default_embedding_timeout=_embedding_timeout_default()` kwarg | VERIFIED | Single call site confirmed; `grep -c` → 1; git diff shows exact kwarg added |
| `tests/unit/test_lightrag_embedding_timeout.py` | `kg_synthesize.synthesize_response` | `monkeypatch.setattr("kg_synthesize.LightRAG", _StubRAG)` | VERIFIED | Pattern `monkeypatch.setattr("kg_synthesize.LightRAG"` present in all 4 tests via `_make_stub_rag` factory |

---

## Data-Flow Trace (Level 4)

Not applicable — this phase modifies a configuration kwarg passed to an async call, not a UI rendering path. The relevant data flow is: `LIGHTRAG_EMBEDDING_TIMEOUT` env → `_embedding_timeout_default()` → `LightRAG(default_embedding_timeout=N)` → LightRAG internal Worker budget. The first two hops are fully verified locally; the third hop (LightRAG using the value at runtime) is the Aliyun LOK-05 check.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Default returns 90 | `venv/Scripts/python.exe -c "import kg_synthesize; print(kg_synthesize._embedding_timeout_default())"` | `90` | PASS |
| 4 new unit tests pass | `venv/Scripts/python.exe -m pytest tests/unit/test_lightrag_embedding_timeout.py -v` | `4 passed in 11.63s` | PASS |
| Full KB suite clean (493/493) | `venv/Scripts/python.exe -m pytest tests/integration/kb tests/unit/kb tests/unit/test_lightrag_embedding_timeout.py -q` | `493 passed in 36.03s` | PASS |
| Single call site only | `grep -c "default_embedding_timeout" kg_synthesize.py` | `1` | PASS |
| No vendor code touched | `git log --oneline --since="2026-05-17" -- "venv/Lib/site-packages/lightrag/"` | (empty — no commits) | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| LOK-01 | 260517-lok-PLAN.md | Pass `default_embedding_timeout` kwarg to LightRAG() in kg_synthesize.py:106 | SATISFIED | Line 127 in kg_synthesize.py; single kwarg confirmed by `grep -c` → 1 |
| LOK-02 | 260517-lok-PLAN.md | Honor `LIGHTRAG_EMBEDDING_TIMEOUT` env var override (default 90) | SATISFIED | `_embedding_timeout_default()` reads env; test 2 passes with value 120 |
| LOK-03 | 260517-lok-PLAN.md | Defensive int() parse — non-numeric env falls back to 90 | SATISFIED | Lines 58-60: `try/except (TypeError, ValueError): return 90`; test 3 passes |
| LOK-04 | 260517-lok-PLAN.md | Unit-test coverage asserting kwarg propagation (mock LightRAG; no network) | SATISFIED | `tests/unit/test_lightrag_embedding_timeout.py` — 140 lines, 4 tests, 0 real LightRAG inits |
| LOK-05 | 260517-lok-PLAN.md | Aliyun journal must show Func: 90s, Worker: 180s, Health Check: 195s | NEEDS HUMAN | Task 3 checkpoint:human-action pending |
| LOK-06 | 260517-lok-PLAN.md | POST /api/synthesize qa + long_form return non-empty markdown | NEEDS HUMAN | Task 3 checkpoint:human-action pending |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No anti-patterns found in changed files |

Scope scan confirmed: no `TODO/FIXME`, no `return []`/`return {}` stubs, no hardcoded empty data in the two files modified by 260517-lok commits.

---

## Scope Adherence Verification

The plan specified a hard constraint: ZERO changes to `kb/services/synthesize.py`, `lib/lightrag_embedding.py`, `venv/Lib/site-packages/lightrag/`, systemd/WireGuard/Caddy/.env files.

| Constraint | Status | Evidence |
|------------|--------|----------|
| No changes to `kb/services/synthesize.py` | CLEAN | `git log --oneline --since="2026-05-17" -- kb/services/synthesize.py` → empty |
| No changes to `lib/lightrag_embedding.py` | CLEAN | `git log --oneline --since="2026-05-17" -- lib/lightrag_embedding.py` → empty |
| No vendor code changes | CLEAN | `git log --oneline --since="2026-05-17" -- "venv/Lib/site-packages/lightrag/"` → empty |
| Commit 647628b (T1 RED test) | VERIFIED | Creates `tests/unit/test_lightrag_embedding_timeout.py` only (140 lines) |
| Commit bb5605d (T2 GREEN edit) | VERIFIED | Modifies `kg_synthesize.py` only (+23/-1 lines; helper + kwarg) |
| Commit 6813500 (SUMMARY) | VERIFIED | Creates `.planning/quick/260517-lok-lightrag-embedding-worker-timeout-kg/260517-lok-SUMMARY.md` only |
| Commit c9cc7bf (stub cleanup) | VERIFIED | Modifies `tests/integration/kb/test_synthesize_wrapper.py` only (+5 lines); adds `return output` to `fake_synthesize` in `_patch_c1` |

### Note on c9cc7bf (stub cleanup completing 260517-fyb)

Commit `c9cc7bf` touches `tests/integration/kb/test_synthesize_wrapper.py`, a file attributed to 260517-fyb rather than 260517-lok. This is a test-only stub cleanup: 260517-fyb's SUMMARY claimed 5 `_patch_c1` stub updates but only landed 4; the 5th was in `test_synthesize_wrapper.py` which 260517-fyb itself extended with a new regression test. Without this fix, 2 tests from 260517-fyb's own new test file would have remained failing and blocked the 493/493 baseline count this task required. The change is purely additive (`return output` in a test stub helper), touches no production code, and is correctly scoped as a test-only cleanup. It is not scope creep — it is prerequisite work for getting a clean baseline count, and the executor documented it transparently in the commit message.

---

## Human Verification Required

### 1. Aliyun Systemd Restart + Journal Grep (LOK-05)

**Test:** SCP `kg_synthesize.py` to `aliyun-vitaclaw:/root/OmniGraph-Vault/kg_synthesize.py`, then `systemctl restart kb-api.service`, then:
```bash
ssh aliyun-vitaclaw "journalctl -u kb-api.service -n 50 --no-pager | grep -i 'embedding func.*workers initialized'"
```
**Expected:** Line containing `Timeouts: Func: 90s, Worker: 180s, Health Check: 195s`

**Why human:** Requires Aliyun SSH + live systemd state. The kwarg is verified as present in the code; this step confirms LightRAG honors it at the Python runtime level on the prod host.

**Failure mode:** If journal still shows `Func: 30s, Worker: 60s` — check that SCP landed the correct file path and that the service actually restarted (not just reloaded).

### 2. POST /api/synthesize mode=qa Smoke (LOK-06a)

**Test:**
```bash
ssh aliyun-vitaclaw "curl -s -X POST http://127.0.0.1:8000/api/synthesize \
  -H 'Content-Type: application/json' \
  -d '{\"mode\":\"qa\",\"question\":\"Hermes Agent 是什么\"}' | python3 -m json.tool"
```
**Expected:** JSON with `error: null` and non-empty `markdown` field (real KB content, not empty string)

**Why human:** Aliyun-only endpoint; the original timeout manifested as empty markdown silently — only a real cross-border round-trip can confirm the fix resolved the symptom.

### 3. POST /api/synthesize mode=long_form Smoke (LOK-06b)

**Test:**
```bash
ssh aliyun-vitaclaw "curl -s -X POST http://127.0.0.1:8000/api/synthesize \
  -H 'Content-Type: application/json' \
  -d '{\"mode\":\"long_form\",\"question\":\"对比 LangChain 和 LangGraph 各自的设计哲学\"}' | python3 -m json.tool"
```
**Expected:** `error: null`, `markdown_len > 2000`, `sources` array with at least 1 entry

**Why human:** Long-form queries stress the Worker budget most heavily (longer vector retrieval = more embedding calls within one Worker invocation). If any single Worker still exceeds 180s, this query will expose it.

### 4. No Worker Timeout Warnings During Smoke

**Test:**
```bash
ssh aliyun-vitaclaw "journalctl -u kb-api.service --since '2 minutes ago' --no-pager | grep -i 'worker timeout' || echo 'NO WORKER TIMEOUT — clean'"
```
**Expected:** `NO WORKER TIMEOUT — clean`

**Why human:** Confirms the Worker budget (180s) is sufficient for actual cross-border latency. If warnings appear, 180s is still too tight; next step would be `LIGHTRAG_EMBEDDING_TIMEOUT=120` (Func=120/Worker=240/Health=255) noting the Worker=240 margin against KB_SYNTHESIZE_TIMEOUT=240s outer budget.

---

## Gaps Summary

No automated gaps. All four locally-testable requirements (LOK-01 through LOK-04) are fully satisfied. The two remaining items (LOK-05, LOK-06) are Aliyun-only runtime checks that require operator SSH access — they are correctly classified as `checkpoint:human-action` in the plan and cannot be verified programmatically from the dev machine.

The code change is minimal, surgical, and correct: a 16-line helper function plus a 4-line constructor kwarg expansion. The helper is the defensive variant (try/except on non-numeric env value), the default is 90s, and there is no change to any vendor code or other production file.

---

_Verified: 2026-05-17T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
